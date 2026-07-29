"""Transparent weighted baseline (Context.md §17.1, §36).

This is the first thing that should work, and Context.md §36 is explicit that no
ML model should be added before it does. Its value is diagnostic: the weights
are hand-set and the arithmetic is inspectable, so if known Parkinson's targets
do not surface near the top, the problem is in the data pipeline rather than in
the model. A gradient-boosted model that fails the same way gives no such signal.

The weights in ``configs/model.yaml`` are illustrative and must not be presented
as scientifically validated (Context.md §17.1).
"""

from __future__ import annotations

import polars as pl

__all__ = ["WeightedBaseline"]


class WeightedBaseline:
    """Weighted sum of normalized per-group evidence scores.

    Args:
        weights: Group name → weight. Validated to sum to 1.0 by ModelConfig.
    """

    def __init__(self, weights: dict[str, float]) -> None:
        self.weights = weights

    def score(self, features: pl.DataFrame) -> pl.DataFrame:
        """Score each disease-target pair.

        Scores are computed **within each disease** so that diseases with more
        evidence overall do not dominate a shared ranking (Context.md §32.4).

        Returns:
            ``disease_id``, ``target_id``, ``score``, plus the per-group
            contributions — the contributions are what make the score
            explainable without SHAP.
        """
        raise NotImplementedError("Milestone 1 — Context.md §36 step 6")

    def explain(self, features: pl.DataFrame, target_id: str) -> dict[str, float]:
        """Per-group contribution breakdown for one target."""
        raise NotImplementedError("Milestone 1")
