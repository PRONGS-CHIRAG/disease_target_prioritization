#!/usr/bin/env python
"""Run the full Milestone 2 pipeline and produce the evaluation report (Context.md §37).

Runs training (same as scripts/train_model.py) and additionally produces the
figure and the generated report. Exits non-zero if the acceptance check
fails — every model must beat the random-ranking floor on NDCG@10 in at
least 9 of 10 diseases.

Produces every §37 deliverable:

    data/processed/disease_target_features.parquet
    data/processed/labels.parquet
    models/trained/xgboost_baseline.json
    reports/evaluation/baseline_metrics.json
    reports/evaluation/baseline_report.md
    reports/figures/milestone2_popularity_comparison.png

Usage:
    python scripts/evaluate_model.py
"""

from __future__ import annotations

import sys

from rich.console import Console

from target_prioritization.milestone2 import run_milestone_2
from target_prioritization.reporting2 import METHOD_LABELS, build_report
from target_prioritization.utils.logging import configure_logging
from target_prioritization.utils.paths import (
    EVALUATION_DIR,
    FIGURES_DIR,
    ensure_dir,
    relative_to_root,
)
from target_prioritization.viz import plot_popularity_comparison

console = Console()

FIGURE_NAME = "milestone2_popularity_comparison.png"
REPORT_NAME = "baseline_report.md"


def main() -> int:
    configure_logging()
    result = run_milestone_2(write_outputs=True)

    figure_path = plot_popularity_comparison(
        result.aggregate("ndcg_at_10"),
        result.aggregate("ndcg_at_10", novel_only=True),
        METHOD_LABELS,
        FIGURES_DIR / FIGURE_NAME,
    )

    ensure_dir(EVALUATION_DIR)
    report_path = EVALUATION_DIR / REPORT_NAME
    report_path.write_text(build_report(result))

    console.print(f"Wrote {relative_to_root(figure_path)}")
    console.print(f"Wrote {relative_to_root(report_path)}")

    primary = result.aggregate("ndcg_at_10")
    novel = result.aggregate("ndcg_at_10", novel_only=True)
    console.print(
        f"\ntarget_popularity NDCG@10: {primary.get('target_popularity', 0):.3f} primary, "
        f"{novel.get('target_popularity', 0):.3f} novel-only"
    )
    console.print(
        f"xgboost NDCG@10:            {primary.get('xgboost', 0):.3f} primary, "
        f"{novel.get('xgboost', 0):.3f} novel-only"
    )

    if result.acceptance_passed:
        console.print("\n[green]Acceptance check PASSED[/green]: every model beats random in >= 9/10 diseases.")
        return 0

    console.print("\n[red]Acceptance check FAILED.[/red]")
    return 1


if __name__ == "__main__":
    sys.exit(main())
