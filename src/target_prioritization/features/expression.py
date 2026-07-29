"""Tissue-expression features (Context.md §14.4, §10.6).

Built from GTEx v10 median TPM. The disease-relevant tissues come from
``relevant_tissues`` in ``configs/diseases.yaml`` — a Parkinson's target is more
interesting if it is expressed in brain than if it is merely expressed
somewhere.

Expression also carries safety signal in the opposite direction: a gene
expressed highly across many healthy tissues is a broader intervention and a
larger risk surface (Context.md §14.7).
"""

from __future__ import annotations

import polars as pl

__all__ = ["build_expression_features", "tissue_specificity"]


def tissue_specificity(tpm_by_tissue: pl.DataFrame) -> pl.DataFrame:
    """Compute a tissue-specificity index per gene.

    Returns:
        ``ensembl_gene_id`` plus a specificity score in [0, 1], where 1 means
        expression is concentrated in a single tissue.
    """
    raise NotImplementedError("Milestone 1")


def build_expression_features(
    gene_ids: list[str],
    relevant_tissues: list[str],
) -> pl.DataFrame:
    """Derive expression features for *gene_ids*.

    Args:
        gene_ids: Unversioned Ensembl gene IDs.
        relevant_tissues: GTEx tissue names for the disease. Matching is on
            normalized names, and an unmatched tissue name is an error rather
            than a silent zero — see ``gtex.tissue_columns`` for the vocabulary.

    Returns:
        One row per gene with the columns declared under ``groups.expression``.
    """
    raise NotImplementedError("Milestone 1 — see configs/features.yaml groups.expression")
