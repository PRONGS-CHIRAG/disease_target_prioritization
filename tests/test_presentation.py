"""Tests for src/target_prioritization/presentation.py (milestone5_plan.md
§2.6): the UI-facing constants both the Streamlit app and the Next.js
frontend read, lifted out of app/common.py so neither hand-maintains its
own copy.
"""

from __future__ import annotations

from target_prioritization.config import load_model_config
from target_prioritization.presentation import (
    CUSTOM_LABEL,
    CUSTOM_SLUG,
    DIMENSION_KEYS,
    DIMENSION_LABELS,
    LIMITATIONS,
    NOT_BUILDABLE,
    SAFETY_FIRST_LABEL,
    SAFETY_FIRST_SLUG,
    SCENARIO_PRESETS,
)


class TestScenarioPresets:
    def test_every_preset_weight_key_is_a_real_dimension(self) -> None:
        for preset in SCENARIO_PRESETS:
            assert set(preset.weights) <= set(DIMENSION_KEYS)

    def test_every_preset_sums_to_one(self) -> None:
        for preset in SCENARIO_PRESETS:
            assert abs(sum(preset.weights.values()) - 1.0) < 1e-9, preset.slug

    def test_slugs_are_unique_and_stable_identifiers(self) -> None:
        slugs = [p.slug for p in SCENARIO_PRESETS]
        assert len(slugs) == len(set(slugs))
        assert all(slug.replace("_", "").isalnum() for slug in slugs), (
            "slugs travel in URLs (milestone5_plan.md §4.4) — must be URL-safe"
        )

    def test_safety_first_and_custom_slugs_do_not_collide_with_presets(self) -> None:
        preset_slugs = {p.slug for p in SCENARIO_PRESETS}
        assert SAFETY_FIRST_SLUG not in preset_slugs
        assert CUSTOM_SLUG not in preset_slugs
        assert SAFETY_FIRST_SLUG != CUSTOM_SLUG

    def test_labels_are_non_empty(self) -> None:
        for preset in SCENARIO_PRESETS:
            assert preset.label
        assert SAFETY_FIRST_LABEL and CUSTOM_LABEL


class TestDimensionKeysMatchModelConfig:
    def test_dimension_keys_match_milestone_1_weights(self) -> None:
        """The scenario-control UI is deliberately restricted to
        milestone_1_weights' five dimensions, never the six-dimension
        baseline_weights (model.yaml, milestone4_plan.md §2.4) — this test
        pins that restriction against the actual config so the two can't
        silently drift apart."""
        assert set(DIMENSION_KEYS) == set(load_model_config().milestone_1_weights)

    def test_every_dimension_key_has_a_label(self) -> None:
        assert set(DIMENSION_KEYS) == set(DIMENSION_LABELS)


class TestLimitationsAndNotBuildable:
    def test_limitations_non_empty_strings(self) -> None:
        assert LIMITATIONS
        assert all(isinstance(item, str) and item for item in LIMITATIONS)

    def test_not_buildable_has_a_reason_for_every_item(self) -> None:
        assert NOT_BUILDABLE
        assert all(isinstance(reason, str) and reason for reason in NOT_BUILDABLE.values())
