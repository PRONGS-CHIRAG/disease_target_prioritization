#!/usr/bin/env python
"""Compare ``baseline_weights`` against ``milestone_1_weights`` (Milestone 4).

``baseline_weights`` (Context.md §17.1's original six-dimension formula)
became reachable once Milestone 4 wired ``dim__pathways``/``dim__network``/
``dim__expression`` in (milestone4_plan.md §2.4). This script does NOT change
the app/training default — that stays ``milestone_1_weights``, empirically
validated against the five established Parkinson's genes (milestone1.md §3)
— it just makes the comparison Context.md §17.1 itself calls for reportable,
reusing the ``disease_target_features.parquet`` / ``labels.parquet``
``scripts/train_model.py`` already writes.

``WeightedBaseline`` needs no fitting (models/train.py) — its weights are
fixed constants, not learned from data — so scoring the whole table once
with each profile is equivalent to scoring it per leave-one-disease-out
fold; no split is needed here the way it is for the fitted models.

Also runs ``configs/model.yaml``'s ``evaluation.ablations`` (``no_literature``,
``no_network``, ``genetics_only``) against ``baseline_weights`` via
``WeightedBaseline.ablate`` — declared in config since Milestone 2 but never
wired to a runner (only XGBoost's separate, feature-column-dropping literature
ablation in ``milestone2.py`` actually ran). ``no_network`` only means
something against ``baseline_weights`` (``milestone_1_weights`` has no
``network`` key to drop at all), which is exactly why it was "not applicable"
before Milestone 4 and reachable now.

Writes:
    reports/evaluation/baseline_weights_comparison.json

Usage:
    python scripts/compare_baseline_weights.py
"""

from __future__ import annotations

import json
import sys

import polars as pl
from rich.console import Console
from rich.table import Table

from target_prioritization.config import load_model_config
from target_prioritization.models.baseline import SCORE_COLUMN, WeightedBaseline
from target_prioritization.models.evaluate import evaluate_ranking, novel_only_labels
from target_prioritization.utils.logging import configure_logging
from target_prioritization.utils.paths import DATA_PROCESSED, EVALUATION_DIR

console = Console()


def _score_frame(scored: pl.DataFrame) -> pl.DataFrame:
    return scored.select("disease_id", "target_id", pl.col(SCORE_COLUMN).alias("score"))


def _evaluate(
    scored: pl.DataFrame,
    labels: pl.DataFrame,
    novel_labels: pl.DataFrame,
    ranking_metrics: list[str],
    classification_metrics: list[str],
) -> dict[str, object]:
    primary = evaluate_ranking(scored, labels, ranking_metrics, classification_metrics)
    novel = evaluate_ranking(scored, novel_labels, ranking_metrics, classification_metrics)
    return {"primary": primary["aggregate"], "novel_only": novel["aggregate"]}


def main() -> int:
    configure_logging()
    model_config = load_model_config()

    features_path = DATA_PROCESSED / "disease_target_features.parquet"
    labels_path = DATA_PROCESSED / "labels.parquet"
    if not features_path.exists() or not labels_path.exists():
        console.print(f"[red]Missing {features_path} or {labels_path}.[/red] Run scripts/train_model.py first.")
        return 1

    features = pl.read_parquet(features_path)
    labels = pl.read_parquet(labels_path)
    novel_labels = novel_only_labels(labels)

    ranking_metrics = model_config.evaluation.ranking_metrics
    classification_metrics = model_config.evaluation.classification_metrics

    profiles = {
        "milestone_1_weights": dict(model_config.milestone_1_weights),
        "baseline_weights": dict(model_config.baseline_weights),
    }

    def _ndcg_at_10(evaluated: dict[str, object], key: str) -> float | None:
        aggregate = evaluated[key]
        assert isinstance(aggregate, dict)
        value = aggregate.get("ndcg_at_10")
        assert value is None or isinstance(value, float)
        return value

    results: dict[str, object] = {}
    aggregates: dict[str, dict[str, object]] = {}
    for name, weights in profiles.items():
        scored = _score_frame(WeightedBaseline(weights).score(features))
        evaluated = _evaluate(scored, labels, novel_labels, ranking_metrics, classification_metrics)
        results[name] = {"weights": weights, **evaluated}
        aggregates[name] = evaluated

    baseline = WeightedBaseline(dict(model_config.baseline_weights))
    ablation_results: dict[str, dict[str, object]] = {}
    ablation_aggregates: dict[str, dict[str, object]] = {}
    for ablation in model_config.evaluation.ablations:
        drop = ablation.drop_groups or [d for d in baseline.weights if d not in ablation.keep_groups]
        try:
            ablated_scored = _score_frame(baseline.ablate(features, drop))
        except ValueError as exc:
            ablation_results[ablation.name] = {"skipped": str(exc)}
            continue
        evaluated = _evaluate(ablated_scored, labels, novel_labels, ranking_metrics, classification_metrics)
        ablation_results[ablation.name] = {"dropped": drop, **evaluated}
        ablation_aggregates[ablation.name] = evaluated
    results["baseline_weights_ablations"] = ablation_results

    table = Table(title="milestone_1_weights vs. baseline_weights", header_style="bold")
    table.add_column("Profile")
    table.add_column("NDCG@10 (primary)", justify="right")
    table.add_column("NDCG@10 (novel-only)", justify="right")
    for name, evaluated in aggregates.items():
        primary_ndcg = _ndcg_at_10(evaluated, "primary")
        novel_ndcg = _ndcg_at_10(evaluated, "novel_only")
        table.add_row(
            name,
            f"{primary_ndcg:.3f}" if primary_ndcg is not None else "—",
            f"{novel_ndcg:.3f}" if novel_ndcg is not None else "—",
        )
    for ablation_name, evaluated in ablation_aggregates.items():
        primary_ndcg = _ndcg_at_10(evaluated, "primary")
        novel_ndcg = _ndcg_at_10(evaluated, "novel_only")
        table.add_row(
            f"baseline_weights, {ablation_name}",
            f"{primary_ndcg:.3f}" if primary_ndcg is not None else "—",
            f"{novel_ndcg:.3f}" if novel_ndcg is not None else "—",
        )
    console.print(table)

    output_path = EVALUATION_DIR / "baseline_weights_comparison.json"
    output_path.write_text(json.dumps(results, indent=2))
    console.print(f"\nWrote {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
