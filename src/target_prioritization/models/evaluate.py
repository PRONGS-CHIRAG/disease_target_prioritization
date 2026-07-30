"""Evaluation (Context.md §19, §37).

Two rules that are easy to get wrong and expensive to discover late:

* **Compute per disease, then aggregate** (§19.3). A single pooled metric lets a
  few data-rich diseases carry the average and hides total failure on the rest.
  Every function here that reports a headline number does so by averaging
  per-disease values, never by pooling rows across diseases first.
* **Never split rows randomly** (§19.4). The same disease in train and test lets
  the model memorise that disease's targets instead of learning what makes a
  target promising. :func:`leave_one_disease_out_splits` groups by disease.

PR-AUC is the headline classification metric, not ROC-AUC: positives are rare
here (~2.5% prevalence, milestone2.md §1) and ROC-AUC flatters under
imbalance (§19.1).

**Stratification.** 78-98% of every disease's positives are also positives in
at least one other configured disease (milestone2.md §1) — a model can rank
well under leave-one-disease-out by learning "this is a druggable,
well-studied protein" without any disease-specific signal at all.
:func:`novel_only_labels` isolates the subset where that shortcut is
unavailable, by relabeling every positive that recurs across diseases to
negative. Re-running :func:`evaluate_ranking` against its output — instead of
against a differently-shaped set of rows — measures exactly the same ranking
with exactly the same candidates, so the two results are directly comparable.
"""

from __future__ import annotations

import math
import re
from typing import Any

import polars as pl
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

from target_prioritization.utils.logging import get_logger

__all__ = [
    "average_precision",
    "classification_metrics_for_disease",
    "evaluate_ranking",
    "hit_rate_at_k",
    "label_positive_prevalence_excluding",
    "leave_one_disease_out_splits",
    "ndcg_at_k",
    "novel_only_labels",
    "precision_at_k",
    "rank_within_disease",
    "recall_at_k",
    "reciprocal_rank",
]

log = get_logger(__name__)

# Context.md never specifies a k for "hit rate"; matched to the primary
# metric's k (ndcg_at_10, configs/model.yaml) and precision_at_10 rather than
# left ambiguous.
DEFAULT_HIT_RATE_K = 10

_RANKING_METRIC_PATTERN = re.compile(r"^(precision|recall|ndcg)_at_(\d+)$")
_CLASSIFICATION_THRESHOLD = 0.5


# ---------------------------------------------------------------------------
# Deterministic ranking
# ---------------------------------------------------------------------------


def rank_within_disease(scored: pl.DataFrame) -> pl.DataFrame:
    """Add a 1-based ``rank`` column, computed independently per disease.

    Ties break on ``target_id`` — the only unique key. Milestone 1
    (milestone1.md §5a) hit non-determinism from exactly this: DuckDB's
    parallel scan returns tied rows in a different order each run, and
    without a unique final sort key the written output was not
    byte-reproducible even though the scores were identical. Logistic
    regression scoring the 71%-literature-only rows Milestone 1 found will
    produce plenty of exact ties, so this matters here even more than it did
    there.

    Args:
        scored: Must have ``disease_id``, ``target_id``, ``score``.

    Returns:
        *scored* plus ``rank``, sorted by ``(disease_id, score desc,
        target_id asc)``.
    """
    return scored.sort(
        ["disease_id", "score", "target_id"], descending=[False, True, False]
    ).with_columns(pl.cum_count("target_id").over("disease_id").alias("rank"))


# ---------------------------------------------------------------------------
# Per-disease ranking metrics
#
# Each takes one disease's ranked frame — `rank` (1-based) and `label` (0/1,
# nulls already excluded by the caller) — and returns a float, or None when
# the metric is undefined for that disease (no positives at all). None
# values are excluded from the aggregate mean, not treated as zero.
# ---------------------------------------------------------------------------


def precision_at_k(ranked: pl.DataFrame, k: int) -> float:
    """Precision@k for a single disease's ranking.

    Denominator is ``min(k, n_candidates)`` — a disease with fewer than k
    candidates cannot be penalised for candidates that don't exist.
    """
    if ranked.is_empty():
        return 0.0
    denom = min(k, ranked.height)
    n_relevant = int(ranked.filter(pl.col("rank") <= k).get_column("label").sum())
    return n_relevant / denom


def recall_at_k(ranked: pl.DataFrame, k: int) -> float | None:
    """Recall@k for a single disease's ranking.

    Returns:
        None if the disease has zero positives — recall is undefined, not
        zero, in that case. Reported counts (milestone2.md §5) mean recall@20
        for a 342-positive disease ceilings at 5.8% purely from denominator
        size, and is not comparable to recall@20 for an 87-positive one; do
        not average this across diseases without also reporting positive
        counts.
    """
    n_positive = int(ranked.get_column("label").sum())
    if n_positive == 0:
        return None
    n_relevant = int(ranked.filter(pl.col("rank") <= k).get_column("label").sum())
    return n_relevant / n_positive


def ndcg_at_k(ranked: pl.DataFrame, k: int) -> float | None:
    """NDCG@k for a single disease's ranking. Primary metric per model.yaml.

    Binary relevance: DCG@k = sum_{i<=k} label_i / log2(i+1). IDCG@k is the
    same sum over the ideal ordering (every positive first).
    """
    n_positive = int(ranked.get_column("label").sum())
    if n_positive == 0:
        return None

    top_k = ranked.filter(pl.col("rank") <= k).sort("rank")
    dcg = sum(
        label / math.log2(rank + 1)
        for rank, label in zip(top_k.get_column("rank"), top_k.get_column("label"), strict=True)
        if label
    )
    ideal_hits = min(n_positive, k, ranked.height)
    idcg = sum(1.0 / math.log2(i + 1) for i in range(1, ideal_hits + 1))
    return dcg / idcg if idcg else None


def average_precision(ranked: pl.DataFrame) -> float | None:
    """Average precision over the FULL ranking (not truncated to a k).

    The per-disease numerator of Mean Average Precision:
    AP = (1 / n_positive) * sum over ranks i with label_i=1 of precision@i.
    """
    n_positive = int(ranked.get_column("label").sum())
    if n_positive == 0:
        return None

    ordered = ranked.sort("rank").with_columns(pl.col("label").cum_sum().alias("n_relevant_so_far"))
    hits = ordered.filter(pl.col("label") == 1)
    precisions_at_hits = hits.get_column("n_relevant_so_far") / hits.get_column("rank")
    return float(precisions_at_hits.sum()) / n_positive


def reciprocal_rank(ranked: pl.DataFrame) -> float | None:
    """1 / rank of the first positive. The per-disease numerator of MRR."""
    hits = ranked.filter(pl.col("label") == 1)
    if hits.is_empty():
        return None
    first_rank = int(hits.get_column("rank").min())  # type: ignore[arg-type]
    return 1.0 / first_rank


def hit_rate_at_k(ranked: pl.DataFrame, k: int = DEFAULT_HIT_RATE_K) -> float | None:
    """1.0 if any positive appears in the top k, else 0.0."""
    n_positive = int(ranked.get_column("label").sum())
    if n_positive == 0:
        return None
    return 1.0 if int(ranked.filter(pl.col("rank") <= k).get_column("label").sum()) > 0 else 0.0


# ---------------------------------------------------------------------------
# Per-disease classification metrics
# ---------------------------------------------------------------------------


def classification_metrics_for_disease(
    ranked: pl.DataFrame,
    metric_names: list[str],
    *,
    threshold: float = _CLASSIFICATION_THRESHOLD,
) -> dict[str, float | None]:
    """Classification metrics for one disease's scored candidates.

    Args:
        ranked: Must have ``score`` (treated as a probability-like value in
            [0, 1] for thresholding) and ``label`` (0/1).
        metric_names: Subset of ``roc_auc``, ``pr_auc``, ``precision``,
            ``recall``, ``f1``, ``brier_score``.
        threshold: Cutoff for precision/recall/f1. roc_auc, pr_auc and
            brier_score are threshold-free.

    Returns:
        ``{metric_name: value}``. A value is None when the metric is
        undefined for this disease (e.g. roc_auc needs both classes present)
        or not requested.

    Note:
        Meaningful only for models whose ``score`` is an actual probability
        (logistic regression, random forest, XGBoost). For the weighted
        baseline, `target_popularity` and `random_ranking`, ``score`` is not
        calibrated to [0, 1] as a probability, and threshold=0.5 in
        particular has no principled meaning — reported for completeness,
        not as a fair comparison (see the report's baseline-fairness note).
        ``target_popularity`` in particular is a raw count (0..n_diseases-1,
        not bounded to [0, 1] at all), so ``brier_score`` is undefined for it
        rather than merely uncalibrated — handled as None below rather than
        letting sklearn raise, consistent with every other "undefined for
        this model/disease" case in this module.
    """
    y_true = ranked.get_column("label").to_numpy()
    y_score = ranked.get_column("score").to_numpy()
    has_both_classes = len(set(y_true.tolist())) == 2

    out: dict[str, float | None] = {}
    if "roc_auc" in metric_names:
        out["roc_auc"] = float(roc_auc_score(y_true, y_score)) if has_both_classes else None
    if "pr_auc" in metric_names:
        out["pr_auc"] = float(average_precision_score(y_true, y_score)) if has_both_classes else None
    if "brier_score" in metric_names:
        if float(y_score.min()) < 0.0 or float(y_score.max()) > 1.0:
            out["brier_score"] = None
        else:
            out["brier_score"] = float(brier_score_loss(y_true, y_score))
    if {"precision", "recall", "f1"} & set(metric_names):
        y_pred = (y_score >= threshold).astype(int)
        if "precision" in metric_names:
            out["precision"] = float(precision_score(y_true, y_pred, zero_division=0))
        if "recall" in metric_names:
            out["recall"] = float(recall_score(y_true, y_pred, zero_division=0))
        if "f1" in metric_names:
            out["f1"] = float(f1_score(y_true, y_pred, zero_division=0))
    return out


# ---------------------------------------------------------------------------
# Leave-one-disease-out splitting (Context.md §19.4)
# ---------------------------------------------------------------------------


def leave_one_disease_out_splits(features: pl.DataFrame) -> list[tuple[list[int], list[int]]]:
    """Yield (train_idx, test_idx) with one disease held out per fold.

    Args:
        features: Must have a ``disease_id`` column. Row order is preserved —
            returned indices are positional into *features* as given.

    Returns:
        One ``(train_idx, test_idx)`` pair per distinct disease, ordered by
        sorted ``disease_id`` for reproducibility (Context.md §33) — dict/set
        iteration order is not guaranteed to be stable input-to-input.
    """
    disease_ids = features.get_column("disease_id").to_list()
    distinct = sorted(set(disease_ids))

    splits: list[tuple[list[int], list[int]]] = []
    for held_out in distinct:
        train_idx = [i for i, d in enumerate(disease_ids) if d != held_out]
        test_idx = [i for i, d in enumerate(disease_ids) if d == held_out]
        splits.append((train_idx, test_idx))
    return splits


# ---------------------------------------------------------------------------
# Stratification: isolating disease-specific signal from cross-disease
# target popularity (milestone2.md §1)
# ---------------------------------------------------------------------------


def label_positive_prevalence_excluding(labels: pl.DataFrame, disease_id: str) -> pl.DataFrame:
    """For every target, how many diseases OTHER than *disease_id* it is a
    positive in.

    Shared by two callers: the ``target_popularity`` baseline (models/train.py
    Milestone 2 — the count itself becomes the score) and stratification here
    (whether the count is > 0). Kept as one function rather than two so the
    "positive elsewhere" definition can't drift between the baseline and the
    metric that is supposed to be measuring it.

    Returns:
        ``target_id``, ``n_other_diseases_positive``.
    """
    return (
        labels.filter((pl.col("disease_id") != disease_id) & (pl.col("label") == 1))
        .group_by("target_id")
        .agg(pl.len().alias("n_other_diseases_positive"))
    )


def novel_only_labels(labels: pl.DataFrame) -> pl.DataFrame:
    """*labels* with every cross-disease-recurring positive relabeled to 0.

    A positive that recurs (is label=1 in 2+ diseases) is, from any one of
    those diseases' perspective as the leave-one-disease-out held-out fold,
    "seen elsewhere" in the training folds. Relabeling it to 0 rather than
    dropping the row means the candidate set and the ranking itself are
    IDENTICAL to the primary evaluation — only which positives count as
    relevant changes — so :func:`evaluate_ranking` run against this output is
    directly comparable to the primary result, not confounded by a
    differently-sized population (the same population-mismatch mistake this
    project's label provenance design already had to fix once, in
    ``build_labels_for_disease``'s ``n_positive_direct_only`` — see
    milestone2.md §2).

    Negatives (label=0) and excluded rows (label=None) pass through
    unchanged.
    """
    recurring = (
        labels.filter(pl.col("label") == 1)
        .group_by("target_id")
        .agg(pl.len().alias("n_diseases_positive"))
        .filter(pl.col("n_diseases_positive") > 1)
        .get_column("target_id")
        .to_list()
    )
    return labels.with_columns(
        pl.when((pl.col("label") == 1) & pl.col("target_id").is_in(recurring))
        .then(0)
        .otherwise(pl.col("label"))
        .cast(pl.Int8)
        .alias("label")
    )


# ---------------------------------------------------------------------------
# Top-level evaluation
# ---------------------------------------------------------------------------


def _ranking_metric_value(ranked: pl.DataFrame, metric_name: str) -> float | None:
    if metric_name == "map":
        return average_precision(ranked)
    if metric_name == "mrr":
        return reciprocal_rank(ranked)
    if metric_name == "hit_rate":
        return hit_rate_at_k(ranked, DEFAULT_HIT_RATE_K)

    match = _RANKING_METRIC_PATTERN.match(metric_name)
    if not match:
        raise ValueError(f"Unrecognised ranking metric name: {metric_name!r}")
    family, k = match.group(1), int(match.group(2))
    if family == "precision":
        return precision_at_k(ranked, k)
    if family == "recall":
        return recall_at_k(ranked, k)
    return ndcg_at_k(ranked, k)  # family == "ndcg"


def evaluate_ranking(
    scored: pl.DataFrame,
    labels: pl.DataFrame,
    ranking_metrics: list[str],
    classification_metrics: list[str] | None = None,
) -> dict[str, Any]:
    """Per-disease metrics plus their aggregate.

    Args:
        scored: ``disease_id``, ``target_id``, ``score``. One row per
            candidate this model produced a score for.
        labels: ``disease_id``, ``target_id``, ``label``. Rows with
            ``label`` null (Context.md §34 — UNKNOWN clinical stage,
            data/labels.py) are dropped before scoring; they are neither
            positive nor negative and must not count as either.
        ranking_metrics: Names from ``configs/model.yaml``
            ``evaluation.ranking_metrics``, e.g. ``"ndcg_at_10"``.
        classification_metrics: Names from ``evaluation.classification_metrics``.

    Returns:
        Both the per-disease breakdown and the aggregate. The aggregate alone
        conceals per-disease variance, which is usually the most informative
        part of the result (Context.md §19.3) — callers that only need one
        number should still look at ``per_disease`` before trusting it.

        ``{"per_disease": {disease_id: {metric: value, "n_candidates": int,
        "n_positive": int}}, "aggregate": {metric: mean_over_diseases},
        "n_diseases_excluded_per_metric": {metric: int}}``. A metric is
        excluded for a disease (and skipped in that metric's aggregate mean)
        when it is undefined there — e.g. recall@k for a disease with zero
        positives in *labels*, which should not occur among the ten
        configured diseases but is handled rather than assumed away.
    """
    classification_metrics = classification_metrics or []
    labelled = labels.filter(pl.col("label").is_not_null())
    joined = scored.join(
        labelled.select(["disease_id", "target_id", "label"]),
        on=["disease_id", "target_id"],
        how="inner",
    )
    ranked = rank_within_disease(joined)

    per_disease: dict[str, dict[str, Any]] = {}
    metric_values: dict[str, list[float]] = {m: [] for m in (*ranking_metrics, *classification_metrics)}
    excluded_counts: dict[str, int] = dict.fromkeys(metric_values, 0)

    for disease_id in sorted(ranked.get_column("disease_id").unique().to_list()):
        disease_ranked = ranked.filter(pl.col("disease_id") == disease_id)
        result: dict[str, Any] = {
            "n_candidates": disease_ranked.height,
            "n_positive": int(disease_ranked.get_column("label").sum()),
        }

        for metric_name in ranking_metrics:
            value = _ranking_metric_value(disease_ranked, metric_name)
            result[metric_name] = value
            if value is None:
                excluded_counts[metric_name] += 1
            else:
                metric_values[metric_name].append(value)

        if classification_metrics:
            class_values = classification_metrics_for_disease(disease_ranked, classification_metrics)
            for metric_name, value in class_values.items():
                result[metric_name] = value
                if value is None:
                    excluded_counts[metric_name] += 1
                else:
                    metric_values[metric_name].append(value)

        per_disease[disease_id] = result

    aggregate = {
        metric_name: (sum(values) / len(values) if values else None)
        for metric_name, values in metric_values.items()
    }

    # Rounded to 10 decimal places — sklearn.metrics (roc_auc, pr_auc,
    # brier_score) route through numpy reductions whose summation order can
    # vary run-to-run under multi-threaded BLAS, producing last-ULP
    # differences (~1e-16 relative) that are scientifically meaningless but
    # break Context.md §33's byte-identical-rerun requirement. The
    # hand-written ranking metrics above are pure Python and would already be
    # exact; rounding is applied uniformly rather than only where it happens
    # to be needed, so the guarantee does not depend on which metric family
    # produced a given value.
    per_disease = {
        disease_id: {k: (round(v, 10) if isinstance(v, float) else v) for k, v in row.items()}
        for disease_id, row in per_disease.items()
    }
    aggregate = {k: (round(v, 10) if v is not None else None) for k, v in aggregate.items()}

    for metric_name, n_excluded in excluded_counts.items():
        if n_excluded:
            log.warning(
                "metric_undefined_for_some_diseases",
                metric=metric_name,
                n_diseases_excluded=n_excluded,
                note="excluded from that metric's aggregate mean, not treated as zero",
            )

    log.info(
        "evaluate_ranking_done",
        n_diseases=len(per_disease),
        n_scored_rows=scored.height,
        n_joined_rows=joined.height,
        **{k: v for k, v in aggregate.items() if v is not None},
    )

    return {
        "per_disease": per_disease,
        "aggregate": aggregate,
        "n_diseases_excluded_per_metric": excluded_counts,
    }
