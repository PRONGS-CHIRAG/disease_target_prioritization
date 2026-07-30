"""Tests for ranking/classification metrics and LODO splitting (Context.md §19, §37).

Ranking metric values are checked against hand-computed numbers, not just
"does it run" — a plausible-looking NDCG implementation is exactly the kind
of bug that would otherwise surface only as a suspiciously good or bad
headline number, the same failure mode Milestone 1 kept finding (milestone1.md
§5a: a wrapped-rank bug that silently reported the opposite of the truth).
"""

from __future__ import annotations

import math

import polars as pl
import pytest

from target_prioritization.models.evaluate import (
    average_precision,
    classification_metrics_for_disease,
    evaluate_ranking,
    hit_rate_at_k,
    label_positive_prevalence_excluding,
    leave_one_disease_out_splits,
    ndcg_at_k,
    novel_only_labels,
    precision_at_k,
    rank_within_disease,
    recall_at_k,
    reciprocal_rank,
)


def _ranked(labels: list[int], scores: list[float] | None = None, disease: str = "A") -> pl.DataFrame:
    n = len(labels)
    scores = scores or list(range(n, 0, -1))  # already-descending scores by default
    frame = pl.DataFrame(
        {
            "disease_id": [disease] * n,
            "target_id": [f"t{i}" for i in range(n)],
            "score": scores,
            "label": labels,
        }
    )
    return rank_within_disease(frame)


class TestRankWithinDisease:
    def test_sorts_by_score_descending(self):
        ranked = _ranked([0, 0, 0], scores=[0.1, 0.9, 0.5])
        assert ranked.sort("rank").get_column("score").to_list() == [0.9, 0.5, 0.1]

    def test_ties_break_on_target_id_ascending(self):
        frame = pl.DataFrame(
            {
                "disease_id": ["A", "A", "A"],
                "target_id": ["z", "a", "m"],
                "score": [0.5, 0.5, 0.9],
            }
        )
        ranked = rank_within_disease(frame).sort("rank")
        assert ranked.get_column("target_id").to_list() == ["m", "a", "z"]

    def test_ranks_are_independent_per_disease(self):
        frame = pl.DataFrame(
            {
                "disease_id": ["A", "A", "B", "B"],
                "target_id": ["a1", "a2", "b1", "b2"],
                "score": [0.1, 0.9, 0.1, 0.9],
            }
        )
        ranked = rank_within_disease(frame)
        for disease in ("A", "B"):
            sub = ranked.filter(pl.col("disease_id") == disease).sort("rank")
            assert sub.get_column("rank").to_list() == [1, 2]

    def test_repeated_calls_are_identical(self):
        """Determinism (Context.md §33) — same input, same output, every time."""
        frame = pl.DataFrame(
            {
                "disease_id": ["A"] * 4,
                "target_id": ["t1", "t2", "t3", "t4"],
                "score": [0.5, 0.5, 0.5, 0.9],
            }
        )
        first = rank_within_disease(frame)
        for _ in range(3):
            assert rank_within_disease(frame).equals(first)


class TestPrecisionAtK:
    def test_hand_computed(self):
        ranked = _ranked([1, 0, 1, 0, 0])
        assert precision_at_k(ranked, 1) == 1.0
        assert precision_at_k(ranked, 3) == pytest.approx(2 / 3)
        assert precision_at_k(ranked, 5) == pytest.approx(2 / 5)

    def test_k_larger_than_candidates_uses_actual_count_as_denominator(self):
        ranked = _ranked([1, 1])
        assert precision_at_k(ranked, 10) == 1.0  # 2 relevant / min(10, 2) = 1.0, not 0.2


class TestRecallAtK:
    def test_hand_computed(self):
        ranked = _ranked([1, 0, 1, 0, 0])
        assert recall_at_k(ranked, 1) == 0.5
        assert recall_at_k(ranked, 3) == 1.0

    def test_undefined_when_no_positives_returns_none_not_zero(self):
        ranked = _ranked([0, 0, 0])
        assert recall_at_k(ranked, 1) is None


class TestNdcgAtK:
    def test_hand_computed(self):
        ranked = _ranked([1, 0, 1, 0, 0])
        dcg3 = 1 / math.log2(2) + 1 / math.log2(4)
        idcg3 = 1 / math.log2(2) + 1 / math.log2(3)
        assert ndcg_at_k(ranked, 3) == pytest.approx(dcg3 / idcg3)

    def test_perfect_ranking_scores_one(self):
        ranked = _ranked([1, 1, 0, 0])
        assert ndcg_at_k(ranked, 2) == pytest.approx(1.0)

    def test_worst_ranking_scores_less_than_one(self):
        ranked = _ranked([0, 0, 1, 1])
        assert ndcg_at_k(ranked, 4) < 1.0

    def test_undefined_when_no_positives(self):
        ranked = _ranked([0, 0])
        assert ndcg_at_k(ranked, 2) is None

    def test_idcg_caps_at_available_candidates_not_just_k(self):
        """A disease with only 1 candidate can't have IDCG for 2 ideal hits."""
        ranked = _ranked([1])
        assert ndcg_at_k(ranked, 10) == pytest.approx(1.0)


class TestAveragePrecision:
    def test_hand_computed(self):
        ranked = _ranked([1, 0, 1, 0, 0])
        # AP = (1/2) * (precision@1 + precision@3) = (1/2) * (1/1 + 2/3)
        assert average_precision(ranked) == pytest.approx(0.5 * (1 / 1 + 2 / 3))

    def test_perfect_ranking_scores_one(self):
        ranked = _ranked([1, 1, 0])
        assert average_precision(ranked) == pytest.approx(1.0)

    def test_undefined_when_no_positives(self):
        assert average_precision(_ranked([0, 0])) is None


class TestReciprocalRank:
    def test_first_positive_at_rank_one(self):
        assert reciprocal_rank(_ranked([1, 0, 0])) == 1.0

    def test_first_positive_at_rank_three(self):
        assert reciprocal_rank(_ranked([0, 0, 1])) == pytest.approx(1 / 3)

    def test_undefined_when_no_positives(self):
        assert reciprocal_rank(_ranked([0, 0])) is None


class TestHitRateAtK:
    def test_hit_within_k(self):
        assert hit_rate_at_k(_ranked([0, 1, 0]), k=2) == 1.0

    def test_miss_within_k(self):
        assert hit_rate_at_k(_ranked([0, 0, 1]), k=1) == 0.0

    def test_undefined_when_no_positives(self):
        assert hit_rate_at_k(_ranked([0, 0]), k=1) is None


class TestClassificationMetrics:
    def test_roc_auc_and_pr_auc_need_both_classes(self):
        ranked = _ranked([1, 1, 1], scores=[0.9, 0.8, 0.7])  # no negatives
        result = classification_metrics_for_disease(ranked, ["roc_auc", "pr_auc"])
        assert result["roc_auc"] is None
        assert result["pr_auc"] is None

    def test_perfect_separation_gives_auc_one(self):
        ranked = _ranked([1, 1, 0, 0], scores=[0.9, 0.8, 0.2, 0.1])
        result = classification_metrics_for_disease(ranked, ["roc_auc", "pr_auc"])
        assert result["roc_auc"] == pytest.approx(1.0)
        assert result["pr_auc"] == pytest.approx(1.0)

    def test_threshold_controls_precision_recall_f1(self):
        ranked = _ranked([1, 0], scores=[0.6, 0.4])
        below = classification_metrics_for_disease(ranked, ["precision", "recall"], threshold=0.5)
        assert below["precision"] == 1.0
        assert below["recall"] == 1.0

        above = classification_metrics_for_disease(ranked, ["precision", "recall"], threshold=0.9)
        assert above["recall"] == 0.0  # nothing crosses 0.9, the one positive is missed

    def test_brier_score_undefined_for_out_of_zero_one_range_scores(self):
        """target_popularity's score is a raw count (0..9), not a
        probability — sklearn's brier_score_loss raises on that; this must
        return None instead of crashing the whole evaluation run."""
        ranked = _ranked([1, 0, 1], scores=[9.0, 0.0, 3.0])
        result = classification_metrics_for_disease(ranked, ["brier_score", "roc_auc"])
        assert result["brier_score"] is None
        assert result["roc_auc"] is not None  # rank-based metrics are unaffected by scale


class TestLeaveOneDiseaseOutSplits:
    def test_every_disease_held_out_exactly_once(self):
        features = pl.DataFrame({"disease_id": ["A", "A", "B", "C", "C", "C"]})
        splits = leave_one_disease_out_splits(features)
        assert len(splits) == 3

        held_out_sizes = sorted(len(test_idx) for _, test_idx in splits)
        assert held_out_sizes == [1, 2, 3]

    def test_train_and_test_partition_every_row(self):
        features = pl.DataFrame({"disease_id": ["A", "A", "B", "B"]})
        for train_idx, test_idx in leave_one_disease_out_splits(features):
            assert sorted(train_idx + test_idx) == [0, 1, 2, 3]
            assert set(train_idx) & set(test_idx) == set()

    def test_no_disease_appears_in_both_train_and_test_of_its_own_fold(self):
        features = pl.DataFrame({"disease_id": ["A", "A", "B", "B", "C"]})
        disease_ids = features.get_column("disease_id").to_list()
        for train_idx, test_idx in leave_one_disease_out_splits(features):
            train_diseases = {disease_ids[i] for i in train_idx}
            test_diseases = {disease_ids[i] for i in test_idx}
            assert train_diseases & test_diseases == set()

    def test_order_is_deterministic(self):
        features = pl.DataFrame({"disease_id": ["C", "A", "B"]})
        first = leave_one_disease_out_splits(features)
        second = leave_one_disease_out_splits(features)
        assert first == second


class TestNovelOnlyLabels:
    def test_positive_in_two_diseases_is_relabelled_negative_in_both(self):
        labels = pl.DataFrame(
            {
                "disease_id": ["A", "B", "C"],
                "target_id": ["shared", "shared", "unique"],
                "label": [1, 1, 1],
            }
        )
        result = novel_only_labels(labels)
        shared = result.filter(pl.col("target_id") == "shared").get_column("label").to_list()
        assert shared == [0, 0]

    def test_positive_in_only_one_disease_stays_positive(self):
        labels = pl.DataFrame(
            {
                "disease_id": ["A", "B", "C"],
                "target_id": ["shared", "shared", "unique"],
                "label": [1, 1, 1],
            }
        )
        result = novel_only_labels(labels)
        unique_row = result.filter(pl.col("target_id") == "unique").row(0, named=True)
        assert unique_row["label"] == 1

    def test_negatives_and_nulls_pass_through_unchanged(self):
        labels = pl.DataFrame(
            {
                "disease_id": ["A", "B"],
                "target_id": ["neg", "unk"],
                "label": [0, None],
            }
        )
        result = novel_only_labels(labels)
        assert result.get_column("label").to_list() == [0, None]

    def test_candidate_population_is_unchanged_only_labels_move(self):
        """The whole point: same rows, same ranking population — only
        relevance for the metric changes, so results stay comparable."""
        labels = pl.DataFrame(
            {
                "disease_id": ["A", "B"],
                "target_id": ["shared", "shared"],
                "label": [1, 1],
            }
        )
        result = novel_only_labels(labels)
        assert result.height == labels.height
        assert result.get_column("target_id").to_list() == labels.get_column("target_id").to_list()


class TestLabelPositivePrevalenceExcluding:
    def test_excludes_the_named_disease_own_positives(self):
        labels = pl.DataFrame(
            {
                "disease_id": ["A", "B", "C"],
                "target_id": ["shared", "shared", "unique"],
                "label": [1, 1, 1],
            }
        )
        prevalence = label_positive_prevalence_excluding(labels, "A")
        shared_row = prevalence.filter(pl.col("target_id") == "shared").row(0, named=True)
        assert shared_row["n_other_diseases_positive"] == 1  # only B counts, A excluded

    def test_target_positive_only_in_the_excluded_disease_is_absent(self):
        labels = pl.DataFrame(
            {"disease_id": ["A"], "target_id": ["only_in_a"], "label": [1]}
        )
        prevalence = label_positive_prevalence_excluding(labels, "A")
        assert "only_in_a" not in prevalence.get_column("target_id").to_list()


class TestEvaluateRanking:
    def test_null_labels_are_excluded_not_counted_as_negative(self):
        scored = pl.DataFrame(
            {"disease_id": ["A", "A"], "target_id": ["t1", "t2"], "score": [0.9, 0.1]}
        )
        labels = pl.DataFrame(
            {"disease_id": ["A", "A"], "target_id": ["t1", "t2"], "label": [1, None]}
        )
        result = evaluate_ranking(scored, labels, ["precision_at_1"])
        assert result["per_disease"]["A"]["n_candidates"] == 1  # t2 dropped

    def test_aggregate_averages_per_disease_not_pooled_rows(self):
        """Context.md §19.3 — a data-rich disease must not dominate the mean."""
        scored = pl.DataFrame(
            {
                "disease_id": ["A"] * 1 + ["B"] * 99,
                "target_id": [f"t{i}" for i in range(100)],
                "score": [1.0] + [0.5] * 99,
            }
        )
        labels = pl.DataFrame(
            {
                "disease_id": ["A"] * 1 + ["B"] * 99,
                "target_id": [f"t{i}" for i in range(100)],
                # A: 1 candidate, 1 positive -> precision@1 = 1.0
                # B: 99 candidates, only the last is positive -> precision@1 = 0.0
                "label": [1] + [0] * 98 + [1],
            }
        )
        result = evaluate_ranking(scored, labels, ["precision_at_1"])
        # Macro average of {A: 1.0, B: 0.0} is 0.5, not a row-weighted 0.99.
        assert result["aggregate"]["precision_at_1"] == pytest.approx(0.5)

    def test_metric_undefined_for_one_disease_is_excluded_from_aggregate(self):
        scored = pl.DataFrame(
            {"disease_id": ["A", "B"], "target_id": ["t1", "t2"], "score": [0.9, 0.5]}
        )
        labels = pl.DataFrame(
            {"disease_id": ["A", "B"], "target_id": ["t1", "t2"], "label": [1, 0]}
        )
        result = evaluate_ranking(scored, labels, ["recall_at_1"])
        assert result["aggregate"]["recall_at_1"] == pytest.approx(1.0)  # only A counted
        assert result["n_diseases_excluded_per_metric"]["recall_at_1"] == 1

    def test_classification_metrics_included_when_requested(self):
        scored = pl.DataFrame(
            {
                "disease_id": ["A", "A", "A", "A"],
                "target_id": ["t1", "t2", "t3", "t4"],
                "score": [0.9, 0.8, 0.2, 0.1],
            }
        )
        labels = pl.DataFrame(
            {
                "disease_id": ["A", "A", "A", "A"],
                "target_id": ["t1", "t2", "t3", "t4"],
                "label": [1, 1, 0, 0],
            }
        )
        result = evaluate_ranking(scored, labels, ["precision_at_1"], ["roc_auc"])
        assert result["aggregate"]["roc_auc"] == pytest.approx(1.0)

    def test_unrecognised_metric_name_raises(self):
        scored = pl.DataFrame({"disease_id": ["A"], "target_id": ["t1"], "score": [0.5]})
        labels = pl.DataFrame({"disease_id": ["A"], "target_id": ["t1"], "label": [1]})
        with pytest.raises(ValueError, match="Unrecognised ranking metric"):
            evaluate_ranking(scored, labels, ["not_a_real_metric"])
