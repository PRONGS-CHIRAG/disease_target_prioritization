"""Model explanations (Context.md §20).

Scientific users need to see the evidence, not a number. Context.md §20.2
requires per-target SHAP values, the strongest positive and negative factors,
which evidence types are present, which are *missing*, and source references.

The missing-evidence part is not decoration: Context.md §32.3 warns that a
target can look weak simply because nobody has studied it, and a UI that shows
only positive contributions actively misleads.
"""

from __future__ import annotations

from typing import Any

import polars as pl

__all__ = ["explain_target", "global_feature_importance", "shap_values"]


def shap_values(model: object, features: pl.DataFrame) -> pl.DataFrame:
    """SHAP values per feature per row."""
    raise NotImplementedError("Milestone 2 — Context.md §20.2")


def global_feature_importance(model: object, features: pl.DataFrame) -> pl.DataFrame:
    """Global feature importance across all predictions (§20.1)."""
    raise NotImplementedError("Milestone 2")


def explain_target(
    model: object,
    features: pl.DataFrame,
    disease_id: str,
    target_id: str,
) -> dict[str, Any]:
    """Structured explanation for one disease-target pair.

    Returns a dict carrying the score, the strongest positive and negative
    contributions, evidence present, **evidence missing**, source links and the
    standing limitations. The shape mirrors the example in Context.md §20.3.
    """
    raise NotImplementedError("Milestone 2 — Context.md §20.3")
