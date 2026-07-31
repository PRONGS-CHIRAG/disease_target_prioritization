"""Tests for the ranking service (Context.md §21, Milestone 3).

Exercised entirely against synthetic feature/app-data frames passed
explicitly, never the real processed parquets — consistent with the rest of
this suite. The synthetic frames are shaped exactly like
``disease_target_features.parquet`` / ``app_scores.parquet`` for one
disease, which is also what lets these tests double as a check of the
score-first-join-second boundary the module docstring describes.
"""

from __future__ import annotations

import polars as pl
import pytest

from target_prioritization.services.target_ranking import (
    APP_EVIDENCE_CATEGORIES,
    UNAVAILABLE_EVIDENCE_CATEGORIES,
    RankingFilters,
    load_precomputed_scores,
    normalize_weights,
    rank_for_disease,
)

DISEASE = "D1"

WEIGHTS = {"genetics": 0.4, "evidence_diversity": 0.2, "functional": 0.15, "literature": 0.15, "druggability": 0.1}


def _features() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "disease_id": [DISEASE] * 4,
            "target_id": ["T1", "T2", "T3", "T4"],
            "gene_symbol": ["G1", "G2", "G3", "G4"],
            "gene_name": ["Gene One", "Gene Two", "Gene Three", "Gene Four"],
            "dim__genetics": [0.9, 0.1, None, 0.5],
            "dim__evidence_diversity": [0.8, 0.2, 0.5, 0.5],
            "dim__functional": [0.7, None, 0.3, 0.4],
            "dim__literature": [0.6, 0.6, 0.6, 0.6],
            "dim__druggability": [1.0, 0.0, 0.5, None],
            "missing__genetics": [0, 0, 1, 0],
            "missing__functional": [0, 1, 0, 0],
            "missing__druggability": [0, 0, 0, 1],
            # Milestone 4's three built categories. Each of T2/T3/T4 is
            # missing exactly one of these (in addition to its pre-existing
            # milestone-1 gap), so app_evidence_completeness reads 4/6 for
            # them and 6/6 for T1 — see test_app_evidence_completeness_denominator_is_six.
            "missing__pathways": [0, 1, 0, 0],
            "missing__network": [0, 0, 1, 0],
            "missing__expression": [0, 0, 0, 1],
            # T1 clearly above TPM_DETECTION_THRESHOLD (1.0), T2 clearly
            # below, T3 above, T4 null (gene absent from GTEx or its
            # disease's relevant_tissues didn't resolve).
            "expr__relevant_tissue_tpm": [5.0, 0.5, 2.0, None],
            "prio__has_small_molecule_binder": [1, 0, 1, 0],
            "prio__has_safety_event": [None, -1, None, None],
        }
    )


def _app_data() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "disease_id": [DISEASE] * 4,
            "target_id": ["T1", "T2", "T3", "T4"],
            "xgboost_score_held_out": [0.2, 0.9, 0.5, 0.4],
            "xgboost_rank_held_out": [4, 1, 2, 3],
            "assoc_overall__score": [0.5, 0.5, 0.5, 0.5],
            "n_other_diseases_positive": [3, 0, 1, 0],
            "label__max_clinical_stage": [4, None, 2, None],
            "label__n_drugs": [2, 0, 1, 0],
            "label__drug_names": ["DRUGA, DRUGB", None, "DRUGC", None],
        }
    )


class TestRankForDisease:
    def test_default_sort_is_weighted_baseline(self):
        results = rank_for_disease(DISEASE, weights=WEIGHTS, features=_features(), app_data=_app_data())
        # T1 has the strongest genetics/functional/druggability evidence.
        assert results[0].target_id == "T1"
        assert results[0].rank == 1

    def test_xgboost_held_out_sort_reorders(self):
        results = rank_for_disease(
            DISEASE, weights=WEIGHTS, features=_features(), app_data=_app_data(), sort_by="xgboost_held_out"
        )
        assert results[0].target_id == "T2"  # highest xgboost_score_held_out
        assert results[0].score == pytest.approx(0.9)

    def test_both_scores_are_always_present_regardless_of_sort(self):
        results = rank_for_disease(DISEASE, weights=WEIGHTS, features=_features(), app_data=_app_data())
        t1 = next(r for r in results if r.target_id == "T1")
        assert t1.weighted_baseline_score is not None
        assert t1.xgboost_score_held_out is not None

    def test_rank_reflects_full_population_not_the_filtered_subset(self):
        """A filter must narrow WHAT is shown, not renumber the survivors —
        rank #1 stays #1 even if rank #2 gets filtered out."""
        all_results = rank_for_disease(DISEASE, weights=WEIGHTS, features=_features(), app_data=_app_data())
        rank_by_target = {r.target_id: r.rank for r in all_results}

        filtered = rank_for_disease(
            DISEASE,
            weights=WEIGHTS,
            filters=RankingFilters(require_druggable=True),
            features=_features(),
            app_data=_app_data(),
        )
        for r in filtered:
            assert r.rank == rank_by_target[r.target_id]

    def test_min_genetics_evidence_filter(self):
        results = rank_for_disease(
            DISEASE,
            weights=WEIGHTS,
            filters=RankingFilters(min_genetics_evidence=0.5),
            features=_features(),
            app_data=_app_data(),
        )
        assert {r.target_id for r in results} == {"T1", "T4"}

    def test_require_druggable_filter(self):
        results = rank_for_disease(
            DISEASE,
            weights=WEIGHTS,
            filters=RankingFilters(require_druggable=True),
            features=_features(),
            app_data=_app_data(),
        )
        assert {r.target_id for r in results} == {"T1", "T3"}

    def test_min_evidence_completeness_filter(self):
        results = rank_for_disease(
            DISEASE,
            weights=WEIGHTS,
            filters=RankingFilters(min_evidence_completeness=0.5),
            features=_features(),
            app_data=_app_data(),
        )
        # T1 has all six categories present -> 6/6 = 1.0.
        assert "T1" in {r.target_id for r in results}

    def test_exclude_safety_concerns_filter(self):
        results = rank_for_disease(
            DISEASE,
            weights=WEIGHTS,
            filters=RankingFilters(exclude_safety_concerns=True),
            features=_features(),
            app_data=_app_data(),
        )
        assert "T2" not in {r.target_id for r in results}  # T2 has prio__has_safety_event = -1

    def test_exclude_safety_concerns_keeps_null_flags(self):
        """A null safety flag means 'not assessed', not 'no concern'
        (Context.md §32.3) — it must never be excluded by this filter."""
        results = rank_for_disease(
            DISEASE,
            weights=WEIGHTS,
            filters=RankingFilters(exclude_safety_concerns=True),
            features=_features(),
            app_data=_app_data(),
        )
        assert {"T1", "T3", "T4"}.issubset({r.target_id for r in results})

    def test_relevant_tissue_filter_keeps_targets_above_the_detection_threshold(self):
        """Milestone 4: relevant_tissue is buildable now (expr__relevant_tissue_tpm
        exists) — it filters, it no longer raises."""
        results = rank_for_disease(
            DISEASE,
            weights=WEIGHTS,
            filters=RankingFilters(relevant_tissue="brain"),
            features=_features(),
            app_data=_app_data(),
        )
        # T1 (5.0) and T3 (2.0) clear TPM_DETECTION_THRESHOLD; T2 (0.5) and
        # T4 (null) do not.
        assert {r.target_id for r in results} == {"T1", "T3"}

    def test_target_family_filter_raises_rather_than_silently_ignoring(self):
        with pytest.raises(ValueError, match="not buildable"):
            rank_for_disease(
                DISEASE,
                filters=RankingFilters(target_family="kinase"),
                features=_features(),
                app_data=_app_data(),
            )

    def test_unknown_sort_by_raises(self):
        with pytest.raises(ValueError, match="Unknown sort_by"):
            rank_for_disease(DISEASE, sort_by="bogus", features=_features(), app_data=_app_data())

    def test_unknown_disease_raises_key_error(self):
        with pytest.raises(KeyError):
            rank_for_disease("NOT_A_DISEASE", features=_features(), app_data=_app_data())

    def test_top_n_truncates_after_filtering(self):
        results = rank_for_disease(DISEASE, weights=WEIGHTS, top_n=2, features=_features(), app_data=_app_data())
        assert len(results) == 2

    def test_top_n_none_returns_every_candidate(self):
        results = rank_for_disease(DISEASE, weights=WEIGHTS, top_n=None, features=_features(), app_data=_app_data())
        assert len(results) == 4

    def test_missing_evidence_is_per_target_only_now_all_six_are_built(self):
        """As of Milestone 4, UNAVAILABLE_EVIDENCE_CATEGORIES is empty — every
        category in a target's missing_evidence reflects that SPECIFIC
        target lacking that evidence, not a categorical, every-target gap."""
        results = rank_for_disease(DISEASE, weights=WEIGHTS, features=_features(), app_data=_app_data())
        assert UNAVAILABLE_EVIDENCE_CATEGORIES == {}

        t3 = next(r for r in results if r.target_id == "T3")  # missing__genetics=1, missing__network=1
        assert set(t3.missing_evidence) == {"genetics", "network"}

        t1 = next(r for r in results if r.target_id == "T1")  # nothing missing
        assert t1.missing_evidence == []

    def test_app_evidence_completeness_denominator_is_six(self):
        results = rank_for_disease(DISEASE, weights=WEIGHTS, features=_features(), app_data=_app_data())
        t1 = next(r for r in results if r.target_id == "T1")
        # T1 has all six built categories present.
        assert t1.app_evidence_completeness == pytest.approx(6 / len(APP_EVIDENCE_CATEGORIES))
        assert len(APP_EVIDENCE_CATEGORIES) == 6

        t3 = next(r for r in results if r.target_id == "T3")  # missing genetics + network
        assert t3.app_evidence_completeness == pytest.approx(4 / 6)

    def test_n_other_diseases_positive_is_attached_from_app_data(self):
        results = rank_for_disease(DISEASE, weights=WEIGHTS, features=_features(), app_data=_app_data())
        t1 = next(r for r in results if r.target_id == "T1")
        assert t1.n_other_diseases_positive == 3

    def test_no_label_derived_column_reaches_weighted_baseline_score(self, monkeypatch):
        """The score-first-join-second guarantee, exercised directly: patch
        WeightedBaseline.score to record what it was called with, and assert
        no label__* / xgboost_*/n_other_diseases_positive column is present."""
        import target_prioritization.services.target_ranking as target_ranking_module

        seen_columns: list[str] = []
        original_score = target_ranking_module.WeightedBaseline.score

        def spying_score(self, features):
            seen_columns.extend(features.columns)
            return original_score(self, features)

        monkeypatch.setattr(target_ranking_module.WeightedBaseline, "score", spying_score)
        rank_for_disease(DISEASE, weights=WEIGHTS, features=_features(), app_data=_app_data())

        leaked = [c for c in seen_columns if c.startswith("label__") or c.startswith("xgboost_") or c == "n_other_diseases_positive"]
        assert leaked == []

    def test_source_links_present_for_every_result(self):
        results = rank_for_disease(DISEASE, weights=WEIGHTS, features=_features(), app_data=_app_data())
        for r in results:
            assert set(r.source_links) == {"target", "disease", "evidence"}
            assert r.target_id in r.source_links["target"]
            assert DISEASE in r.source_links["disease"]


class TestLoadPrecomputedScores:
    def test_filters_to_one_disease(self):
        app_data = _app_data()
        other = app_data.with_columns(pl.lit("D2").alias("disease_id"))
        combined = pl.concat([app_data, other])
        result = load_precomputed_scores(DISEASE, app_data=combined)
        assert set(result.get_column("disease_id").unique().to_list()) == {DISEASE}


class TestNormalizeWeights:
    def test_rescales_to_sum_to_one(self):
        result = normalize_weights({"a": 2.0, "b": 2.0})
        assert result == {"a": 0.5, "b": 0.5}
        assert sum(result.values()) == pytest.approx(1.0)

    def test_preserves_relative_proportions(self):
        result = normalize_weights({"a": 1.0, "b": 3.0})
        assert result["b"] == pytest.approx(3 * result["a"])

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="at least one weight"):
            normalize_weights({})

    def test_negative_weight_raises(self):
        with pytest.raises(ValueError, match="Negative"):
            normalize_weights({"a": -1.0, "b": 2.0})

    def test_zero_sum_raises(self):
        with pytest.raises(ValueError, match="zero or less"):
            normalize_weights({"a": 0.0})
