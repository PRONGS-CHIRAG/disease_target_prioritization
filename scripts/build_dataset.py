#!/usr/bin/env python
"""Build the Milestone 1 candidate-target table (Context.md §36).

Writes data/processed/parkinsons_targets.parquet plus a provenance sidecar.
Logic lives in target_prioritization.milestone1 (Context.md §34).

Usage:
    python scripts/build_dataset.py
    python scripts/build_dataset.py --disease crohns_disease
"""

from __future__ import annotations

import argparse
import sys

from rich.console import Console

from target_prioritization.config import load_diseases
from target_prioritization.milestone1 import PARQUET_NAME, output_name, run_milestone_1
from target_prioritization.utils.logging import configure_logging
from target_prioritization.utils.paths import DATA_PROCESSED, relative_to_root

console = Console()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--disease",
        default=None,
        help="Disease key from configs/diseases.yaml. Defaults to the milestone_1 disease.",
    )
    args = parser.parse_args()

    configure_logging()

    diseases = load_diseases()
    disease = diseases.by_key(args.disease) if args.disease else diseases.milestone_1_disease()

    result = run_milestone_1(disease, write_outputs=True)

    console.print(
        f"\n[green]Wrote {relative_to_root(DATA_PROCESSED / output_name(disease, PARQUET_NAME))}[/green] — "
        f"{result.ranked.height:,} candidate targets for {disease.name} ({disease.efo_id})."
    )

    # The acceptance check compares against established *Parkinson's* genes, so
    # it only means anything for that disease. Running it against Crohn's would
    # report a confident failure that says nothing about the pipeline.
    if not disease.milestone_1:
        console.print(
            f"[dim]No acceptance check for {disease.name}: the known-gene list is "
            "Parkinson's-specific (Context.md §36).[/dim]"
        )
        return 0

    ranks = ", ".join(
        f"{symbol} #{rank}" if rank else f"{symbol} absent"
        for symbol, rank in sorted(result.known_gene_ranks.items(), key=lambda kv: kv[1] or 10**9)
    )
    console.print(f"Known Parkinson's genes: {ranks}")

    if result.acceptance_passed:
        console.print("[green]Acceptance check passed:[/green] all 5 known genes in the top 20.")
        return 0

    console.print(
        "[red]Acceptance check FAILED:[/red] not all known genes reached the top 20. "
        "That points at the data pipeline rather than the biology (Context.md §36)."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
