"""Milestone 1 pipeline: Parkinson's rule-based target ranking (Context.md §36).

Orchestrates the ten §36 tasks end to end. Lives in the package rather than in
``scripts/`` so it stays importable and testable (Context.md §34); the notebook
and the CLI scripts are both thin layers over this.

Deliverables produced:

===========================================  ==========================
``data/processed/parkinsons_targets.parquet``  ranked candidate table
``reports/figures/parkinsons_top_targets.png`` evidence breakdown
``reports/parkinsons_baseline_report.md``      findings and limitations
===========================================  ==========================
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import polars as pl

from target_prioritization.config import (
    DiseaseSpec,
    load_diseases,
    load_features,
    load_model_config,
)
from target_prioritization.features.build_features import build_disease_features
from target_prioritization.models.baseline import (
    SCORE_COLUMN,
    TargetExplanation,
    WeightedBaseline,
)
from target_prioritization.utils.logging import get_logger
from target_prioritization.utils.paths import DATA_PROCESSED, ensure_dir

__all__ = [
    "KNOWN_PARKINSONS_GENES",
    "MilestoneResult",
    "output_name",
    "run_milestone_1",
]

log = get_logger(__name__)

# Established Parkinson's disease genes, used as a pipeline sanity check
# (Context.md §36 task 9, §19.5). These are *not* training labels and nothing
# in the scoring knows about them — they exist to answer one question: does a
# transparent score built from public evidence recover what the field already
# knows? If it does not, the fault is in the pipeline, not the biology.
#
# All five are named in Context.md §4's illustrative output.
KNOWN_PARKINSONS_GENES: dict[str, str] = {
    "ENSG00000188906": "LRRK2",
    "ENSG00000145335": "SNCA",
    "ENSG00000177628": "GBA1",
    "ENSG00000185345": "PRKN",
    "ENSG00000158828": "PINK1",
}

# Further Mendelian/risk PD genes used only for commentary in the report, never
# for scoring. Kept separate from the five above so the headline check stays
# honest and is not quietly widened until it passes.
ADDITIONAL_PD_GENES: dict[str, str] = {
    "ENSG00000116288": "PARK7",
    "ENSG00000069329": "VPS35",
    "ENSG00000184381": "PLA2G6",
    "ENSG00000186868": "MAPT",
    "ENSG00000127419": "TMEM175",
}

# Context.md §36 names these deliverables explicitly for Parkinson's.
PARQUET_NAME = "parkinsons_targets.parquet"
FIGURE_NAME = "parkinsons_top_targets.png"
REPORT_NAME = "parkinsons_baseline_report.md"


def output_name(disease: DiseaseSpec, template: str) -> str:
    """Output filename for *disease*.

    The §36 names are used verbatim for the milestone-1 disease. Any other
    disease gets its key as the prefix — otherwise ``--disease crohns_disease``
    would silently overwrite the Parkinson's deliverable with Crohn's data,
    leaving a file whose name says one thing and whose contents say another.

    >>> from types import SimpleNamespace
    >>> output_name(SimpleNamespace(milestone_1=False, key='crohns_disease'),
    ...             'parkinsons_targets.parquet')
    'crohns_disease_targets.parquet'
    """
    if disease.milestone_1:
        return template
    suffix = template.split("_", 1)[1] if "_" in template else template
    return f"{disease.key}_{suffix}"


@dataclass(slots=True)
class MilestoneResult:
    """Everything the milestone produced, for the report and the notebook."""

    disease: DiseaseSpec
    ranked: pl.DataFrame
    ablated: pl.DataFrame
    provenance: dict[str, Any]
    weights: dict[str, float]
    known_gene_ranks: dict[str, int | None] = field(default_factory=dict)
    known_gene_ranks_no_literature: dict[str, int | None] = field(default_factory=dict)
    additional_gene_ranks: dict[str, int | None] = field(default_factory=dict)
    explanations: list[TargetExplanation] = field(default_factory=list)

    @property
    def top_20(self) -> pl.DataFrame:
        return self.ranked.head(20)

    @property
    def known_genes_in_top_20(self) -> list[str]:
        return sorted(
            symbol
            for symbol, rank in self.known_gene_ranks.items()
            if rank is not None and rank <= 20
        )

    @property
    def known_genes_in_top_20_without_literature(self) -> list[str]:
        """How many established genes survive in the top 20 with literature removed.

        Reported because it qualifies the headline result: if the acceptance
        check only passes with literature evidence in play, then part of what
        it is measuring is publication volume rather than biology
        (Context.md §32.2).
        """
        return sorted(
            symbol
            for symbol, rank in self.known_gene_ranks_no_literature.items()
            if rank is not None and rank <= 20
        )

    @property
    def acceptance_passed(self) -> bool:
        """§36's real pass/fail: do all five established genes reach the top 20?"""
        return len(self.known_genes_in_top_20) == len(KNOWN_PARKINSONS_GENES)


def _ranks_for(ranked: pl.DataFrame, genes: dict[str, str]) -> dict[str, int | None]:
    """Rank of each gene, or None if absent from the candidate set."""
    lookup = dict(
        zip(
            ranked.get_column("target_id").to_list(),
            ranked.get_column("rank").to_list(),
            strict=True,
        )
    )
    return {symbol: lookup.get(target_id) for target_id, symbol in genes.items()}


def run_milestone_1(
    disease: DiseaseSpec | None = None,
    *,
    write_outputs: bool = True,
) -> MilestoneResult:
    """Run the full Milestone 1 pipeline.

    Args:
        disease: Disease to rank. Defaults to the one flagged ``milestone_1``
            in ``configs/diseases.yaml`` (Parkinson's).
        write_outputs: Write the parquet deliverable to ``data/processed``.

    Returns:
        A :class:`MilestoneResult` carrying the ranking, the literature
        ablation, provenance, and where the known genes landed.
    """
    disease = disease or load_diseases().milestone_1_disease()
    model_config = load_model_config()
    features_config = load_features()

    log.info("milestone_1_start", disease=disease.key, disease_id=disease.efo_id)

    # §36 tasks 1-5: resolve, retrieve, extract, normalize, build the table.
    features, provenance = build_disease_features(
        disease,
        config=features_config,
        saturation=model_config.evidence_diversity_saturation,
    )

    # §36 tasks 6-7: transparent weighted score, then rank.
    baseline = WeightedBaseline(model_config.milestone_1_weights)
    ranked = baseline.rank(baseline.score(features))

    # Context.md §32.2: the same ranking without literature, to expose how much
    # of it is publication volume rather than biology.
    ablated = baseline.rank(baseline.ablate(features, drop=["literature"]))

    known_ranks = _ranks_for(ranked, KNOWN_PARKINSONS_GENES)
    known_ranks_no_lit = _ranks_for(ablated, KNOWN_PARKINSONS_GENES)
    additional_ranks = _ranks_for(ranked, ADDITIONAL_PD_GENES)

    explanations = [
        baseline.explain(ranked, target_id)
        for target_id in ranked.head(10).get_column("target_id").to_list()
    ]

    provenance = {
        **provenance,
        "weights": model_config.milestone_1_weights,
        "known_gene_ranks": known_ranks,
        "ablation": "literature dropped, remaining weights renormalized",
    }

    result = MilestoneResult(
        disease=disease,
        ranked=ranked,
        ablated=ablated,
        provenance=provenance,
        weights=model_config.milestone_1_weights,
        known_gene_ranks=known_ranks,
        known_gene_ranks_no_literature=known_ranks_no_lit,
        additional_gene_ranks=additional_ranks,
        explanations=explanations,
    )

    log.info(
        "milestone_1_acceptance",
        known_genes_in_top_20=result.known_genes_in_top_20,
        passed=result.acceptance_passed,
        ranks=known_ranks,
    )
    # Reported unconditionally: if the check only passes with literature in
    # play, the headline number is partly measuring fame (Context.md §32.2).
    log.info(
        "milestone_1_acceptance_without_literature",
        known_genes_in_top_20=result.known_genes_in_top_20_without_literature,
        ranks=known_ranks_no_lit,
    )

    if write_outputs:
        ensure_dir(DATA_PROCESSED)
        output = DATA_PROCESSED / output_name(disease, PARQUET_NAME)
        ranked.write_parquet(output)

        # Provenance beside the data, matching the pattern used for raw
        # downloads (Context.md §33).
        (output.with_name(output.name + ".provenance.json")).write_text(
            json.dumps(provenance, indent=2, sort_keys=True, default=str) + "\n"
        )
        log.info("wrote_parquet", path=str(output), rows=ranked.height)

    return result


def ablation_movement(result: MilestoneResult, top_n: int = 20) -> pl.DataFrame:
    """How the top-N ranking shifts when literature is removed.

    Context.md §32.2 asks for performance with and without literature features.
    With no labels yet (Milestone 2), "performance" here is rank movement: a
    target that falls without literature was being carried by publication
    volume rather than by biological evidence.

    Returns:
        ``target_id``, ``gene_symbol``, ``rank``, ``rank_no_literature`` and
        ``rank_change`` — **negative means the target fell** (moved to a worse
        rank), positive means it rose.

    Note:
        Ranks are cast to a signed type first. ``with_row_index`` produces
        UInt32, and subtracting it unsigned wraps a fall of one place into
        4294967295 — a silent underflow that inverts the entire conclusion.
    """
    base = result.ranked.select(["target_id", "gene_symbol", "rank"]).head(top_n)
    without = result.ablated.select(["target_id", pl.col("rank").alias("rank_no_literature")])
    return (
        base.join(without, on="target_id", how="left")
        .with_columns(
            pl.col("rank").cast(pl.Int64),
            pl.col("rank_no_literature").cast(pl.Int64),
        )
        .with_columns(
            (pl.col("rank") - pl.col("rank_no_literature")).cast(pl.Int64).alias("rank_change")
        )
        .sort("rank")
    )


def score_column_summary(result: MilestoneResult) -> pl.DataFrame:
    """Distribution of the score and its dimensions, for the report."""
    columns = [SCORE_COLUMN, "evidence_completeness", "n_evidence_types"]
    columns += [c for c in result.ranked.columns if c.startswith("dim__")]
    return result.ranked.select([c for c in columns if c in result.ranked.columns]).describe()
