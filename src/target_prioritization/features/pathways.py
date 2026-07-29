"""Pathway features (Context.md §14.3, §10.4).

Built from Reactome, filtered to human (that filter drops ~95% of the source
file — see data/reactome.py).

Caution: Reactome is a hierarchy, so a naive "number of pathways this gene
belongs to" counts the same biology repeatedly at several levels of
granularity, and rewards well-annotated genes rather than biologically central
ones. ``ReactomePathwaysRelation.txt`` is downloaded so features can be
computed at a chosen depth instead.
"""

from __future__ import annotations

import polars as pl

__all__ = ["build_pathway_features", "pathway_overlap_with_known_genes"]


def pathway_overlap_with_known_genes(
    gene_ids: list[str],
    known_disease_genes: list[str],
) -> pl.DataFrame:
    """Share of a gene's pathways that contain a known disease gene.

    A candidate sitting in the same pathways as established disease genes is a
    more plausible target than one that shares none — the mechanism-level
    version of guilt by association.
    """
    raise NotImplementedError("Milestone 1")


def build_pathway_features(
    gene_ids: list[str],
    known_disease_genes: list[str] | None = None,
) -> pl.DataFrame:
    """Derive pathway features. See ``groups.pathways`` in features.yaml."""
    raise NotImplementedError("Milestone 1 — see configs/features.yaml groups.pathways")
