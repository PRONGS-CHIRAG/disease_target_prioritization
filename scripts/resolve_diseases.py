#!/usr/bin/env python
"""Resolve the disease names in configs/diseases.yaml to Open Targets IDs.

Context.md §32.6 lists identifier errors among the top project risks. Rather
than hand-typing EFO IDs from memory, this reads them out of the pinned
release's `disease` table and writes them back into the config, recording which
release they were resolved against.

Usage:
    python scripts/resolve_diseases.py            # write the IDs back
    python scripts/resolve_diseases.py --dry-run  # show matches only
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime

import yaml
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from target_prioritization.config import DiseaseSpec, load_diseases
from target_prioritization.data.open_targets import connect, release_tag, resolve_diseases
from target_prioritization.utils.logging import configure_logging
from target_prioritization.utils.paths import CONFIG_DIR

console = Console()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Show matches without writing.")
    args = parser.parse_args()

    configure_logging()

    try:
        specs = load_diseases().diseases
    except ValidationError as exc:
        # This script is the tool that repairs diseases.yaml, so it must be able
        # to run when diseases.yaml is broken — otherwise the only way out of a
        # bad config is hand-editing, which is what this exists to avoid.
        console.print(
            f"[yellow]diseases.yaml does not currently validate; falling back to a raw "
            f"read so the file can be repaired.[/yellow]\n[dim]{exc}[/dim]\n"
        )
        specs = _load_specs_unvalidated()

    with connect() as con:
        matches, unresolved = resolve_diseases(specs, con)

    table = Table(title="Disease resolution", header_style="bold")
    table.add_column("Key")
    table.add_column("Query")
    table.add_column("Resolved ID")
    table.add_column("Resolved name")
    table.add_column("Match")

    by_key = {m.key: m for m in matches}
    for spec in specs:
        match = by_key.get(spec.key)
        if match:
            style = "yellow" if "ambiguous" in match.match_kind else "green"
            table.add_row(
                spec.key,
                spec.name,
                f"[{style}]{match.disease_id}[/{style}]",
                match.resolved_name,
                match.match_kind,
            )
        else:
            table.add_row(spec.key, spec.name, "[red]UNRESOLVED[/red]", "-", "-")

    console.print(table)

    if unresolved:
        console.print(
            f"[red]{len(unresolved)} disease(s) did not resolve: "
            f"{', '.join(s.key for s in unresolved)}[/red]\n"
            "Adjust the `name` field to match the ontology label, or set efo_id by hand "
            "after confirming it on https://platform.opentargets.org."
        )

    if args.dry_run:
        console.print("\n[bold]--dry-run: configs/diseases.yaml not modified.[/bold]")
        return 1 if unresolved else 0

    # Round-trip through yaml rather than rewriting the file, so the comments
    # are lost only in the values we deliberately replace... PyYAML drops
    # comments entirely, so patch the raw text line-wise instead.
    path = CONFIG_DIR / "diseases.yaml"
    text = path.read_text()

    for match in matches:
        text = _set_field_for_key(text, match.key, "efo_id", match.disease_id)
        text = _set_field_for_key(text, match.key, "resolved_name", _quote(match.resolved_name))

    # Quoted deliberately: unquoted, YAML reads "26.06" as a float and an
    # ISO timestamp as a datetime, both of which fail string validation.
    text = _set_top_level(text, "resolved_against_release", _quote(release_tag()))
    text = _set_top_level(
        text, "resolved_at", _quote(datetime.now(UTC).isoformat(timespec="seconds"))
    )

    # Confirm the result still validates before overwriting.
    parsed = yaml.safe_load(text)
    if not isinstance(parsed, dict) or "diseases" not in parsed:
        console.print("[red]Refusing to write: patched YAML failed to parse.[/red]")
        return 2

    path.write_text(text)
    console.print(f"\n[green]Wrote {len(matches)} disease ID(s) to {path.name}.[/green]")
    return 1 if unresolved else 0


def _load_specs_unvalidated() -> list[DiseaseSpec]:
    """Read just enough of diseases.yaml to attempt a repair.

    Only ``key``, ``name`` and ``category`` are needed to resolve; everything
    else is defaulted so a schema error elsewhere in the file does not block
    fixing it.
    """
    payload = yaml.safe_load((CONFIG_DIR / "diseases.yaml").read_text())
    entries = (payload or {}).get("diseases") or []
    specs: list[DiseaseSpec] = []
    for entry in entries:
        if not isinstance(entry, dict) or not entry.get("key") or not entry.get("name"):
            continue
        specs.append(
            DiseaseSpec(
                key=str(entry["key"]),
                name=str(entry["name"]),
                category=str(entry.get("category", "unknown")),
            )
        )
    if not specs:
        raise SystemExit("diseases.yaml has no usable disease entries to resolve.")
    return specs


def _quote(value: str) -> str:
    escaped = value.replace('"', '\\"')
    return f'"{escaped}"'


def _set_field_for_key(text: str, key: str, field: str, value: str) -> str:
    """Set ``field: value`` inside the list entry whose ``key:`` is *key*.

    Replaces the field if present; inserts it directly after the ``- key:``
    line if absent. Inserting rather than skipping matters for
    ``resolved_name``, which does not exist in the hand-written config but is
    the audit trail showing that e.g. "Parkinson's disease" matched the
    ontology label "Parkinson disease".

    Raises:
        KeyError: If no entry with *key* exists. Silently returning the text
            unchanged would leave the caller believing it had written a value
            it had not — the failure mode this codebase rejects everywhere else
            (Context.md §34).
    """
    lines = text.splitlines()
    entry_start: int | None = None
    in_entry = False

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("- key:"):
            in_entry = stripped.split("- key:", 1)[1].strip() == key
            if in_entry:
                entry_start = i
            continue
        if in_entry and stripped.startswith(f"{field}:"):
            indent = len(line) - len(line.lstrip())
            lines[i] = " " * indent + f"{field}: {value}"
            return "\n".join(lines) + ("\n" if text.endswith("\n") else "")

    if entry_start is None:
        raise KeyError(f"No disease entry with key {key!r} in diseases.yaml")

    # Field absent: insert it under the entry, matching the sibling indentation.
    sibling_indent = next(
        (
            len(line) - len(line.lstrip())
            for line in lines[entry_start + 1 :]
            if line.strip() and not line.strip().startswith("- ")
        ),
        len(lines[entry_start]) - len(lines[entry_start].lstrip()) + 2,
    )
    lines.insert(entry_start + 1, " " * sibling_indent + f"{field}: {value}")
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


def _set_top_level(text: str, field: str, value: str) -> str:
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith(f"{field}:"):
            lines[i] = f"{field}: {value}"
            break
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


if __name__ == "__main__":
    sys.exit(main())
