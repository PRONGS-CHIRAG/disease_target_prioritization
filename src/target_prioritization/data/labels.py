"""Multi-disease label construction (Context.md §15, §37).

Built from ``clinical_target``: a target is a positive for a disease when a
drug reached at least ``positive_min_clinical_stage`` in a trial for that
disease (or, with ``label.expand_to_descendants``, for an ontology descendant
of it — a phase-3 drug for HER2-positive breast carcinoma counts as evidence
for breast carcinoma).

Three decisions, each made by measuring release 26.06 rather than by
assumption. Full numbers in milestone2.md §2.

**Descendants are expanded by default.** ``clinical_target.diseases`` often
names a child ontology term. Effect ranges from +0 (most diseases) to +263
in the raw ontology-driven count (breast carcinoma, 98 -> 361 before
restricting to the candidate set). Both counts are recorded in provenance so
the swing is visible, not buried.

**UNKNOWN stage is excluded from both classes**, never coerced to negative —
``label`` is left null and ``label_reason`` records why. Coercing it would
silently invent a fact release 26.06 does not assert.

**Targets whose only Open Targets evidence is the denylisted
``clinical_precedence`` datasource are dropped before labelling.** They have
no features to rank on (Context.md §16); keeping them would inflate recall
denominators with rows no model can place. The loss is not uniform — up to
50% of positives for the data-poorest diseases — so per-disease counts are
mandatory in provenance, not optional (Context.md §34).

A related, subtler gap: candidate generation queries only a disease's OWN
Open Targets id, but the label (with descendants expanded) does not. A target
can be a family positive while never appearing in the disease's own candidate
set at all — 18 targets release-wide. These are detected and logged rather
than silently vanishing; see :func:`build_labels_for_disease`.

Any ``maxClinicalStage`` value absent from ``configs/features.yaml``'s
``clinical_stage_map`` raises rather than silently falling through to a
default: an unmapped value is exactly the kind of thing that should stop the
build, per Context.md §34.

The core logic (:func:`build_labels_for_disease`) takes evidence and the
disease family as plain arguments rather than reading them itself, so it can
be unit-tested against synthetic frames without touching the downloaded
release. :func:`build_labels` is the thin I/O wrapper used in practice.
"""

from __future__ import annotations

from typing import Any

import duckdb
import polars as pl

from target_prioritization.config import DiseaseSpec, FeaturesConfig, LabelConfig, load_features
from target_prioritization.data import open_targets
from target_prioritization.features.build_features import drop_denylisted_datasources
from target_prioritization.utils.logging import get_logger, log_dropped

__all__ = [
    "LABEL_COLUMNS",
    "REASON_EARLY_STAGE",
    "REASON_NO_CLINICAL_EVIDENCE",
    "REASON_UNKNOWN_STAGE",
    "LabelError",
    "build_labels",
    "build_labels_for_disease",
    "disease_family",
    "load_clinical_target",
]

log = get_logger(__name__)

LABEL_COLUMNS = [
    "disease_id",
    "target_id",
    "label",
    "label_source",
    "max_clinical_stage",
    "label_reason",
]

REASON_NO_CLINICAL_EVIDENCE = "negative_no_clinical_evidence"
REASON_EARLY_STAGE = "negative_early_stage"
REASON_UNKNOWN_STAGE = "excluded_unknown_stage"


class LabelError(RuntimeError):
    """The label table could not be built as configured."""


def _positive_reason(threshold: int) -> str:
    return f"positive_stage_ge_{threshold}"


def disease_family(disease_id: str, con: duckdb.DuckDBPyConnection) -> list[str]:
    """*disease_id* plus every ontology descendant, or just itself if none.

    Open Targets precomputes the full descendant closure (not just direct
    children) in ``disease.descendants``, so no graph traversal is needed
    here.

    Raises:
        LabelError: If *disease_id* is not in the disease table at all —
            distinct from having zero descendants, which is normal.
    """
    glob = open_targets.dataset_glob("disease")
    row = con.execute(
        f"SELECT descendants FROM read_parquet('{glob}') WHERE id = ?", [disease_id]
    ).fetchone()
    if row is None:
        raise LabelError(f"Disease {disease_id!r} not found in the Open Targets disease table")
    descendants = row[0] or []
    return [disease_id, *descendants]


def load_clinical_target(con: duckdb.DuckDBPyConnection) -> pl.DataFrame:
    """Long frame: one row per (target, directly-named disease) pair.

    ``clinical_target`` carries one row per (drug, target) with a *list* of
    diseases that drug's trials covered; this unnests it so the family
    membership check downstream is a plain ``is_in``.

    Returns:
        ``target_id``, ``disease_id_direct``, ``max_clinical_stage``.
    """
    glob = open_targets.dataset_glob("clinical_target")
    query = f"""
        SELECT targetId AS target_id,
               unnest(diseases).diseaseId AS disease_id_direct,
               maxClinicalStage AS max_clinical_stage
        FROM read_parquet('{glob}')
    """
    frame = pl.from_arrow(con.execute(query).arrow())
    assert isinstance(frame, pl.DataFrame)
    return frame


def _validate_stage_map(stages_in_release: list[str], label: LabelConfig) -> None:
    """Fail loudly rather than silently dropping an unrecognised stage value.

    Checked against every stage value in the *release*, not only the ones
    touching the configured diseases — a value could be irrelevant today and
    still matter the moment an eleventh disease is added.
    """
    unmapped = sorted(set(stages_in_release) - set(label.clinical_stage_map))
    if unmapped:
        raise LabelError(
            f"clinical_target.maxClinicalStage has value(s) {unmapped} not present in "
            "configs/features.yaml label.clinical_stage_map. Add them explicitly — "
            "Context.md §34 forbids silently coercing an unrecognised value."
        )


def build_labels_for_disease(
    disease: DiseaseSpec,
    evidence: pl.DataFrame,
    clinical: pl.DataFrame,
    family: list[str],
    config: FeaturesConfig | None = None,
) -> tuple[pl.DataFrame, dict[str, Any]]:
    """Build labels for one disease from already-loaded frames.

    Pure function — no I/O — so it can be exercised with synthetic evidence
    and clinical frames in tests. :func:`build_labels` is the wrapper that
    loads the real release and calls this once per disease.

    Args:
        disease: Disease to label; must have a resolved ``efo_id``.
        evidence: Long-format Open Targets association evidence for
            *disease*'s own id ONLY (i.e. the output of
            :func:`target_prioritization.data.open_targets.load_targets_for_disease`
            for ``disease.efo_id``), including the denylisted datasource —
            this defines the candidate universe before any drop.
        clinical: Output of :func:`load_clinical_target`, filtered or not —
            this function filters to *family* itself.
        family: ``[disease.efo_id, *descendants]`` if descendants are being
            expanded, else just ``[disease.efo_id]``. Passed in rather than
            computed here so the caller controls the ontology lookup.
        config: Feature config (carries ``label`` and ``leakage_guard``).
            Defaults to ``configs/features.yaml``.

    Returns:
        ``(labels, provenance)``. *labels* has one row per candidate target
        that survives the clinical-only drop, with columns
        :data:`LABEL_COLUMNS`. Targets whose only evidence is the denylisted
        label datasource, or whose only positive evidence is a descendant
        disease outside *disease*'s own candidate set, are absent entirely —
        counted in provenance, never silently dropped (Context.md §34).

    Raises:
        ValueError: If *disease* has no resolved ``efo_id``.
    """
    config = config or load_features()
    label_config = config.label

    if not disease.efo_id:
        raise ValueError(f"Disease {disease.key!r} has no resolved efo_id.")

    full_candidates = set(evidence.get_column("target_id").unique().to_list())

    filtered_evidence, _dropped_datasources = drop_denylisted_datasources(
        evidence, config.leakage_guard
    )
    scored_candidates = set(filtered_evidence.get_column("target_id").unique().to_list())
    clinical_only = full_candidates - scored_candidates

    log_dropped(
        log,
        stage="labels_clinical_only_candidates",
        reason=(
            "target's only Open Targets evidence for this disease is the denylisted "
            "clinical_precedence datasource, so it has no features to rank on"
        ),
        count=len(clinical_only),
        total=len(full_candidates),
        examples=sorted(clinical_only)[:5],
    )

    threshold = label_config.positive_min_clinical_stage
    positive_reason = _positive_reason(threshold)
    stage_map: dict[str, int | None] = label_config.clinical_stage_map

    disease_clinical = clinical.filter(pl.col("disease_id_direct").is_in(family)).with_columns(
        pl.col("max_clinical_stage")
        .replace_strict(stage_map, return_dtype=pl.Int64)
        .alias("stage_value")
    )

    per_target = disease_clinical.group_by("target_id").agg(
        pl.col("stage_value").max().alias("stage_value"),
        pl.len().alias("n_clinical_rows"),
    )

    # Candidate generation (the `evidence` argument) queries only the
    # disease's OWN id — it is not expanded to the family, unlike the label.
    # A target can therefore be a family positive (a phase-3 drug for a
    # DESCENDANT disease) while Open Targets' association table never links
    # it to the parent disease under any datasource at all, not even the
    # denylisted one. Such a target would otherwise vanish silently: it is
    # absent from scored_frame below, so it never reaches `labels`. Measured
    # on release 26.06 this is small (18 targets total across all ten
    # diseases, up to 11 for breast carcinoma) but real, and Context.md §34
    # requires it be visible rather than inferred.
    family_positive = set(
        per_target.filter(pl.col("stage_value") >= threshold).get_column("target_id").to_list()
    )
    outside_own_candidates = sorted(family_positive - full_candidates)
    # The other way a family positive can fail to become a labelled row: it
    # IS in the disease's own candidate universe, but its only evidence there
    # is the denylisted datasource, so drop_denylisted_datasources already
    # removed it from scored_candidates above. Tracked separately from
    # outside_own_candidates so the two provenance counts plus n_positive
    # reconcile exactly against n_family_positive (Context.md §34).
    dropped_clinical_only_positives = sorted(family_positive & clinical_only)
    log_dropped(
        log,
        stage="labels_family_positive_outside_own_candidate_set",
        reason=(
            "target has clinically-advanced drug evidence for a descendant of this "
            "disease, but Open Targets' association table does not link it to the "
            "disease's own id under any datasource — outside the candidate set "
            "entirely, so outside the evaluation"
        ),
        count=len(outside_own_candidates),
        total=len(family_positive),
        examples=outside_own_candidates[:5],
    )

    # Labelling sensitivity check (milestone2.md §2): positives under
    # direct-ID-only matching instead of descendant expansion, restricted to
    # the SAME scored_candidates population as n_positive below. Comparing
    # populations of different sizes would make descendant expansion look
    # like it loses positives rather than gains them — direct-only computed
    # over the unrestricted `clinical` frame very nearly equals the raw
    # family-positive count, so the two numbers would differ mostly by
    # population size, not by what expansion actually changed.
    direct_clinical = clinical.filter(pl.col("disease_id_direct") == disease.efo_id).with_columns(
        pl.col("max_clinical_stage")
        .replace_strict(stage_map, return_dtype=pl.Int64)
        .alias("stage_value")
    )
    n_positive_direct_only = (
        direct_clinical.group_by("target_id")
        .agg(pl.col("stage_value").max().alias("stage_value"))
        .filter(
            (pl.col("stage_value") >= threshold) & (pl.col("target_id").is_in(scored_candidates))
        )
        .height
    )

    scored_frame = pl.DataFrame({"target_id": sorted(scored_candidates)})
    joined = scored_frame.join(per_target, on="target_id", how="left")

    labelled = joined.with_columns(
        pl.when(pl.col("n_clinical_rows").is_null())
        .then(pl.lit(REASON_NO_CLINICAL_EVIDENCE))
        .when(pl.col("stage_value").is_null())
        .then(pl.lit(REASON_UNKNOWN_STAGE))
        .when(pl.col("stage_value") >= threshold)
        .then(pl.lit(positive_reason))
        .otherwise(pl.lit(REASON_EARLY_STAGE))
        .alias("label_reason")
    ).with_columns(
        pl.when(pl.col("label_reason") == positive_reason)
        .then(1)
        .when(pl.col("label_reason") == REASON_UNKNOWN_STAGE)
        .then(None)
        .otherwise(0)
        .cast(pl.Int8)
        .alias("label"),
        pl.lit(label_config.source).alias("label_source"),
        pl.lit(disease.efo_id).alias("disease_id"),
    ).rename({"stage_value": "max_clinical_stage"})

    labels = labelled.select(LABEL_COLUMNS)

    n_positive = int(labels.filter(pl.col("label") == 1).height)
    n_negative = int(labels.filter(pl.col("label") == 0).height)
    n_excluded_unknown = int(labels.filter(pl.col("label_reason") == REASON_UNKNOWN_STAGE).height)

    log.info(
        "labels_built",
        disease=disease.key,
        disease_id=disease.efo_id,
        family_size=len(family),
        n_positive=n_positive,
        n_negative=n_negative,
        n_excluded_unknown_stage=n_excluded_unknown,
        n_positive_direct_only=n_positive_direct_only,
    )

    provenance = {
        "disease_key": disease.key,
        "disease_id": disease.efo_id,
        "expand_to_descendants": label_config.expand_to_descendants,
        "family_size": len(family),
        "n_full_candidates": len(full_candidates),
        "n_scored_candidates": len(scored_candidates),
        "n_dropped_clinical_only": len(clinical_only),
        # Reconciliation (Context.md §34): n_family_positive ==
        # n_positive + n_family_positive_outside_own_candidate_set
        # + n_family_positive_dropped_clinical_only. Every family positive is
        # accounted for by exactly one of these three buckets.
        "n_family_positive": len(family_positive),
        "n_family_positive_outside_own_candidate_set": len(outside_own_candidates),
        "n_family_positive_dropped_clinical_only": len(dropped_clinical_only_positives),
        "n_positive": n_positive,
        "n_negative": n_negative,
        "n_excluded_unknown_stage": n_excluded_unknown,
        "n_positive_direct_only": n_positive_direct_only,
        "positive_min_clinical_stage": threshold,
    }
    return labels, provenance


def build_labels(
    diseases: list[DiseaseSpec],
    config: FeaturesConfig | None = None,
    con: duckdb.DuckDBPyConnection | None = None,
) -> tuple[pl.DataFrame, dict[str, Any]]:
    """Build labels for every disease in *diseases* against the real release.

    Args:
        diseases: Diseases to label; each must have a resolved ``efo_id``.
        config: Feature config. Defaults to ``configs/features.yaml``.

    Returns:
        ``(labels, provenance)``. *labels* concatenates every disease's rows.
        *provenance* carries per-disease detail plus totals, so the row-count
        arithmetic across all ten diseases is auditable rather than inferred
        (Context.md §34).

    Raises:
        LabelError: If any ``maxClinicalStage`` value in the release is
            unmapped, or a disease's ID is not in the disease table.
    """
    config = config or load_features()

    owns = con is None
    con = con or open_targets.connect()
    try:
        clinical = load_clinical_target(con)
        stages_in_release = clinical.get_column("max_clinical_stage").unique().to_list()
        _validate_stage_map(stages_in_release, config.label)

        per_disease: dict[str, dict[str, Any]] = {}
        frames: list[pl.DataFrame] = []
        for disease in diseases:
            if not disease.efo_id:
                raise ValueError(f"Disease {disease.key!r} has no resolved efo_id.")
            evidence = open_targets.load_targets_for_disease(disease.efo_id, con)
            family = (
                disease_family(disease.efo_id, con)
                if config.label.expand_to_descendants
                else [disease.efo_id]
            )
            frame, prov = build_labels_for_disease(disease, evidence, clinical, family, config)
            frames.append(frame)
            per_disease[disease.key] = prov

        labels = pl.concat(frames, how="vertical")

        provenance = {
            "diseases": per_disease,
            "n_diseases": len(diseases),
            "n_total_rows": labels.height,
            "n_total_positive": int(labels.filter(pl.col("label") == 1).height),
            "n_total_negative": int(labels.filter(pl.col("label") == 0).height),
            "n_total_excluded_unknown_stage": int(
                labels.filter(pl.col("label_reason") == REASON_UNKNOWN_STAGE).height
            ),
            "n_total_dropped_clinical_only": sum(
                p["n_dropped_clinical_only"] for p in per_disease.values()
            ),
            "n_total_family_positive_outside_own_candidate_set": sum(
                p["n_family_positive_outside_own_candidate_set"] for p in per_disease.values()
            ),
        }
        log.info(
            "labels_built_all_diseases",
            n_diseases=len(diseases),
            n_positive=provenance["n_total_positive"],
            n_negative=provenance["n_total_negative"],
            prevalence=(
                round(provenance["n_total_positive"] / labels.height, 4) if labels.height else 0.0
            ),
        )
        return labels, provenance
    finally:
        if owns:
            con.close()
