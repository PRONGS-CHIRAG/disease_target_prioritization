"""Open Targets Platform readers.

Bulk parquet is read with DuckDB rather than loaded into memory: the
association tables are ~7.8M rows, and the pipeline only ever needs the
slices belonging to the ten MVP diseases.

Nothing here queries the GraphQL API. The API is for interactive disease
search in the app (``services/disease_search.py``); the pinned FTP release is
what the pipeline reads, so results stay reproducible (Context.md §32.7).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import duckdb
import polars as pl

from target_prioritization.config import DiseaseSpec, load_data_sources
from target_prioritization.utils.logging import get_logger
from target_prioritization.utils.paths import DATA_RAW

__all__ = [
    "DiseaseMatch",
    "connect",
    "dataset_glob",
    "load_target_metadata",
    "load_target_prioritisation",
    "load_targets_for_disease",
    "pivot_evidence",
    "release_tag",
    "resolve_disease",
    "resolve_diseases",
]

log = get_logger(__name__)

OPEN_TARGETS_RAW = DATA_RAW / "open_targets"


def dataset_glob(dataset: str) -> str:
    """Parquet glob for an Open Targets dataset.

    Covers both naming conventions in the release: Spark-partitioned
    ``part-00000-*.snappy.parquet`` and single-file ``<dataset>.parquet``.
    """
    path = OPEN_TARGETS_RAW / dataset
    if not path.exists():
        raise FileNotFoundError(
            f"Open Targets dataset {dataset!r} not found at {path}. "
            "Run: python scripts/download_data.py --profile core"
        )
    return str(path / "*.parquet")


def connect() -> duckdb.DuckDBPyConnection:
    """An in-memory DuckDB connection for querying the parquet files."""
    return duckdb.connect()


def release_tag() -> str:
    """The pinned Open Targets release, for stamping derived tables (§33)."""
    return load_data_sources().sources["open_targets"].release or "unknown"


# ---------------------------------------------------------------------------
# Disease resolution
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class DiseaseMatch:
    """A resolved disease.

    *match_kind* records how the name was matched, so a reviewer can see
    whether an ID came from an exact name match or a looser synonym hit
    before trusting it.
    """

    key: str
    query: str
    disease_id: str
    resolved_name: str
    match_kind: str
    n_candidates: int
    alternatives: list[tuple[str, str]]


def _normalize(text: str) -> str:
    """Lowercase, strip punctuation and collapse whitespace for matching.

    Handles the apostrophe and hyphen variants that differ between our config
    and the ontology: "Parkinson's disease" vs "parkinson disease",
    "non-small cell lung carcinoma" vs "non small cell lung carcinoma".
    """
    text = text.lower().replace("'", "").replace("’", "")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def load_disease_index(
    con: duckdb.DuckDBPyConnection | None = None,
) -> list[tuple[str, str, object]]:
    """Load ``(id, name, synonyms)`` for every disease in the release.

    Read once and reused across all lookups: the table is ~47k rows, and
    rescanning it per disease turns a one-second job into a ten-second one for
    no benefit.
    """
    owns = con is None
    con = con or connect()
    try:
        glob = dataset_glob("disease")
        # No COALESCE on `synonyms`: it is a struct of string lists, and
        # coalescing it against an empty list is a type error in DuckDB.
        # _flatten_synonyms handles None.
        return con.execute(f"SELECT id, name, synonyms FROM read_parquet('{glob}')").fetchall()
    finally:
        if owns:
            con.close()


def match_disease(
    spec: DiseaseSpec,
    index: list[tuple[str, str, object]],
) -> DiseaseMatch | None:
    """Match one disease spec against a preloaded disease index.

    Matching is attempted in decreasing order of confidence:

    1. exact normalized name
    2. exact normalized synonym
    3. substring match on name

    Ambiguity is reported rather than hidden — Context.md §32.6 warns that a
    wrong disease mapping invents associations no database asserts, so the
    match kind is recorded and a warning logged whenever the choice was not
    forced.

    Returns:
        The match, or None if nothing matched at all.
    """
    target = _normalize(spec.name)

    exact: list[tuple[str, str]] = []
    synonym: list[tuple[str, str]] = []
    partial: list[tuple[str, str]] = []

    for disease_id, name, synonyms in index:
        normalized_name = _normalize(name or "")
        if normalized_name == target:
            exact.append((disease_id, name))
            continue

        if any(_normalize(s) == target for s in _flatten_synonyms(synonyms)):
            synonym.append((disease_id, name))
            continue

        if target and target in normalized_name:
            partial.append((disease_id, name))

    for kind, candidates in (
        ("exact_name", exact),
        ("exact_synonym", synonym),
        ("substring", partial),
    ):
        if not candidates:
            continue

        if len(candidates) == 1:
            disease_id, name = candidates[0]
            return DiseaseMatch(
                key=spec.key,
                query=spec.name,
                disease_id=disease_id,
                resolved_name=name,
                match_kind=kind,
                n_candidates=1,
                alternatives=[],
            )

        # Prefer EFO: Open Targets uses it as the canonical namespace for the
        # diseases in scope here. The alternatives are kept so the choice is
        # reviewable rather than buried.
        ranked = sorted(candidates, key=lambda c: (not c[0].startswith("EFO_"), c[0]))
        disease_id, name = ranked[0]
        log.warning(
            "ambiguous_disease_match",
            key=spec.key,
            query=spec.name,
            match_kind=kind,
            n_candidates=len(candidates),
            chosen=disease_id,
            alternatives=[c[0] for c in ranked[1:6]],
        )
        return DiseaseMatch(
            key=spec.key,
            query=spec.name,
            disease_id=disease_id,
            resolved_name=name,
            match_kind=f"{kind}_ambiguous",
            n_candidates=len(candidates),
            alternatives=ranked[1:6],
        )

    log.error("unresolved_disease", key=spec.key, query=spec.name)
    return None


def resolve_disease(
    spec: DiseaseSpec,
    con: duckdb.DuckDBPyConnection | None = None,
) -> DiseaseMatch | None:
    """Resolve one disease name to an Open Targets disease ID."""
    return match_disease(spec, load_disease_index(con))


def _flatten_synonyms(synonyms: object) -> list[str]:
    """Flatten the nested synonym structure into a list of strings.

    The ``synonyms`` column is a struct of lists (exact, related, narrow,
    broad), and its exact shape has changed between releases, so this walks
    whatever it is given rather than assuming a schema.
    """
    out: list[str] = []
    stack = [synonyms]
    while stack:
        item = stack.pop()
        if item is None:
            continue
        if isinstance(item, str):
            out.append(item)
        elif isinstance(item, dict):
            stack.extend(item.values())
        elif isinstance(item, (list, tuple)):
            stack.extend(item)
    return out


def resolve_diseases(
    specs: list[DiseaseSpec],
    con: duckdb.DuckDBPyConnection | None = None,
) -> tuple[list[DiseaseMatch], list[DiseaseSpec]]:
    """Resolve many diseases.

    Returns:
        ``(matches, unresolved)``. Unresolved specs are returned rather than
        dropped so the caller must decide what to do about them.
    """
    owns = con is None
    con = con or connect()
    try:
        index = load_disease_index(con)
        log.info("disease_index_loaded", diseases=len(index))

        matches: list[DiseaseMatch] = []
        unresolved: list[DiseaseSpec] = []
        for spec in specs:
            match = match_disease(spec, index)
            if match:
                matches.append(match)
            else:
                unresolved.append(spec)
        return matches, unresolved
    finally:
        if owns:
            con.close()


def load_targets_for_disease(
    disease_id: str,
    con: duckdb.DuckDBPyConnection | None = None,
) -> pl.DataFrame:
    """Candidate targets associated with *disease_id* (Context.md §13).

    The MVP candidate set is "all disease-associated targets returned by Open
    Targets", which keeps the focus on feature engineering and ranking rather
    than on candidate generation.
    """
    owns = con is None
    con = con or connect()
    try:
        glob = dataset_glob("association_by_datasource_direct")
        table = con.execute(
            f"""
            SELECT targetId AS target_id,
                   aggregationValue AS datasource,
                   associationScore AS score,
                   evidenceCount AS evidence_count
            FROM read_parquet('{glob}')
            WHERE diseaseId = ?
            """,
            [disease_id],
        ).arrow()
        # from_arrow returns DataFrame | Series; an Arrow Table is always the
        # former, but the annotation is a union.
        frame = pl.from_arrow(table)
        assert isinstance(frame, pl.DataFrame)
        return frame
    finally:
        if owns:
            con.close()


def load_target_metadata(
    target_ids: list[str] | None = None,
    con: duckdb.DuckDBPyConnection | None = None,
) -> pl.DataFrame:
    """Gene symbol, name and biotype for targets.

    Args:
        target_ids: Restrict to these Ensembl gene IDs. None loads all 78,691.

    Returns:
        ``target_id``, ``gene_symbol``, ``gene_name``, ``biotype``.
    """
    owns = con is None
    con = con or connect()
    try:
        glob = dataset_glob("target")
        query = f"""
            SELECT id AS target_id,
                   approvedSymbol AS gene_symbol,
                   approvedName AS gene_name,
                   biotype
            FROM read_parquet('{glob}')
        """
        if target_ids:
            con.register("wanted_targets", pl.DataFrame({"target_id": target_ids}).to_arrow())
            query += " WHERE target_id IN (SELECT target_id FROM wanted_targets)"
        frame = pl.from_arrow(con.execute(query).arrow())
        assert isinstance(frame, pl.DataFrame)
        return frame
    finally:
        if owns:
            con.close()


def load_target_prioritisation(
    columns: list[str],
    target_ids: list[str] | None = None,
    con: duckdb.DuckDBPyConnection | None = None,
) -> pl.DataFrame:
    """Selected columns from ``target_prioritisation``.

    Note the scale: these are signed values where negative indicates a
    liability (``hasSafetyEvent`` is only ever -1 or null, never +1), and the
    binary flags are 0/1. They are NOT all probabilities.

    Args:
        columns: Column names to read, e.g. ``["hasPocket", "hasLigand"]``.
        target_ids: Restrict to these Ensembl gene IDs.
    """
    owns = con is None
    con = con or connect()
    try:
        glob = dataset_glob("target_prioritisation")
        available = {
            row[0]
            for row in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{glob}')").fetchall()
        }
        if missing := [c for c in columns if c not in available]:
            raise KeyError(
                f"target_prioritisation has no column(s) {missing}. Available: {sorted(available)}"
            )

        selected = ", ".join(f'"{c}"' for c in columns)
        query = f"SELECT targetId AS target_id, {selected} FROM read_parquet('{glob}')"
        if target_ids:
            con.register("wanted_prio", pl.DataFrame({"target_id": target_ids}).to_arrow())
            query += " WHERE targetId IN (SELECT target_id FROM wanted_prio)"
        frame = pl.from_arrow(con.execute(query).arrow())
        assert isinstance(frame, pl.DataFrame)
        return frame
    finally:
        if owns:
            con.close()


def pivot_evidence(evidence: pl.DataFrame) -> pl.DataFrame:
    """Pivot long-format evidence to one row per target.

    Args:
        evidence: Long frame from :func:`load_targets_for_disease`, with any
            denylisted datasources ALREADY removed. Filtering must happen
            before this call so leaked columns are never even constructed
            (Context.md §16).

    Returns:
        ``target_id`` plus ``assoc_ds__<datasource>_score`` and
        ``assoc_ds__<datasource>_evidence_count`` per datasource. Absent
        evidence stays null rather than becoming zero — Context.md §32.3, a
        null means "not studied" while a zero means "studied and found absent".
    """
    if evidence.is_empty():
        return pl.DataFrame({"target_id": []}, schema={"target_id": pl.String})

    scores = evidence.pivot(
        on="datasource", index="target_id", values="score", aggregate_function="max"
    ).rename(lambda c: c if c == "target_id" else f"assoc_ds__{c}_score")

    counts = evidence.pivot(
        on="datasource", index="target_id", values="evidence_count", aggregate_function="sum"
    ).rename(lambda c: c if c == "target_id" else f"assoc_ds__{c}_evidence_count")

    return scores.join(counts, on="target_id", how="left")


def read_parquet_dataset(dataset: str, columns: list[str] | None = None) -> pl.LazyFrame:
    """Lazily scan an Open Targets dataset with Polars."""
    pattern = dataset_glob(dataset)
    frame = pl.scan_parquet(pattern)
    return frame.select(columns) if columns else frame


def raw_path(dataset: str) -> Path:
    return OPEN_TARGETS_RAW / dataset
