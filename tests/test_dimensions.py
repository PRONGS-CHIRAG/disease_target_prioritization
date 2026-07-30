"""Tests for evidence-dimension aggregation and the guard-liveness check.

Covers the two decisions in `features/genetics.py` that most change the
ranking — max-within-dimension and null-not-zero — plus the staleness check
that keeps the leakage guard honest once denylisted datasources are correctly
filtered upstream.
"""

from __future__ import annotations

import polars as pl
import pytest

from target_prioritization.config import (
    DenylistRule,
    EvidenceDimension,
    FeaturesConfig,
    LeakageGuardConfig,
    load_features,
)
from target_prioritization.features.build_features import (
    _NON_FEATURE_COLUMNS,
    LeakageError,
    drop_denylisted_datasources,
    verify_guard_liveness,
)
from target_prioritization.features.druggability import prio_column
from target_prioritization.features.genetics import (
    build_dimension_scores,
    build_evidence_diversity,
)


@pytest.fixture
def evidence() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "target_id": ["A", "A", "A", "B", "C", "C"],
            "datasource": [
                "gwas_credible_sets",
                "eva",
                "europepmc",
                "europepmc",
                "impc",
                "clinical_precedence",
            ],
            "score": [0.9, 0.4, 0.8, 0.7, 0.6, 0.95],
            "evidence_count": [10, 2, 100, 50, 3, 1],
        }
    )


@pytest.fixture
def config() -> FeaturesConfig:
    """A minimal config mirroring the real dimension structure."""
    real = load_features()
    return FeaturesConfig(
        version=1,
        label=real.label,
        leakage_guard=real.leakage_guard,
        groups=real.groups,
        evidence_dimensions={
            "genetics": EvidenceDimension(
                description="genetics",
                datasources=["gwas_credible_sets", "eva", "orphanet"],
            ),
            "functional": EvidenceDimension(description="functional", datasources=["impc"]),
            "literature": EvidenceDimension(description="literature", datasources=["europepmc"]),
            "pathways": EvidenceDimension(description="pathways", datasources=["reactome"]),
        },
        druggability_flags=real.druggability_flags,
        safety_columns=real.safety_columns,
    )


class TestDimensionScores:
    def test_takes_the_max_within_a_dimension(self, evidence, config):
        """A target is as good as its best evidence of that kind.

        Target A has gwas=0.9 and eva=0.4. Mean would give 0.65 and punish A
        for the datasources that simply have not studied it.
        """
        scores = build_dimension_scores(evidence, config)
        row = scores.filter(pl.col("target_id") == "A").row(0, named=True)
        assert row["dim__genetics"] == pytest.approx(0.9)

    def test_absent_evidence_is_null_not_zero(self, evidence, config):
        """Context.md §32.3 — null means unstudied, zero means studied-and-absent."""
        scores = build_dimension_scores(evidence, config)
        row = scores.filter(pl.col("target_id") == "B").row(0, named=True)
        assert row["dim__genetics"] is None
        assert row["dim__literature"] == pytest.approx(0.7)

    def test_missing_indicators_track_the_nulls(self, evidence, config):
        scores = build_dimension_scores(evidence, config)
        row = scores.filter(pl.col("target_id") == "B").row(0, named=True)
        assert row["missing__genetics"] == 1
        assert row["missing__literature"] == 0

    def test_dimension_with_no_data_becomes_an_all_null_column(self, evidence, config):
        """The Parkinson's pathways case: declared, but OT has no rows for it.

        The column must still exist so the gap is visible downstream rather
        than silently absent from the schema.
        """
        scores = build_dimension_scores(evidence, config)
        assert "dim__pathways" in scores.columns
        assert scores.get_column("dim__pathways").null_count() == scores.height
        assert scores.get_column("missing__pathways").sum() == scores.height

    def test_unmapped_datasource_is_ignored(self, evidence, config):
        """clinical_precedence is in the fixture but no dimension claims it."""
        scores = build_dimension_scores(evidence, config)
        assert not [c for c in scores.columns if "clinical" in c]

    def test_every_target_gets_a_row(self, evidence, config):
        scores = build_dimension_scores(evidence, config)
        assert set(scores.get_column("target_id")) == {"A", "B", "C"}

    def test_empty_evidence_returns_typed_empty_frame(self, config):
        empty = pl.DataFrame(
            schema={
                "target_id": pl.String(),
                "datasource": pl.String(),
                "score": pl.Float64(),
                "evidence_count": pl.Int64(),
            }
        )
        scores = build_dimension_scores(empty, config)
        assert scores.is_empty()
        assert "dim__genetics" in scores.columns


class TestEvidenceDiversity:
    def test_counts_distinct_datasources(self, evidence):
        diversity = build_evidence_diversity(evidence, saturation=4)
        counts = dict(
            zip(
                diversity.get_column("target_id"),
                diversity.get_column("n_evidence_types"),
                strict=True,
            )
        )
        assert counts == {"A": 3, "B": 1, "C": 2}

    def test_scales_by_saturation(self, evidence):
        diversity = build_evidence_diversity(evidence, saturation=4)
        row = diversity.filter(pl.col("target_id") == "A").row(0, named=True)
        assert row["dim__evidence_diversity"] == pytest.approx(0.75)

    def test_saturates_at_one(self, evidence):
        """Above the cap the term must stop rewarding outliers."""
        diversity = build_evidence_diversity(evidence, saturation=2)
        values = diversity.get_column("dim__evidence_diversity").to_list()
        assert max(values) == pytest.approx(1.0)
        assert all(v <= 1.0 for v in values)


class TestDropDenylistedDatasources:
    def test_removes_the_label_datasource(self, evidence):
        filtered, dropped = drop_denylisted_datasources(evidence)
        assert dropped == ["clinical_precedence"]
        assert "clinical_precedence" not in filtered.get_column("datasource").to_list()

    def test_keeps_everything_else(self, evidence):
        filtered, _ = drop_denylisted_datasources(evidence)
        assert set(filtered.get_column("datasource")) == {
            "gwas_credible_sets",
            "eva",
            "europepmc",
            "impc",
        }

    def test_target_with_only_label_evidence_is_removed(self):
        """Correct, but it changes the row count — hence the explicit logging."""
        only_label = pl.DataFrame(
            {
                "target_id": ["ONLY_LABEL", "KEEP"],
                "datasource": ["clinical_precedence", "europepmc"],
                "score": [0.9, 0.5],
                "evidence_count": [1, 1],
            }
        )
        filtered, _ = drop_denylisted_datasources(only_label)
        assert set(filtered.get_column("target_id")) == {"KEEP"}

    def test_noop_when_nothing_is_denylisted(self):
        clean = pl.DataFrame(
            {
                "target_id": ["A"],
                "datasource": ["europepmc"],
                "score": [0.5],
                "evidence_count": [1],
            }
        )
        filtered, dropped = drop_denylisted_datasources(clean)
        assert dropped == []
        assert filtered.height == 1


class TestGuardLiveness:
    """The staleness check, asked against what the sources *could* produce.

    Checking the final matrix instead would report a correctly-filtered
    pipeline as stale, since the denylisted column is gone by design.
    """

    @pytest.fixture
    def guard(self) -> LeakageGuardConfig:
        return LeakageGuardConfig(
            enabled=True,
            denylist=[
                DenylistRule(
                    id="ot_clinical_precedence_datasource",
                    match="assoc_ds__clinical_precedence*",
                    reason="is the label",
                    required=True,
                )
            ],
        )

    def test_passes_when_the_guarded_column_exists_upstream(self, guard):
        universe = ["assoc_ds__clinical_precedence_score", "assoc_ds__europepmc_score"]
        verify_guard_liveness(universe, guard)  # must not raise

    def test_fails_when_upstream_renamed_the_datasource(self, guard):
        """The scenario the required flag exists for."""
        universe = ["assoc_ds__chembl_score", "assoc_ds__europepmc_score"]
        with pytest.raises(LeakageError, match="stale"):
            verify_guard_liveness(universe, guard)

    def test_disabled_guard_is_not_checked(self):
        verify_guard_liveness([], LeakageGuardConfig(enabled=False, denylist=[]))

    def test_real_config_is_live_against_release_26_06(self):
        """The shipped denylist must guard something that exists in this release."""
        universe = [
            "assoc_ds__clinical_precedence_score",
            "assoc_ds__europepmc_score",
            "prio__max_clinical_stage",
            "assoc_overall__score",
        ]
        verify_guard_liveness(universe, load_features().leakage_guard)


class TestPrioColumnNaming:
    """Prioritisation columns must be renamed before the guard sees them.

    The denylist globs over *column names*. Open Targets ships camelCase
    (`maxClinicalStage`), the denylist is written in snake_case
    (`prio__max_clinical_stage`), and without the rename the two never meet —
    a real leak vector reached the output parquet while the guard logged
    "leakage_guard_passed".
    """

    @pytest.mark.parametrize(
        ("field", "expected"),
        [
            ("maxClinicalStage", "prio__max_clinical_stage"),
            ("hasPocket", "prio__has_pocket"),
            ("hasSmallMoleculeBinder", "prio__has_small_molecule_binder"),
            ("geneticConstraint", "prio__genetic_constraint"),
            ("isCancerDriverGene", "prio__is_cancer_driver_gene"),
        ],
    )
    def test_camel_case_becomes_prefixed_snake_case(self, field, expected):
        assert prio_column(field) == expected

    def test_the_denylist_matches_the_renamed_column(self):
        """The join that was broken: rule pattern vs produced column name."""
        guard = load_features().leakage_guard
        assert guard.find_violations([prio_column("maxClinicalStage")]), (
            "prio_column() output must match a denylist rule, or the guard "
            "silently protects nothing"
        )

    def test_the_raw_camel_case_name_would_not_have_matched(self):
        """Documents why the rename exists at all."""
        guard = load_features().leakage_guard
        assert not guard.find_violations(["maxClinicalStage"])


class TestNonFeatureColumns:
    """The final assertion must check everything, not a prefix whitelist."""

    def test_identifier_columns_are_excluded(self):
        assert {"target_id", "gene_symbol", "disease_id"} <= _NON_FEATURE_COLUMNS

    def test_biotype_is_excluded_as_descriptive(self):
        assert "biotype" in _NON_FEATURE_COLUMNS

    def test_a_novel_column_name_is_still_checked(self):
        """An unanticipated column must be treated as a feature candidate.

        A prefix whitelist fails open on names nobody predicted; this
        non-feature allowlist fails closed.
        """
        surprising = "someNewUpstreamColumn"
        assert surprising not in _NON_FEATURE_COLUMNS


class TestRealDimensionConfig:
    def test_scored_dimensions_exclude_underscore_prefixed(self):
        config = load_features()
        assert "_unmapped" in config.evidence_dimensions
        assert "_unmapped" not in config.scored_dimensions

    def test_label_datasource_is_not_in_any_scored_dimension(self):
        """Belt and braces — the config validator enforces this at load time."""
        config = load_features()
        for name, dimension in config.scored_dimensions.items():
            assert "clinical_precedence" not in dimension.datasources, name
            assert "chembl" not in dimension.datasources, name

    def test_scored_dimensions_are_disjoint(self):
        config = load_features()
        seen: set[str] = set()
        for dimension in config.scored_dimensions.values():
            overlap = seen & set(dimension.datasources)
            assert not overlap, f"datasource double-counted: {overlap}"
            seen |= set(dimension.datasources)
