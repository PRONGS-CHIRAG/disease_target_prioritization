#!/usr/bin/env python
"""Milestone 5 acceptance check (milestone5_plan.md §6).

Runs the checks in ``target_prioritization.frontend_checks`` against the
real processed artifacts, real fold models and the real configured
diseases. See that module's docstring for what each check does and why.

Exits non-zero if any check fails.

Usage:
    python scripts/check_frontend.py
"""

from __future__ import annotations

import sys

from rich.console import Console
from rich.table import Table

from target_prioritization.frontend_checks import run_all_checks

console = Console()


def main() -> int:
    try:
        results = run_all_checks()
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[red]{exc}[/red]")
        return 1

    table = Table(title="Milestone 5 acceptance check", header_style="bold")
    table.add_column("Check")
    table.add_column("Result")
    for result in results:
        table.add_row(
            result.name, "[green]PASS[/green]" if result.passed else f"[red]FAIL ({len(result.problems)})[/red]"
        )
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
