"""Milestone 3 app-facing precompute (Context.md §21; milestone3_plan.md §3-4).

The Streamlit app must not require the ~3 GB raw Open Targets pull just to
show a disease description or an existing-drug summary (milestone3_plan.md
§4.1) — those live only in the raw tables today. This module bakes them,
once, into ``data/processed/app_scores.parquet``, alongside the two things
that genuinely cannot be computed from ``disease_target_features.parquet``
alone: the held-out XGBoost score (needs the per-disease fold model under
``models/trained/folds/``) and the cross-disease popularity badge (needs
``labels.parquet``).

**Deliberately excluded from this artifact**, per milestone3_plan.md §4.2:
SHAP explanations. Measured directly (see that section): a single target's
SHAP is bit-identical to the same target's SHAP computed over its whole
disease and costs ~30ms, so ``services.evidence_summary`` computes it live —
precomputing it here would just be a stale copy of a cheap live call.

**The leakage boundary this artifact must respect**: several columns here
(``label__max_clinical_stage``, ``label__n_drugs``, ``label__drug_names``)
are literally the clinical-development evidence the training label is built
from. They are named with the ``label__`` prefix on purpose, so
``configs/features.yaml``'s ``label_columns`` denylist rule (``match:
"label*"``) fires if this frame is ever joined into something a model sees —
the same reason ``assoc_overall__score`` keeps that exact name rather than a
friendlier one. ``services.target_ranking`` enforces the actual boundary by
joining this artifact in only AFTER scoring, never before.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import duckdb
import polars as pl

from target_prioritization.config import DiseaseSpec, load_diseases
from target_prioritization.data import open_targets
from target_prioritization.data.labels import disease_family
from target_prioritization.milestone2 import FOLD_MODELS_DIRNAME, fold_model_filename
from target_prioritization.models.baselines import score_open_targets_overall
from target_prioritization.models.evaluate import (
    label_positive_prevalence_excluding,
    rank_within_disease,
)
from target_prioritization.models.predict import score_targets
from target_prioritization.models.train import load_fitted_xgboost
from target_prioritization.utils.logging import get_logger
from target_prioritization.utils.paths import DATA_PROCESSED, TRAINED_MODELS

__all__ = ["APP_DATA_NAME", "build_app_data"]

log = get_logger(__name__)

APP_DATA_NAME = "app_scores.parquet"

# Existing-drug summary (Context.md §21 target detail / filters): how many
# names to keep per (disease, target), so a target with a long clinical
# history doesn't produce an unreadable table cell.
MAX_DRUG_NAMES_DISPLAYED = 5


def _xgboost_held_out(features: pl.DataFrame, diseases: list[DiseaseSpec]) -> pl.DataFrame:
    """Held-out XGBoost score and rank per (disease_id, target_id).

    Scored by the fold model that EXCLUDED each disease
    (``models.train.load_fitted_xgboost`` reading
    ``models/trained/folds/xgboost_lodo_<key>.json``) — never
    ``models/trained/xgboost_baseline.json``, the all-disease refit, which is
    in-sample for every disease it could score (milestone3_plan.md §2.1).
    """
    frames = []
    for disease in diseases:
        model_path = TRAINED_MODELS / FOLD_MODELS_DIRNAME / fold_model_filename(disease.key)
        model = load_fitted_xgboost(model_path)
        disease_features = features.filter(pl.col("disease_id") == disease.efo_id)
        scored = score_targets(model, disease_features)
        ranked = rank_within_disease(scored)
        frames.append(
            ranked.select(
                "disease_id",
                "target_id",
                pl.col("score").alias("xgboost_score_held_out"),
                pl.col("rank").alias("xgboost_rank_held_out"),
            )
        )
    return pl.concat(frames, how="vertical")


def _ot_overall(
    features: pl.DataFrame, diseases: list[DiseaseSpec], con: duckdb.DuckDBPyConnection
) -> pl.DataFrame:
    """Open Targets' own overall score, for on-screen comparison only —
    never a feature (Context.md §16).

    Column kept as ``assoc_overall__score``, the exact name denylist rule
    ``ot_overall_association_score`` matches
    (``models.baselines.score_open_targets_overall``'s docstring: the name is
    chosen so an accidental join into a feature frame fires the guard).
    Renaming it to something innocuous for display would disarm that trap.
    """
    frames = []
    for d in diseases:
        if not d.efo_id:
            raise ValueError(f"Disease {d.key!r} has no resolved efo_id.")
        frames.append(
            score_open_targets_overall(features.filter(pl.col("disease_id") == d.efo_id), d.efo_id, con).rename(
                {"score": "assoc_overall__score"}
            )
        )
    return pl.concat(frames, how="vertical")


def _popularity(labels: pl.DataFrame) -> pl.DataFrame:
    """``n_other_diseases_positive`` per (disease_id, target_id) — the
    per-target, concrete form of milestone2.md §1's cross-disease-popularity
    finding (milestone3_plan.md §2.2).

    Reuses ``evaluate.label_positive_prevalence_excluding``, the SAME
    function the ``target_popularity`` baseline and novel-only
    stratification use, so this badge cannot drift from either's definition
    of "positive elsewhere" (models/baselines.py makes the identical point
    about ``score_target_popularity``).
    """
    disease_ids = sorted(labels.get_column("disease_id").unique().to_list())
    frames = [
        label_positive_prevalence_excluding(labels, disease_id).with_columns(
            pl.lit(disease_id).alias("disease_id")
        )
        for disease_id in disease_ids
    ]
    return pl.concat(frames, how="vertical").select("disease_id", "target_id", "n_other_diseases_positive")


def _disease_descriptions(diseases: list[DiseaseSpec], con: duckdb.DuckDBPyConnection) -> pl.DataFrame:
    """Disease description text, for the disease-overview page (§38.1) and
    disease search (§21) — the one field ``disease_search`` needs from raw
    data, baked in here so the running app never reads raw itself."""
    glob = open_targets.dataset_glob("disease")
    con.register("wanted_diseases", pl.DataFrame({"disease_id": [d.efo_id for d in diseases]}).to_arrow())
    query = f"""
        SELECT id AS disease_id, description AS disease_description
        FROM read_parquet('{glob}')
        WHERE id IN (SELECT disease_id FROM wanted_diseases)
    """
    frame = pl.from_arrow(con.execute(query).arrow())
    assert isinstance(frame, pl.DataFrame)
    return frame


def _target_function_descriptions(target_ids: list[str], con: duckdb.DuckDBPyConnection) -> pl.DataFrame:
    """First entry of ``target.functionDescriptions`` per target (Context.md
    §21 target detail). A target-level property, not disease-specific — this
    joins on ``target_id`` alone, broadcasting across every disease a target
    appears in."""
    glob = open_targets.dataset_glob("target")
    con.register("wanted_targets", pl.DataFrame({"target_id": target_ids}).to_arrow())
    # DuckDB list indexing is 1-based.
    query = f"""
        SELECT id AS target_id,
               functionDescriptions[1] AS target_function_description
        FROM read_parquet('{glob}')
        WHERE id IN (SELECT target_id FROM wanted_targets)
    """
    frame = pl.from_arrow(con.execute(query).arrow())
    assert isinstance(frame, pl.DataFrame)
    return frame


def _existing_drug_summary(diseases: list[DiseaseSpec], con: duckdb.DuckDBPyConnection) -> pl.DataFrame:
    """Drug count and names per (disease_id, target_id) (Context.md §21
    target detail / filters).

    Expanded to the same ontology family the label uses
    (``data.labels.disease_family``) — a target credited with a drug here is
    credited for exactly the clinical evidence that could have made it a
    labelled positive (Context.md §15), not a narrower or looser set.

    Deliberately NOT restricted to clinically-advanced drugs only:
    Context.md §21's "Existing drug information" is a display field for
    every target, unlike the label's phase>=3 threshold — a target with only
    a preclinical or phase-1 compound still shows it here.

    Column names are prefixed ``label__`` deliberately — see the module
    docstring.
    """
    clinical_glob = open_targets.dataset_glob("clinical_target")
    clinical = pl.from_arrow(
        con.execute(
            f"""
            SELECT targetId AS target_id,
                   drugId,
                   unnest(diseases).diseaseId AS disease_id_direct
            FROM read_parquet('{clinical_glob}')
            """
        ).arrow()
    )
    assert isinstance(clinical, pl.DataFrame)
    drug_glob = open_targets.dataset_glob("drug_molecule")
    drug_names = pl.from_arrow(con.execute(f"SELECT id AS drugId, name FROM read_parquet('{drug_glob}')").arrow())
    assert isinstance(drug_names, pl.DataFrame)
    with_names = clinical.join(drug_names, on="drugId", how="left")

    frames = []
    for disease in diseases:
        if not disease.efo_id:
            raise ValueError(f"Disease {disease.key!r} has no resolved efo_id.")
        family = disease_family(disease.efo_id, con)
        summary = (
            with_names.filter(pl.col("disease_id_direct").is_in(family))
            .group_by("target_id")
            .agg(
                pl.col("drugId").n_unique().alias("label__n_drugs"),
                pl.col("name").drop_nulls().unique().sort().head(MAX_DRUG_NAMES_DISPLAYED).alias("_names"),
            )
            .with_columns(
                pl.lit(disease.efo_id).alias("disease_id"),
                pl.col("_names").list.join(", ").alias("label__drug_names"),
            )
            .drop("_names")
        )
        frames.append(summary)
    return pl.concat(frames, how="vertical").select(
        "disease_id", "target_id", "label__n_drugs", "label__drug_names"
    )


def build_app_data(
    diseases: list[DiseaseSpec] | None = None,
    *,
    features: pl.DataFrame | None = None,
    labels: pl.DataFrame | None = None,
    con: duckdb.DuckDBPyConnection | None = None,
) -> tuple[pl.DataFrame, dict[str, Any]]:
    """Assemble the Milestone 3 app-facing artifact.

    Holds only what ``disease_target_features.parquet`` does not already
    carry: held-out XGBoost score/rank, the OT overall score for comparison,
    the cross-disease popularity badge, disease/target descriptions, and the
    existing-drug summary. ``services.target_ranking`` reads both parquets
    and joins this one in only AFTER scoring — see that module's docstring
    and the leakage-boundary note above for why the order matters.

    Requires ``scripts/train_model.py`` to have already produced
    ``disease_target_features.parquet``, ``labels.parquet`` and the
    per-disease fold models under ``models/trained/folds/``.

    Returns:
        ``(app_data, provenance)``. One row per ``(disease_id, target_id)``
        in the candidate universe — the same universe
        ``disease_target_features.parquet`` has, so a plain join against it
        never drops or duplicates rows.
    """
    diseases = diseases if diseases is not None else load_diseases().resolved
    features = (
        features if features is not None else pl.read_parquet(DATA_PROCESSED / "disease_target_features.parquet")
    )
    labels = labels if labels is not None else pl.read_parquet(DATA_PROCESSED / "labels.parquet")

    owns = con is None
    con = con or open_targets.connect()
    try:
        universe = features.select("disease_id", "target_id").unique()
        target_ids = universe.get_column("target_id").unique().to_list()

        xgb_held_out = _xgboost_held_out(features, diseases)
        ot_overall = _ot_overall(features, diseases, con)
        popularity = _popularity(labels)
        disease_desc = _disease_descriptions(diseases, con)
        target_desc = _target_function_descriptions(target_ids, con)
        drug_summary = _existing_drug_summary(diseases, con)
        label_stage = labels.select(
            "disease_id", "target_id", pl.col("max_clinical_stage").alias("label__max_clinical_stage")
        )

        app_data = (
            universe.join(xgb_held_out, on=["disease_id", "target_id"], how="left")
            .join(ot_overall, on=["disease_id", "target_id"], how="left")
            .join(popularity, on=["disease_id", "target_id"], how="left")
            .join(label_stage, on=["disease_id", "target_id"], how="left")
            .join(drug_summary, on=["disease_id", "target_id"], how="left")
            .join(disease_desc, on="disease_id", how="left")
            .join(target_desc, on="target_id", how="left")
            .with_columns(
                pl.col("n_other_diseases_positive").fill_null(0),
                pl.col("label__n_drugs").fill_null(0),
                pl.lit(open_targets.release_tag()).alias("dataset_version"),
                pl.lit(datetime.now(UTC).date().isoformat()).alias("extraction_date"),
            )
        )

        n_missing_held_out = app_data.filter(pl.col("xgboost_score_held_out").is_null()).height
        if n_missing_held_out:
            log.warning(
                "app_data_missing_held_out_score",
                n_missing=n_missing_held_out,
                note="every candidate should get a held-out score; a gap means a fold model or "
                "feature-table mismatch",
            )

        provenance = {
            "n_diseases": len(diseases),
            "n_rows": app_data.height,
            "n_distinct_targets": len(target_ids),
            "dataset_version": open_targets.release_tag(),
            "extraction_date": datetime.now(UTC).date().isoformat(),
            "n_missing_held_out_score": n_missing_held_out,
            "fold_models_used": {
                d.key: str(
                    (TRAINED_MODELS / FOLD_MODELS_DIRNAME / fold_model_filename(d.key)).relative_to(
                        TRAINED_MODELS.parent
                    )
                )
                for d in diseases
            },
        }
        log.info("app_data_built", n_diseases=len(diseases), rows=app_data.height)
        return app_data, provenance
    finally:
        if owns:
            con.close()
