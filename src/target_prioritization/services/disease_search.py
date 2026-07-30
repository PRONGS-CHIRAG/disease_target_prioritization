"""Disease search for the UI (Context.md §21 MVP interface).

**The search space is the ten diseases in ``configs/diseases.yaml``, and only
those ten** (milestone3_plan.md §1, §2). Release 26.06 has 47,080 diseases;
features exist for ten of them. A live Open Targets GraphQL lookup — which
the original stub anticipated as a fallback — would resolve any of the
47,080 and then render an empty ranking for the 47,070 this pipeline never
built, which reads as a bug rather than as the out-of-scope result it is, and
it reintroduces the version-drift risk Context.md §32.7 warns about (a live
API result can point at a disease ID this release's local data does not
contain). So nothing here reads the raw ``disease`` table or calls the API:
matching is against ``DiseaseSpec.name`` / ``resolved_name`` / ``key`` only.

One consequence worth being explicit about: because nothing outside the ten
is ever consulted, there is no second case of "a real disease that just
isn't precomputed" to represent with a special result type. An unmatched
query is a plain empty list — the honest encoding, not an omission — and it
is the caller's job (the Streamlit page, not this module) to say "no disease
found in the precomputed set of ten" when it renders one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import polars as pl

from target_prioritization.app_data import APP_DATA_NAME
from target_prioritization.config import DiseaseSpec, load_diseases
from target_prioritization.utils.logging import get_logger
from target_prioritization.utils.paths import DATA_PROCESSED

__all__ = ["DiseaseSearchResult", "search_diseases", "suggest"]

log = get_logger(__name__)

FEATURES_PATH = DATA_PROCESSED / "disease_target_features.parquet"
APP_DATA_PATH = DATA_PROCESSED / APP_DATA_NAME


@dataclass(slots=True)
class DiseaseSearchResult:
    disease_id: str
    name: str
    description: str | None
    therapeutic_areas: list[str]
    n_associated_targets: int | None = None


def _normalize(text: str) -> str:
    """Lowercase, strip apostrophes/punctuation, collapse whitespace.

    Mirrors ``data.open_targets._normalize`` — the same apostrophe/hyphen
    variants that needed handling when resolving disease names against the
    Open Targets ontology (Context.md §32.6) show up again here when a user
    types "parkinsons" without the apostrophe.
    """
    text = text.lower().replace("'", "").replace("’", "")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def _target_counts_from_features(features: pl.DataFrame) -> dict[str, int]:
    if features.is_empty():
        return {}
    counts = features.group_by("disease_id").agg(pl.col("target_id").n_unique().alias("n"))
    return dict(zip(counts.get_column("disease_id").to_list(), counts.get_column("n").to_list(), strict=True))


def _descriptions_from_app_data(app_data: pl.DataFrame) -> dict[str, str]:
    if app_data.is_empty() or "disease_description" not in app_data.columns:
        return {}
    per_disease = (
        app_data.select(["disease_id", "disease_description"])
        .unique(subset=["disease_id"])
        .drop_nulls("disease_description")
    )
    return dict(
        zip(
            per_disease.get_column("disease_id").to_list(),
            per_disease.get_column("disease_description").to_list(),
            strict=True,
        )
    )


def _load_target_counts() -> dict[str, int]:
    """Best-effort target counts from the processed feature table.

    Returns an empty mapping rather than raising when the parquet has not
    been built yet — search must still work (with ``n_associated_targets``
    unset) before ``scripts/train_model.py`` has ever run, e.g. in tests.
    """
    if not FEATURES_PATH.exists():
        return {}
    try:
        return _target_counts_from_features(pl.read_parquet(FEATURES_PATH, columns=["disease_id", "target_id"]))
    except Exception:
        log.warning("disease_search_target_counts_unavailable", path=str(FEATURES_PATH))
        return {}


def _load_descriptions() -> dict[str, str]:
    """Best-effort disease descriptions from the Milestone 3 app-data artifact
    (``scripts/build_app_data.py``). Empty mapping if it has not been built."""
    if not APP_DATA_PATH.exists():
        return {}
    try:
        return _descriptions_from_app_data(
            pl.read_parquet(APP_DATA_PATH, columns=["disease_id", "disease_description"])
        )
    except Exception:
        log.warning("disease_search_descriptions_unavailable", path=str(APP_DATA_PATH))
        return {}


def _matches(disease: DiseaseSpec, normalized_query: str) -> bool:
    if not normalized_query:
        return True
    candidates = [disease.name, disease.resolved_name or "", disease.key.replace("_", " ")]
    return any(normalized_query in _normalize(c) for c in candidates if c)


def _sort_key(disease: DiseaseSpec, normalized_query: str) -> tuple[bool, str]:
    """Exact name matches first, then alphabetical — deterministic (Context.md §33)."""
    return (_normalize(disease.name) != normalized_query, disease.name)


def search_diseases(
    query: str,
    limit: int = 10,
    *,
    diseases: list[DiseaseSpec] | None = None,
    target_counts: dict[str, int] | None = None,
    descriptions: dict[str, str] | None = None,
) -> list[DiseaseSearchResult]:
    """Search the ten configured diseases by name, resolved name or key.

    Pure with respect to its keyword arguments — pass *diseases*,
    *target_counts* and *descriptions* explicitly to test matching logic
    against synthetic data with no I/O, the same pattern
    ``data.labels.build_labels_for_disease`` uses for the same reason. The
    no-argument defaults read the real config and the real processed
    artifacts (best-effort — see :func:`_load_target_counts` /
    :func:`_load_descriptions`).

    Args:
        query: Free-text name, partial name, or the config ``key``
            (e.g. ``"parkinsons_disease"``). Empty string matches all ten.
        limit: Maximum results.

    Returns:
        Matches ordered exact-name-first, then alphabetically. Empty list
        means no configured disease matched — see the module docstring for
        why that is the correct and complete signal, not a partial one.
    """
    diseases = diseases if diseases is not None else load_diseases().resolved
    target_counts = target_counts if target_counts is not None else _load_target_counts()
    descriptions = descriptions if descriptions is not None else _load_descriptions()

    normalized_query = _normalize(query)
    matched = [d for d in diseases if _matches(d, normalized_query)]
    matched.sort(key=lambda d: _sort_key(d, normalized_query))

    return [
        DiseaseSearchResult(
            disease_id=d.efo_id,  # type: ignore[arg-type]  # .resolved guarantees non-null
            name=d.name,
            description=descriptions.get(d.efo_id or ""),
            therapeutic_areas=[d.category],
            n_associated_targets=target_counts.get(d.efo_id or ""),
        )
        for d in matched[:limit]
    ]


def suggest(prefix: str, limit: int = 10, *, diseases: list[DiseaseSpec] | None = None) -> list[str]:
    """Autocomplete suggestions for a partial disease name.

    Prefix match only (not substring) — the standard autocomplete contract,
    and distinct from :func:`search_diseases`'s substring matching, which
    suits a submitted query better than a still-being-typed one.
    """
    diseases = diseases if diseases is not None else load_diseases().resolved
    normalized_prefix = _normalize(prefix)
    matches = [d.name for d in diseases if _normalize(d.name).startswith(normalized_prefix)]
    return sorted(matches)[:limit]
