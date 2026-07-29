"""Genetics features (Context.md §14.1, Project_info.md §17.2).

Human genetic evidence is the strongest single predictor of clinical success in
the published literature, which makes this the most important feature group —
and the one where Context.md §31.4 applies most sharply: association is not
causation, and genetic evidence rarely reveals *which direction* a target should
be modulated in.

Datasources contributing here in release 26.06: gwas_credible_sets, gene_burden,
eva, genomics_england, gene2phenotype, clingen, orphanet, uniprot_variants.
"""

from __future__ import annotations

import polars as pl

__all__ = ["build_genetics_features"]


def build_genetics_features(associations: pl.DataFrame) -> pl.DataFrame:
    """Derive genetics features from the per-datasource association table.

    Args:
        associations: Long-format rows for one or more diseases with columns
            ``disease_id``, ``target_id``, ``datasource``, ``score``,
            ``evidence_count``.

    Returns:
        One row per ``(disease_id, target_id)`` with the genetics columns
        declared under ``groups.genetics`` in ``configs/features.yaml``, plus
        ``genetics__n_datasources`` and ``genetics__max_score``.

    Note:
        Absence of genetic evidence must become an explicit
        ``missing__genetics`` indicator rather than a zero — Context.md §32.3.
        A zero says "studied and found unrelated"; missing says "not studied".
        Collapsing the two is how understudied genes get ranked as bad targets.
    """
    raise NotImplementedError("Milestone 1 — see configs/features.yaml groups.genetics")
