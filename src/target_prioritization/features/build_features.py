"""Feature-table assembly and the leakage guard.

The guard was written first and tested first, before any feature computation
existed — deliberately. Context.md §16 and §32.1 identify label leakage as
the central scientific risk of this project: a model trained on the evidence
that defines its own label reproduces the Open Targets score and looks
excellent while having learned nothing. That failure is silent — it shows up
as unusually good metrics, which is the last thing anyone investigates.

:func:`build_disease_features` (Milestone 1, Context.md §36) builds one
disease's table; :func:`build_feature_table` (Milestone 2, §37) calls it once
per disease and concatenates the results.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import duckdb
import polars as pl

from target_prioritization.config import (
    DiseaseSpec,
    FeaturesConfig,
    LeakageGuardConfig,
    load_diseases,
    load_features,
)
from target_prioritization.data import open_targets
from target_prioritization.features.druggability import (
    build_druggability_features,
    build_safety_features,
)
from target_prioritization.features.genetics import (
    build_dimension_scores,
    build_evidence_diversity,
)
from target_prioritization.utils.logging import get_logger, log_dropped

__all__ = [
    "LeakageError",
    "LeakageReport",
    "assert_no_leakage",
    "build_disease_features",
    "build_feature_table",
    "check_leakage",
    "drop_denylisted_datasources",
    "select_feature_columns",
    "verify_guard_liveness",
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

# Descriptive columns carried for display that are not model input. Everything
# NOT in this set is treated as a feature candidate and checked against the
# denylist — an allowlist of non-features is safe to get wrong (a stray entry
# only means an extra column gets checked), whereas an allowlist of feature
# prefixes fails open.
_NON_FEATURE_COLUMNS = ID_COLUMNS | LABEL_COLUMNS | frozenset({"biotype"})


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
    *,
    check_stale: bool = True,
) -> None:
    """Raise :class:`LeakageError` if the denylist is violated or stale.

    Call this at every boundary where a frame becomes model input — the end of
    feature assembly, and again immediately before ``fit``. Checking twice is
    cheap; a leaked label is not.

    Args:
        columns: Column names destined for the model matrix.
        guard: Guard config. Defaults to ``configs/features.yaml``.
        check_stale: Also fail when a ``required`` rule matches nothing.
            Set False when the denylisted source data was already removed
            upstream — a pipeline that correctly drops a datasource before the
            pivot would otherwise be reported as having a stale rule, since the
            column it guards can no longer appear. In that case verify
            liveness separately with :func:`verify_guard_liveness`, which asks
            the question the right way round: does the thing this rule guards
            against still exist *in the source*?

    Raises:
        LeakageError: On any violation, or on a stale required rule when
            *check_stale* is set.
    """
    report = check_leakage(columns, guard)
    stale = report.stale_rules if check_stale else []

    if not report.violations and not stale:
        log.info("leakage_guard_passed", columns=report.checked_columns, stale_checked=check_stale)
        return

    detail = LeakageReport(
        violations=report.violations, stale_rules=stale, checked_columns=report.checked_columns
    )
    raise LeakageError(
        "Leakage guard failed (see Context.md §16).\n"
        + detail.describe()
        + "\n\nIf a column is genuinely safe, remove or narrow its rule in "
        "configs/features.yaml and record why in the commit message."
    )


def verify_guard_liveness(
    potential_columns: list[str],
    guard: LeakageGuardConfig | None = None,
) -> None:
    """Confirm every ``required`` denylist rule still guards something real.

    This is the staleness check asked the right way round. Rather than
    inspecting the final matrix — from which correctly-filtered columns are
    absent by design — it inspects the columns the pipeline's *sources could
    produce*. A required rule matching nothing there means the thing it was
    written to block no longer exists upstream, which is how a guard silently
    stops guarding (an upstream rename is the usual cause: releases before
    26.06 called ``clinical_precedence`` ``chembl``).

    Args:
        potential_columns: Every column name the source tables could yield,
            whether or not it survives filtering.

    Raises:
        LeakageError: If a required rule matches nothing in *potential_columns*.
    """
    guard = guard or load_features().leakage_guard
    if not guard.enabled:
        return

    if stale := guard.unmatched_required_rules(potential_columns):
        raise LeakageError(
            "Leakage guard is stale (see Context.md §16).\n"
            f"Required rule(s) {[r.id for r in stale]} match nothing that the current "
            "sources can produce, so they no longer protect anything. An upstream "
            "rename is the usual cause.\n"
            "Update the `match` pattern in configs/features.yaml to the new name, or "
            "flip the rule to required: false if the evidence genuinely no longer exists."
        )
    log.info(
        "leakage_guard_live",
        required_rules=[r.id for r in guard.denylist if r.required],
        potential_columns=len(potential_columns),
    )


def select_feature_columns(
    frame: pl.DataFrame,
    *,
    guard: LeakageGuardConfig | None = None,
    extra_exclude: set[str] | None = None,
    check_stale: bool = True,
) -> list[str]:
    """Return the model-input columns of *frame*, after checking for leakage.

    Identifier and label columns are excluded first, then the remainder is
    passed through :func:`assert_no_leakage`.

    Uses :data:`_NON_FEATURE_COLUMNS` — the same exclusion set
    ``build_disease_features``'s own final check uses — rather than a second,
    separately-maintained list. Two definitions of "not a feature" is exactly
    how ``biotype`` (a string column, present but uncounted here until this
    was unified) would have reached a model's ``.fit()`` and failed there
    instead of at column-selection time, where the failure is legible.

    Args:
        check_stale: Also fail when a ``required`` denylist rule matches
            nothing (the default — appropriate when *frame* has not yet had
            its denylisted source columns removed). Set False when calling
            this on a frame built by :func:`build_disease_features` or
            :func:`build_feature_table`, which already dropped the
            denylisted datasource before this point — the same "Flaw 1"
            those functions document: a required rule correctly finding
            nothing in an already-filtered frame is not staleness, and
            :func:`verify_guard_liveness` is what actually keeps that check
            honest, against the *unfiltered* source columns.
    """
    excluded = _NON_FEATURE_COLUMNS | (extra_exclude or set())
    candidates = [c for c in frame.columns if c not in excluded]
    assert_no_leakage(candidates, guard, check_stale=check_stale)
    return candidates


# ---------------------------------------------------------------------------
# Multi-disease assembly (Context.md §37)
# ---------------------------------------------------------------------------

# Deterministic column order for the written parquet: identifiers first, then
# every feature column alphabetically. Context.md §33 requires reproducible
# output, and `pl.concat(..., how="diagonal")` orders columns by the order
# frames introduce them — which depends on which disease happened to be built
# first, not on anything meaningful.
_ID_COLUMN_ORDER = [
    "disease_id",
    "disease_name",
    "target_id",
    "gene_symbol",
    "gene_name",
    "biotype",
    "dataset_version",
    "extraction_date",
]


def _sparse_columns_by_disease(
    combined: pl.DataFrame, feature_columns: list[str]
) -> dict[str, list[str]]:
    """Feature columns that are entirely null within a single disease.

    Not acted on here — dropping a zero-variance column is a per-fold
    decision made at evaluation/training time (a column all-null in a
    training fold is untrainable; all-null in a test fold is unusable), since
    which fold is "training" changes under leave-one-disease-out. Logged now
    so the sparsity is visible at build time rather than discovered as a
    training-time surprise: `crispr_screen`-derived columns, for instance,
    are populated for only 3 of the 10 configured diseases.
    """
    sparse: dict[str, list[str]] = {}
    for row in combined.group_by("disease_id").agg(
        [pl.col(c).null_count().eq(pl.len()).alias(c) for c in feature_columns]
    ).iter_rows(named=True):
        disease_id = row.pop("disease_id")
        all_null = [c for c, is_all_null in row.items() if is_all_null]
        if all_null:
            sparse[disease_id] = sorted(all_null)
    return sparse


def build_feature_table(
    diseases: list[DiseaseSpec] | None = None,
    config: FeaturesConfig | None = None,
    *,
    saturation: int = 4,
    con: duckdb.DuckDBPyConnection | None = None,
) -> tuple[pl.DataFrame, dict[str, Any]]:
    """Assemble the disease-target feature table across every configured disease.

    One row per ``(disease_id, target_id)`` pair (Context.md §14, §37). Calls
    :func:`build_disease_features` once per disease — the Milestone 1 path,
    unmodified — and concatenates the results.

    Open Targets datasource coverage varies by disease (`crispr_screen`
    covers 3 of 10, `gene2phenotype` 1 of 10), so each disease's
    :func:`~target_prioritization.data.open_targets.pivot_evidence` produces a
    different column set. Concatenation therefore uses
    ``how="diagonal"``: a datasource absent for a disease becomes null for
    every row of that disease, which is the correct reading under Context.md
    §32.3 — null means "not studied for this disease", not "studied and
    found zero".

    Args:
        diseases: Diseases to include. Defaults to every resolved disease in
            ``configs/diseases.yaml``.
        config: Feature config. Defaults to ``configs/features.yaml``.
        saturation: Evidence-type count at which the diversity term
            saturates; forwarded to :func:`build_disease_features`.

    Returns:
        ``(features, provenance)``. *features* has identifier columns first
        (:data:`_ID_COLUMN_ORDER`), then every feature column in
        alphabetical order — deterministic regardless of disease build
        order, so the written parquet hashes identically across runs
        (Context.md §33) once the run-varying ``extraction_date`` is
        excluded from the comparison. *provenance* carries per-disease detail
        from :func:`build_disease_features` plus the cross-disease sparsity
        map.

    Raises:
        LeakageError: If the assembled table violates the denylist.
    """
    config = config or load_features()
    diseases = diseases if diseases is not None else load_diseases().resolved

    if not diseases:
        raise ValueError("No diseases to build features for")

    owns = con is None
    con = con or open_targets.connect()
    try:
        frames: list[pl.DataFrame] = []
        per_disease: dict[str, dict[str, Any]] = {}
        for disease in diseases:
            features, prov = build_disease_features(
                disease,
                config=config,
                saturation=saturation,
                include_raw_datasource_scores=True,
                con=con,
            )
            frames.append(features)
            per_disease[disease.key] = prov
            log.info(
                "disease_features_added_to_table",
                disease=disease.key,
                rows=features.height,
                columns=features.width,
            )

        combined = pl.concat(frames, how="diagonal")

        id_columns = [c for c in _ID_COLUMN_ORDER if c in combined.columns]
        feature_columns = sorted(c for c in combined.columns if c not in id_columns)
        combined = combined.select([*id_columns, *feature_columns])

        sparse_by_disease = _sparse_columns_by_disease(combined, feature_columns)
        for disease_id, columns in sparse_by_disease.items():
            log.info(
                "disease_has_all_null_feature_columns",
                disease_id=disease_id,
                n_columns=len(columns),
                columns=columns,
                note=(
                    "datasource(s) not present for this disease at all; "
                    "handled per-fold at evaluation/training time, not here"
                ),
            )

        # A second check on the assembled multi-disease frame, in addition to
        # the one build_disease_features already runs per disease inside the
        # loop above — cheap, and a diagonal concat is exactly the kind of
        # operation that could in principle introduce a column no per-disease
        # check ever saw.
        assert_no_leakage(
            [c for c in combined.columns if c not in _NON_FEATURE_COLUMNS],
            config.leakage_guard,
            check_stale=False,
        )

        provenance = {
            "diseases": per_disease,
            "n_diseases": len(diseases),
            "n_total_rows": combined.height,
            "n_feature_columns": len(feature_columns),
            "sparse_columns_by_disease": sparse_by_disease,
        }
        log.info(
            "feature_table_built",
            n_diseases=len(diseases),
            rows=combined.height,
            columns=combined.width,
        )
        return combined, provenance
    finally:
        if owns:
            con.close()


def drop_denylisted_datasources(
    evidence: pl.DataFrame,
    guard: LeakageGuardConfig | None = None,
) -> tuple[pl.DataFrame, list[str]]:
    """Remove denylisted datasources from long-format evidence.

    Applied **before** the pivot, so leaked columns are never constructed in
    the first place. Dropping them after the fact would work too, but leaves a
    window in which a leaking column exists and could be picked up by anything
    that inspects the frame's schema.

    Returns:
        ``(filtered_evidence, dropped_datasources)``.
    """
    guard = guard or load_features().leakage_guard

    datasources = evidence.get_column("datasource").unique().to_list()
    # Map each datasource to the column name it would produce, then ask the
    # guard about that name — the denylist globs over column names, not raw
    # datasource IDs.
    blocked = [
        datasource
        for datasource in datasources
        if guard.find_violations([f"assoc_ds__{datasource}_score"])
    ]

    if not blocked:
        return evidence, []

    before_rows = evidence.height
    before_targets = evidence.get_column("target_id").n_unique()
    filtered = evidence.filter(~pl.col("datasource").is_in(blocked))
    lost_targets = before_targets - filtered.get_column("target_id").n_unique()

    log.info(
        "denylisted_datasources_dropped",
        datasources=sorted(blocked),
        rows_dropped=before_rows - filtered.height,
        reason="these encode the training label (Context.md §16)",
    )

    if lost_targets:
        # Targets whose ONLY evidence was the label now have no features at
        # all, so they leave the candidate set. Correct, but it changes the row
        # count and must be visible rather than inferred (Context.md §34).
        log_dropped(
            log,
            stage="candidates_lost_to_denylist",
            reason=(
                "target had no evidence other than the denylisted label datasource, "
                "so it has no features to score"
            ),
            count=lost_targets,
            total=before_targets,
        )

    return filtered, sorted(blocked)


def _potential_column_universe(
    evidence: pl.DataFrame,
    con: duckdb.DuckDBPyConnection,
) -> list[str]:
    """Every column name this pipeline's sources could produce.

    Used by :func:`verify_guard_liveness`. Deliberately includes columns the
    pipeline never actually builds — every ``target_prioritisation`` field, for
    instance — because the question being asked is "does the evidence this rule
    blocks still exist upstream?", not "did we build it?".
    """
    columns = [
        f"assoc_ds__{datasource}_{suffix}"
        for datasource in evidence.get_column("datasource").unique().to_list()
        for suffix in ("score", "evidence_count")
    ]

    glob = open_targets.dataset_glob("target_prioritisation")
    prio_columns = [
        row[0] for row in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{glob}')").fetchall()
    ]
    # camelCase -> snake_case, matching the prio__ naming used by the denylist.
    columns += [f"prio__{re.sub(r'(?<!^)(?=[A-Z])', '_', name).lower()}" for name in prio_columns]
    columns.append("assoc_overall__score")
    return columns


def build_disease_features(
    disease: DiseaseSpec,
    *,
    config: FeaturesConfig | None = None,
    saturation: int = 4,
    include_raw_datasource_scores: bool = False,
    con: duckdb.DuckDBPyConnection | None = None,
) -> tuple[pl.DataFrame, dict[str, Any]]:
    """Build the Milestone 1 feature table for a single disease (Context.md §36).

    Open Targets only. Assembly order:

    1. Candidate generation — every target Open Targets associates with the
       disease (Context.md §13).
    2. Drop denylisted datasources from the long evidence frame.
    3. Collapse the remainder into scored dimensions (max within dimension).
    4. Add the evidence-diversity term (Context.md §14.9).
    5. Join druggability and safety from ``target_prioritisation``.
    6. Join gene symbols and names.
    7. Stamp ``dataset_version`` and ``extraction_date`` (Context.md §33).
    8. Assert no leakage before returning.

    Args:
        disease: The disease to build for; must have a resolved ``efo_id``.
        saturation: Evidence-type count at which the diversity term saturates.
        include_raw_datasource_scores: Also join the per-datasource
            ``assoc_ds__<name>_score`` / ``_evidence_count`` columns from
            :func:`~target_prioritization.data.open_targets.pivot_evidence`,
            in addition to the five ``dim__`` aggregates. Off by default so
            Milestone 1's documented column count (milestone1.md §4: "18
            columns") stays exactly reproducible; Milestone 2
            (:func:`build_feature_table`) turns it on, since SHAP needs
            individually interpretable columns rather than pre-aggregated
            dimensions. Safe either way — the columns come from *evidence*
            AFTER the denylist drop, same as the dimensions do.

    Returns:
        ``(features, provenance)``. *provenance* records what was dropped and
        which datasources were used, for the report.

    Raises:
        ValueError: If *disease* has no resolved identifier.
        LeakageError: If a denylisted column survives into the table.
    """
    config = config or load_features()

    if not disease.efo_id:
        raise ValueError(
            f"Disease {disease.key!r} has no resolved efo_id. "
            "Run: python scripts/resolve_diseases.py"
        )

    owns = con is None
    con = con or open_targets.connect()
    try:
        evidence = open_targets.load_targets_for_disease(disease.efo_id, con)
        n_candidates = evidence.get_column("target_id").n_unique()
        log.info(
            "candidates_loaded",
            disease=disease.key,
            disease_id=disease.efo_id,
            candidates=n_candidates,
            evidence_rows=evidence.height,
        )

        if evidence.is_empty():
            raise ValueError(
                f"No Open Targets evidence for {disease.key!r} ({disease.efo_id}). "
                "Check the identifier resolved against the pinned release."
            )

        # Ask the staleness question against what the sources COULD produce,
        # before anything is filtered out. Doing it after the drop would report
        # a correctly-working guard as stale.
        verify_guard_liveness(_potential_column_universe(evidence, con), config.leakage_guard)

        evidence, dropped_datasources = drop_denylisted_datasources(evidence, config.leakage_guard)

        dimensions = build_dimension_scores(evidence, config)
        diversity = build_evidence_diversity(evidence, saturation)

        target_ids = dimensions.get_column("target_id").to_list()
        druggability = build_druggability_features(target_ids, config, con)
        safety = build_safety_features(target_ids, config, con)
        metadata = open_targets.load_target_metadata(target_ids, con)

        features = dimensions.join(diversity, on="target_id", how="left")

        if include_raw_datasource_scores:
            # Built from `evidence` AFTER drop_denylisted_datasources, same
            # source the dimensions above are built from — the denylisted
            # datasource cannot reach this pivot either.
            raw_scores = open_targets.pivot_evidence(evidence)
            features = features.join(raw_scores, on="target_id", how="left")

        features = (
            features.join(druggability, on="target_id", how="left")
            .join(safety, on="target_id", how="left")
            .join(metadata, on="target_id", how="left")
            .with_columns(
                pl.lit(disease.efo_id).alias("disease_id"),
                pl.lit(disease.name).alias("disease_name"),
                pl.lit(open_targets.release_tag()).alias("dataset_version"),
                pl.lit(datetime.now(UTC).date().isoformat()).alias("extraction_date"),
            )
        )

        # Symbols come from the same release, so a miss means a genuine
        # inconsistency rather than a version mismatch. Report, never drop (§34).
        unresolved = features.filter(pl.col("gene_symbol").is_null())
        log_dropped(
            log,
            stage="target_symbol_lookup",
            reason="target_id absent from the Open Targets target table",
            count=unresolved.height,
            total=features.height,
            examples=unresolved.get_column("target_id").head(5).to_list(),
        )

        # Check EVERY non-identifier column, not a prefix whitelist. A
        # whitelist only guards names someone remembered to anticipate: an
        # earlier version filtered on ("assoc_ds__", "dim__", "prio__") and let
        # a raw camelCase `maxClinicalStage` through untouched while logging
        # "leakage_guard_passed".
        #
        # Violations only: liveness was verified above against the unfiltered
        # source universe, and the denylisted columns are gone by design.
        assert_no_leakage(
            [c for c in features.columns if c not in _NON_FEATURE_COLUMNS],
            config.leakage_guard,
            check_stale=False,
        )

        provenance = {
            "disease_key": disease.key,
            "disease_id": disease.efo_id,
            "disease_name": disease.name,
            "dataset_version": open_targets.release_tag(),
            "extraction_date": datetime.now(UTC).date().isoformat(),
            "n_candidates": n_candidates,
            "n_scored": features.height,
            "n_dropped_label_only": n_candidates - features.height,
            "datasources_dropped_as_label": dropped_datasources,
            "scored_dimensions": list(config.scored_dimensions),
            "evidence_diversity_saturation": saturation,
            "n_unresolved_symbols": unresolved.height,
        }
        return features, provenance
    finally:
        if owns:
            con.close()
