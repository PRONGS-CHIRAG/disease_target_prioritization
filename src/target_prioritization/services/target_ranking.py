"""Ranking service backing the API and the app (Context.md §21).

Sits between the trained model and the UI: takes a disease, returns ranked
targets with their evidence, and applies the filters listed in Context.md §21.
"""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl

__all__ = ["RankedTarget", "RankingFilters", "rank_for_disease"]


@dataclass(slots=True)
class RankingFilters:
    """Filters from the MVP interface spec (Context.md §21)."""

    min_genetics_evidence: float | None = None
    relevant_tissue: str | None = None
    require_druggable: bool = False
    min_evidence_completeness: float | None = None
    target_family: str | None = None


@dataclass(slots=True)
class RankedTarget:
    rank: int
    target_id: str
    gene_symbol: str
    gene_name: str
    score: float
    evidence: dict[str, float]
    # Context.md §32.3 — shown alongside the score, not buried. A high score
    # from two evidence types is a weaker claim than the same score from six.
    evidence_completeness: float
    missing_evidence: list[str]


def rank_for_disease(
    disease_id: str,
    filters: RankingFilters | None = None,
    top_n: int = 50,
) -> list[RankedTarget]:
    """Ranked targets for one disease, with evidence attached."""
    raise NotImplementedError("Milestone 3 — Context.md §21")


def load_precomputed_scores(disease_id: str) -> pl.DataFrame:
    """Load precomputed scores. The MVP scores offline, not per request."""
    raise NotImplementedError("Milestone 3")
