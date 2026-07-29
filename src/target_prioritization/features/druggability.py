"""Druggability and safety features (Context.md §14.6, §14.7).

Built from Open Targets ``target`` (tractability, safetyLiabilities, constraint)
and ``target_prioritisation``.

The distinction that keeps these features legitimate: they describe whether a
target *can* be drugged — does it have a binding pocket, is it on the membrane,
is there a chemical probe — not whether a drug for this disease already exists.
The latter is the label. ``target_prioritisation.maxClinicalStage`` crosses that
line and is denylisted in ``configs/features.yaml``.

Safety features are risk signals, never toxicity predictions (Context.md §14.7,
§31.7): a druggable target may still be unsafe, and this data cannot say.
"""

from __future__ import annotations

import polars as pl

__all__ = ["build_druggability_features", "build_safety_features"]


def build_druggability_features(gene_ids: list[str]) -> pl.DataFrame:
    """Derive tractability features. See ``groups.druggability``.

    Raises:
        LeakageError: If a clinical-stage column reaches the output.
    """
    raise NotImplementedError("Milestone 1 — see configs/features.yaml groups.druggability")


def build_safety_features(gene_ids: list[str]) -> pl.DataFrame:
    """Derive safety features. See ``groups.safety``."""
    raise NotImplementedError("Milestone 1 — see configs/features.yaml groups.safety")
