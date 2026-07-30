"""Druggability and safety features (Context.md §14.6, §14.7).

Built from Open Targets ``target_prioritisation``.

The distinction that keeps these features legitimate: they describe whether a
target *can* be drugged — does it have a binding pocket, a known ligand, a
small-molecule binder — not whether a drug for this disease already exists. The
latter is the label. ``target_prioritisation.maxClinicalStage`` crosses that
line and is denylisted in ``configs/features.yaml``.

Safety is computed but **not scored**. Context.md §14.7 and §31.7 are explicit
that a druggable target may still be unsafe and that this data cannot settle it,
so safety columns ride along for display and are never summed into the
prioritization score.
"""

from __future__ import annotations

import re

import duckdb
import polars as pl

from target_prioritization.config import FeaturesConfig, load_features
from target_prioritization.data.open_targets import load_target_prioritisation
from target_prioritization.utils.logging import get_logger, log_dropped

__all__ = [
    "DRUGGABILITY_COLUMN",
    "PRIO_PREFIX",
    "build_druggability_features",
    "build_safety_features",
    "prio_column",
]

log = get_logger(__name__)

DRUGGABILITY_COLUMN = "dim__druggability"
PRIO_PREFIX = "prio__"


def prio_column(field: str) -> str:
    """Column name for a ``target_prioritisation`` field.

    Open Targets uses camelCase (``maxClinicalStage``); the pipeline uses
    ``prio__snake_case``. Renaming on load is not cosmetic — the leakage
    denylist globs over *column names*, so a raw camelCase column would slip
    past a rule written as ``prio__max_clinical_stage`` and reach the output
    unchallenged.

    >>> prio_column("maxClinicalStage")
    'prio__max_clinical_stage'
    >>> prio_column("hasPocket")
    'prio__has_pocket'
    """
    snake = re.sub(r"(?<!^)(?=[A-Z])", "_", field).lower()
    return f"{PRIO_PREFIX}{snake}"


def build_druggability_features(
    gene_ids: list[str],
    config: FeaturesConfig | None = None,
    con: duckdb.DuckDBPyConnection | None = None,
) -> pl.DataFrame:
    """Tractability score per target, in [0, 1].

    The score is the mean of the binary flags listed under
    ``druggability_flags`` in ``configs/features.yaml`` — restricted to the
    three with full coverage. Sparser flags (``hasTEP`` covers 41 targets,
    ``hasHighQualityChemicalProbes`` 929) are deliberately excluded from the
    score: at that coverage a flag encodes "has anyone looked at this" more
    than "is this druggable", and scoring it would reward attention again.

    Targets absent from ``target_prioritisation`` — non-coding genes, mostly —
    get a null rather than a zero, and the count is logged (Context.md §34).

    Returns:
        ``target_id``, ``dim__druggability``, ``missing__druggability`` and the
        raw flags, prefixed ``prio__`` for display.
    """
    config = config or load_features()
    flags = config.druggability_flags

    if not flags:
        raise ValueError("configs/features.yaml declares no druggability_flags")

    prioritisation = load_target_prioritisation(flags, gene_ids, con)

    scored = prioritisation.with_columns(
        pl.mean_horizontal([pl.col(f).cast(pl.Float64) for f in flags]).alias(DRUGGABILITY_COLUMN)
    ).rename({flag: prio_column(flag) for flag in flags})

    log_dropped(
        log,
        stage="druggability_coverage",
        reason="target absent from target_prioritisation (typically non-coding)",
        count=len(gene_ids) - scored.height,
        total=len(gene_ids),
    )

    return scored.with_columns(
        pl.col(DRUGGABILITY_COLUMN).is_null().cast(pl.Int8).alias("missing__druggability")
    )


def build_safety_features(
    gene_ids: list[str],
    config: FeaturesConfig | None = None,
    con: duckdb.DuckDBPyConnection | None = None,
) -> pl.DataFrame:
    """Safety-related columns per target, for display only.

    These are **not** combined into a score and **not** inverted into a
    penalty. Context.md §14.7: safety evidence must not be presented as a
    toxicity prediction, and §17.1's baseline formula has no safety term.

    Note the scale — these are signed, not probabilities. ``hasSafetyEvent`` is
    -1 or null and never +1; ``geneticConstraint`` and ``mouseKOScore`` run
    roughly [-1, 1] with negative meaning a liability. A caller that treats them
    as [0, 1] will draw the conclusion backwards.

    Returns:
        ``target_id`` plus the columns listed under ``safety_columns``, and
        ``safety__n_flags`` counting how many are present (not how bad they are).
    """
    config = config or load_features()
    columns = config.safety_columns

    if not columns:
        raise ValueError("configs/features.yaml declares no safety_columns")

    safety = load_target_prioritisation(columns, gene_ids, con)

    return safety.with_columns(
        pl.sum_horizontal([pl.col(c).is_not_null().cast(pl.Int8) for c in columns]).alias(
            "safety__n_flags"
        )
    ).rename({column: prio_column(column) for column in columns})
