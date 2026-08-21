#!/usr/bin/env python
"""Build the browsable evidence-detail artifacts (Context.md §21).

Requires the raw Reactome, GTEx and STRING pulls under ``data/raw/`` (see
``make download``) and ``data/processed/disease_target_features.parquet``,
which defines the set of targets the API can be asked about.

Writes, each with a ``.provenance.json`` sidecar:
    data/processed/target_pathways.parquet
    data/processed/target_tissue_expression.parquet
    data/processed/target_interactions.parquet

These are committed to the repository — ``data/raw/`` is excluded from the
container image, so a clean checkout must already carry them (the same
contract as ``app_scores.parquet``). Re-run only when the pinned release
changes.

Usage:
    python scripts/build_evidence_detail.py
"""

from __future__ import annotations

import json
import sys

import polars as pl
from rich.console import Console
from rich.table import Table

from target_prioritization.detail_data import build_detail_data
from target_prioritization.services.target_ranking import FEATURES_PATH
from target_prioritization.utils.logging import configure_logging
from target_prioritization.utils.paths import DATA_PROCESSED, ensure_dir

console = Console()


def main() -> int:
    configure_logging()

    if not FEATURES_PATH.exists():
        console.print(f"[red]Missing prerequisite:[/red] {FEATURES_PATH}")
        console.print("Run scripts/train_model.py first.")
        return 1

    target_ids = (
        pl.read_parquet(FEATURES_PATH, columns=["target_id"])
        .get_column("target_id")
        .unique()
        .sort()
        .to_list()
    )
    console.print(f"Building detail for [bold]{len(target_ids):,}[/bold] targets…")

    try:
        frames, provenance = build_detail_data(target_ids)
    except FileNotFoundError as exc:
        console.print(f"[red]Missing raw data:[/red] {exc}")
        console.print("Run `make download` first — this script reads Reactome, GTEx and STRING.")
        return 1

    ensure_dir(DATA_PROCESSED)
    summary = Table("artifact", "rows", "targets", "size")
    for stem, frame in frames.items():
        output_path = DATA_PROCESSED / f"{stem}.parquet"
        frame.write_parquet(output_path, compression="zstd")
        (output_path.with_name(output_path.name + ".provenance.json")).write_text(
            json.dumps(provenance, indent=2, sort_keys=True, default=str) + "\n"
        )
        size_mb = output_path.stat().st_size / 1_000_000
        summary.add_row(
            stem,
            f"{frame.height:,}",
            f"{frame.get_column('target_id').n_unique():,}",
            f"{size_mb:.1f} MB",
        )
    console.print(summary)

    empty = [stem for stem, frame in frames.items() if frame.is_empty()]
    if empty:
        console.print(f"[red]Empty artifact(s):[/red] {', '.join(empty)} — check the raw inputs.")
        return 1

    console.print("[green]Done.[/green] Commit these parquets — the image build needs them.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
