"""Tests for the leakage guard.

Context.md §16 and §32.1 name label leakage as the central scientific risk of
this project. These tests exist to prove the guard actually fires — a guard
that silently passes everything is worse than no guard, because it manufactures
confidence.
"""

from __future__ import annotations

import polars as pl
import pytest

from target_prioritization.config import DenylistRule, LeakageGuardConfig, load_features
from target_prioritization.features.build_features import (
    LeakageError,
    assert_no_leakage,
    check_leakage,
    select_feature_columns,
)

SAFE_COLUMNS = [
    "assoc_ds__gwas_credible_sets_score",
    "assoc_ds__europepmc_score",
    "expr__max_tpm",
    "net__degree",
    "prio__has_pocket",
]


@pytest.fixture
def guard() -> LeakageGuardConfig:
    """A guard mirroring the real config, with only required rules."""
    return LeakageGuardConfig(
        enabled=True,
        denylist=[
            DenylistRule(
                id="ot_chembl_datasource",
                match="assoc_ds__chembl*",
                reason="ChEMBL evidence defines the label",
                required=True,
            ),
            DenylistRule(
                id="prioritisation_max_clinical_stage",
                match="prio__max_clinical_stage",
                reason="derived from clinical development status",
                required=True,
            ),
            DenylistRule(
                id="ot_overall_association_score",
                match="assoc_overall__*",
                reason="aggregates the clinical evidence behind the label",
                required=False,
            ),
        ],
    )


class TestGuardFires:
    """The direct failure: a denylisted column reaches the matrix."""

    def test_chembl_datasource_is_rejected(self, guard):
        columns = [*SAFE_COLUMNS, "assoc_ds__chembl_score", "prio__max_clinical_stage"]

        with pytest.raises(LeakageError) as exc:
            assert_no_leakage(columns, guard)

        assert "assoc_ds__chembl_score" in str(exc.value)
        assert "ot_chembl_datasource" in str(exc.value)

    def test_overall_score_is_rejected(self, guard):
        """Context.md §16, first leakage example."""
        columns = [
            *SAFE_COLUMNS,
            "assoc_overall__score",
            "assoc_ds__chembl_score",
            "prio__max_clinical_stage",
        ]

        with pytest.raises(LeakageError, match="assoc_overall__score"):
            assert_no_leakage(columns, guard)

    def test_max_clinical_stage_is_rejected(self, guard):
        """The easy one to miss: the rest of that table is safe."""
        columns = [*SAFE_COLUMNS, "assoc_ds__chembl_score", "prio__max_clinical_stage"]
        report = check_leakage(columns, guard)
        assert "prioritisation_max_clinical_stage" in report.violations

    def test_error_names_every_violation_not_just_the_first(self, guard):
        columns = [
            *SAFE_COLUMNS,
            "assoc_ds__chembl_score",
            "assoc_ds__chembl_evidence_count",
            "prio__max_clinical_stage",
            "assoc_overall__score",
        ]
        with pytest.raises(LeakageError) as exc:
            assert_no_leakage(columns, guard)

        message = str(exc.value)
        for column in (
            "assoc_ds__chembl_score",
            "assoc_ds__chembl_evidence_count",
            "prio__max_clinical_stage",
            "assoc_overall__score",
        ):
            assert column in message


class TestStaleRuleDetection:
    """The indirect failure: a rule that no longer matches anything.

    If Open Targets renames the `chembl` datasource, the rule protecting
    against it quietly stops applying. Nothing looks wrong — which is exactly
    the problem.
    """

    def test_required_rule_matching_nothing_fails(self, guard):
        # Every column is safe, so no violation — but the two required rules
        # matched nothing, meaning the guard is no longer verifying anything.
        with pytest.raises(LeakageError, match="matched nothing"):
            assert_no_leakage(SAFE_COLUMNS, guard)

    def test_stale_rules_are_reported_by_id(self, guard):
        report = check_leakage(SAFE_COLUMNS, guard)
        assert set(report.stale_rules) == {
            "ot_chembl_datasource",
            "prioritisation_max_clinical_stage",
        }

    def test_optional_rules_may_match_nothing(self, guard):
        """Only `required` rules are expected to be present in every release."""
        report = check_leakage(SAFE_COLUMNS, guard)
        assert "ot_overall_association_score" not in report.stale_rules

    def test_renamed_datasource_is_caught(self):
        """The scenario the `required` flag exists for."""
        guard = LeakageGuardConfig(
            enabled=True,
            denylist=[
                DenylistRule(
                    id="ot_chembl_datasource",
                    match="assoc_ds__chembl*",
                    reason="ChEMBL evidence defines the label",
                    required=True,
                )
            ],
        )
        # Upstream renamed `chembl` to `clinical_precedence`. The old rule now
        # matches nothing, and the leaking column sails through unnoticed —
        # unless the guard notices its own irrelevance.
        renamed = [*SAFE_COLUMNS, "assoc_ds__clinical_precedence_score"]

        with pytest.raises(LeakageError, match="matched nothing"):
            assert_no_leakage(renamed, guard)


class TestGuardPasses:
    def test_clean_columns_pass(self):
        guard = LeakageGuardConfig(
            enabled=True,
            denylist=[
                DenylistRule(
                    id="ot_chembl_datasource",
                    match="assoc_ds__chembl*",
                    reason="ChEMBL evidence defines the label",
                    required=False,
                )
            ],
        )
        assert_no_leakage(SAFE_COLUMNS, guard)  # must not raise

    def test_disabled_guard_passes_but_is_recorded(self):
        guard = LeakageGuardConfig(enabled=False, denylist=[])
        report = check_leakage(["assoc_ds__chembl_score"], guard)
        assert report.ok


class TestSelectFeatureColumns:
    def test_excludes_identifier_and_label_columns(self):
        guard = LeakageGuardConfig(enabled=True, denylist=[])
        frame = pl.DataFrame(
            {
                "disease_id": ["EFO_0002508"],
                "target_id": ["ENSG00000188906"],
                "gene_symbol": ["LRRK2"],
                "label": [1],
                "expr__max_tpm": [12.5],
                "net__degree": [42],
            }
        )
        assert select_feature_columns(frame, guard=guard) == ["expr__max_tpm", "net__degree"]

    def test_raises_when_a_leaking_column_is_present(self):
        guard = LeakageGuardConfig(
            enabled=True,
            denylist=[
                DenylistRule(
                    id="ot_chembl_datasource",
                    match="assoc_ds__chembl*",
                    reason="ChEMBL evidence defines the label",
                    required=True,
                )
            ],
        )
        frame = pl.DataFrame(
            {
                "target_id": ["ENSG00000188906"],
                "label": [1],
                "assoc_ds__chembl_score": [0.9],
            }
        )
        with pytest.raises(LeakageError):
            select_feature_columns(frame, guard=guard)

    def test_label_column_alone_does_not_trip_the_guard(self):
        """`label` is excluded as an identifier before the denylist runs."""
        guard = LeakageGuardConfig(
            enabled=True,
            denylist=[DenylistRule(id="label_columns", match="label*", reason="…", required=False)],
        )
        frame = pl.DataFrame({"label": [1], "expr__max_tpm": [12.5]})
        assert select_feature_columns(frame, guard=guard) == ["expr__max_tpm"]

    def test_excludes_biotype(self):
        """biotype is a string column; letting it through fails at model.fit(),
        not here, which is a much less legible place to discover it (Milestone 2
        hit exactly this before select_feature_columns was unified onto
        _NON_FEATURE_COLUMNS)."""
        guard = LeakageGuardConfig(enabled=True, denylist=[])
        frame = pl.DataFrame(
            {
                "target_id": ["ENSG00000188906"],
                "biotype": ["protein_coding"],
                "expr__max_tpm": [12.5],
            }
        )
        assert select_feature_columns(frame, guard=guard) == ["expr__max_tpm"]

    def test_check_stale_false_allows_an_already_filtered_frame(self):
        """A frame from build_disease_features/build_feature_table has already
        had its denylisted columns dropped — required rules correctly find
        nothing there, which is not staleness (Milestone 1's "Flaw 1")."""
        guard = LeakageGuardConfig(
            enabled=True,
            denylist=[
                DenylistRule(
                    id="ot_clinical_precedence_datasource",
                    match="assoc_ds__clinical_precedence*",
                    reason="the label",
                    required=True,
                )
            ],
        )
        frame = pl.DataFrame({"target_id": ["T1"], "assoc_ds__gwas_credible_sets_score": [0.5]})

        with pytest.raises(LeakageError, match="matched nothing"):
            select_feature_columns(frame, guard=guard)  # default check_stale=True

        assert select_feature_columns(frame, guard=guard, check_stale=False) == [
            "assoc_ds__gwas_credible_sets_score"
        ]


class TestRealConfig:
    """The shipped configs/features.yaml must be coherent."""

    def test_real_denylist_loads(self):
        guard = load_features().leakage_guard
        assert guard.enabled
        assert len(guard.denylist) >= 4

    def test_every_rule_has_a_reason(self):
        """A rule nobody can justify later gets deleted by the next reader."""
        for rule in load_features().leakage_guard.denylist:
            assert rule.reason.strip(), f"rule {rule.id} has no reason"

    def test_the_known_leakage_paths_are_covered(self):
        """Every column known to encode the label must be blocked.

        ``clinical_precedence`` is the name that matters in release 26.06;
        ``chembl`` is the pre-26.06 name for the same evidence. Both are listed
        because either can be the live one depending on the pinned release, and
        a test that names only the legacy one would pass against a config whose
        working rule had been deleted.
        """
        guard = load_features().leakage_guard
        leaking = [
            "assoc_ds__clinical_precedence_score",
            "assoc_ds__clinical_precedence_evidence_count",
            "assoc_ds__chembl_score",
            "assoc_overall__score",
            "prio__max_clinical_stage",
        ]
        violations = guard.find_violations(leaking)
        covered = {c for cols in violations.values() for c in cols}
        assert covered == set(leaking)

    def test_a_required_rule_covers_the_live_clinical_datasource(self):
        """The live datasource must be guarded by a rule that cannot go stale.

        ``required: true`` is what makes the guard fail loudly when an upstream
        rename stops it matching. If the live datasource is only covered by an
        optional rule, deleting that rule breaks nothing visibly — which is the
        failure this test exists to prevent.
        """
        guard = load_features().leakage_guard
        live_column = "assoc_ds__clinical_precedence_score"
        required_hits = [
            rule for rule in guard.denylist if rule.required and rule.matches(live_column)
        ]
        assert required_hits, (
            f"No required denylist rule matches {live_column!r}. The datasource "
            "recorded in docs/dataset_card.md for this release must be covered by "
            "a rule with required: true."
        )

    def test_deleting_the_live_rule_would_fail_the_guard(self):
        """Removing the live rule must break something — prove it does.

        Simulates a config where ``ot_clinical_precedence_datasource`` has been
        deleted, and asserts the guard then reports a stale required rule rather
        than quietly passing.
        """
        guard = load_features().leakage_guard
        without_live_rule = LeakageGuardConfig(
            enabled=True,
            denylist=[
                rule
                for rule in guard.denylist
                if not rule.matches("assoc_ds__clinical_precedence_score")
            ],
        )
        columns = ["assoc_ds__clinical_precedence_score", "expr__max_tpm"]

        # The leaking column now passes the denylist...
        assert not without_live_rule.find_violations(columns)
        # ...but the guard still fails, because a required rule went stale.
        with pytest.raises(LeakageError):
            assert_no_leakage(columns, without_live_rule)

    def test_real_feature_group_columns_pass_the_guard(self):
        """No declared feature is itself denylisted — the configs must agree."""
        config = load_features()
        declared = [f for group in config.groups.values() for f in group.features]
        violations = config.leakage_guard.find_violations(declared)
        assert not violations, f"features.yaml declares denylisted columns: {violations}"
