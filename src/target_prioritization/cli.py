"""Command-line entry points.

Kept in the package rather than in ``scripts/`` so the logic is importable and
testable (Context.md §34). ``scripts/*.py`` are thin wrappers around these.
"""

from __future__ import annotations

import sys

import httpx
import typer
from rich.console import Console
from rich.table import Table

from target_prioritization.config import load_data_sources, settings
from target_prioritization.data.download import (
    IntegrityManifest,
    download_all,
    expand_items,
    plan_datasets,
    verify_downloads,
)
from target_prioritization.utils.logging import configure_logging, get_logger
from target_prioritization.utils.paths import DATA_RAW, relative_to_root

app = typer.Typer(add_completion=False, help="Disease-target prioritization data tools.")
console = Console()
log = get_logger(__name__)


def _fmt_size(num_bytes: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if abs(num_bytes) < 1024 or unit == "GB":
            return f"{num_bytes:,.1f} {unit}" if unit != "B" else f"{num_bytes:,.0f} B"
        num_bytes /= 1024
    return f"{num_bytes:,.1f} GB"


@app.command("download")
def download(
    profile: str = typer.Option("core", "--profile", "-p", help="core (~2.5 GB) or full (~15 GB)."),
    only: str = typer.Option(
        "",
        "--only",
        help="Comma-separated sources or datasets, e.g. 'string,open_targets/target'.",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be fetched, write nothing."
    ),
    verify: bool = typer.Option(
        False, "--verify", help="Re-check existing files against their manifests and exit."
    ),
    force: bool = typer.Option(
        False, "--force", help="Re-download even if a file already verifies."
    ),
    concurrency: int = typer.Option(
        0, "--concurrency", "-j", help="Parallel downloads (default from DTP_DOWNLOAD_CONCURRENCY)."
    ),
) -> None:
    """Download the datasets declared in ``configs/data_sources.yaml``."""
    configure_logging()

    if verify:
        _run_verify()
        return

    config = load_data_sources()
    only_list = [s for s in only.split(",") if s.strip()] if only else None

    try:
        planned = plan_datasets(config, profile, only_list)
    except KeyError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=2) from exc

    if not planned:
        console.print(f"[yellow]No datasets selected for profile {profile!r}.[/yellow]")
        raise typer.Exit(code=1)

    client = httpx.Client(timeout=httpx.Timeout(30.0, read=120.0), follow_redirects=True)

    try:
        # Resolve directory listings so the reported counts are real rather
        # than estimated. Falls back to the config estimate if listing fails
        # (offline, or upstream reorganised a path).
        try:
            items = expand_items(planned, client)
            expanded = True
        except Exception as exc:
            if not dry_run:
                raise
            log.warning("listing_failed_using_estimates", error=str(exc))
            items, expanded = [], False

        _print_plan(planned, items, profile, expanded)

        if dry_run:
            console.print("\n[bold]--dry-run: nothing written.[/bold]")
            return

        integrity = None
        ot_source = config.sources.get("open_targets")
        if ot_source and ot_source.checksum_manifest_url:
            url = ot_source.checksum_manifest_url.format(release=ot_source.release or "")
            console.print("Fetching Open Targets release integrity manifest…")
            integrity = IntegrityManifest.fetch(url, client)

        stats = download_all(
            items,
            concurrency=concurrency or settings.download_concurrency,
            force=force,
            integrity=integrity,
            client=client,
        )
    finally:
        client.close()

    console.print(
        f"\n[bold]Done.[/bold] {len(stats.downloaded)} downloaded "
        f"({_fmt_size(stats.bytes_written)}), {len(stats.skipped)} already present, "
        f"{len(stats.failed)} failed."
    )

    if stats.failed:
        console.print("\n[red]Failures:[/red]")
        for result in stats.failed:
            console.print(
                f"  {result.item.source_name}/{result.item.dataset_name}/"
                f"{result.item.dest.name}: {result.detail}"
            )
        raise typer.Exit(code=1)


def _print_plan(planned: list, items: list, profile: str, expanded: bool) -> None:
    table = Table(title=f"Download plan — profile: {profile}", header_style="bold")
    table.add_column("Source")
    table.add_column("Dataset")
    table.add_column("Files", justify="right")
    table.add_column("Size", justify="right")
    table.add_column("Note", overflow="fold", max_width=42)

    files_by_dataset: dict[tuple[str, str], int] = {}
    for item in items:
        key = (item.source_name, item.dataset_name)
        files_by_dataset[key] = files_by_dataset.get(key, 0) + 1

    total_bytes = 0
    for entry in planned:
        key = (entry.source_name, entry.dataset.name)
        n_files = files_by_dataset.get(key, 1) if expanded else 1
        size = entry.approx_bytes
        total_bytes += size
        note = ""
        if entry.dataset.leakage_note:
            note = "[yellow]leakage note — see features.yaml[/yellow]"
        elif not entry.source.release_pinned:
            note = "[cyan]unversioned URL; date-stamped only[/cyan]"
        table.add_row(
            entry.source_name,
            entry.dataset.name,
            str(n_files) if expanded else "?",
            _fmt_size(size),
            note,
        )

    console.print(table)
    suffix = "" if expanded else "  (estimates: directory listing unavailable)"
    console.print(
        f"[bold]{len(planned)} datasets"
        + (f", {len(items)} files" if expanded else "")
        + f", ~{_fmt_size(total_bytes)} total[/bold]{suffix}"
    )
    console.print(f"Destination: {relative_to_root(DATA_RAW)}/")


def _run_verify() -> None:
    console.print(f"Verifying files under {relative_to_root(DATA_RAW)}/ …")

    # Check against the checksums Open Targets published, not only against the
    # ones we computed locally — a locally-computed hash of corrupt bytes
    # matches itself perfectly.
    integrity = None
    config = load_data_sources()
    ot_source = config.sources.get("open_targets")
    if ot_source and ot_source.checksum_manifest_url:
        url = ot_source.checksum_manifest_url.format(release=ot_source.release or "")
        with httpx.Client(timeout=httpx.Timeout(30.0, read=120.0), follow_redirects=True) as client:
            integrity = IntegrityManifest.fetch(url, client)
        if integrity is None:
            console.print(
                "[yellow]Upstream integrity manifest unavailable; "
                "falling back to local checksums only.[/yellow]"
            )

    ok, failures, upstream = verify_downloads(integrity=integrity)

    if not ok and not failures:
        console.print("[yellow]No manifests found — nothing has been downloaded yet.[/yellow]")
        raise typer.Exit(code=1)

    console.print(
        f"[green]{len(ok)} file(s) verified[/green]"
        + (f" ({upstream} against upstream Open Targets checksums)" if upstream else "")
    )
    if failures:
        console.print(f"[red]{len(failures)} file(s) failed:[/red]")
        for path, detail in failures:
            console.print(f"  {relative_to_root(path)}: {detail}")
        raise typer.Exit(code=1)


def download_main() -> None:
    """Entry point for the ``dtp-download`` console script."""
    typer.run(download)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(app())
