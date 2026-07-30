"""Tests for the Milestone 3 app-data precompute (Context.md §21).

``build_app_data`` itself needs the downloaded release (disease
descriptions, target function descriptions and the existing-drug summary
all read raw Open Targets tables) plus the trained fold models, so —
consistent with the rest of this suite (see tests/test_milestone2.py's
module docstring) — it is exercised as a real run rather than in pytest;
that run produced ``data/processed/app_scores.parquet``. What's covered
here is the pure logic: the popularity badge and the held-out-scoring path,
both of which need no raw data.
"""

from __future__ import annotations

import polars as pl

from target_prioritization.app_data import _popularity, _xgboost_held_out
from target_prioritization.config import DiseaseSpec
from target_prioritization.models.train import save_fitted_xgboost, train_model


class TestPopularity:
    def test_matches_label_positive_prevalence_excluding(self):
        """Must reuse evaluate.label_positive_prevalence_excluding, not a
        parallel reimplementation that could drift from it
        (milestone3_plan.md §2.2, models/baselines.py's identical point
        about score_target_popularity)."""
        labels = pl.DataFrame(
            {
                "disease_id": ["A", "B", "C"],
                "target_id": ["shared", "shared", "shared"],
                "label": [1, 1, 1],
            }
        )
        result = _popularity(labels)
        row = result.filter((pl.col("disease_id") == "A") & (pl.col("target_id") == "shared")).row(
            0, named=True
        )
        assert row["n_other_diseases_positive"] == 2

    def test_iterates_over_every_disease_present_in_labels(self):
        """`shared` is positive in A and B; from C's perspective (excluding
        C) that is 2 other diseases. From A's perspective (excluding A),
        `shared` is positive only in B (1), and `only_c` (positive only in
        C) is also 1 — every disease gets rows for whatever is positive
        elsewhere, not just its own recurring positives."""
        labels = pl.DataFrame(
            {
                "disease_id": ["A", "B", "C"],
                "target_id": ["shared", "shared", "only_c"],
                "label": [1, 1, 1],
            }
        )
        result = _popularity(labels)
        by_key = {
            (r["disease_id"], r["target_id"]): r["n_other_diseases_positive"]
            for r in result.iter_rows(named=True)
        }
        assert by_key[("C", "shared")] == 2
        assert by_key[("A", "shared")] == 1
        assert by_key[("A", "only_c")] == 1
        assert ("B", "shared") in by_key

    def test_targets_never_positive_elsewhere_are_absent_not_errored(self):
        """label_positive_prevalence_excluding only returns rows for targets
        that ARE positive somewhere else — callers (build_app_data) are
        responsible for left-joining and filling zero. Documented here so a
        future reader doesn't mistake the absence for a bug."""
        labels = pl.DataFrame({"disease_id": ["A"], "target_id": ["never_positive"], "label": [0]})
        result = _popularity(labels)
        assert result.filter(pl.col("target_id") == "never_positive").is_empty()


class TestXgboostHeldOut:
    def test_scores_come_from_the_disease_specific_fold_model(self, tmp_path):
        """The whole point of Step 1: each disease's held-out score must
        come from the model that excluded it, not from any other fold."""
        features = pl.DataFrame(
            {
                "disease_id": ["D1"] * 6 + ["D2"] * 6,
                "target_id": [f"T{i}" for i in range(12)],
                "gene_symbol": [f"G{i}" for i in range(12)],
                "dim__genetics": [0.1, 0.9, 0.2, 0.8, 0.3, 0.7] * 2,
                "dim__druggability": [0.5] * 12,
            }
        )
        labels = pl.DataFrame(
            {
                "disease_id": ["D1"] * 6 + ["D2"] * 6,
                "target_id": [f"T{i}" for i in range(12)],
                "label": [0, 1, 0, 1, 0, 1] * 2,
            }
        )

        d1_model = train_model(
            features.filter(pl.col("disease_id") == "D2"),
            labels.filter(pl.col("disease_id") == "D2"),
            "xgboost",
            {"n_estimators": 10, "n_jobs": 1},
            seed=1,
        )
        d2_model = train_model(
            features.filter(pl.col("disease_id") == "D1"),
            labels.filter(pl.col("disease_id") == "D1"),
            "xgboost",
            {"n_estimators": 10, "n_jobs": 1},
            seed=2,
        )
        save_fitted_xgboost(d1_model, tmp_path / "trained" / "folds" / "xgboost_lodo_disease_one.json")
        save_fitted_xgboost(d2_model, tmp_path / "trained" / "folds" / "xgboost_lodo_disease_two.json")

        import target_prioritization.app_data as app_data_module

        original_trained_models = app_data_module.TRAINED_MODELS
        app_data_module.TRAINED_MODELS = tmp_path / "trained"
        try:
            diseases = [
                DiseaseSpec(key="disease_one", name="Disease One", efo_id="EFO_0000001", category="test"),
                DiseaseSpec(key="disease_two", name="Disease Two", efo_id="EFO_0000002", category="test"),
            ]
            features_with_ids = features.with_columns(
                pl.when(pl.col("disease_id") == "D1")
                .then(pl.lit("EFO_0000001"))
                .otherwise(pl.lit("EFO_0000002"))
                .alias("disease_id")
            )
            result = _xgboost_held_out(features_with_ids, diseases)
        finally:
            app_data_module.TRAINED_MODELS = original_trained_models

        assert set(result.columns) == {
            "disease_id",
            "target_id",
            "xgboost_score_held_out",
            "xgboost_rank_held_out",
        }
        assert result.height == 12
        d1_scores = result.filter(pl.col("disease_id") == "EFO_0000001").sort("target_id")
        expected = d1_model.predict_proba(
            features_with_ids.filter(pl.col("disease_id") == "EFO_0000001").sort("target_id")
        )
        assert d1_scores.get_column("xgboost_score_held_out").to_list() == expected
