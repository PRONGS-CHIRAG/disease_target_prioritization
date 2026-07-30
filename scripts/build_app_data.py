#!/usr/bin/env python
"""Build the Milestone 3 app-facing artifact (Context.md §21).

Requires ``scripts/train_model.py`` to have already produced the multi-disease
feature table, labels, and the per-disease held-out XGBoost fold models under
``models/trained/folds/``.

Writes:
    data/processed/app_scores.parquet
    data/processed/app_scores.parquet.provenance.json

Usage:
    python scripts/build_app_data.py
"""

from __future__ import annotations

import json
import sys

from rich.console import Console

from target_prioritization.app_data import build_app_data
from target_prioritization.utils.logging import configure_logging
from target_prioritization.utils.paths import DATA_PROCESSED, ensure_dir

console = Console()


def main() -> int:
    configure_logging()

    try:
        app_data, provenance = build_app_data()
    except FileNotFoundError as exc:
        console.print(f"[red]Missing prerequisite:[/red] {exc}")
        console.print("Run scripts/train_model.py first.")
        return 1

    ensure_dir(DATA_PROCESSED)
    output_path = DATA_PROCESSED / "app_scores.parquet"
    app_data.write_parquet(output_path)
    (output_path.with_name(output_path.name + ".provenance.json")).write_text(
        json.dumps(provenance, indent=2, sort_keys=True, default=str) + "\n"
    )

    console.print(f"[green]Wrote[/green] {output_path} ({app_data.height} rows, {app_data.width} columns)")
    if provenance["n_missing_held_out_score"]:
        console.print(
            f"[yellow]Warning:[/yellow] {provenance['n_missing_held_out_score']} rows have no held-out "
            "XGBoost score — check the fold models under models/trained/folds/."
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
