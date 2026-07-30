"""Tests for multi-disease label construction (Context.md §15, §37).

``build_labels_for_disease`` is pure — it takes evidence, clinical and family
frames as arguments rather than reading them itself — so these tests exercise
it against small synthetic frames instead of the downloaded release. See
milestone2.md §2 for the measurements against the real data that motivated
each of these behaviors.
"""

from __future__ import annotations

import polars as pl
import pytest

from target_prioritization.config import (
    DenylistRule,
    DiseaseSpec,
    FeaturesConfig,
    LabelConfig,
    LeakageGuardConfig,
)
from target_prioritization.data.labels import (
    REASON_EARLY_STAGE,
    REASON_NO_CLINICAL_EVIDENCE,
    REASON_UNKNOWN_STAGE,
    LabelError,
    _validate_stage_map,
    build_labels_for_disease,
)

STAGE_MAP = {
    "APPROVAL": 4,
    "PHASE_3": 3,
    "PHASE_2_3": 3,
    "PHASE_2": 2,
    "PHASE_1": 1,
    "UNKNOWN": None,
}


@pytest.fixture
def config() -> FeaturesConfig:
    return FeaturesConfig(
        version=1,
        label=LabelConfig(
            name="clinically_advanced_target",
            source="test/clinical_target",
            clinical_stage_map=STAGE_MAP,
            positive_min_clinical_stage=3,
            negative_definition="test negatives",
            expand_to_descendants=True,
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
def disease() -> DiseaseSpec:
    return DiseaseSpec(key="test_disease", name="Test disease", efo_id="MONDO_TEST", category="test")


@pytest.fixture
def family() -> list[str]:
    return ["MONDO_TEST", "MONDO_CHILD"]


@pytest.fixture
def evidence() -> pl.DataFrame:
    """Candidate universe for MONDO_TEST's own id.

    T1: genetics + the label datasource (scored; would survive the drop).
    T2: label datasource ONLY (clinical-only candidate; dropped entirely).
    T3, T4, T5, T6, T8: genetics only, no label datasource.
    T7 is deliberately ABSENT — see the family-positive-outside-candidates
    scenario below.
    """
    return pl.DataFrame(
        {
            "target_id": ["T1", "T1", "T2", "T3", "T4", "T5", "T6", "T8"],
            "datasource": [
                "gwas_credible_sets",
                "clinical_precedence",
                "clinical_precedence",
                "gwas_credible_sets",
                "gwas_credible_sets",
                "gwas_credible_sets",
                "gwas_credible_sets",
                "gwas_credible_sets",
            ],
            "score": [0.9, 0.99, 0.99, 0.5, 0.5, 0.5, 0.5, 0.5],
            "evidence_count": [3, 1, 1, 2, 2, 2, 2, 2],
        }
    )


@pytest.fixture
def clinical() -> pl.DataFrame:
    """clinical_target rows, already unnested (one row per direct disease).

    T1: phase 3 directly against MONDO_TEST -> positive.
    T2: approved directly against MONDO_TEST -> would be positive, but T2 has
        no non-label evidence so it never reaches the output.
    T4: phase 1 directly -> below threshold, negative.
    T5: UNKNOWN directly -> excluded from both classes.
    T6: phase 1 directly AND phase 3 against the CHILD disease -> the max
        across both rows (3) makes it positive; proves descendant expansion
        and per-target max both work.
    T7: phase 3 against the CHILD disease only, and T7 never appears in
        `evidence` at all -> family-positive but outside the candidate set.
    T8: phase 2/3 directly -> positive (stage 3 meets the threshold).
    T3 has no clinical_target row at all -> negative, no clinical evidence.
    """
    return pl.DataFrame(
        {
            "target_id": ["T1", "T2", "T4", "T5", "T6", "T6", "T7", "T8"],
            "disease_id_direct": [
                "MONDO_TEST",
                "MONDO_TEST",
                "MONDO_TEST",
                "MONDO_TEST",
                "MONDO_TEST",
                "MONDO_CHILD",
                "MONDO_CHILD",
                "MONDO_TEST",
            ],
            "max_clinical_stage": [
                "PHASE_3",
                "APPROVAL",
                "PHASE_1",
                "UNKNOWN",
                "PHASE_1",
                "PHASE_3",
                "PHASE_3",
                "PHASE_2_3",
            ],
        }
    )


class TestLabelling:
    def test_positive_above_threshold(self, disease, evidence, clinical, family, config):
        labels, _ = build_labels_for_disease(disease, evidence, clinical, family, config)
        row = labels.filter(pl.col("target_id") == "T1").row(0, named=True)
        assert row["label"] == 1
        assert row["label_reason"] == "positive_stage_ge_3"
        assert row["max_clinical_stage"] == 3

    def test_negative_below_threshold(self, disease, evidence, clinical, family, config):
        labels, _ = build_labels_for_disease(disease, evidence, clinical, family, config)
        row = labels.filter(pl.col("target_id") == "T4").row(0, named=True)
        assert row["label"] == 0
        assert row["label_reason"] == REASON_EARLY_STAGE

    def test_negative_with_no_clinical_evidence_at_all(self, disease, evidence, clinical, family, config):
        labels, _ = build_labels_for_disease(disease, evidence, clinical, family, config)
        row = labels.filter(pl.col("target_id") == "T3").row(0, named=True)
        assert row["label"] == 0
        assert row["label_reason"] == REASON_NO_CLINICAL_EVIDENCE
        assert row["max_clinical_stage"] is None

    def test_unknown_stage_is_excluded_not_negative(self, disease, evidence, clinical, family, config):
        """Context.md §34 — UNKNOWN must never be silently coerced to a class."""
        labels, _ = build_labels_for_disease(disease, evidence, clinical, family, config)
        row = labels.filter(pl.col("target_id") == "T5").row(0, named=True)
        assert row["label"] is None
        assert row["label_reason"] == REASON_UNKNOWN_STAGE

    def test_descendant_disease_counts_toward_the_parent(
        self, disease, evidence, clinical, family, config
    ):
        """A phase-3 drug for the child makes the parent-disease label positive."""
        labels, _ = build_labels_for_disease(disease, evidence, clinical, family, config)
        row = labels.filter(pl.col("target_id") == "T6").row(0, named=True)
        assert row["label"] == 1
        assert row["max_clinical_stage"] == 3  # the max across both rows, not the direct one (1)

    def test_direct_id_only_misses_the_descendant_positive(
        self, disease, evidence, clinical, config
    ):
        """Same target, no descendant expansion: only the direct row (phase 1) counts."""
        labels, _ = build_labels_for_disease(disease, evidence, clinical, ["MONDO_TEST"], config)
        row = labels.filter(pl.col("target_id") == "T6").row(0, named=True)
        assert row["label"] == 0
        assert row["label_reason"] == REASON_EARLY_STAGE


class TestClinicalOnlyCandidatesAreDropped:
    def test_clinical_only_target_is_absent_from_output(self, disease, evidence, clinical, family, config):
        labels, _ = build_labels_for_disease(disease, evidence, clinical, family, config)
        assert "T2" not in labels.get_column("target_id").to_list()

    def test_drop_is_counted_in_provenance(self, disease, evidence, clinical, family, config):
        _, prov = build_labels_for_disease(disease, evidence, clinical, family, config)
        assert prov["n_dropped_clinical_only"] == 1
        assert prov["n_full_candidates"] == 7  # T1, T2, T3, T4, T5, T6, T8
        assert prov["n_scored_candidates"] == 6


class TestFamilyPositiveOutsideCandidateSet:
    """The gap found while implementing, not while measuring: a target can be
    a positive for a descendant disease while Open Targets never associates
    it with the parent disease's own id at all."""

    def test_target_absent_from_evidence_is_excluded_not_crashed(
        self, disease, evidence, clinical, family, config
    ):
        labels, _ = build_labels_for_disease(disease, evidence, clinical, family, config)
        assert "T7" not in labels.get_column("target_id").to_list()

    def test_is_counted_in_provenance(self, disease, evidence, clinical, family, config):
        _, prov = build_labels_for_disease(disease, evidence, clinical, family, config)
        assert prov["n_family_positive_outside_own_candidate_set"] == 1

    def test_family_positive_buckets_reconcile_exactly(self, disease, evidence, clinical, family, config):
        """Every family positive (T1, T2, T6, T7, T8) lands in exactly one of
        three buckets: became a labelled positive, fell outside the
        candidate set entirely, or was dropped as clinical-only."""
        _, prov = build_labels_for_disease(disease, evidence, clinical, family, config)
        assert prov["n_family_positive"] == 5
        assert (
            prov["n_positive"]
            + prov["n_family_positive_outside_own_candidate_set"]
            + prov["n_family_positive_dropped_clinical_only"]
            == prov["n_family_positive"]
        )


class TestSensitivityCheck:
    def test_direct_only_positive_count_uses_the_same_population_as_n_positive(
        self, disease, evidence, clinical, family, config
    ):
        """n_positive_direct_only must be restricted to scored_candidates,
        same as n_positive — otherwise the two numbers differ partly because
        of descendant expansion and partly because of an unrelated
        population-size difference, and a reader comparing them would
        conclude expansion LOST positives instead of gaining them.

        T2 is a family/direct positive (APPROVAL) but is clinical-only, so it
        is excluded from both n_positive and n_positive_direct_only here —
        the sensitivity check isolates the expansion effect only."""
        _, prov = build_labels_for_disease(disease, evidence, clinical, family, config)
        assert prov["n_positive_direct_only"] == 2  # T1, T8 (T2 excluded: clinical-only)


class TestRowCountArithmetic:
    def test_every_scored_candidate_gets_exactly_one_row(
        self, disease, evidence, clinical, family, config
    ):
        labels, prov = build_labels_for_disease(disease, evidence, clinical, family, config)
        assert labels.height == prov["n_scored_candidates"]
        assert labels.get_column("target_id").n_unique() == labels.height

    def test_positive_plus_negative_plus_excluded_equals_total(
        self, disease, evidence, clinical, family, config
    ):
        labels, prov = build_labels_for_disease(disease, evidence, clinical, family, config)
        assert prov["n_positive"] + prov["n_negative"] + prov["n_excluded_unknown_stage"] == labels.height
        assert prov["n_positive"] == 3  # T1, T6, T8
        assert prov["n_negative"] == 2  # T3, T4
        assert prov["n_excluded_unknown_stage"] == 1  # T5

    def test_disease_id_is_stamped_on_every_row(self, disease, evidence, clinical, family, config):
        labels, _ = build_labels_for_disease(disease, evidence, clinical, family, config)
        assert set(labels.get_column("disease_id").to_list()) == {"MONDO_TEST"}


class TestMissingEfoId:
    def test_raises_without_resolved_id(self, evidence, clinical, family, config):
        unresolved = DiseaseSpec(key="x", name="X", efo_id=None, category="test")
        with pytest.raises(ValueError, match="no resolved efo_id"):
            build_labels_for_disease(unresolved, evidence, clinical, family, config)


class TestStageMapValidation:
    def test_unmapped_value_raises(self, config):
        with pytest.raises(LabelError, match="PHASE_4"):
            _validate_stage_map(["PHASE_3", "PHASE_4"], config.label)

    def test_fully_mapped_values_pass(self, config):
        _validate_stage_map(list(STAGE_MAP), config.label)  # must not raise
