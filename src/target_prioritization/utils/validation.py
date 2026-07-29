"""Schema validation at pipeline boundaries (Context.md §34).

Context.md §34 requires schemas to be validated where data crosses between
stages. The failure this prevents is the quiet one: a renamed upstream column
becomes an all-null feature, the model trains happily, and the metric drop is
attributed to the model.
"""

from __future__ import annotations

import polars as pl

__all__ = ["SchemaError", "require_columns", "require_no_nulls", "require_unique_key"]


class SchemaError(ValueError):
    """A frame did not match its expected schema."""


def require_columns(frame: pl.DataFrame, columns: list[str], *, context: str = "") -> None:
    """Raise if any of *columns* is absent.

    Raises:
        SchemaError: naming every missing column, not just the first.
    """
    if missing := [c for c in columns if c not in frame.columns]:
        where = f" in {context}" if context else ""
        raise SchemaError(f"Missing column(s){where}: {missing}. Present: {sorted(frame.columns)}")


def require_unique_key(frame: pl.DataFrame, key: list[str], *, context: str = "") -> None:
    """Raise if *key* is not unique.

    A duplicated (disease_id, target_id) silently multiplies rows on the next
    join and skews every aggregate downstream.
    """
    require_columns(frame, key, context=context)
    n_dupes = frame.height - frame.select(key).unique().height
    if n_dupes:
        where = f" in {context}" if context else ""
        examples = frame.group_by(key).len().filter(pl.col("len") > 1).head(3).to_dicts()
        raise SchemaError(f"{n_dupes} duplicate key row(s){where} on {key}. Examples: {examples}")


def require_no_nulls(frame: pl.DataFrame, columns: list[str], *, context: str = "") -> None:
    """Raise if any of *columns* contains nulls."""
    require_columns(frame, columns, context=context)
    counts = {c: frame.get_column(c).null_count() for c in columns}
    if bad := {c: n for c, n in counts.items() if n}:
        where = f" in {context}" if context else ""
        raise SchemaError(f"Unexpected nulls{where}: {bad}")
