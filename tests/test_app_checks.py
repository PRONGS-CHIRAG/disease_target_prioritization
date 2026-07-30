"""Tests for the Milestone 3 acceptance checks (Context.md §21, §22).

Most checks in ``app_checks.py`` need the real processed artifacts (the
feature table, the fold models, ``app_scores.parquet``) — consistent with
the rest of this suite (see tests/test_milestone2.py's module docstring),
they are exercised as a real run rather than in pytest; that run is
``scripts/check_app.py``, which passed against the real pipeline. What's
covered here is the pure logic: ``is_label_derived``'s classification, and
a synthetic proof that the leakage-boundary probe's "can this even fire"
self-check actually distinguishes a well-ordered frame from a badly-ordered
one — the property the real check depends on to be trustworthy.
"""

from __future__ import annotations

from target_prioritization.app_checks import is_label_derived


class TestIsLabelDerived:
    def test_label_prefixed_columns_are_label_derived(self):
        assert is_label_derived("label__max_clinical_stage")
        assert is_label_derived("label__n_drugs")
        assert is_label_derived("label__drug_names")

    def test_xgboost_held_out_score_and_rank_are_label_derived(self):
        """These come from app_scores.parquet, built using labels — not
        because their VALUES leak the label, but because they must never be
        fed back into a model as a feature (models/predict.py doesn't
        consume its own output as input, but this module's job is to catch
        a display-only column being handed to a model at all, regardless of
        why)."""
        assert is_label_derived("xgboost_score_held_out")
        assert is_label_derived("xgboost_rank_held_out")

    def test_ot_overall_score_is_label_derived(self):
        """assoc_overall__score is deliberately named to match the existing
        denylist rule ot_overall_association_score (models/baselines.py) —
        this check must recognise the same name."""
        assert is_label_derived("assoc_overall__score")

    def test_popularity_badge_is_label_derived(self):
        assert is_label_derived("n_other_diseases_positive")

    def test_ordinary_feature_columns_are_not_label_derived(self):
        for column in ("dim__genetics", "missing__functional", "prio__has_small_molecule_binder", "gene_symbol"):
            assert not is_label_derived(column), column

    def test_disease_and_target_id_are_not_label_derived(self):
        assert not is_label_derived("disease_id")
        assert not is_label_derived("target_id")


class TestLeakageProbeCanDistinguishGoodFromBadOrdering:
    """Synthetic proof that the SELF-CHECK inside check_leakage_boundary
    (does a badly-ordered frame have detectable columns at all) does what
    it claims — a well-ordered (feature-only) frame has none, a
    badly-ordered (display-joined) frame has some."""

    def test_a_feature_only_frame_has_no_label_derived_columns(self):
        feature_columns = ["disease_id", "target_id", "gene_symbol", "dim__genetics", "missing__genetics"]
        assert not [c for c in feature_columns if is_label_derived(c)]

    def test_a_display_joined_frame_has_detectable_label_derived_columns(self):
        display_joined_columns = [
            "disease_id",
            "target_id",
            "gene_symbol",
            "dim__genetics",
            "xgboost_score_held_out",
            "n_other_diseases_positive",
            "label__max_clinical_stage",
        ]
        detected = [c for c in display_joined_columns if is_label_derived(c)]
        assert detected == ["xgboost_score_held_out", "n_other_diseases_positive", "label__max_clinical_stage"]
