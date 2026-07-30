"""Tests for model training (Context.md §17, §33, §37).

Exercised against small synthetic feature/label frames rather than the
downloaded release — consistent with the rest of this suite (see
tests/test_labels.py's module docstring for why). What matters here is the
training *mechanics*: fold-fitted preprocessing, per-model null handling,
determinism, the leakage re-check, and that ``weighted_baseline`` goes
through the identical interface as the ML models.
"""

from __future__ import annotations

import json

import numpy as np
import polars as pl
import pytest

from target_prioritization.config import (
    DenylistRule,
    FeaturesConfig,
    LabelConfig,
    LeakageGuardConfig,
)
from target_prioritization.features.build_features import LeakageError
from target_prioritization.models.predict import rank_targets, score_targets
from target_prioritization.models.train import (
    FittedModel,
    load_fitted_xgboost,
    save_fitted_xgboost,
    train_model,
    write_run_metadata,
)

N = 120


def _synthetic_features(seed: int = 0) -> pl.DataFrame:
    """Two informative columns plus one that's all-null for HALF the rows
    (simulating a sparse-datasource column, Context.md §32.3) and a
    disease-constant string column (simulating gene_symbol) that must never
    reach a model's `.fit()`.

    dim_a/dim_b are uniform on [0, 1], matching real `dim__*` columns
    (WeightedBaseline.score assumes that scale — milestone1.md §3) rather
    than an unbounded normal, so the weighted-baseline path's score stays in
    [0, 1] the way it would on real data.
    """
    rng = np.random.default_rng(seed)
    dim_a = rng.random(N)
    dim_b = rng.random(N)
    sparse = np.where(rng.random(N) < 0.5, np.nan, rng.random(N))
    return pl.DataFrame(
        {
            "disease_id": ["D1"] * (N // 2) + ["D2"] * (N // 2),
            "target_id": [f"T{i}" for i in range(N)],
            "gene_symbol": [f"GENE{i}" for i in range(N)],
            "dim__genetics": dim_a,
            "dim__literature": dim_b,
            "assoc_ds__rare_datasource_score": sparse,
        }
    )


def _synthetic_labels(features: pl.DataFrame) -> pl.DataFrame:
    """Label = 1 when dim__genetics is in the top third — gives the ML models
    genuine signal to find, so determinism/sanity checks aren't testing a
    coin flip."""
    threshold = features.get_column("dim__genetics").quantile(0.67)
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


class TestWeightedBaselinePath:
    def test_requires_weights(self, features, labels, config):
        with pytest.raises(ValueError, match="requires weights"):
            train_model(features, labels, "weighted_baseline", params=None, config=config)

    def test_wraps_weighted_baseline_and_scores_in_zero_one(self, features, labels, config):
        model = train_model(
            features,
            labels,
            "weighted_baseline",
            params={"genetics": 0.6, "literature": 0.4},
            config=config,
        )
        assert isinstance(model, FittedModel)
        assert model.weighted_baseline is not None
        proba = model.predict_proba(features)
        assert len(proba) == features.height
        assert all(0.0 <= p <= 1.0 for p in proba)


class TestLogisticRegression:
    def test_predict_proba_shape_and_range(self, features, labels, config):
        model = train_model(
            features, labels, "logistic_regression", {"max_iter": 200}, seed=42, config=config
        )
        proba = model.predict_proba(features)
        assert len(proba) == features.height
        assert all(0.0 <= p <= 1.0 for p in proba)

    def test_finds_the_planted_signal(self, features, labels, config):
        """dim__genetics literally defines the label, so a fitted model should
        separate the classes far better than chance."""
        model = train_model(
            features, labels, "logistic_regression", {"max_iter": 200}, seed=42, config=config
        )
        proba = np.array(model.predict_proba(features))
        y = labels.get_column("label").to_numpy()
        assert proba[y == 1].mean() > proba[y == 0].mean()

    def test_determinism_same_seed_same_predictions(self, features, labels, config):
        m1 = train_model(features, labels, "logistic_regression", {"max_iter": 200}, seed=42, config=config)
        m2 = train_model(features, labels, "logistic_regression", {"max_iter": 200}, seed=42, config=config)
        assert m1.predict_proba(features) == m2.predict_proba(features)

    def test_handles_a_fold_entirely_null_column_without_crashing(self, config):
        """A column that's all-null within THIS fold (the sparse-datasource
        scenario build_feature_table logs, milestone2.md Phase 2) must not
        crash fitting — sklearn's imputer drops it, which is correct: a
        constant column carries no signal and, un-dropped, would make
        StandardScaler divide by a zero variance."""
        n = 40
        features = pl.DataFrame(
            {
                "disease_id": ["D1"] * n,
                "target_id": [f"T{i}" for i in range(n)],
                "dim__genetics": np.linspace(0, 1, n),
                "assoc_ds__all_null_score": [None] * n,
            }
        )
        labels = pl.DataFrame(
            {
                "disease_id": ["D1"] * n,
                "target_id": [f"T{i}" for i in range(n)],
                "label": [1 if i >= n * 0.7 else 0 for i in range(n)],
            }
        )
        model = train_model(features, labels, "logistic_regression", {"max_iter": 200}, config=config)
        assert len(model.predict_proba(features)) == n


class TestRandomForest:
    def test_predict_proba_shape_and_range(self, features, labels, config):
        model = train_model(
            features,
            labels,
            "random_forest",
            {"n_estimators": 20, "max_depth": 3},
            seed=42,
            config=config,
        )
        proba = model.predict_proba(features)
        assert len(proba) == features.height
        assert all(0.0 <= p <= 1.0 for p in proba)

    def test_determinism_regardless_of_n_jobs(self, features, labels, config):
        """sklearn's RandomForest assigns each tree its own seed derived from
        random_state before dispatch, so parallelism must not change the
        fitted result — verified rather than assumed (the same standard
        Milestone 1 held itself to for reproducibility, milestone1.md §8)."""
        m1 = train_model(
            features, labels, "random_forest", {"n_estimators": 20, "n_jobs": 1}, seed=42, config=config
        )
        m2 = train_model(
            features, labels, "random_forest", {"n_estimators": 20, "n_jobs": -1}, seed=42, config=config
        )
        assert m1.predict_proba(features) == m2.predict_proba(features)


class TestXgboost:
    def test_predict_proba_shape_and_range(self, features, labels, config):
        model = train_model(
            features,
            labels,
            "xgboost",
            {"n_estimators": 20, "max_depth": 3, "n_jobs": 1},
            seed=42,
            config=config,
        )
        proba = model.predict_proba(features)
        assert len(proba) == features.height
        assert all(0.0 <= p <= 1.0 for p in proba)

    def test_takes_raw_nan_without_imputation(self, features, labels, config):
        """XGBoost must receive the null column AS-IS — no preprocessor."""
        model = train_model(
            features, labels, "xgboost", {"n_estimators": 20, "n_jobs": 1}, seed=42, config=config
        )
        assert model.preprocessor is None

    def test_scale_pos_weight_is_computed_from_the_given_labels(self, features, labels, config):
        model = train_model(
            features, labels, "xgboost", {"n_estimators": 10, "n_jobs": 1}, seed=42, config=config
        )
        n_pos = int(labels.get_column("label").sum())
        n_neg = labels.height - n_pos
        assert model.params["scale_pos_weight"] == pytest.approx(n_neg / n_pos)

    def test_explicit_scale_pos_weight_in_params_is_overridden(self, features, labels, config):
        """model.yaml sets scale_pos_weight: null specifically so it's always
        recomputed per fold; a stray non-null value must not silently win."""
        model = train_model(
            features,
            labels,
            "xgboost",
            {"n_estimators": 10, "n_jobs": 1, "scale_pos_weight": 999.0},
            seed=42,
            config=config,
        )
        assert model.params["scale_pos_weight"] != 999.0

    def test_determinism_with_pinned_n_jobs(self, features, labels, config):
        m1 = train_model(features, labels, "xgboost", {"n_estimators": 20, "n_jobs": 1}, seed=42, config=config)
        m2 = train_model(features, labels, "xgboost", {"n_estimators": 20, "n_jobs": 1}, seed=42, config=config)
        assert m1.predict_proba(features) == m2.predict_proba(features)


class TestLeakageReCheck:
    def test_denylisted_column_in_features_raises_at_fit_time(self, features, labels, config):
        """Even though build_feature_table would never produce this column,
        train_model re-checks anyway (Context.md §16) — checking twice is
        cheap, a leaked label is not."""
        leaking = features.with_columns(pl.lit(0.9).alias("assoc_ds__clinical_precedence_score"))
        with pytest.raises(LeakageError):
            train_model(leaking, labels, "logistic_regression", {"max_iter": 100}, config=config)

    def test_biotype_string_column_does_not_reach_the_matrix(self, features, labels, config):
        """A string column reaching sklearn's .fit() fails with a confusing
        numpy/sklearn error far from the actual cause; select_feature_columns
        must exclude it before that point (see test_features.py's matching
        regression test)."""
        with_biotype = features.with_columns(pl.lit("protein_coding").alias("biotype"))
        model = train_model(with_biotype, labels, "logistic_regression", {"max_iter": 100}, config=config)
        assert "biotype" not in model.feature_columns


class TestUnknownModelName:
    def test_raises(self, features, labels, config):
        with pytest.raises(ValueError, match="Unknown model_name"):
            train_model(features, labels, "not_a_real_model", config=config)


class TestNullLabelsAreDropped:
    def test_rows_with_null_label_are_excluded_from_fitting(self, features, config):
        labels_with_unknown = _synthetic_labels(features).with_columns(
            pl.when(pl.col("target_id") == "T0").then(None).otherwise(pl.col("label")).alias("label")
        )
        # Must not raise, and must not treat the excluded T0 row as negative.
        model = train_model(
            features, labels_with_unknown, "logistic_regression", {"max_iter": 100}, config=config
        )
        assert len(model.predict_proba(features)) == features.height  # scoring still covers every row


class TestScoreAndRankIntegration:
    def test_score_targets_then_rank_targets_round_trip(self, features, labels, config):
        model = train_model(features, labels, "logistic_regression", {"max_iter": 200}, config=config)
        scored = score_targets(model, features)
        assert set(scored.columns) == {"disease_id", "target_id", "score"}
        assert scored.height == features.height

        ranked = rank_targets(scored, top_n=5)
        for disease_id in ("D1", "D2"):
            sub = ranked.filter(pl.col("disease_id") == disease_id)
            assert sub.height == 5
            assert sub.get_column("rank").to_list() == [1, 2, 3, 4, 5]


class TestSaveAndLoadFittedXgboost:
    """Milestone 3 (Context.md §21): persisted fold models must score new
    rows identically to the in-memory model they were saved from — a
    round-trip mismatch would silently corrupt every held-out score the app
    displays."""

    def test_round_trip_predict_proba_matches_exactly(self, features, labels, config, tmp_path):
        model = train_model(
            features, labels, "xgboost", {"n_estimators": 20, "n_jobs": 1}, seed=42, config=config
        )
        path = tmp_path / "fold" / "xgboost_lodo_test.json"
        save_fitted_xgboost(model, path)
        loaded = load_fitted_xgboost(path)
        assert loaded.predict_proba(features) == model.predict_proba(features)

    def test_feature_columns_and_params_survive_the_round_trip(self, features, labels, config, tmp_path):
        model = train_model(
            features, labels, "xgboost", {"n_estimators": 10, "n_jobs": 1}, seed=42, config=config
        )
        path = tmp_path / "xgboost_lodo_test.json"
        save_fitted_xgboost(model, path)
        loaded = load_fitted_xgboost(path)
        assert loaded.feature_columns == model.feature_columns
        assert loaded.params["scale_pos_weight"] == model.params["scale_pos_weight"]

    def test_writes_a_sidecar_next_to_the_model_file(self, features, labels, config, tmp_path):
        model = train_model(
            features, labels, "xgboost", {"n_estimators": 10, "n_jobs": 1}, seed=42, config=config
        )
        path = tmp_path / "xgboost_lodo_test.json"
        save_fitted_xgboost(model, path)
        assert path.exists()
        assert path.with_name(path.name + ".meta.json").exists()

    def test_non_xgboost_model_is_rejected(self, features, labels, config, tmp_path):
        model = train_model(features, labels, "logistic_regression", {"max_iter": 100}, config=config)
        with pytest.raises(ValueError, match="xgboost"):
            save_fitted_xgboost(model, tmp_path / "not_xgboost.json")

    def test_load_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_fitted_xgboost(tmp_path / "does_not_exist.json")


class TestWriteRunMetadata:
    def test_writes_valid_json(self, tmp_path):
        path = tmp_path / "nested" / "run.json"
        write_run_metadata(path, {"model": "xgboost", "seed": 42, "metrics": {"ndcg_at_10": 0.5}})
        assert path.exists()
        assert json.loads(path.read_text()) == {
            "model": "xgboost",
            "seed": 42,
            "metrics": {"ndcg_at_10": 0.5},
        }
