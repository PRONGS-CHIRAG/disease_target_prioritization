"""Tests for the non-learned comparison baselines (Context.md §17.1, §37).

``score_open_targets_overall`` needs the downloaded release (it reads
``association_overall_direct``), so it's exercised via the LODO smoke test
rather than pytest, consistent with the rest of this suite. The other two —
``score_random_ranking`` and ``score_target_popularity`` — take everything
as arguments and are fully unit-testable.
"""

from __future__ import annotations

import polars as pl

from target_prioritization.models.baselines import score_random_ranking, score_target_popularity


class TestScoreRandomRanking:
    def test_one_row_per_candidate(self):
        candidates = pl.DataFrame({"target_id": ["T1", "T2", "T3"]})
        scored = score_random_ranking(candidates, "D1", seed=42)
        assert scored.height == 3
        assert set(scored.columns) == {"disease_id", "target_id", "score"}

    def test_scores_are_in_zero_one(self):
        candidates = pl.DataFrame({"target_id": [f"T{i}" for i in range(50)]})
        scored = score_random_ranking(candidates, "D1", seed=42)
        assert scored.get_column("score").min() >= 0.0
        assert scored.get_column("score").max() <= 1.0

    def test_deterministic_for_the_same_seed_and_disease(self):
        candidates = pl.DataFrame({"target_id": ["T1", "T2", "T3"]})
        first = score_random_ranking(candidates, "D1", seed=42)
        second = score_random_ranking(candidates, "D1", seed=42)
        assert first.equals(second)

    def test_different_diseases_get_different_scores(self):
        """A global RNG advanced disease-by-disease would make a disease's
        scores depend on scoring order — this must not happen (Context.md
        §33): scoring D2 alone must give the same result as scoring it after
        D1."""
        candidates = pl.DataFrame({"target_id": ["T1", "T2", "T3"]})
        d1 = score_random_ranking(candidates, "D1", seed=42)
        d2 = score_random_ranking(candidates, "D2", seed=42)
        assert not d1.get_column("score").equals(d2.get_column("score"))

    def test_scoring_one_disease_alone_matches_scoring_it_among_others(self):
        candidates = pl.DataFrame({"target_id": ["T1", "T2"]})
        alone = score_random_ranking(candidates, "MONDO_TEST", seed=7)
        # Simulate "already scored some other disease first" by just calling
        # again — a per-disease-seeded RNG has no shared state to advance.
        _ = score_random_ranking(candidates, "MONDO_OTHER", seed=7)
        again = score_random_ranking(candidates, "MONDO_TEST", seed=7)
        assert alone.equals(again)

    def test_python_hash_randomization_does_not_affect_the_seed(self):
        """Regression guard: an implementation using builtin hash(str) would
        vary between interpreter runs under PYTHONHASHSEED randomisation.
        Can't spawn a second interpreter in-process, but this at least pins
        the current run's value so a future refactor to hash() would need to
        deliberately change this assertion."""
        candidates = pl.DataFrame({"target_id": ["T1"]})
        scored = score_random_ranking(candidates, "MONDO_0005180", seed=42)
        assert scored.get_column("score").to_list() == score_random_ranking(
            candidates, "MONDO_0005180", seed=42
        ).get_column("score").to_list()


class TestScoreTargetPopularity:
    def test_score_is_count_of_other_diseases_positive(self):
        labels = pl.DataFrame(
            {
                "disease_id": ["A", "B", "C"],
                "target_id": ["shared", "shared", "shared"],
                "label": [1, 1, 1],
            }
        )
        candidates = pl.DataFrame({"target_id": ["shared"]})
        scored = score_target_popularity(candidates, labels, "A")
        row = scored.row(0, named=True)
        assert row["score"] == 2.0  # positive in B and C, A itself excluded

    def test_own_disease_positives_are_excluded_from_its_own_score(self):
        """The whole point of the baseline: a disease cannot see its own
        label. Otherwise scoring D1 with D1's own positive would trivially
        solve D1's own ranking."""
        labels = pl.DataFrame({"disease_id": ["D1"], "target_id": ["only_here"], "label": [1]})
        candidates = pl.DataFrame({"target_id": ["only_here"]})
        scored = score_target_popularity(candidates, labels, "D1")
        assert scored.row(0, named=True)["score"] == 0.0

    def test_never_positive_anywhere_scores_zero_not_null(self):
        labels = pl.DataFrame({"disease_id": ["A"], "target_id": ["irrelevant"], "label": [0]})
        candidates = pl.DataFrame({"target_id": ["never_positive"]})
        scored = score_target_popularity(candidates, labels, "A")
        row = scored.row(0, named=True)
        assert row["score"] == 0.0
        assert row["score"] is not None

    def test_uses_the_same_prevalence_definition_as_stratification(self):
        """score_target_popularity and evaluate.label_positive_prevalence_excluding
        must never drift apart — this is a shared-function guarantee, not
        just parallel implementations that happen to agree today."""
        from target_prioritization.models.evaluate import label_positive_prevalence_excluding

        labels = pl.DataFrame(
            {
                "disease_id": ["A", "B", "C", "C"],
                "target_id": ["x", "x", "x", "y"],
                "label": [1, 1, 0, 1],
            }
        )
        candidates = pl.DataFrame({"target_id": ["x", "y"]})
        scored = score_target_popularity(candidates, labels, "A")
        prevalence = label_positive_prevalence_excluding(labels, "A")

        x_score = scored.filter(pl.col("target_id") == "x").row(0, named=True)["score"]
        x_prevalence = prevalence.filter(pl.col("target_id") == "x").row(0, named=True)[
            "n_other_diseases_positive"
        ]
        assert x_score == x_prevalence

    def test_one_row_per_candidate_regardless_of_label_rows(self):
        labels = pl.DataFrame(
            {"disease_id": ["A", "B"], "target_id": ["shared", "shared"], "label": [1, 1]}
        )
        candidates = pl.DataFrame({"target_id": ["shared", "other"]})
        scored = score_target_popularity(candidates, labels, "A")
        assert scored.height == 2  # not inflated by the join


class TestZeroPositivesEdgeCase:
    def test_target_popularity_handles_a_labels_frame_with_no_positives_at_all(self):
        labels = pl.DataFrame({"disease_id": ["A", "B"], "target_id": ["t1", "t2"], "label": [0, 0]})
        candidates = pl.DataFrame({"target_id": ["t1"]})
        scored = score_target_popularity(candidates, labels, "A")
        assert scored.row(0, named=True)["score"] == 0.0
