"""Tests for the evidence-card service (Context.md §21, §30.12, §37).

The weighted-baseline half is fully synthetic (no fold model needed). The
XGBoost half needs a real fitted model to explain, so those tests train and
save a tiny one to ``tmp_path`` rather than depending on the real,
multi-megabyte fold models under ``models/trained/folds/`` — consistent
with how ``tests/test_explain.py`` exercises SHAP against a small synthetic
model rather than the production one.
"""

from __future__ import annotations

import polars as pl
import pytest

from target_prioritization.config import DiseaseSpec
from target_prioritization.models.train import save_fitted_xgboost, train_model
from target_prioritization.services.evidence_summary import build_evidence_card

WEIGHTS = {"genetics": 0.4, "evidence_diversity": 0.2, "functional": 0.15, "literature": 0.15, "druggability": 0.1}


def _features() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "disease_id": ["D1"] * 4,
            "target_id": ["T1", "T2", "T3", "T4"],
            "gene_symbol": ["G1", "G2", "G3", "G4"],
            "dim__genetics": [0.9, 0.1, 0.4, 0.5],
            "dim__evidence_diversity": [0.8, 0.2, 0.5, 0.5],
            "dim__functional": [0.7, 0.3, 0.3, 0.4],
            "dim__literature": [0.6, 0.6, 0.6, 0.6],
            "dim__druggability": [1.0, 0.0, 0.5, 0.5],
            "missing__genetics": [0, 0, 0, 0],
            "missing__functional": [0, 0, 0, 0],
            "missing__druggability": [0, 0, 0, 0],
            "missing__pathways": [0, 1, 0, 0],
            "missing__network": [0, 0, 0, 0],
            "missing__expression": [0, 0, 0, 0],
            "prio__has_safety_event": [None, None, -1, None],
            "dataset_version": ["26.06"] * 4,
        }
    )


class TestBuildEvidenceCardWithoutAFoldModel:
    """No models/trained/folds/ directory exists for these synthetic
    diseases — the XGBoost half degrades to empty lists rather than
    raising, so the weighted-baseline half is still usable on its own."""

    def test_score_and_supporting_come_from_the_weighted_baseline(self):
        card = build_evidence_card("D1", "T1", features=_features(), weights=WEIGHTS, diseases=[])
        assert card.score == pytest.approx(0.4 * 0.9 + 0.2 * 0.8 + 0.15 * 0.7 + 0.15 * 0.6 + 0.1 * 1.0)
        sources = {item.source for item in card.supporting}
        assert sources == {"weighted_baseline"}

    def test_safety_event_appears_as_contradicting_evidence(self):
        card = build_evidence_card("D1", "T3", features=_features(), weights=WEIGHTS, diseases=[])
        categories = [item.category for item in card.contradicting]
        assert "safety_event" in categories

    def test_no_safety_event_means_no_contradicting_evidence(self):
        card = build_evidence_card("D1", "T1", features=_features(), weights=WEIGHTS, diseases=[])
        assert card.contradicting == []

    def test_missing_is_empty_when_every_category_is_present(self):
        """As of Milestone 4, UNAVAILABLE_EVIDENCE_CATEGORIES is empty — a
        category appears in `missing` only when THIS target's own
        `missing__<category>` flag is set, never categorically for every
        target (unlike through Milestone 3)."""
        card = build_evidence_card("D1", "T1", features=_features(), weights=WEIGHTS, diseases=[])
        assert card.missing == []

    def test_missing_reflects_a_genuinely_missing_category(self):
        card = build_evidence_card("D1", "T2", features=_features(), weights=WEIGHTS, diseases=[])
        assert card.missing == ["pathways"]

    def test_limitations_include_standing_limitations(self):
        card = build_evidence_card("D1", "T1", features=_features(), weights=WEIGHTS, diseases=[])
        assert any("prioritization score" in limitation for limitation in card.limitations)

    def test_source_links_are_attached(self):
        card = build_evidence_card("D1", "T1", features=_features(), weights=WEIGHTS, diseases=[])
        assert set(card.source_links) == {"target", "disease", "evidence"}
        assert "T1" in card.source_links["target"]
        assert "D1" in card.source_links["disease"]

    def test_unknown_pair_raises_key_error(self):
        with pytest.raises(KeyError):
            build_evidence_card("D1", "NOT_A_TARGET", features=_features(), weights=WEIGHTS, diseases=[])

    def test_gene_symbol_is_attached(self):
        card = build_evidence_card("D1", "T2", features=_features(), weights=WEIGHTS, diseases=[])
        assert card.gene_symbol == "G2"


class TestBuildEvidenceCardWithAFoldModel:
    def test_xgboost_factors_are_included_when_a_fold_model_exists(self, tmp_path, monkeypatch):
        disease_id = "EFO_0000002"
        train_features = pl.DataFrame(
            {
                "disease_id": [disease_id] * 8,
                "target_id": [f"X{i}" for i in range(8)],
                "gene_symbol": [f"G{i}" for i in range(8)],
                "dim__genetics": [0.1, 0.9, 0.2, 0.8, 0.3, 0.7, 0.4, 0.6],
                "dim__evidence_diversity": [0.5] * 8,
                "dim__functional": [0.5] * 8,
                "dim__literature": [0.5] * 8,
                "dim__druggability": [0.5] * 8,
                "prio__has_safety_event": [None] * 8,
                "dataset_version": ["26.06"] * 8,
            }
        )
        labels = pl.DataFrame(
            {
                "disease_id": [disease_id] * 8,
                "target_id": [f"X{i}" for i in range(8)],
                "label": [0, 1, 0, 1, 0, 1, 0, 1],
            }
        )
        model = train_model(train_features, labels, "xgboost", {"n_estimators": 10, "n_jobs": 1}, seed=1)

        import target_prioritization.services.evidence_summary as evidence_summary_module

        fold_path = tmp_path / "trained" / "folds" / "xgboost_lodo_disease_two.json"
        save_fitted_xgboost(model, fold_path)
        monkeypatch.setattr(evidence_summary_module, "TRAINED_MODELS", tmp_path / "trained")

        diseases = [DiseaseSpec(key="disease_two", name="Disease Two", efo_id=disease_id, category="test")]
        card = build_evidence_card(
            disease_id, "X1", features=train_features, weights=WEIGHTS, diseases=diseases
        )
        sources = {item.source for item in card.supporting}
        assert "xgboost_held_out" in sources
