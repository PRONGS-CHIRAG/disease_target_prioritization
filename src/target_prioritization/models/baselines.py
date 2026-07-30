"""Non-learned comparison baselines (Context.md §17.1, §37).

Three scores evaluated alongside the trained models (``models/train.py``),
none of them "trained" in the sklearn sense — each is a direct lookup or
computation, with no fitting step and nothing to leak.

* :func:`score_open_targets_overall` — the database's own aggregate score,
  used ONLY as an evaluation baseline (Context.md §16); the leakage guard
  denylists it as a feature because training on it would reproduce the
  label by construction (the overall score aggregates the same clinical
  evidence the label is built from).
* :func:`score_random_ranking` — seeded uniform random score, the floor
  every real model or baseline must clear to be worth reporting at all.
* :func:`score_target_popularity` — milestone2.md §1's central
  methodological check. 78-98% of positives recur across the ten configured
  diseases, so a model can rank well under leave-one-disease-out purely by
  learning "this target is a positive somewhere else", without any
  disease-specific signal. This baseline scores candidates by EXACTLY that
  signal and nothing else. If it beats the trained models, that is the
  milestone's finding, not a footnote.
"""

from __future__ import annotations

import zlib

import duckdb
import numpy as np
import polars as pl

from target_prioritization.data import open_targets
from target_prioritization.models.evaluate import label_positive_prevalence_excluding
from target_prioritization.utils.logging import get_logger

__all__ = [
    "score_open_targets_overall",
    "score_random_ranking",
    "score_target_popularity",
]

log = get_logger(__name__)


def _stable_seed(seed: int, disease_id: str) -> int:
    """A per-disease seed derived deterministically from *disease_id*.

    Python's builtin ``hash()`` on a string is randomised per-process
    (``PYTHONHASHSEED``) unless explicitly disabled, which would silently
    break the "byte-identical reruns" requirement (Context.md §33) —
    ``zlib.crc32`` is stable across processes and interpreters by
    construction.
    """
    return (seed + zlib.crc32(disease_id.encode())) % (2**32)


def score_open_targets_overall(
    candidates: pl.DataFrame,
    disease_id: str,
    con: duckdb.DuckDBPyConnection | None = None,
) -> pl.DataFrame:
    """Open Targets' own overall association score, as an evaluation baseline.

    Args:
        candidates: Must have ``target_id`` for *disease_id*'s candidates.
        disease_id: Restricts the lookup to one disease.

    Returns:
        ``disease_id``, ``target_id``, ``score``. A candidate absent from
        ``association_overall_direct`` gets a null score — should not
        happen (every candidate with any evidence gets an overall row,
        verified: release 26.06 gives exactly one overall row per candidate
        for every configured disease) but logged rather than assumed
        impossible.
    """
    overall = open_targets.load_overall_association_scores(disease_id, con)
    scored = (
        candidates.select("target_id")
        .unique()
        .join(overall, on="target_id", how="left")
        .rename({"assoc_overall__score": "score"})
        .with_columns(pl.lit(disease_id).alias("disease_id"))
        .select(["disease_id", "target_id", "score"])
    )
    n_missing = scored.filter(pl.col("score").is_null()).height
    if n_missing:
        log.warning(
            "open_targets_overall_baseline_missing_scores",
            disease_id=disease_id,
            n_missing=n_missing,
            total=scored.height,
        )
    return scored


def score_random_ranking(candidates: pl.DataFrame, disease_id: str, *, seed: int) -> pl.DataFrame:
    """Uniform random score per candidate.

    Seeded per disease (:func:`_stable_seed`) rather than globally, so
    re-scoring one disease alone reproduces exactly the same random scores
    as scoring all ten together — a global RNG advanced disease-by-disease
    would make each disease's scores depend on which diseases were scored
    before it, silently breaking that property (Context.md §33).
    """
    target_ids = (
        candidates.select("target_id").unique().sort("target_id").get_column("target_id").to_list()
    )
    rng = np.random.default_rng(_stable_seed(seed, disease_id))
    scores = rng.random(len(target_ids))
    return pl.DataFrame(
        {"disease_id": [disease_id] * len(target_ids), "target_id": target_ids, "score": scores}
    )


def score_target_popularity(
    candidates: pl.DataFrame,
    labels: pl.DataFrame,
    disease_id: str,
) -> pl.DataFrame:
    """Score = number of OTHER diseases (never *disease_id* itself) where the
    target is a labelled positive.

    Uses :func:`~target_prioritization.models.evaluate.label_positive_prevalence_excluding`
    — the identical function :func:`~target_prioritization.models.evaluate.novel_only_labels`-based
    stratification uses to decide which positives are "seen elsewhere" in
    training folds. Sharing the function means the baseline that measures
    the cross-disease-popularity effect and the stratification that
    corrects for it cannot drift apart from each other's definition of
    "elsewhere".

    Returns:
        ``disease_id``, ``target_id``, ``score``. Candidates never positive
        in any other disease score 0 — a genuine, meaningful zero ("popular
        nowhere else"), unlike an evidence null elsewhere in this project.
    """
    prevalence = label_positive_prevalence_excluding(labels, disease_id)
    return (
        candidates.select("target_id")
        .unique()
        .join(prevalence, on="target_id", how="left")
        .with_columns(
            pl.col("n_other_diseases_positive").fill_null(0).cast(pl.Float64).alias("score"),
            pl.lit(disease_id).alias("disease_id"),
        )
        .select(["disease_id", "target_id", "score"])
    )
