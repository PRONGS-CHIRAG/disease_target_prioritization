"""UI-facing presentation constants shared by every frontend (Context.md
§21, §38.5; milestone5_plan.md §2.6).

Moved out of ``app/common.py`` and ``app/pages/*`` so the Next.js frontend
(milestone5_plan.md) and the Streamlit app read the exact same constants
instead of each hand-maintaining a copy that can drift from
``configs/model.yaml``. This module holds only *display* constants —
labels, presets, standing limitations text — never scoring logic, which
stays in ``models/baseline.py`` and ``services/``.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "CUSTOM_LABEL",
    "CUSTOM_SLUG",
    "DIMENSION_KEYS",
    "DIMENSION_LABELS",
    "LIMITATIONS",
    "NOT_BUILDABLE",
    "SAFETY_FIRST_LABEL",
    "SAFETY_FIRST_SLUG",
    "SCENARIO_PRESETS",
    "ScenarioPreset",
]

# Every constant below was previously duplicated across app/common.py and
# app/pages/*.py (Context.md §21, Project_info.md §38.5) — see each
# docstring for the spec section and reasoning that shaped it; that
# reasoning did not change when the constants moved here.

LIMITATIONS = [
    "A high score does not prove a target will produce an effective drug (Context.md §31.1).",
    "Database evidence is incomplete and biased toward well-studied genes (Context.md §32.2).",
    "Association does not prove causation.",
    "Absence of evidence is not evidence of absence — check evidence completeness before "
    "reading a low score as a weak target (Context.md §32.3).",
    "Cross-disease target popularity drives most of the XGBoost score for most targets "
    "(milestone2.md §1) — a high XGBoost score is a weaker claim than the same score's "
    "novel-only counterpart would be.",
    "Predictions change when the underlying databases are updated (Context.md §32.7).",
    "This is a research-support prototype, not for medical diagnosis or treatment decisions.",
]

# The five dimensions every scenario preset and the custom-slider UI are
# restricted to — ``models.baseline.WeightedBaseline`` itself is generic
# over any ``dim__*`` column, but the scenario-control UI (and, by
# extension, ``RankedTarget.evidence`` /
# ``services.target_ranking._DISPLAY_DIMENSIONS``) is deliberately fixed to
# ``configs/model.yaml``'s ``milestone_1_weights`` dimensions, never the
# six-dimension ``baseline_weights`` (model.yaml: "reachable and reportable,
# not the new default"; milestone4_plan.md §2.4).
DIMENSION_KEYS = ["genetics", "evidence_diversity", "functional", "literature", "druggability"]

DIMENSION_LABELS: dict[str, str] = {
    "genetics": "Genetics",
    "evidence_diversity": "Evidence diversity",
    "functional": "Functional / biology",
    "literature": "Literature",
    "druggability": "Druggability",
}


@dataclass(slots=True, frozen=True)
class ScenarioPreset:
    """One named scenario-weight preset (Context.md §38.5).

    ``slug`` is the stable identifier used in shareable URLs
    (milestone5_plan.md §4.4) and API requests — it must never change once
    published, even if ``label`` is reworded. ``label`` is the prose shown
    in a picker.
    """

    slug: str
    label: str
    weights: dict[str, float]


# Scenario weight presets (Context.md §38.5, Project_info.md §21.4) mapped onto
# the five dimensions this baseline actually scores (configs/model.yaml
# milestone_1_weights) — Project_info.md §21.4's own examples reference a
# "clinical" and a "safety" weight, neither of which exists here: clinical
# evidence IS the training label (denylisted, never a feature — Context.md
# §16) and safety has no scored dimension at all (Context.md §14.7 forbids
# presenting it as a validated toxicity prediction). "Clinical-development"
# is approximated by druggability, the closest buildable proxy for "can this
# be drugged near-term". "Safety-first" is approximated by leaving the
# default weights and forcing `exclude_safety_concerns` on instead of
# inventing a safety weight that doesn't exist.
SCENARIO_PRESETS: list[ScenarioPreset] = [
    ScenarioPreset(
        slug="research",
        label="Research-focused (genetics-first)",
        weights={
            "genetics": 0.45,
            "evidence_diversity": 0.25,
            "functional": 0.15,
            "literature": 0.10,
            "druggability": 0.05,
        },
    ),
    ScenarioPreset(
        slug="clinical",
        label="Clinical-development-focused",
        weights={
            "genetics": 0.20,
            "evidence_diversity": 0.10,
            "functional": 0.15,
            "literature": 0.15,
            "druggability": 0.40,
        },
    ),
    ScenarioPreset(
        slug="novel",
        label="Novel-target-focused",
        weights={
            "genetics": 0.40,
            "evidence_diversity": 0.30,
            "functional": 0.25,
            "literature": 0.0,
            "druggability": 0.05,
        },
    ),
]

# Rendered so the UI never claims a scenario changed the score when it only
# changed a filter — Safety-first is exactly that case: default weights,
# `exclude_safety_concerns` forced on.
SAFETY_FIRST_SLUG = "safety_first"
SAFETY_FIRST_LABEL = "Safety-first (default weights + hide safety concerns)"
CUSTOM_SLUG = "custom"
CUSTOM_LABEL = "Custom"

# Target evidence page: items Context.md §21/§37/§38.4 ask for that no
# pipeline stage computes yet — unrelated to Reactome/GTEx/STRING
# (milestone4_plan.md), so Milestone 4 did not change their status. Rendered
# as an explicit placeholder naming what would be needed, never as a blank
# or a zero (Context.md §32.3).
NOT_BUILDABLE: dict[str, str] = {
    "Direction of effect": "nothing in the pipeline computes this yet (Context.md §37.6)",
    "Confidence level": "no calibrated uncertainty estimate exists yet (Context.md §30.13, §37.1)",
}
