"""Tests for Milestone 2 orchestration (Context.md §37).

``run_milestone_2`` itself needs the downloaded release (it calls
``build_feature_table``/``build_labels``), so — consistent with the rest of
this suite — it's exercised as a real run rather than in pytest; that run
produced ``reports/evaluation/baseline_metrics.json`` and
``models/trained/xgboost_baseline.json``, and its determinism was verified
by diffing two consecutive runs' metrics byte-for-byte (milestone2.md §6).
What's covered here is the pure logic: the acceptance-check arithmetic, the
literature-ablation column selection, and the leakage probe's own ability to
detect a guard that isn't working.
"""

from __future__ import annotations

import polars as pl
import pytest

from target_prioritization.config import (
    DenylistRule,
    FeaturesConfig,
    LabelConfig,
    LeakageGuardConfig,
)
from target_prioritization.milestone2 import (
    Milestone2Result,
    _drop_literature_columns,
    _weights_for,
    run_leakage_probe,
)


@pytest.fixture
def features_config() -> FeaturesConfig:
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
        evidence_dimensions={
            "literature": {
                "description": "test",
                "datasources": ["europepmc", "uniprot_literature"],
            }
        },
    )


class TestDropLiteratureColumns:
    def test_removes_every_literature_column(self, features_config):
        features = pl.DataFrame(
            {
                "target_id": ["T1"],
                "assoc_ds__europepmc_score": [0.9],
                "assoc_ds__europepmc_evidence_count": [5],
                "assoc_ds__uniprot_literature_score": [0.5],
                "assoc_ds__uniprot_literature_evidence_count": [1],
                "dim__literature": [0.7],
                "missing__literature": [0],
                "dim__genetics": [0.3],
            }
        )
        result = _drop_literature_columns(features, features_config)
        assert set(result.columns) == {"target_id", "dim__genetics"}

    def test_removes_evidence_diversity_too(self, features_config):
        """n_evidence_types/dim__evidence_diversity count literature datasources
        among the distinct evidence types, so leaving them behind would let the
        ablated model recover literature presence indirectly."""
        features = pl.DataFrame(
            {
                "target_id": ["T1"],
                "n_evidence_types": [3],
                "dim__evidence_diversity": [0.75],
                "dim__genetics": [0.3],
            }
        )
        result = _drop_literature_columns(features, features_config)
        assert set(result.columns) == {"target_id", "dim__genetics"}

    def test_missing_columns_do_not_raise(self, features_config):
        """Not every fold's feature table has every literature column
        (build_feature_table's per-disease sparsity, Phase 2) — dropping a
        column that doesn't exist must be a no-op, not an error."""
        features = pl.DataFrame({"target_id": ["T1"], "dim__genetics": [0.3]})
        result = _drop_literature_columns(features, features_config)
        assert result.columns == ["target_id", "dim__genetics"]


class TestWeightsFor:
    def test_weighted_baseline_returns_the_weight_dict(self):
        from target_prioritization.config import load_model_config

        model_config = load_model_config()
        weights = _weights_for("weighted_baseline", model_config)
        assert weights == dict(model_config.milestone_1_weights)

    def test_ml_model_returns_its_sklearn_params(self):
        from target_prioritization.config import load_model_config

        model_config = load_model_config()
        params = _weights_for("xgboost", model_config)
        assert params == dict(model_config.models["xgboost"]["params"])


class TestMilestone2ResultAcceptance:
    def _result_with_evaluation(self, evaluation: dict) -> Milestone2Result:
        return Milestone2Result(
            features=pl.DataFrame(),
            labels=pl.DataFrame(),
            scored_by_model={},
            evaluation=evaluation,
            evaluation_novel_only={},
            literature_ablation={},
            final_xgboost=None,  # type: ignore[arg-type]
            global_feature_importance=pl.DataFrame(),
        )

    def test_beats_random_counts_wins_correctly(self):
        evaluation = {
            "random_ranking": {
                "per_disease": {
                    "A": {"ndcg_at_10": 0.1},
                    "B": {"ndcg_at_10": 0.1},
                }
            },
            "xgboost": {
                "per_disease": {
                    "A": {"ndcg_at_10": 0.9},  # beats random
                    "B": {"ndcg_at_10": 0.05},  # loses to random
                }
            },
        }
        result = self._result_with_evaluation(evaluation)
        assert result.acceptance_beats_random["xgboost"] == (1, 2)

    def test_undefined_metric_is_excluded_from_the_denominator(self):
        """A disease where either side's ndcg_at_10 is None (e.g. zero
        positives) must not count toward wins OR total — the milestone2.md
        §6 threshold is "9 of 10 defined comparisons", not "9 of 10 diseases
        regardless of whether the comparison was possible"."""
        evaluation = {
            "random_ranking": {"per_disease": {"A": {"ndcg_at_10": 0.1}, "B": {"ndcg_at_10": None}}},
            "xgboost": {"per_disease": {"A": {"ndcg_at_10": 0.9}, "B": {"ndcg_at_10": 0.5}}},
        }
        result = self._result_with_evaluation(evaluation)
        assert result.acceptance_beats_random["xgboost"] == (1, 1)

    def test_acceptance_passed_requires_nine_of_ten_for_every_model(self):
        # 9/10 wins -> passes the >= 9 threshold.
        per_disease_random = {f"D{i}": {"ndcg_at_10": 0.1} for i in range(10)}
        per_disease_winner = {f"D{i}": {"ndcg_at_10": 0.9 if i < 9 else 0.05} for i in range(10)}
        evaluation = {
            "random_ranking": {"per_disease": per_disease_random},
            "xgboost": {"per_disease": per_disease_winner},
        }
        assert self._result_with_evaluation(evaluation).acceptance_passed is True

    def test_acceptance_fails_below_nine_of_ten(self):
        per_disease_random = {f"D{i}": {"ndcg_at_10": 0.5} for i in range(10)}
        # Only 8 wins.
        per_disease_loser = {f"D{i}": {"ndcg_at_10": 0.9 if i < 8 else 0.1} for i in range(10)}
        evaluation = {
            "random_ranking": {"per_disease": per_disease_random},
            "xgboost": {"per_disease": per_disease_loser},
        }
        assert self._result_with_evaluation(evaluation).acceptance_passed is False

    def test_random_ranking_itself_is_excluded_from_the_comparison(self):
        evaluation = {"random_ranking": {"per_disease": {"A": {"ndcg_at_10": 0.5}}}}
        result = self._result_with_evaluation(evaluation)
        assert "random_ranking" not in result.acceptance_beats_random


class TestLeakageProbe:
    def test_passes_silently_when_the_guard_works(self, features_config):
        features = pl.DataFrame(
            {
                "disease_id": ["D1"] * 20,
                "target_id": [f"T{i}" for i in range(20)],
                "dim__genetics": [i / 20 for i in range(20)],
            }
        )
        labels = pl.DataFrame(
            {
                "disease_id": ["D1"] * 20,
                "target_id": [f"T{i}" for i in range(20)],
                "label": [1 if i >= 14 else 0 for i in range(20)],
            }
        )
        run_leakage_probe(features, labels, features_config)  # must not raise

    def test_raises_assertion_error_when_the_guard_is_disabled(self, features_config):
        """The probe's whole point: if the guard were silently broken (as
        Milestone 1's was before it was fixed, milestone1.md §4), this must
        surface that loudly rather than passing quietly."""
        broken_config = features_config.model_copy(
            update={"leakage_guard": LeakageGuardConfig(enabled=False, denylist=[])}
        )
        features = pl.DataFrame(
            {
                "disease_id": ["D1"] * 20,
                "target_id": [f"T{i}" for i in range(20)],
                "dim__genetics": [i / 20 for i in range(20)],
            }
        )
        labels = pl.DataFrame(
            {
                "disease_id": ["D1"] * 20,
                "target_id": [f"T{i}" for i in range(20)],
                "label": [1 if i >= 14 else 0 for i in range(20)],
            }
        )
        with pytest.raises(AssertionError, match="Leakage probe FAILED"):
            run_leakage_probe(features, labels, broken_config)
