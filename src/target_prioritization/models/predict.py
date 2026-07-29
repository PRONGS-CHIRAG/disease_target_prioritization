"""Scoring and ranking (Context.md §9.1, §19.2).

Ranking is per disease. Context.md §19.3 requires metrics to be computed within
each disease and then aggregated; a single global ranking across all
disease-target pairs is dominated by whichever diseases have the most evidence.
"""

from __future__ import annotations

import polars as pl

__all__ = ["rank_targets", "score_targets"]


def score_targets(model: object, features: pl.DataFrame) -> pl.DataFrame:
    """Attach a prioritization score to each disease-target pair.

    The output is a *prioritization score*, not a probability of therapeutic
    success (Context.md §15, §31.1). Anything user-facing must say so.
    """
    raise NotImplementedError("Milestone 2")


def rank_targets(scored: pl.DataFrame, top_n: int | None = None) -> pl.DataFrame:
    """Rank targets within each disease, densest rank first."""
    raise NotImplementedError("Milestone 2")
