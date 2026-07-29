"""Reactome pathway reader (Context.md §10.4, §14.3).

``Ensembl2Reactome_All_Levels.txt`` has **no header row** and covers **every
species Reactome has inferred pathways for** — the first data row in the
current file is a *C. elegans* gene. Both facts are load-bearing: reading it
with an assumed header silently discards a row, and skipping the species filter
lets a mouse ortholog inflate a human target's pathway count.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from target_prioritization.data.identifiers import MappingReport, filter_reactome_to_human
from target_prioritization.utils.logging import get_logger
from target_prioritization.utils.paths import DATA_RAW

__all__ = [
    "ENSEMBL2REACTOME_COLUMNS",
    "REACTOME_RAW",
    "load_ensembl_to_pathway",
    "load_pathway_names",
    "load_pathway_relations",
]

log = get_logger(__name__)

REACTOME_RAW = DATA_RAW / "reactome"

# The file ships headerless; these are the documented column positions.
ENSEMBL2REACTOME_COLUMNS = [
    "ensembl_gene_id",
    "pathway_id",
    "pathway_url",
    "pathway_name",
    "evidence_code",
    "species",
]

# "Inferred from Electronic Annotation" — computationally propagated rather
# than curated from an experiment. Kept, but flagged so callers can weight or
# exclude it (Project_info.md §45 ranks curated evidence above inferred).
INFERRED_EVIDENCE_CODE = "IEA"


def _path(name: str) -> Path:
    path = REACTOME_RAW / name
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run: python scripts/download_data.py --only reactome"
        )
    return path


def load_ensembl_to_pathway(
    path: Path | None = None,
    *,
    human_only: bool = True,
) -> tuple[pl.DataFrame, MappingReport | None]:
    """Load the Ensembl gene → Reactome pathway mapping.

    Args:
        path: Override the default file location.
        human_only: Restrict to *Homo sapiens*. Leave this on unless you are
            deliberately doing cross-species analysis.

    Returns:
        ``(frame, report)``; *report* is None when *human_only* is False.
    """
    frame = pl.read_csv(
        path or _path("Ensembl2Reactome_All_Levels.txt"),
        separator="\t",
        has_header=False,
        new_columns=ENSEMBL2REACTOME_COLUMNS,
        infer_schema_length=0,  # everything is text; avoid guessing on IDs
        quote_char=None,  # pathway names contain unbalanced quotes
    )

    if not human_only:
        return frame, None

    return filter_reactome_to_human(frame)


def load_pathway_names(path: Path | None = None) -> pl.DataFrame:
    """Load ``ReactomePathways.txt``: pathway id, name, species."""
    return pl.read_csv(
        path or _path("ReactomePathways.txt"),
        separator="\t",
        has_header=False,
        new_columns=["pathway_id", "pathway_name", "species"],
        infer_schema_length=0,
        quote_char=None,
    )


def load_pathway_relations(path: Path | None = None) -> pl.DataFrame:
    """Load ``ReactomePathwaysRelation.txt``: parent → child pathway edges.

    Reactome is a hierarchy, so "number of pathways a gene belongs to" counts
    the same biology repeatedly at several levels of granularity. This table
    lets pathway features be computed at a chosen depth instead.
    """
    return pl.read_csv(
        path or _path("ReactomePathwaysRelation.txt"),
        separator="\t",
        has_header=False,
        new_columns=["parent_pathway_id", "child_pathway_id"],
        infer_schema_length=0,
    )
