#!/usr/bin/env python
"""Milestone 3 acceptance check (Context.md §21, §22).

Runs the six checks in ``target_prioritization.app_checks`` against the
real processed artifacts and the real configured diseases. See that
module's docstring for what each check does and why.

Exits non-zero if any check fails.

Usage:
    python scripts/check_app.py
"""

from __future__ import annotations

import sys

from rich.console import Console
from rich.table import Table

from target_prioritization.app_checks import run_all_checks

console = Console()


def main() -> int:
    try:
        results = run_all_checks()
    except FileNotFoundError as exc:
        console.print(f"[red]Missing prerequisite:[/red] {exc}")
        console.print("Run scripts/train_model.py and scripts/build_app_data.py first.")
        return 1
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        return 1

    table = Table(title="Milestone 3 acceptance check", header_style="bold")
    table.add_column("Check")
    table.add_column("Result")
    for result in results:
        table.add_row(result.name, "[green]PASS[/green]" if result.passed else f"[red]FAIL ({len(result.problems)})[/red]")
    console.print(table)

    any_failed = False
    for result in results:
        for problem in result.problems:
            any_failed = True
            console.print(f"[red]  [{result.name}][/red] {problem}")

    if any_failed:
        console.print("\n[red]Acceptance check FAILED.[/red]")
        return 1

    console.print("\n[green]Acceptance check PASSED.[/green]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
