"""Evidence-dimension aggregation from Open Targets (Context.md §14.1, §14.9).

Collapses per-datasource association scores into the scored dimensions declared
under ``evidence_dimensions`` in ``configs/features.yaml``.

Despite the module name (fixed by Context.md §26) this covers every
association-derived dimension — genetics, functional and literature — because
they differ only in which datasources feed them.

Two choices here carry real weight:

**Within a dimension, take the max.** A target is as good as its best evidence
of that kind. Averaging would penalise a gene with one strong GWAS signal for
lacking the other seven genetics datasources — a fact about how much the gene
has been studied, not about the gene.

**Absent evidence stays null, not zero.** Context.md §32.3: a zero asserts
"studied and found unrelated"; a null admits "not studied". Conflating them is
how understudied genes get ranked as bad targets. Nulls become zero only at the
final scoring step, and a ``missing__<dimension>`` column records where.
"""

from __future__ import annotations

import polars as pl

from target_prioritization.config import FeaturesConfig, load_features
from target_prioritization.utils.logging import get_logger

__all__ = [
    "DIMENSION_PREFIX",
    "MISSING_PREFIX",
    "add_cross_dimension_diversity",
    "build_dimension_scores",
    "build_evidence_diversity",
    "build_genetics_features",
]

log = get_logger(__name__)

DIMENSION_PREFIX = "dim__"
MISSING_PREFIX = "missing__"


def build_dimension_scores(
    evidence: pl.DataFrame,
    config: FeaturesConfig | None = None,
) -> pl.DataFrame:
    """Collapse long-format evidence into one score per dimension per target.

    Args:
        evidence: Long frame with ``target_id``, ``datasource``, ``score``.
            Denylisted datasources must already be removed by the caller.
        config: Feature config. Defaults to ``configs/features.yaml``.

    Returns:
        ``target_id`` plus ``dim__<name>`` (null where the target has no
        evidence of that kind) and ``missing__<name>`` (1 where null).
    """
    config = config or load_features()
    dimensions = config.scored_dimensions

    if evidence.is_empty():
        schema: dict[str, pl.DataType] = {"target_id": pl.String()}
        for name in dimensions:
            schema[f"{DIMENSION_PREFIX}{name}"] = pl.Float64()
            schema[f"{MISSING_PREFIX}{name}"] = pl.Int8()
        return pl.DataFrame(schema=schema)

    present = set(evidence.get_column("datasource").unique().to_list())
    result = evidence.select("target_id").unique()

    for name, dimension in dimensions.items():
        wanted = [d for d in dimension.datasources if d in present]

        if not wanted:
            # Declared but empty for this disease — true of any pathway
            # dimension for Parkinson's, where OT's reactome datasource has no
            # rows. Emit an all-null column rather than dropping it, so the gap
            # stays visible downstream instead of silently disappearing.
            log.info(
                "dimension_absent_for_disease",
                dimension=name,
                declared=dimension.datasources,
                note="no rows for any of its datasources; column will be all-null",
            )
            result = result.with_columns(
                pl.lit(None, dtype=pl.Float64).alias(f"{DIMENSION_PREFIX}{name}")
            )
            continue

        scores = (
            evidence.filter(pl.col("datasource").is_in(wanted))
            .group_by("target_id")
            .agg(pl.col("score").max().alias(f"{DIMENSION_PREFIX}{name}"))
        )
        result = result.join(scores, on="target_id", how="left")

        log.info(
            "dimension_built",
            dimension=name,
            datasources_used=wanted,
            datasources_absent=[d for d in dimension.datasources if d not in present],
            targets_with_evidence=scores.height,
        )

    return result.with_columns(
        [
            pl.col(f"{DIMENSION_PREFIX}{name}")
            .is_null()
            .cast(pl.Int8)
            .alias(f"{MISSING_PREFIX}{name}")
            for name in dimensions
        ]
    )


def build_evidence_diversity(
    evidence: pl.DataFrame,
    saturation: int = 4,
) -> pl.DataFrame:
    """Count distinct evidence types per target and scale to [0, 1].

    Context.md §14.9 argues evidence diversity may be more informative than
    evidence quantity. For Parkinson's that is measurably true: the five
    established genes hold more distinct evidence types than any other
    candidate, while 71% of candidates have exactly one type (literature).

    The count saturates at *saturation* so the term keeps discriminating in the
    range where candidates actually sit. Only 16 of 8,727 Parkinson's
    candidates exceed four types; uncapped, the term would mostly reward a
    handful of outliers.

    Returns:
        ``target_id``, ``n_evidence_types`` (raw count, kept for the report)
        and ``dim__evidence_diversity`` (scaled to [0, 1]).
    """
    if evidence.is_empty():
        return pl.DataFrame(
            schema={
                "target_id": pl.String(),
                "n_evidence_types": pl.UInt32(),
                f"{DIMENSION_PREFIX}evidence_diversity": pl.Float64(),
            }
        )

    return (
        evidence.group_by("target_id")
        .agg(pl.col("datasource").n_unique().alias("n_evidence_types"))
        .with_columns(
            (pl.col("n_evidence_types") / saturation)
            .clip(0.0, 1.0)
            .cast(pl.Float64)
            .alias(f"{DIMENSION_PREFIX}evidence_diversity")
        )
    )


def add_cross_dimension_diversity(features: pl.DataFrame) -> pl.DataFrame:
    """Add genetics+pathway and genetics+expression evidence co-occurrence flags.

    Context.md §14.9 lists "genetics plus expression agreement" and "genetics
    plus pathway agreement" among possible diversity features.
    ``configs/features.yaml`` has declared ``diversity__genetics_and_pathway``
    and ``diversity__genetics_and_expression`` since Milestone 1, but nothing
    computed them until Milestone 4 wired ``features/pathways.py`` and
    ``features/expression.py`` in. They need ``dim__genetics`` plus
    ``missing__pathways``/``missing__expression``, which live on the WIDE
    per-disease feature frame after those groups are joined — not on the long
    ``evidence`` frame :func:`build_evidence_diversity` works from — hence
    this is a separate function, called later in the assembly.

    Args:
        features: Must already carry ``dim__genetics``, ``missing__pathways``
            and ``missing__expression`` (i.e. called from
            ``build_features.build_disease_features`` after pathway and
            expression features are joined in).

    Returns:
        *features* plus ``diversity__genetics_and_pathway`` and
        ``diversity__genetics_and_expression`` (``Int8``, 1 iff the target
        has both kinds of evidence, 0 otherwise — never null, since absence
        of either side is itself a fact, not a missing measurement).
    """
    return features.with_columns(
        (
            pl.col(f"{DIMENSION_PREFIX}genetics").is_not_null()
            & (pl.col(f"{MISSING_PREFIX}pathways") == 0)
        )
        .cast(pl.Int8)
        .alias("diversity__genetics_and_pathway"),
        (
            pl.col(f"{DIMENSION_PREFIX}genetics").is_not_null()
            & (pl.col(f"{MISSING_PREFIX}expression") == 0)
        )
        .cast(pl.Int8)
        .alias("diversity__genetics_and_expression"),
    )


def build_genetics_features(associations: pl.DataFrame) -> pl.DataFrame:
    """Genetics dimension only (Context.md §14.1).

    Thin wrapper over :func:`build_dimension_scores`, kept because Context.md
    §26 names this entry point. Human genetic evidence is the strongest single
    predictor of clinical success in the published literature — and the place
    Context.md §31.4 bites hardest: association is not causation, and genetic
    evidence rarely reveals which *direction* a target should be modulated in.
    """
    scores = build_dimension_scores(associations)
    return scores.select([c for c in scores.columns if c == "target_id" or c.endswith("genetics")])
