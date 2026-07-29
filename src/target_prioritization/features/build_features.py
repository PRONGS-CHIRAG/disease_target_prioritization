"""Feature-table assembly and the leakage guard.

The guard in this module is fully implemented; the feature computation around
it is not yet. That ordering is deliberate. Context.md §16 and §32.1 identify
label leakage as the central scientific risk of this project: a model trained
on the evidence that defines its own label reproduces the Open Targets score
and looks excellent while having learned nothing. That failure is silent — it
shows up as unusually good metrics, which is the last thing anyone
investigates.

So the guard is written first, tested first, and fails the build rather than
warning.
"""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from target_prioritization.config import FeaturesConfig, LeakageGuardConfig, load_features
from target_prioritization.utils.logging import get_logger

__all__ = [
    "LeakageError",
    "LeakageReport",
    "assert_no_leakage",
    "build_feature_table",
    "check_leakage",
    "select_feature_columns",
]

log = get_logger(__name__)

# Columns that identify a row rather than describe it. Excluded from the
# feature matrix but carried through for joins, grouping and display.
ID_COLUMNS = frozenset(
    {
        "disease_id",
        "disease_name",
        "target_id",
        "gene_symbol",
        "gene_name",
        "dataset_version",
        "extraction_date",
    }
)

LABEL_COLUMNS = frozenset({"label", "label_source", "max_clinical_stage"})


class LeakageError(RuntimeError):
    """A denylisted column reached the model matrix, or the guard went stale.

    Raised rather than warned: Context.md §16 treats leakage as a correctness
    failure, and a warning in a long pipeline log is functionally invisible.
    """


@dataclass(slots=True)
class LeakageReport:
    """Outcome of a leakage check."""

    violations: dict[str, list[str]]
    stale_rules: list[str]
    checked_columns: int

    @property
    def ok(self) -> bool:
        return not self.violations and not self.stale_rules

    def describe(self) -> str:
        lines: list[str] = []
        if self.violations:
            lines.append("Denylisted columns present in the feature matrix:")
            for rule_id, columns in sorted(self.violations.items()):
                lines.append(f"  [{rule_id}] {', '.join(sorted(columns))}")
        if self.stale_rules:
            lines.append(
                "Required denylist rules matched nothing — the guard may no longer "
                "protect what it was written for (an upstream rename is the usual "
                "cause):"
            )
            lines.extend(f"  [{rule_id}]" for rule_id in sorted(self.stale_rules))
        return "\n".join(lines)


def check_leakage(
    columns: list[str],
    guard: LeakageGuardConfig | None = None,
) -> LeakageReport:
    """Check *columns* against the denylist without raising.

    Two distinct failures are detected:

    1. **Violation** — a denylisted column is present. The direct problem.
    2. **Stale rule** — a rule marked ``required`` matched nothing. The
       indirect problem, and the more dangerous one: if Open Targets renames
       the ``chembl`` datasource, the rule protecting against it quietly stops
       applying and the pipeline keeps reporting a clean bill of health. A
       guard that cannot fail is not a guard.

    Args:
        columns: Column names destined for the model matrix.
        guard: Guard config. Defaults to ``configs/features.yaml``.
    """
    guard = guard or load_features().leakage_guard

    if not guard.enabled:
        log.warning(
            "leakage_guard_disabled",
            note="features.yaml sets leakage_guard.enabled=false; results are not trustworthy",
        )
        return LeakageReport(violations={}, stale_rules=[], checked_columns=len(columns))

    violations = guard.find_violations(columns)
    stale = [rule.id for rule in guard.unmatched_required_rules(columns)]

    return LeakageReport(
        violations=violations,
        stale_rules=stale,
        checked_columns=len(columns),
    )


def assert_no_leakage(
    columns: list[str],
    guard: LeakageGuardConfig | None = None,
) -> None:
    """Raise :class:`LeakageError` if the denylist is violated or stale.

    Call this at every boundary where a frame becomes model input — the end of
    feature assembly, and again immediately before ``fit``. Checking twice is
    cheap; a leaked label is not.

    Raises:
        LeakageError: On any violation or stale required rule.
    """
    report = check_leakage(columns, guard)

    if report.ok:
        log.info("leakage_guard_passed", columns=report.checked_columns)
        return

    raise LeakageError(
        "Leakage guard failed (see Context.md §16).\n"
        + report.describe()
        + "\n\nIf a column is genuinely safe, remove or narrow its rule in "
        "configs/features.yaml and record why in the commit message."
    )


def select_feature_columns(
    frame: pl.DataFrame,
    *,
    guard: LeakageGuardConfig | None = None,
    extra_exclude: set[str] | None = None,
) -> list[str]:
    """Return the model-input columns of *frame*, after checking for leakage.

    Identifier and label columns are excluded first, then the remainder is
    passed through :func:`assert_no_leakage`.
    """
    excluded = ID_COLUMNS | LABEL_COLUMNS | (extra_exclude or set())
    candidates = [c for c in frame.columns if c not in excluded]
    assert_no_leakage(candidates, guard)
    return candidates


# ---------------------------------------------------------------------------
# Feature assembly — not yet implemented
# ---------------------------------------------------------------------------


def build_feature_table(
    config: FeaturesConfig | None = None,
    *,
    disease_ids: list[str] | None = None,
) -> pl.DataFrame:
    """Assemble the disease-target feature table.

    One row per ``(disease_id, target_id)`` pair, per Context.md §14 and the
    schema in §27. Assembly order:

    1. Candidate generation — all targets Open Targets associates with each
       disease (Context.md §13).
    2. Pivot ``association_by_datasource_direct`` from long to wide, dropping
       denylisted datasources *before* the pivot so leaked columns are never
       even constructed.
    3. Join the per-group features from ``genetics``, ``expression``,
       ``pathways``, ``network`` and ``druggability``.
    4. Add ``missing__<group>`` indicators (Context.md §32.3 — a target can
       look weak merely because nobody has studied it).
    5. Add the evidence-diversity features (Context.md §14.9).
    6. Stamp ``dataset_version`` and ``extraction_date`` (§33).
    7. Call :func:`assert_no_leakage` before returning.

    Args:
        config: Feature config. Defaults to ``configs/features.yaml``.
        disease_ids: Restrict to these diseases. Defaults to every resolved
            disease in ``configs/diseases.yaml``.

    Returns:
        The feature table, written by the caller to
        ``data/processed/disease_target_features.parquet``.

    Raises:
        LeakageError: If the assembled table violates the denylist.
    """
    raise NotImplementedError(
        "Feature assembly is Milestone 1 work. The leakage guard above is "
        "implemented and tested; see docs/data_dictionary.md for the target schema."
    )
