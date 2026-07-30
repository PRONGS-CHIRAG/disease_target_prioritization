"""Transparent weighted baseline (Context.md §17.1, §36).

This is the first thing that has to work, and Context.md §36 forbids adding any
ML model before it does. Its value is diagnostic rather than scientific: the
weights are hand-set and the arithmetic is inspectable, so if established
disease genes surface near the top, the data pipeline is sound. A
gradient-boosted model failing the same way would give no such signal.

The weights in ``configs/model.yaml`` are illustrative and must never be
presented as scientifically validated (Context.md §17.1).

**Nulls become zero only here.** Everything upstream keeps "not studied"
distinct from "studied and found absent" (Context.md §32.3). Scoring has to
produce a number, so nulls are treated as zero at this final step — which means
a low score can mean either "weak evidence" or "no evidence". That ambiguity is
why ``evidence_completeness`` travels with the score and why
:meth:`WeightedBaseline.explain` reports which dimensions were missing.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import polars as pl

from target_prioritization.features.genetics import DIMENSION_PREFIX
from target_prioritization.utils.logging import get_logger

__all__ = ["CONTRIBUTION_PREFIX", "SCORE_COLUMN", "TargetExplanation", "WeightedBaseline"]

log = get_logger(__name__)

SCORE_COLUMN = "prioritization_score"
CONTRIBUTION_PREFIX = "contrib__"


def _score_summary(scores: pl.Series) -> dict[str, float]:
    """Summary stats for logging.

    Polars types its aggregations as a broad union covering temporal and
    string columns; this column is Float64 by construction, so the values are
    coerced here rather than scattering casts through the logging call.
    """

    def _as_float(value: object) -> float:
        return float(value) if isinstance(value, (int, float)) else 0.0

    return {
        "score_max": round(_as_float(scores.max()), 4),
        "score_median": round(_as_float(scores.median()), 4),
    }


@dataclass(slots=True)
class TargetExplanation:
    """Per-dimension breakdown of one target's score (Context.md §20.2)."""

    target_id: str
    gene_symbol: str | None
    score: float
    contributions: dict[str, float] = field(default_factory=dict)
    dimension_values: dict[str, float | None] = field(default_factory=dict)
    missing_dimensions: list[str] = field(default_factory=list)
    evidence_completeness: float = 0.0

    def top_contributors(self, n: int = 3) -> list[tuple[str, float]]:
        """The *n* dimensions contributing most to the score."""
        return sorted(self.contributions.items(), key=lambda kv: kv[1], reverse=True)[:n]


class WeightedBaseline:
    """Weighted sum of per-dimension evidence scores.

    Args:
        weights: Dimension name → weight. Must sum to 1.0. ``ModelConfig``
            validates the configured profiles; this class re-checks so a
            hand-constructed instance cannot silently rescale the output.
        dimension_prefix: Column prefix for dimension scores.

    Raises:
        ValueError: If *weights* is empty, contains negatives, or does not
            sum to 1.0.
    """

    def __init__(
        self,
        weights: dict[str, float],
        *,
        dimension_prefix: str = DIMENSION_PREFIX,
    ) -> None:
        if not weights:
            raise ValueError("WeightedBaseline requires at least one weight")
        if negative := {k: v for k, v in weights.items() if v < 0}:
            raise ValueError(f"Negative weight(s): {negative}")
        total = sum(weights.values())
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"Weights must sum to 1.0, got {total:.6f}")

        self.weights = dict(weights)
        self.dimension_prefix = dimension_prefix

    @property
    def dimensions(self) -> list[str]:
        return list(self.weights)

    def _column(self, dimension: str) -> str:
        return f"{self.dimension_prefix}{dimension}"

    def _require_columns(self, features: pl.DataFrame) -> None:
        missing = [d for d in self.weights if self._column(d) not in features.columns]
        if missing:
            present = sorted(c for c in features.columns if c.startswith(self.dimension_prefix))
            raise KeyError(
                f"Feature table is missing column(s) for weighted dimension(s) {missing}: "
                f"expected {[self._column(d) for d in missing]}. Present: {present}"
            )

    def score(self, features: pl.DataFrame) -> pl.DataFrame:
        """Score each target and attach per-dimension contributions.

        Scoring happens **within a single disease**. Context.md §32.4 notes that
        diseases differ enormously in evidence volume, so a score is only
        comparable to other scores for the same disease.

        Returns:
            *features* plus ``contrib__<dimension>`` for each weighted
            dimension, ``prioritization_score``, and ``evidence_completeness``
            (share of weighted dimensions backed by actual evidence).

        Raises:
            KeyError: If a weighted dimension has no corresponding column.
        """
        self._require_columns(features)

        scored = features.with_columns(
            [
                (pl.col(self._column(dimension)).fill_null(0.0) * weight).alias(
                    f"{CONTRIBUTION_PREFIX}{dimension}"
                )
                for dimension, weight in self.weights.items()
            ]
        )

        scored = scored.with_columns(
            pl.sum_horizontal([pl.col(f"{CONTRIBUTION_PREFIX}{d}") for d in self.weights]).alias(
                SCORE_COLUMN
            ),
            pl.mean_horizontal(
                [pl.col(self._column(d)).is_not_null().cast(pl.Float64) for d in self.weights]
            ).alias("evidence_completeness"),
        )

        log.info(
            "baseline_scored",
            targets=scored.height,
            dimensions=self.dimensions,
            **_score_summary(scored.get_column(SCORE_COLUMN)),
        )
        return scored

    def rank(self, scored: pl.DataFrame, top_n: int | None = None) -> pl.DataFrame:
        """Add a 1-based ``rank`` column, highest score first.

        Ties break on gene symbol, then on ``target_id``. Context.md §33
        requires reproducibility, and the final sort key must be **unique** for
        that to hold: DuckDB's parallel scan gives no row-order guarantee, so
        any group of rows the sort cannot separate comes back differently
        ordered on each run.

        Gene symbol alone is not enough. Open Targets 26.06 contains distinct
        Ensembl IDs sharing a symbol — two `calpastatin` entries, one
        protein-coding and one lncRNA — and tied rows like those swapped
        between runs, making the written parquet differ byte-for-byte even
        though the scores were identical.
        """
        sort_columns = [SCORE_COLUMN]
        descending = [True]
        if "gene_symbol" in scored.columns:
            sort_columns.append("gene_symbol")
            descending.append(False)
        # Unique final key, guaranteeing a total order.
        sort_columns.append("target_id")
        descending.append(False)

        ranked = scored.sort(sort_columns, descending=descending, nulls_last=True).with_row_index(
            "rank", offset=1
        )
        return ranked.head(top_n) if top_n else ranked

    def explain(self, scored: pl.DataFrame, target_id: str) -> TargetExplanation:
        """Per-dimension breakdown for one target.

        This is what makes the baseline transparent: contributions sum exactly
        to the score, so a reader can see why a target ranked where it did
        without needing SHAP.

        Raises:
            KeyError: If *target_id* is not present in *scored*.
        """
        rows = scored.filter(pl.col("target_id") == target_id)
        if rows.is_empty():
            raise KeyError(f"Target {target_id!r} not present in the scored frame")
        row = rows.row(0, named=True)

        dimension_values = {d: row.get(self._column(d)) for d in self.weights}
        return TargetExplanation(
            target_id=target_id,
            gene_symbol=row.get("gene_symbol"),
            score=row[SCORE_COLUMN],
            contributions={d: row[f"{CONTRIBUTION_PREFIX}{d}"] for d in self.weights},
            dimension_values=dimension_values,
            missing_dimensions=[d for d, v in dimension_values.items() if v is None],
            evidence_completeness=row.get("evidence_completeness") or 0.0,
        )

    def ablate(self, features: pl.DataFrame, drop: list[str]) -> pl.DataFrame:
        """Re-score with *drop* removed and the remaining weights renormalized.

        Context.md §32.2 requires measuring performance with and without
        literature features, since publication volume rewards well-studied genes
        rather than important ones. Renormalizing rather than zeroing keeps the
        score on the same 0-1 scale, so the two rankings compare directly.

        Raises:
            ValueError: If dropping *drop* leaves no weight behind.
        """
        remaining = {d: w for d, w in self.weights.items() if d not in drop}
        total = sum(remaining.values())
        if not remaining or total <= 0:
            raise ValueError(f"Dropping {drop} leaves no weighted dimensions")

        renormalized = {d: w / total for d, w in remaining.items()}
        log.info("ablation", dropped=drop, renormalized_weights=renormalized)
        return WeightedBaseline(renormalized, dimension_prefix=self.dimension_prefix).score(
            features
        )
