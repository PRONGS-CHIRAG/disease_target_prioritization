"""Tests for the weighted baseline (Context.md §17.1, §36).

The baseline's whole value is that it is inspectable, so these tests check the
properties that make it inspectable: contributions sum exactly to the score,
nulls are handled the documented way, and the ranking is deterministic.
"""

from __future__ import annotations

import polars as pl
import pytest

from target_prioritization.models.baseline import (
    CONTRIBUTION_PREFIX,
    SCORE_COLUMN,
    WeightedBaseline,
)

WEIGHTS = {"genetics": 0.5, "literature": 0.3, "druggability": 0.2}


@pytest.fixture
def features() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "target_id": ["ENSG_A", "ENSG_B", "ENSG_C"],
            "gene_symbol": ["AAA", "BBB", "CCC"],
            "dim__genetics": [1.0, 0.5, None],
            "dim__literature": [0.0, 1.0, 1.0],
            "dim__druggability": [1.0, None, 0.5],
        }
    )


class TestConstruction:
    def test_rejects_weights_that_do_not_sum_to_one(self):
        """Otherwise the score silently changes scale between profiles."""
        with pytest.raises(ValueError, match=r"sum to 1\.0"):
            WeightedBaseline({"genetics": 0.5, "literature": 0.2})

    def test_rejects_negative_weights(self):
        with pytest.raises(ValueError, match="Negative weight"):
            WeightedBaseline({"genetics": 1.5, "literature": -0.5})

    def test_rejects_empty_weights(self):
        with pytest.raises(ValueError, match="at least one weight"):
            WeightedBaseline({})

    def test_accepts_floating_point_imprecision(self):
        """0.4+0.2+0.15+0.15+0.1 sums to 1.0000000000000002 in binary float."""
        WeightedBaseline({"a": 0.4, "b": 0.2, "c": 0.15, "d": 0.15, "e": 0.1})  # must not raise


class TestScoring:
    def test_score_is_the_weighted_sum(self, features):
        scored = WeightedBaseline(WEIGHTS).score(features)
        # AAA: 0.5*1.0 + 0.3*0.0 + 0.2*1.0 = 0.7
        assert scored.filter(pl.col("target_id") == "ENSG_A")[SCORE_COLUMN][0] == pytest.approx(0.7)

    def test_contributions_sum_exactly_to_the_score(self, features):
        """The property that makes this baseline explainable without SHAP."""
        scored = WeightedBaseline(WEIGHTS).score(features)
        contributions = [f"{CONTRIBUTION_PREFIX}{d}" for d in WEIGHTS]
        recomputed = scored.select(pl.sum_horizontal(contributions).alias("total"))
        for total, score in zip(
            recomputed.get_column("total"), scored.get_column(SCORE_COLUMN), strict=True
        ):
            assert total == pytest.approx(score)

    def test_nulls_are_treated_as_zero_in_the_score(self, features):
        """Documented behaviour: scoring must produce a number."""
        scored = WeightedBaseline(WEIGHTS).score(features)
        # CCC has null genetics: 0.5*0 + 0.3*1.0 + 0.2*0.5 = 0.4
        assert scored.filter(pl.col("target_id") == "ENSG_C")[SCORE_COLUMN][0] == pytest.approx(0.4)

    def test_evidence_completeness_distinguishes_weak_from_unstudied(self, features):
        """Context.md §32.3 — a low score alone cannot tell these apart."""
        scored = WeightedBaseline(WEIGHTS).score(features)
        completeness = dict(
            zip(
                scored.get_column("target_id"),
                scored.get_column("evidence_completeness"),
                strict=True,
            )
        )
        assert completeness["ENSG_A"] == pytest.approx(1.0)  # all three present
        assert completeness["ENSG_B"] == pytest.approx(2 / 3)  # druggability null
        assert completeness["ENSG_C"] == pytest.approx(2 / 3)  # genetics null

    def test_missing_dimension_column_raises(self, features):
        """A silently-absent dimension would score every target as if it were 0."""
        with pytest.raises(KeyError, match="dim__network"):
            WeightedBaseline({"genetics": 0.5, "network": 0.5}).score(features)

    def test_score_stays_within_zero_and_one(self, features):
        scored = WeightedBaseline(WEIGHTS).score(features)
        assert scored.get_column(SCORE_COLUMN).min() >= 0.0
        assert scored.get_column(SCORE_COLUMN).max() <= 1.0


class TestRanking:
    def test_ranks_descending_by_score(self, features):
        baseline = WeightedBaseline(WEIGHTS)
        ranked = baseline.rank(baseline.score(features))
        scores = ranked.get_column(SCORE_COLUMN).to_list()
        assert scores == sorted(scores, reverse=True)
        assert ranked.get_column("rank").to_list() == [1, 2, 3]

    def test_top_n_truncates(self, features):
        baseline = WeightedBaseline(WEIGHTS)
        assert baseline.rank(baseline.score(features), top_n=2).height == 2

    def test_ties_break_deterministically(self):
        """Context.md §33 — two identical runs must produce the same table."""
        tied = pl.DataFrame(
            {
                "target_id": ["ENSG_Z", "ENSG_A", "ENSG_M"],
                "gene_symbol": ["ZZZ", "AAA", "MMM"],
                "dim__genetics": [0.5, 0.5, 0.5],
                "dim__literature": [0.5, 0.5, 0.5],
                "dim__druggability": [0.5, 0.5, 0.5],
            }
        )
        baseline = WeightedBaseline(WEIGHTS)
        first = baseline.rank(baseline.score(tied)).get_column("gene_symbol").to_list()
        second = baseline.rank(baseline.score(tied)).get_column("gene_symbol").to_list()
        assert first == second == ["AAA", "MMM", "ZZZ"]

    def test_duplicate_symbols_still_order_deterministically(self):
        """The real bug: two Ensembl IDs sharing a symbol AND a score.

        Open Targets 26.06 has two `calpastatin` entries with different
        Ensembl IDs. Breaking ties on symbol alone left them unordered, so
        rows swapped between runs and the written parquet differed
        byte-for-byte. The final key must be unique.
        """
        duplicate_symbols = pl.DataFrame(
            {
                "target_id": ["ENSG00000310517", "ENSG00000153113"],
                "gene_symbol": ["CAST", "CAST"],
                "dim__genetics": [0.5, 0.5],
                "dim__literature": [0.5, 0.5],
                "dim__druggability": [0.5, 0.5],
            }
        )
        baseline = WeightedBaseline(WEIGHTS)
        ranked = baseline.rank(baseline.score(duplicate_symbols))
        # Fully determined by the unique target_id, ascending.
        assert ranked.get_column("target_id").to_list() == [
            "ENSG00000153113",
            "ENSG00000310517",
        ]

        shuffled = duplicate_symbols.reverse()
        assert (
            baseline.rank(baseline.score(shuffled)).get_column("target_id").to_list()
            == ranked.get_column("target_id").to_list()
        ), "input row order must not affect the output ranking"


class TestExplain:
    def test_explanation_contributions_sum_to_the_score(self, features):
        baseline = WeightedBaseline(WEIGHTS)
        scored = baseline.score(features)
        explanation = baseline.explain(scored, "ENSG_A")
        assert sum(explanation.contributions.values()) == pytest.approx(explanation.score)

    def test_explanation_names_missing_dimensions(self, features):
        baseline = WeightedBaseline(WEIGHTS)
        explanation = baseline.explain(baseline.score(features), "ENSG_C")
        assert explanation.missing_dimensions == ["genetics"]

    def test_top_contributors_are_ordered(self, features):
        baseline = WeightedBaseline(WEIGHTS)
        explanation = baseline.explain(baseline.score(features), "ENSG_A")
        contributors = explanation.top_contributors(2)
        assert [name for name, _ in contributors] == ["genetics", "druggability"]

    def test_unknown_target_raises(self, features):
        baseline = WeightedBaseline(WEIGHTS)
        with pytest.raises(KeyError, match="not present"):
            baseline.explain(baseline.score(features), "ENSG_NOPE")


class TestAblation:
    def test_remaining_weights_are_renormalized(self, features):
        """Context.md §32.2 — keeps both rankings on the same 0-1 scale."""
        baseline = WeightedBaseline(WEIGHTS)
        ablated = baseline.ablate(features, drop=["literature"])
        # genetics 0.5/0.7, druggability 0.2/0.7 -> AAA = 1.0*0.714 + 1.0*0.286 = 1.0
        assert ablated.filter(pl.col("target_id") == "ENSG_A")[SCORE_COLUMN][0] == pytest.approx(
            1.0
        )

    def test_ablated_score_stays_bounded(self, features):
        ablated = WeightedBaseline(WEIGHTS).ablate(features, drop=["literature"])
        assert ablated.get_column(SCORE_COLUMN).max() <= 1.0

    def test_dropping_everything_raises(self, features):
        with pytest.raises(ValueError, match="leaves no weighted dimensions"):
            WeightedBaseline(WEIGHTS).ablate(features, drop=list(WEIGHTS))

    def test_literature_only_target_falls_without_literature(self):
        """The publication-bias check (Context.md §32.2).

        FAMOUS is carried entirely by literature; GENETIC has moderate genetic
        evidence and no publications. With literature FAMOUS leads
        (0.3*1.0 = 0.30 vs 0.5*0.5 = 0.25); without it FAMOUS scores zero and
        GENETIC takes the top spot. This is exactly the reordering the ablation
        exists to expose.
        """
        frame = pl.DataFrame(
            {
                "target_id": ["FAMOUS", "GENETIC"],
                "gene_symbol": ["FAM", "GEN"],
                "dim__genetics": [None, 0.5],
                "dim__literature": [1.0, None],
                "dim__druggability": [None, None],
            }
        )
        baseline = WeightedBaseline(WEIGHTS)
        with_lit = baseline.rank(baseline.score(frame))
        without_lit = baseline.rank(baseline.ablate(frame, drop=["literature"]))

        assert with_lit.filter(pl.col("target_id") == "FAMOUS")["rank"][0] == 1
        assert without_lit.filter(pl.col("target_id") == "FAMOUS")["rank"][0] == 2
        assert without_lit.filter(pl.col("target_id") == "GENETIC")["rank"][0] == 1


class TestAblationMovement:
    """Regression tests for rank-movement arithmetic.

    `with_row_index` yields UInt32. Subtracting ranks without casting wraps a
    one-place fall into 4294967295, which silently inverts every conclusion
    drawn from the ablation — the report would name the most stable targets as
    the biggest fallers.
    """

    @pytest.fixture
    def result(self):
        from target_prioritization.milestone1 import MilestoneResult

        ranked = pl.DataFrame(
            {
                "target_id": ["UP", "DOWN", "SAME"],
                "gene_symbol": ["UP", "DOWN", "SAME"],
                "rank": pl.Series([1, 2, 3], dtype=pl.UInt32),
            }
        )
        ablated = pl.DataFrame(
            {
                "target_id": ["UP", "DOWN", "SAME"],
                "gene_symbol": ["UP", "DOWN", "SAME"],
                # UP improves 1->3 (a fall), DOWN improves 2->1 (a rise)
                "rank": pl.Series([3, 1, 3], dtype=pl.UInt32),
            }
        )
        return MilestoneResult(
            disease=None,  # type: ignore[arg-type]
            ranked=ranked,
            ablated=ablated,
            provenance={},
            weights={},
        )

    def test_a_fall_is_negative_not_a_huge_positive(self, result):
        from target_prioritization.milestone1 import ablation_movement

        movement = ablation_movement(result)
        changes = dict(
            zip(
                movement.get_column("gene_symbol"),
                movement.get_column("rank_change"),
                strict=True,
            )
        )
        assert changes["UP"] == -2, "a fall must be negative, not an unsigned wraparound"
        assert changes["DOWN"] == 1
        assert changes["SAME"] == 0

    def test_no_change_exceeds_the_candidate_count(self, result):
        """A wraparound shows up as an absurdly large magnitude."""
        from target_prioritization.milestone1 import ablation_movement

        movement = ablation_movement(result)
        assert movement.get_column("rank_change").abs().max() < 1000


class TestRealConfig:
    def test_milestone_1_weights_build_a_valid_baseline(self):
        from target_prioritization.config import load_model_config

        WeightedBaseline(load_model_config().milestone_1_weights)  # must not raise

    def test_milestone_1_weights_cover_the_scored_dimensions(self):
        """Every scored dimension in features.yaml must carry a weight.

        A dimension computed but never weighted is dead work; a weight with no
        dimension raises at score time. This catches the configs drifting apart.
        """
        from target_prioritization.config import load_features, load_model_config

        weighted = set(load_model_config().milestone_1_weights)
        computed = set(load_features().scored_dimensions)
        # evidence_diversity and druggability are derived, not association-based.
        derived = {"evidence_diversity", "druggability"}
        assert computed <= weighted, f"computed but unweighted: {computed - weighted}"
        assert weighted - computed == derived, (
            f"unexpected extra weights: {weighted - computed - derived}"
        )
