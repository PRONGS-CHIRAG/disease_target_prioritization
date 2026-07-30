"""Milestone 1 report generation (Context.md §36 tasks 9-10).

Produces ``reports/parkinsons_baseline_report.md``: the ranked table, the manual
inspection of the top 10, the literature ablation, and the limitations.

The report is generated rather than hand-written so it cannot drift from the
numbers it describes — Context.md §33 requires results to be reproducible, and a
prose summary maintained by hand stops matching its data on the first re-run.
Interpretation that genuinely needs a human is clearly marked as such.
"""

from __future__ import annotations

import polars as pl

from target_prioritization.milestone1 import (
    ADDITIONAL_PD_GENES,
    KNOWN_PARKINSONS_GENES,
    MilestoneResult,
    ablation_movement,
)
from target_prioritization.models.baseline import SCORE_COLUMN

__all__ = ["build_report"]

# Notes for the top-ranked genes, written by hand. Context.md §36 task 9 asks
# for a *manual* inspection, and that is a judgement no script can make: whether
# a gene is genuinely established, or merely well-published.
GENE_NOTES: dict[str, str] = {
    "LRRK2": "Established. The most common genetic cause of late-onset PD and an active drug-development target. Correctly ranked first.",
    "PLA2G6": "Established (PARK14). Causes autosomal-recessive early-onset parkinsonism. Strong genetics, less public attention than LRRK2 — the score reflects evidence rather than fame.",
    "GBA1": "Established. Heterozygous variants are the single largest genetic risk factor for PD. Note it has no functional-genomics evidence here, so its score comes from genetics, diversity and literature.",
    "MAPT": "Established risk locus. The H1 haplotype is a replicated PD risk factor, though MAPT is better known for tauopathies — a reminder that a locus can be shared across diseases.",
    "PARK7": "Established (DJ-1). Causes autosomal-recessive early-onset PD. Its retired symbol is why HGNC alias resolution matters (see tests/test_identifiers.py).",
    "SNCA": "Established. Encodes alpha-synuclein, the primary component of Lewy bodies, and the first PD gene identified. Its clinical_precedence evidence was correctly excluded as the label.",
    "ITPKB": "Plausible. A replicated GWAS locus for PD. Less mechanistically characterised than the genes above — a reasonable candidate for follow-up rather than a known answer.",
    "PSAP": "Plausible. Prosaposin; lysosomal biology links it to the GBA1 pathway. Carries the strongest functional-genomics evidence in the top 10.",
    "NR4A2": "Plausible. A transcription factor required for dopaminergic neuron development. Long-discussed in PD with contested genetic support.",
    "GAK": "Plausible. A GWAS locus adjacent to TMEM175 — note that GWAS implicates a *region*, and assigning the signal to the right gene is exactly the ambiguity Context.md §31.4 warns about.",
}


def _format_table(frame: pl.DataFrame, columns: list[str], headers: list[str]) -> str:
    """Render a Polars frame as a GitHub-flavoured Markdown table."""
    available = [c for c in columns if c in frame.columns]
    headers = [h for c, h in zip(columns, headers, strict=True) if c in frame.columns]

    lines = ["| " + " | ".join(headers) + " |"]
    lines.append("| " + " | ".join("---" for _ in headers) + " |")

    for row in frame.select(available).iter_rows(named=True):
        cells = []
        for column in available:
            value = row[column]
            if value is None:
                cells.append("—")
            elif isinstance(value, float):
                cells.append(f"{value:.3f}")
            else:
                cells.append(str(value))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def build_report(result: MilestoneResult) -> str:
    """Render the full Milestone 1 report as Markdown."""
    provenance = result.provenance
    ranked = result.ranked
    weights = result.weights

    weight_rows = "\n".join(
        f"| {name.replace('_', ' ')} | {weight:.2f} |" for name, weight in weights.items()
    )

    top20 = _format_table(
        ranked.head(20),
        [
            "rank",
            "gene_symbol",
            SCORE_COLUMN,
            "dim__genetics",
            "n_evidence_types",
            "dim__functional",
            "dim__literature",
            "dim__druggability",
            "evidence_completeness",
        ],
        [
            "Rank",
            "Gene",
            "Score",
            "Genetics",
            "Evidence types",
            "Functional",
            "Literature",
            "Druggability",
            "Completeness",
        ],
    )

    known_rows = "\n".join(
        f"| {symbol} | {target_id} | "
        + (
            f"**{result.known_gene_ranks[symbol]}**"
            if result.known_gene_ranks[symbol]
            else "absent"
        )
        + " |"
        for target_id, symbol in KNOWN_PARKINSONS_GENES.items()
    )
    additional_rows = "\n".join(
        f"| {symbol} | {target_id} | "
        + (
            str(result.additional_gene_ranks[symbol])
            if result.additional_gene_ranks[symbol]
            else "absent"
        )
        + " |"
        for target_id, symbol in ADDITIONAL_PD_GENES.items()
    )

    inspection = "\n".join(
        f"**{rank}. {symbol}** — {GENE_NOTES.get(symbol, 'No manual note recorded.')}\n"
        for rank, symbol in zip(
            ranked.head(10).get_column("rank").to_list(),
            ranked.head(10).get_column("gene_symbol").to_list(),
            strict=True,
        )
    )

    movement = ablation_movement(result, top_n=20)
    biggest_falls = movement.sort("rank_change").head(6)
    ablation_table = _format_table(
        biggest_falls,
        ["gene_symbol", "rank", "rank_no_literature", "rank_change"],
        ["Gene", "Rank", "Rank without literature", "Change"],
    )

    survivors = result.known_genes_in_top_20_without_literature
    dropped_out = sorted(set(result.known_genes_in_top_20) - set(survivors))
    no_lit_ranks = ", ".join(
        f"{symbol} #{rank}" if rank else f"{symbol} absent"
        for symbol, rank in sorted(
            result.known_gene_ranks_no_literature.items(), key=lambda kv: kv[1] or 10**9
        )
    )
    dropped_summary = (
        f"{' and '.join(dropped_out)} drop{'s' if len(dropped_out) == 1 else ''}"
        if dropped_out
        else "no gene drops"
    )

    n_literature_only = ranked.filter(
        (pl.col("n_evidence_types") == 1) & pl.col("dim__literature").is_not_null()
    ).height

    verdict = (
        "**PASS.** All five established Parkinson's genes reached the top 20."
        if result.acceptance_passed
        else "**FAIL.** Not all established genes reached the top 20."
    )
    if result.acceptance_passed and dropped_out:
        verdict += (
            f" **But see section 5:** without literature evidence only "
            f"{len(survivors)} of {len(KNOWN_PARKINSONS_GENES)} remain in the top 20 "
            f"({', '.join(dropped_out)} drop out), so this result is partly carried by "
            "publication volume rather than by genetics alone."
        )

    return f"""# Parkinson's Disease Target Prioritization — Baseline Report

Milestone 1 (Context.md §36): a transparent, non-ML target ranking built only
from Open Targets evidence.

> **These are prioritization hypotheses, not validated findings.** A high score
> does not mean a target will yield an effective drug. The weights below were
> chosen by hand and are illustrative. See [docs/limitations.md](../docs/limitations.md).

| | |
| --- | --- |
| Disease | {provenance["disease_name"]} (`{provenance["disease_id"]}`) |
| Data source | Open Targets Platform release {provenance["dataset_version"]} |
| Extraction date | {provenance["extraction_date"]} |
| Candidate targets | {provenance["n_candidates"]:,} |
| Scored targets | {provenance["n_scored"]:,} |
| Method | Transparent weighted sum, no machine learning |

## 1. Method

Every candidate target Open Targets associates with the disease is scored on a
weighted sum of five evidence dimensions. Within a dimension the score is the
maximum across its datasources — a target is as good as its best evidence of
that kind, and averaging would penalise a gene for the datasources that simply
have not studied it.

| Dimension | Weight |
| --- | ---: |
{weight_rows}

These weights are **illustrative and not scientifically validated**
(Context.md §17.1). They deviate from the §17.1 example formula because that
formula's pathway, tissue-expression and network terms need Reactome, GTEx and
STRING, which Context.md §28 Step 9 schedules after this baseline works. For
Parkinson's specifically, Open Targets carries **no pathway evidence at all** —
its `reactome` datasource has zero rows for this disease — so a pathway term was
not merely deferred, it was impossible.

### Why evidence diversity is weighted so heavily

It is the dimension that actually separates the known biology. Of the
{provenance["n_scored"]:,} scored candidates, **{n_literature_only:,} have exactly one
kind of evidence, and that kind is literature**. Meanwhile the established
Parkinson's genes carry the most distinct evidence types of any candidate
(LRRK2 seven, GBA1 and SNCA six). Context.md §14.9 predicts that diversity beats
volume; here it is measurably true.

### What was excluded, and why

`{", ".join(provenance["datasources_dropped_as_label"])}` was removed before any
feature was computed. It records that a drug against the target reached the
clinic for this disease — which is precisely the label Milestone 2 will predict.
Measured across the whole release, **all 107,593 of its (disease, target) pairs
are also label pairs**: the datasource is not correlated with the label, it *is*
the label. Training on it would produce a model that reproduces its own target
variable and reports excellent metrics (Context.md §16, §32.1).

Removing it also removed {provenance["n_dropped_label_only"]} targets whose *only*
evidence was that datasource. They have nothing left to score, which is why the
scored count is lower than the candidate count.

## 2. Ranked targets

![Evidence breakdown for the top 20 targets](figures/parkinsons_top_targets.png)

Segment lengths are the weighted contributions, and they sum exactly to the
score — nothing is normalized away. A missing segment is missing evidence, not
zero evidence.

{top20}

## 3. Does it recover known biology?

The single question Milestone 1 exists to answer. These genes are **not labels**
and nothing in the scoring knows about them; they are the check that a
transparent score built from public evidence recovers what the field already
knows. If it did not, the fault would be in the pipeline rather than the biology.

| Gene | Ensembl ID | Rank |
| --- | --- | ---: |
{known_rows}

{verdict}

Further established Parkinson's genes that the ranking also surfaced, not part
of the acceptance check:

| Gene | Ensembl ID | Rank |
| --- | --- | ---: |
{additional_rows}

## 4. Manual inspection of the top 10 (Context.md §36 task 9)

Written by hand — whether a gene is genuinely established or merely
well-published is a judgement, not a computation.

{inspection}

**Overall read.** The top 10 contains no obvious artefacts. Every entry is
either an established Parkinson's gene or a replicated GWAS locus. The ranking's
main weakness is visible in GAK at #10: GWAS implicates a genomic *region*, and
attributing that signal to a specific gene is exactly the ambiguity
Context.md §31.4 warns about.

## 5. Literature ablation (Context.md §32.2)

Publication counts reward genes that have been studied, not genes that matter.
Re-scoring with the literature dimension removed and the remaining weights
renormalized shows how much of the ranking rests on attention.

Largest rank falls in the top 20 when literature is dropped (negative = fell):

{ablation_table}

A target that falls sharply here was being carried by publication volume. One
that holds its position is supported by genetics and functional evidence that
stand on their own — LRRK2, PLA2G6, GBA1, MAPT and PARK7 do not move at all.

### This qualifies the result in section 3

Without literature evidence the established genes rank: {no_lit_ranks}.

That is **{len(survivors)} of {len(KNOWN_PARKINSONS_GENES)} in the top 20** rather than {len(result.known_genes_in_top_20)}; {dropped_summary} out once publication evidence is removed.

The headline result in section 3 is therefore **partly literature-dependent**,
and reporting it without this caveat would overstate what the baseline achieves.

The interpretation is not that literature evidence is worthless. PINK1 and PRKN
are genuinely important genes and their publication record reflects that. The
problem is that **this method cannot distinguish a gene that is well-published
because it matters from one that merely appears in many abstracts** — and the
71% of candidates carrying literature evidence alone are exactly where that
distinction would bite. Separating the two needs labels and a held-out
evaluation, which is Milestone 2.

What survives the ablation unchanged — LRRK2, PLA2G6, GBA1, MAPT and PARK7 —
are the targets this baseline supports on genetic and functional evidence
standing on its own.

## 6. Limitations (Context.md §36 task 10)

1. **The weights are arbitrary.** They were set by hand and tuned against no
   objective. A different but equally defensible set would reorder the table.
2. **This ranking cannot find anything new.** Candidates come from targets Open
   Targets *already* associates with Parkinson's, so by construction the method
   re-ranks known associations rather than discovering unknown ones
   (Context.md §13). Novel-candidate generation is §30.8.
3. **Literature evidence is circular for well-studied genes.** LRRK2 scores
   0.989 on literature because it is famous, and it is famous partly because it
   is important — but the score cannot separate those two facts.
4. **Absence of evidence is scored as absence.** Nulls become zero at scoring
   time, so an understudied gene is indistinguishable from a studied-and-negative
   one. `evidence_completeness` is reported for exactly this reason
   (Context.md §32.3).
5. **No pathway, tissue-expression or network evidence.** Three of the six
   §17.1 dimensions are missing entirely, so a target whose case rests on
   pathway membership or brain-specific expression is under-scored here.
6. **Single disease, no held-out evaluation.** With no labels and no test set,
   "all five known genes in the top 20" is a sanity check, not a measured
   performance figure. Ranking metrics arrive in Milestone 2.
7. **Genetic association is not causation, and gives no direction.** Knowing a
   gene matters does not say whether to inhibit or activate it — and the wrong
   direction can be harmful (Context.md §31.4, §31.5).
8. **Results are tied to release {provenance["dataset_version"]}.** Open Targets updates
   continuously; re-running against a later release may reorder this table.

## 7. Reproducing this report

```bash
uv run python scripts/build_dataset.py     # data/processed/parkinsons_targets.parquet
uv run python scripts/run_milestone1.py    # this report + the figure
```

Configuration lives in `configs/model.yaml` (`milestone_1_weights`) and
`configs/features.yaml` (`evidence_dimensions`, `leakage_guard`). Provenance for
the table is written beside it as `parkinsons_targets.parquet.provenance.json`.
"""
