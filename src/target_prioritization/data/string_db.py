"""STRING protein-interaction reader (Context.md §10.5, §14.5).

STRING keys everything on Ensembl **protein** IDs prefixed with the NCBI taxon
(``9606.ENSP00000493376``). Our internal key is the Ensembl **gene** ID, so the
aliases file is required to make the network joinable at all — see
:func:`target_prioritization.data.identifiers.ensp_to_ensg_from_string_aliases`.

Context.md §10.5 requires keeping the confidence score so low- and
high-confidence edges stay distinguishable. Nothing here filters by score;
callers choose a threshold explicitly and record it.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from target_prioritization.data.identifiers import (
    MappingReport,
    ensp_to_ensg_from_string_aliases,
)
from target_prioritization.utils.logging import get_logger, log_dropped
from target_prioritization.utils.paths import DATA_RAW

__all__ = [
    "HIGH_CONFIDENCE",
    "MEDIUM_CONFIDENCE",
    "STRING_RAW",
    "load_aliases",
    "load_gene_level_edges",
    "load_links",
    "load_protein_info",
]

log = get_logger(__name__)

STRING_RAW = DATA_RAW / "string"

# STRING's own published bands, on its 0-1000 combined score.
MEDIUM_CONFIDENCE = 400
HIGH_CONFIDENCE = 700


def _path(pattern: str) -> Path:
    matches = sorted(STRING_RAW.glob(pattern))
    if not matches:
        raise FileNotFoundError(
            f"No STRING file matching {pattern!r} in {STRING_RAW}. "
            "Run: python scripts/download_data.py --only string"
        )
    return matches[0]


def load_links(path: Path | None = None) -> pl.DataFrame:
    """Load the interaction edge list.

    Returns:
        Columns ``protein1``, ``protein2``, ``combined_score`` (0-1000).
    """
    # Space-separated, not tab — unlike every other STRING file.
    return pl.read_csv(
        path or _path("*protein.links.v*.txt.gz"),
        separator=" ",
        schema_overrides={"protein1": pl.String, "protein2": pl.String},
    )


def load_aliases(path: Path | None = None) -> pl.DataFrame:
    """Load the protein-alias table.

    The header line starts with ``#``, so it is read explicitly rather than
    letting the parser treat it as a comment and lose the column names.
    """
    frame = pl.read_csv(
        path or _path("*protein.aliases.v*.txt.gz"),
        separator="\t",
        has_header=True,
    )
    return frame.rename({frame.columns[0]: "string_protein_id"})


def load_protein_info(path: Path | None = None) -> pl.DataFrame:
    """Load protein names and descriptions."""
    frame = pl.read_csv(
        path or _path("*protein.info.v*.txt.gz"),
        separator="\t",
        has_header=True,
    )
    return frame.rename({frame.columns[0]: "string_protein_id"})


def load_gene_level_edges(
    *,
    min_score: int = MEDIUM_CONFIDENCE,
    links_path: Path | None = None,
    aliases_path: Path | None = None,
) -> tuple[pl.DataFrame, MappingReport]:
    """Load the interaction network collapsed to Ensembl gene IDs.

    Both endpoints are translated ENSP → ENSG, self-loops created by that
    collapse are removed, and parallel edges between the same gene pair are
    reduced to their maximum score.

    Edges are deduplicated by sorting each pair, so ``(A, B)`` and ``(B, A)``
    become one undirected edge. STRING lists both directions; without this,
    every degree would be counted twice.

    Args:
        min_score: Minimum combined score to keep. Defaults to STRING's
            "medium confidence" band. Recorded by the caller as a feature
            parameter — the threshold changes the network, so it is a modelling
            decision, not an implementation detail.

    Returns:
        ``(edges, report)`` with columns ``gene1``, ``gene2``, ``score``.
    """
    links = load_links(links_path)
    aliases = load_aliases(aliases_path)
    lookup, report = ensp_to_ensg_from_string_aliases(aliases)

    before = links.height
    filtered = links.filter(pl.col("combined_score") >= min_score)
    log_dropped(
        log,
        stage="string_score_filter",
        reason=f"combined_score < {min_score}",
        count=before - filtered.height,
        total=before,
    )

    edges = (
        filtered.join(
            lookup.rename({"string_protein_id": "protein1", "ensembl_gene_id": "gene1"}),
            on="protein1",
            how="inner",
        )
        .join(
            lookup.rename({"string_protein_id": "protein2", "ensembl_gene_id": "gene2"}),
            on="protein2",
            how="inner",
        )
        # Different isoforms of the same gene interacting becomes a self-loop
        # once collapsed to gene level. Not a real interaction between genes.
        .filter(pl.col("gene1") != pl.col("gene2"))
        .with_columns(
            pl.min_horizontal("gene1", "gene2").alias("_a"),
            pl.max_horizontal("gene1", "gene2").alias("_b"),
        )
        .group_by("_a", "_b")
        .agg(pl.col("combined_score").max().alias("score"))
        .rename({"_a": "gene1", "_b": "gene2"})
    )

    # Roughly half of the reduction here is STRING listing every interaction in
    # both directions, which the sort-and-group collapses into one undirected
    # edge. The rest is unmapped endpoints and gene-level self-loops. Reported
    # as one number because the three causes are not separable after the fact —
    # the per-cause counts above are the diagnostic ones.
    log_dropped(
        log,
        stage="string_edge_collapse",
        reason="undirected deduplication, unmapped endpoints and gene-level self-loops",
        count=filtered.height - edges.height,
        total=filtered.height,
    )

    return edges, report
