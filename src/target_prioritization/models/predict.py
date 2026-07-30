"""Scoring and ranking (Context.md §9.1, §19.2).

Ranking is per disease. Context.md §19.3 requires metrics to be computed within
each disease and then aggregated; a single global ranking across all
disease-target pairs is dominated by whichever diseases have the most evidence.
"""

from __future__ import annotations

import polars as pl

from target_prioritization.models.evaluate import rank_within_disease
from target_prioritization.models.train import TrainedModel

__all__ = ["rank_targets", "score_targets"]


def score_targets(model: TrainedModel, features: pl.DataFrame) -> pl.DataFrame:
    """Attach a prioritization score to each disease-target pair.

    The output is a *prioritization score*, not a probability of therapeutic
    success (Context.md §15, §31.1). Anything user-facing must say so — even
    for logistic regression and XGBoost, whose ``score`` is a fitted
    probability, it is a probability of *matching the imperfect label*
    (Context.md §15's "approved or clinically-advanced drug" proxy), not of
    real-world therapeutic success.

    Args:
        model: Anything satisfying :class:`~target_prioritization.models.train.TrainedModel`.
        features: Must have ``disease_id``, ``target_id`` plus whatever
            columns *model* expects.

    Returns:
        ``disease_id``, ``target_id``, ``score``.
    """
    scores = model.predict_proba(features)
    return features.select(["disease_id", "target_id"]).with_columns(
        pl.Series("score", scores, dtype=pl.Float64)
    )


def rank_targets(scored: pl.DataFrame, top_n: int | None = None) -> pl.DataFrame:
    """Rank targets within each disease, 1 = highest score.

    Args:
        scored: ``disease_id``, ``target_id``, ``score`` — the output of
            :func:`score_targets`.
        top_n: Keep only the top *n* per disease. None keeps every row.

    Returns:
        *scored* plus ``rank``, ties broken on ``target_id`` (see
        :func:`~target_prioritization.models.evaluate.rank_within_disease` —
        the same tie-break Milestone 1's ``WeightedBaseline.rank`` uses, for
        the same reproducibility reason: milestone1.md §5a).
    """
    ranked = rank_within_disease(scored)
    if top_n is None:
        return ranked
    return ranked.filter(pl.col("rank") <= top_n)
