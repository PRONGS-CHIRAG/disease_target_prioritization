#!/usr/bin/env python
"""Run the full Milestone 1 pipeline (Context.md §36).

Produces every §36 deliverable:

    data/processed/parkinsons_targets.parquet
    reports/figures/parkinsons_top_targets.png
    reports/parkinsons_baseline_report.md

Exits non-zero if the acceptance check fails — all five established Parkinson's
genes must reach the top 20. That check is the milestone's real pass condition:
it is what tells us the data pipeline works.

Usage:
    python scripts/run_milestone1.py
"""

from __future__ import annotations

import argparse
import sys

from rich.console import Console
from rich.table import Table

from target_prioritization.milestone1 import (
    ADDITIONAL_PD_GENES,
    FIGURE_NAME,
    KNOWN_PARKINSONS_GENES,
    REPORT_NAME,
    ablation_movement,
    output_name,
    run_milestone_1,
)
from target_prioritization.reporting import build_report
from target_prioritization.utils.logging import configure_logging
from target_prioritization.utils.paths import FIGURES_DIR, REPORTS_DIR, relative_to_root
from target_prioritization.viz import plot_evidence_breakdown

console = Console()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top-n", type=int, default=20, help="Targets to plot (default 20).")
    args = parser.parse_args()

    configure_logging()
    result = run_milestone_1(write_outputs=True)

    # Established genes get a marker in the figure, never a colour change —
    # the categorical encoding must keep meaning exactly one thing.
    highlight = {
        **dict.fromkeys(KNOWN_PARKINSONS_GENES.values(), "known"),
        **dict.fromkeys(ADDITIONAL_PD_GENES.values(), "additional"),
    }
    figure_path = plot_evidence_breakdown(
        result.ranked,
        FIGURES_DIR / output_name(result.disease, FIGURE_NAME),
        top_n=args.top_n,
        highlight=highlight,
        weights=result.weights,
    )

    report_path = REPORTS_DIR / output_name(result.disease, REPORT_NAME)
    report_path.write_text(build_report(result))

    # --- console summary -----------------------------------------------------
    table = Table(title=f"Top {args.top_n} — {result.disease.name}", header_style="bold")
    table.add_column("#", justify="right")
    table.add_column("Gene")
    table.add_column("Score", justify="right")
    table.add_column("Genetics", justify="right")
    table.add_column("Types", justify="right")
    table.add_column("Known", justify="center")

    for row in result.ranked.head(args.top_n).iter_rows(named=True):
        symbol = row["gene_symbol"] or "—"
        genetics = row["dim__genetics"]
        table.add_row(
            str(row["rank"]),
            symbol,
            f"{row['prioritization_score']:.3f}",
            f"{genetics:.3f}" if genetics is not None else "—",
            str(row["n_evidence_types"]),
            "●" if symbol in KNOWN_PARKINSONS_GENES.values() else "",
        )
    console.print(table)

    movement = ablation_movement(result, top_n=args.top_n).sort("rank_change").head(3)
    falls = ", ".join(
        f"{r['gene_symbol']} {r['rank']}→{r['rank_no_literature']}"
        for r in movement.iter_rows(named=True)
        if r["rank_no_literature"] is not None
    )
    console.print(f"\nLargest falls without literature evidence: {falls}")

    console.print(f"\nWrote {relative_to_root(figure_path)}")
    console.print(f"Wrote {relative_to_root(report_path)}")

    ranks = ", ".join(
        f"{s} #{r}" if r else f"{s} absent"
        for s, r in sorted(result.known_gene_ranks.items(), key=lambda kv: kv[1] or 10**9)
    )
    if result.acceptance_passed:
        console.print(f"\n[green]Acceptance check PASSED[/green] — {ranks}")
        return 0

    console.print(f"\n[red]Acceptance check FAILED[/red] — {ranks}")
    console.print("This points at the data pipeline rather than the biology (Context.md §36).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
