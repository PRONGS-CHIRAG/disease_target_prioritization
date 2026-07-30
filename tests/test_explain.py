"""Tests for model explanations (Context.md §20).

Exercised against small synthetic feature/label frames — see
tests/test_train.py's module docstring for why. The reconstruction checks
here are the load-bearing ones: SHAP values that don't sum back to the
model's own prediction are wrong regardless of how plausible they look, and
this is exactly the kind of bug that stays invisible until someone checks
(the same lesson milestone1.md §5a already drew from an unrelated bug).
"""

from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from target_prioritization.config import (
    DenylistRule,
    FeaturesConfig,
    LabelConfig,
    LeakageGuardConfig,
)
from target_prioritization.models.explain import (
    STANDING_LIMITATIONS,
    explain_target,
    global_feature_importance,
    shap_values,
)
from target_prioritization.models.train import train_model

N = 150


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-z))


def _synthetic_features(seed: int = 0) -> pl.DataFrame:
    rng = np.random.default_rng(seed)
    dim_a = rng.random(N)
    dim_b = rng.random(N)
    return pl.DataFrame(
        {
            "disease_id": ["D1"] * N,
            "target_id": [f"T{i}" for i in range(N)],
            "gene_symbol": [f"GENE{i}" for i in range(N)],
            "dim__genetics": dim_a,
            "dim__literature": dim_b,
            "missing__genetics": (dim_a.round(6) == 0).astype(np.int8),  # essentially never
        }
    )


def _synthetic_labels(features: pl.DataFrame) -> pl.DataFrame:
    threshold = features.get_column("dim__genetics").quantile(0.6)
    return features.select(["disease_id", "target_id"]).with_columns(
        (features.get_column("dim__genetics") > threshold).cast(pl.Int8).alias("label")
    )


@pytest.fixture
def features() -> pl.DataFrame:
    return _synthetic_features()


@pytest.fixture
def labels(features) -> pl.DataFrame:
    return _synthetic_labels(features)


@pytest.fixture
def config() -> FeaturesConfig:
    return FeaturesConfig(
        version=1,
        label=LabelConfig(
            name="clinically_advanced_target",
            source="test",
            positive_min_clinical_stage=3,
            negative_definition="test",
            output_path="data/processed/labels.parquet",
        ),
        leakage_guard=LeakageGuardConfig(
            enabled=True,
            denylist=[
                DenylistRule(
                    id="ot_clinical_precedence_datasource",
                    match="assoc_ds__clinical_precedence*",
                    reason="the label",
                    required=False,
                )
            ],
        ),
        groups={},
    )


@pytest.fixture
def logreg_model(features, labels, config):
    return train_model(features, labels, "logistic_regression", {"max_iter": 200}, seed=42, config=config)


@pytest.fixture
def rf_model(features, labels, config):
    return train_model(
        features, labels, "random_forest", {"n_estimators": 30, "max_depth": 4}, seed=42, config=config
    )


@pytest.fixture
def xgb_model(features, labels, config):
    return train_model(
        features, labels, "xgboost", {"n_estimators": 30, "max_depth": 3, "n_jobs": 1}, seed=42, config=config
    )


@pytest.fixture
def wb_model(features, labels, config):
    return train_model(
        features, labels, "weighted_baseline", {"genetics": 0.6, "literature": 0.4}, config=config
    )


class TestShapValuesShape:
    def test_one_row_per_feature_per_candidate(self, logreg_model, features):
        subset = features.head(10)
        sv = shap_values(logreg_model, subset)
        assert set(sv.columns) == {"disease_id", "target_id", "feature", "shap_value", "base_value"}
        assert sv.height == 10 * len(logreg_model.feature_columns)

    def test_raises_on_empty_frame(self, logreg_model, features):
        with pytest.raises(ValueError, match="No rows"):
            shap_values(logreg_model, features.head(0))


class TestReconstruction:
    """base_value + sum(shap_value) must reconstruct the model's own output —
    see the module docstring for which space each model uses."""

    def test_logistic_regression_margin_space_reconstructs_via_sigmoid(self, logreg_model, features):
        subset = features.head(15)
        sv = shap_values(logreg_model, subset)
        sums = sv.group_by("target_id", maintain_order=True).agg(pl.col("shap_value").sum().alias("s"))
        base = sv.get_column("base_value")[0]
        recon = _sigmoid(sums.get_column("s").to_numpy() + base)
        proba = np.array(logreg_model.predict_proba(subset))
        np.testing.assert_allclose(recon, proba, atol=1e-6)

    def test_xgboost_margin_space_reconstructs_via_sigmoid(self, xgb_model, features):
        subset = features.head(15)
        sv = shap_values(xgb_model, subset)
        sums = sv.group_by("target_id", maintain_order=True).agg(pl.col("shap_value").sum().alias("s"))
        base = sv.get_column("base_value")[0]
        recon = _sigmoid(sums.get_column("s").to_numpy() + base)
        proba = np.array(xgb_model.predict_proba(subset))
        np.testing.assert_allclose(recon, proba, atol=1e-4)

    def test_random_forest_probability_space_reconstructs_directly_no_sigmoid(self, rf_model, features):
        """The one that's easy to get backwards: RF's TreeExplainer output IS
        already predict_proba-scale — applying a sigmoid here would be wrong,
        not just imprecise (verified during implementation, see module
        docstring)."""
        subset = features.head(15)
        sv = shap_values(rf_model, subset)
        sums = sv.group_by("target_id", maintain_order=True).agg(pl.col("shap_value").sum().alias("s"))
        base = sv.get_column("base_value")[0]
        recon = sums.get_column("s").to_numpy() + base  # NO sigmoid
        proba = np.array(rf_model.predict_proba(subset))
        np.testing.assert_allclose(recon, proba, atol=1e-8)


class TestGlobalFeatureImportance:
    def test_sorted_descending_and_non_negative(self, xgb_model, features):
        gfi = global_feature_importance(xgb_model, features.head(50))
        values = gfi.get_column("mean_abs_shap").to_list()
        assert values == sorted(values, reverse=True)
        assert all(v >= 0 for v in values)

    def test_the_label_defining_feature_ranks_first(self, xgb_model, features):
        """dim__genetics literally defines the synthetic label, so it should
        dominate global importance — a sanity check that SHAP is actually
        picking up real signal, not just running without error."""
        gfi = global_feature_importance(xgb_model, features.head(80))
        assert gfi.row(0, named=True)["feature"] == "dim__genetics"


class TestWeightedBaselineIsNotShapCompatible:
    def test_shap_values_raises(self, wb_model, features):
        with pytest.raises(ValueError, match="no SHAP values"):
            shap_values(wb_model, features)

    def test_global_feature_importance_raises(self, wb_model, features):
        with pytest.raises(ValueError, match="no SHAP values"):
            global_feature_importance(wb_model, features)


class TestExplainTargetForMlModels:
    def test_shape_matches_context_20_3(self, xgb_model, features):
        target_id = features.get_column("target_id")[0]
        result = explain_target(xgb_model, features, "D1", target_id)
        assert set(result) == {
            "target_id",
            "gene_symbol",
            "disease_id",
            "disease_name",
            "model_name",
            "score",
            "top_positive_factors",
            "top_negative_factors",
            "evidence_present",
            "evidence_missing",
            "source_references",
            "limitations",
        }
        assert 0.0 <= result["score"] <= 1.0
        assert result["limitations"] == STANDING_LIMITATIONS

    def test_positive_factors_have_positive_contribution(self, xgb_model, features):
        target_id = features.get_column("target_id")[0]
        result = explain_target(xgb_model, features, "D1", target_id)
        assert all(f["contribution"] > 0 for f in result["top_positive_factors"])

    def test_negative_factors_have_negative_contribution(self, xgb_model, features):
        target_id = features.get_column("target_id")[0]
        result = explain_target(xgb_model, features, "D1", target_id)
        assert all(f["contribution"] < 0 for f in result["top_negative_factors"])

    def test_missing_evidence_is_reported(self, xgb_model, features):
        with_missing = features.with_columns(
            pl.when(pl.col("target_id") == features.get_column("target_id")[0])
            .then(1)
            .otherwise(pl.col("missing__genetics"))
            .alias("missing__genetics")
        )
        target_id = with_missing.get_column("target_id")[0]
        result = explain_target(xgb_model, with_missing, "D1", target_id)
        assert "genetics" in result["evidence_missing"]

    def test_raises_for_unknown_target(self, xgb_model, features):
        with pytest.raises(KeyError):
            explain_target(xgb_model, features, "D1", "NOT_A_REAL_TARGET")

    def test_source_references_use_the_right_ids(self, xgb_model, features):
        target_id = features.get_column("target_id")[0]
        result = explain_target(xgb_model, features, "D1", target_id)
        assert target_id in result["source_references"]["target"]
        assert "D1" in result["source_references"]["disease"]


class TestExplainTargetForWeightedBaseline:
    def test_delegates_to_weighted_baseline_explain(self, wb_model, features):
        target_id = features.get_column("target_id")[0]
        result = explain_target(wb_model, features, "D1", target_id)
        assert result["model_name"] == "weighted_baseline"
        assert 0.0 <= result["score"] <= 1.0

    def test_no_negative_factors_weights_are_non_negative(self, wb_model, features):
        """WeightedBaseline rejects negative weights by construction, so
        there is no 'negative contribution' concept for this model — an
        empty list is the correct answer, not a missing feature."""
        target_id = features.get_column("target_id")[0]
        result = explain_target(wb_model, features, "D1", target_id)
        assert result["top_negative_factors"] == []

    def test_contributions_sum_to_the_score(self, wb_model, features):
        """Milestone 1's exact-decomposition property must survive being
        wrapped for Milestone 2's explain_target interface."""
        target_id = features.get_column("target_id")[0]
        result = explain_target(wb_model, features, "D1", target_id)
        total = sum(f["contribution"] for f in result["top_positive_factors"])
        assert total == pytest.approx(result["score"], abs=1e-9)
