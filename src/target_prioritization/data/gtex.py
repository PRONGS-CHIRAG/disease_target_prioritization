"""GTEx tissue expression reader (Context.md §10.6, §14.4).

The file is GCT format, which is TSV with two preamble lines::

    #1.2
    59033	68                       <- n_genes, n_tissues
    Name	Description	Adipose_Subcutaneous	...

``Name`` holds a **versioned** Ensembl gene ID (``ENSG00000186092.7``). Open
Targets and Reactome use unversioned IDs, so the version is stripped on load —
see :mod:`target_prioritization.data.identifiers` for why that matters.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from target_prioritization.data.identifiers import strip_ensembl_version_expr
from target_prioritization.utils.logging import get_logger
from target_prioritization.utils.paths import DATA_RAW

__all__ = ["GTEX_RAW", "load_median_tpm", "load_median_tpm_long", "tissue_columns"]

log = get_logger(__name__)

GTEX_RAW = DATA_RAW / "gtex"
_GCT_PREAMBLE_LINES = 2


def _default_path() -> Path:
    matches = sorted(GTEX_RAW.glob("*gene_median_tpm.gct.gz"))
    if not matches:
        raise FileNotFoundError(
            f"No GTEx median-TPM file in {GTEX_RAW}. "
            "Run: python scripts/download_data.py --only gtex"
        )
    return matches[0]


def load_median_tpm(path: Path | None = None) -> pl.DataFrame:
    """Load median TPM per gene per tissue in wide form.

    Returns:
        Columns ``ensembl_gene_id``, ``gene_symbol``, then one float column per
        tissue. Gene IDs are unversioned and uppercased.
    """
    path = path or _default_path()

    frame = pl.read_csv(
        path,
        separator="\t",
        skip_rows=_GCT_PREAMBLE_LINES,
        infer_schema_length=10_000,
    )

    frame = frame.rename({"Name": "ensembl_gene_id", "Description": "gene_symbol"})
    frame = frame.with_columns(strip_ensembl_version_expr("ensembl_gene_id"))

    # A handful of GTEx rows are PAR_Y duplicates of an X-chromosome gene and
    # keep a non-numeric suffix, so they survive version stripping and would
    # otherwise collide on join. Drop them rather than pick one arbitrarily.
    par_y = frame.filter(pl.col("ensembl_gene_id").str.contains("_PAR_Y"))
    if par_y.height:
        log.info(
            "dropping_par_y_genes",
            count=par_y.height,
            note="pseudoautosomal Y duplicates of X-chromosome genes",
        )
        frame = frame.filter(~pl.col("ensembl_gene_id").str.contains("_PAR_Y"))

    return frame


def tissue_columns(frame: pl.DataFrame) -> list[str]:
    """Tissue column names (everything that is not an identifier)."""
    return [c for c in frame.columns if c not in {"ensembl_gene_id", "gene_symbol"}]


def load_median_tpm_long(path: Path | None = None) -> pl.DataFrame:
    """Median TPM in long form: ``ensembl_gene_id``, ``tissue``, ``median_tpm``."""
    wide = load_median_tpm(path)
    return wide.unpivot(
        index=["ensembl_gene_id", "gene_symbol"],
        on=tissue_columns(wide),
        variable_name="tissue",
        value_name="median_tpm",
    )
