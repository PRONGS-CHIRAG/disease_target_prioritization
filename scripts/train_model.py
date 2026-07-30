#!/usr/bin/env python
"""Train every Milestone 2 model under leave-one-disease-out (Context.md §37).

Builds the multi-disease feature table and labels, runs the deliberate
leakage probe, trains the weighted baseline / logistic regression / random
forest / XGBoost on nine diseases and scores the tenth — once per disease —
then refits XGBoost on all ten as the production model.

Writes:
    data/processed/disease_target_features.parquet
    data/processed/labels.parquet
    models/trained/xgboost_baseline.json
    reports/evaluation/baseline_metrics.json
    models/metadata/milestone2_<timestamp>.json

Exits non-zero if the acceptance check fails — every model must beat the
random-ranking floor on NDCG@10 in at least 9 of 10 diseases.

Usage:
    python scripts/train_model.py
"""

from __future__ import annotations

import sys

from rich.console import Console
from rich.table import Table

from target_prioritization.milestone2 import run_milestone_2
from target_prioritization.utils.logging import configure_logging

console = Console()


def main() -> int:
    configure_logging()
    result = run_milestone_2(write_outputs=True)

    table = Table(title="NDCG@10 — primary vs. novel-only", header_style="bold")
    table.add_column("Method")
    table.add_column("Primary", justify="right")
    table.add_column("Novel-only", justify="right")
    table.add_column("Beats random", justify="right")

    primary = result.aggregate("ndcg_at_10")
    novel = result.aggregate("ndcg_at_10", novel_only=True)
    for name, value in sorted(primary.items(), key=lambda kv: kv[1] or 0.0, reverse=True):
        beats = result.acceptance_beats_random.get(name)
        beats_str = f"{beats[0]}/{beats[1]}" if beats else "—"
        table.add_row(
            name,
            f"{value:.3f}" if value is not None else "—",
            f"{novel.get(name):.3f}" if novel.get(name) is not None else "—",
            beats_str,
        )
    console.print(table)

    console.print(
        f"\n[bold]target_popularity NDCG@10:[/bold] {primary.get('target_popularity', 0):.3f} vs. "
        f"[bold]xgboost:[/bold] {primary.get('xgboost', 0):.3f} — see reports/evaluation/baseline_report.md"
    )

    if result.acceptance_passed:
        console.print("\n[green]Acceptance check PASSED:[/green] every model beats random in >= 9/10 diseases.")
        return 0

    console.print("\n[red]Acceptance check FAILED.[/red] See beats_random column above.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
