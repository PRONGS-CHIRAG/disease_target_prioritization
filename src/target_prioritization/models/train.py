"""Model training (Context.md §17, §33).

Order matters: logistic regression, then random forest, then XGBoost, each
compared against the weighted baseline. A boosted model that cannot beat the
transparent baseline usually indicates a data problem rather than a modelling
one, and skipping ahead hides that.

Every run must record what Context.md §33 requires — dataset version, extraction
date, disease list, feature and label definitions, split, parameters, seed,
metrics, code commit and known limitations — into ``models/metadata/``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

import polars as pl

__all__ = ["TrainedModel", "train_model", "write_run_metadata"]


class TrainedModel(Protocol):
    """Minimal interface the rest of the pipeline depends on."""

    def predict_proba(self, features: pl.DataFrame) -> list[float]: ...


def train_model(
    features: pl.DataFrame,
    labels: pl.DataFrame,
    model_name: str,
    params: dict[str, Any] | None = None,
    *,
    seed: int = 42,
) -> TrainedModel:
    """Train one model on a disease-grouped split.

    Args:
        features: Feature matrix. Passed through ``assert_no_leakage`` again
            here — checking at both boundaries is cheap, a leaked label is not.
        labels: ``disease_id``, ``target_id``, ``label``.
        model_name: Key from ``configs/model.yaml`` ``models``.

    Raises:
        LeakageError: If a denylisted column reaches the matrix.
    """
    raise NotImplementedError("Milestone 2 — Context.md §37")


def write_run_metadata(path: Path, metadata: dict[str, Any]) -> None:
    """Persist the reproducibility record for a training run (§33)."""
    raise NotImplementedError("Milestone 2")
