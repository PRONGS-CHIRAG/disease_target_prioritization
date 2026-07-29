"""Evaluation (Context.md §19).

Two rules that are easy to get wrong and expensive to discover late:

* **Compute per disease, then aggregate** (§19.3). A single pooled metric lets a
  few data-rich diseases carry the average and hides total failure on the rest.
* **Never split rows randomly** (§19.4). The same disease in train and test lets
  the model memorise that disease's targets instead of learning what makes a
  target promising. Use leave-one-disease-out.

PR-AUC is the headline classification metric, not ROC-AUC: positives are rare
here and ROC-AUC flatters under imbalance (§19.1).
"""

from __future__ import annotations

import polars as pl

__all__ = ["evaluate_ranking", "leave_one_disease_out_splits", "ndcg_at_k", "precision_at_k"]


def precision_at_k(ranked: pl.DataFrame, k: int) -> float:
    """Precision@k for a single disease's ranking."""
    raise NotImplementedError("Milestone 2")


def ndcg_at_k(ranked: pl.DataFrame, k: int) -> float:
    """NDCG@k for a single disease's ranking. Primary metric per model.yaml."""
    raise NotImplementedError("Milestone 2")


def leave_one_disease_out_splits(features: pl.DataFrame) -> list[tuple[list[int], list[int]]]:
    """Yield (train_idx, test_idx) with one disease held out per fold."""
    raise NotImplementedError("Milestone 2")


def evaluate_ranking(scored: pl.DataFrame, labels: pl.DataFrame) -> dict[str, float]:
    """Per-disease metrics plus their aggregate.

    Returns both. The aggregate alone conceals per-disease variance, which is
    usually the most informative part of the result.
    """
    raise NotImplementedError("Milestone 2 — Context.md §19")
