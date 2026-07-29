"""HGNC gene-symbol reader (Context.md §10.8, §12).

HGNC is the authority for human gene symbols and, more usefully here, for the
symbols a gene *used* to have. ``PARK2`` became ``PRKN`` and ``PARK7`` became
``DJ1``; Parkinson's literature and older datasets are full of the retired
names. Matching on current symbols alone loses those records silently.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from target_prioritization.data.identifiers import MappingReport, build_symbol_lookup
from target_prioritization.utils.logging import get_logger
from target_prioritization.utils.paths import DATA_RAW

__all__ = ["HGNC_RAW", "load_hgnc", "load_symbol_lookup"]

log = get_logger(__name__)

HGNC_RAW = DATA_RAW / "hgnc"

USEFUL_COLUMNS = [
    "hgnc_id",
    "symbol",
    "name",
    "locus_group",
    "status",
    "alias_symbol",
    "prev_symbol",
    "ensembl_gene_id",
    "entrez_id",
    "uniprot_ids",
]


def _default_path() -> Path:
    path = HGNC_RAW / "hgnc_complete_set.txt"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run: python scripts/download_data.py --only hgnc"
        )
    return path


def load_hgnc(path: Path | None = None, columns: list[str] | None = None) -> pl.DataFrame:
    """Load the HGNC complete set.

    Read entirely as text (``infer_schema_length=0``): several ID columns look
    numeric but are not — ``entrez_id`` would be inferred as an integer and
    then fail to join against string IDs elsewhere.
    """
    frame = pl.read_csv(
        path or _default_path(),
        separator="\t",
        infer_schema_length=0,
        quote_char=None,  # gene names contain apostrophes and quotes
        null_values=[""],
    )

    wanted = columns or USEFUL_COLUMNS
    available = [c for c in wanted if c in frame.columns]
    if missing := set(wanted) - set(available):
        log.warning("hgnc_columns_missing", missing=sorted(missing))
    return frame.select(available)


def load_symbol_lookup(path: Path | None = None) -> tuple[pl.DataFrame, MappingReport]:
    """Build the symbol → Ensembl gene ID lookup, including retired symbols.

    Returns:
        ``(lookup, report)`` with columns ``symbol``, ``ensembl_gene_id``,
        ``symbol_kind`` (approved/previous/alias) and ``priority``.
    """
    return build_symbol_lookup(load_hgnc(path))
