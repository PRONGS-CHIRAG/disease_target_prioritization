# Parkinson's Disease Target Prioritization — Baseline Report

Milestone 1 (Context.md §36): a transparent, non-ML target ranking built only
from Open Targets evidence.

> **These are prioritization hypotheses, not validated findings.** A high score
> does not mean a target will yield an effective drug. The weights below were
> chosen by hand and are illustrative. See [docs/limitations.md](../docs/limitations.md).

| | |
| --- | --- |
| Disease | Parkinson's disease (`MONDO_0005180`) |
| Data source | Open Targets Platform release 26.06 |
| Extraction date | 2026-07-30 |
| Candidate targets | 8,727 |
| Scored targets | 8,690 |
| Method | Transparent weighted sum, no machine learning |

## 1. Method

Every candidate target Open Targets associates with the disease is scored on a
weighted sum of five evidence dimensions. Within a dimension the score is the
maximum across its datasources — a target is as good as its best evidence of
that kind, and averaging would penalise a gene for the datasources that simply
have not studied it.

| Dimension | Weight |
| --- | ---: |
| genetics | 0.40 |
| evidence diversity | 0.20 |
| functional | 0.15 |
| literature | 0.15 |
| druggability | 0.10 |

These weights are **illustrative and not scientifically validated**
(Context.md §17.1). They deviate from the §17.1 example formula because that
formula's pathway, tissue-expression and network terms need Reactome, GTEx and
STRING, which Context.md §28 Step 9 schedules after this baseline works. For
Parkinson's specifically, Open Targets carries **no pathway evidence at all** —
its `reactome` datasource has zero rows for this disease — so a pathway term was
not merely deferred, it was impossible.

### Why evidence diversity is weighted so heavily

It is the dimension that actually separates the known biology. Of the
8,690 scored candidates, **6,196 have exactly one
kind of evidence, and that kind is literature**. Meanwhile the established
Parkinson's genes carry the most distinct evidence types of any candidate
(LRRK2 seven, GBA1 and SNCA six). Context.md §14.9 predicts that diversity beats
volume; here it is measurably true.

### What was excluded, and why

`clinical_precedence` was removed before any
feature was computed. It records that a drug against the target reached the
clinic for this disease — which is precisely the label Milestone 2 will predict.
Measured across the whole release, **all 107,593 of its (disease, target) pairs
are also label pairs**: the datasource is not correlated with the label, it *is*
the label. Training on it would produce a model that reproduces its own target
variable and reports excellent metrics (Context.md §16, §32.1).

Removing it also removed 37 targets whose *only*
evidence was that datasource. They have nothing left to score, which is why the
scored count is lower than the candidate count.

## 2. Ranked targets

![Evidence breakdown for the top 20 targets](figures/parkinsons_top_targets.png)

Segment lengths are the weighted contributions, and they sum exactly to the
score — nothing is normalized away. A missing segment is missing evidence, not
zero evidence.

| Rank | Gene | Score | Genetics | Evidence types | Functional | Literature | Druggability | Completeness |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | LRRK2 | 0.844 | 0.865 | 7 | 0.556 | 0.989 | 0.667 | 1.000 |
| 2 | PLA2G6 | 0.833 | 0.934 | 4 | 0.358 | 0.926 | 0.667 | 1.000 |
| 3 | GBA1 | 0.823 | 0.937 | 6 | — | 0.989 | 1.000 | 0.800 |
| 4 | MAPT | 0.817 | 0.832 | 4 | 0.464 | 0.987 | 0.667 | 1.000 |
| 5 | PARK7 | 0.786 | 0.929 | 5 | — | 0.981 | 0.667 | 0.800 |
| 6 | SNCA | 0.763 | 0.856 | 5 | 0.036 | 0.988 | 0.667 | 1.000 |
| 7 | ITPKB | 0.747 | 0.804 | 4 | 0.508 | 0.774 | 0.333 | 1.000 |
| 8 | PSAP | 0.739 | 0.547 | 4 | 0.866 | 0.826 | 0.667 | 1.000 |
| 9 | NR4A2 | 0.732 | 0.680 | 4 | 0.347 | 0.943 | 0.667 | 1.000 |
| 10 | GAK | 0.666 | 0.544 | 3 | 0.544 | 0.778 | 1.000 | 1.000 |
| 11 | APOE | 0.625 | 0.723 | 3 | 0.267 | 0.972 | 0.000 | 1.000 |
| 12 | CTSB | 0.612 | 0.695 | 2 | — | 0.894 | 1.000 | 0.800 |
| 13 | BST1 | 0.608 | 0.854 | 2 | — | 0.887 | 0.333 | 0.800 |
| 14 | TMEM175 | 0.608 | 0.811 | 3 | — | 0.889 | 0.000 | 0.800 |
| 15 | PINK1 | 0.607 | 0.608 | 3 | — | 0.981 | 0.667 | 0.800 |
| 16 | TNK2 | 0.605 | 0.520 | 3 | 0.374 | 0.602 | 1.000 | 1.000 |
| 17 | CD38 | 0.602 | 0.723 | 2 | — | 0.755 | 1.000 | 0.800 |
| 18 | GALC | 0.600 | 0.597 | 3 | 0.567 | 0.841 | 0.000 | 1.000 |
| 19 | PRKN | 0.591 | 0.608 | 5 | — | 0.987 | 0.000 | 0.800 |
| 20 | VPS35 | 0.587 | 0.608 | 4 | — | 0.956 | 0.000 | 0.800 |

## 3. Does it recover known biology?

The single question Milestone 1 exists to answer. These genes are **not labels**
and nothing in the scoring knows about them; they are the check that a
transparent score built from public evidence recovers what the field already
knows. If it did not, the fault would be in the pipeline rather than the biology.

| Gene | Ensembl ID | Rank |
| --- | --- | ---: |
| LRRK2 | ENSG00000188906 | **1** |
| SNCA | ENSG00000145335 | **6** |
| GBA1 | ENSG00000177628 | **3** |
| PRKN | ENSG00000185345 | **19** |
| PINK1 | ENSG00000158828 | **15** |

**PASS.** All five established Parkinson's genes reached the top 20. **But see section 5:** without literature evidence only 3 of 5 remain in the top 20 (PINK1, PRKN drop out), so this result is partly carried by publication volume rather than by genetics alone.

Further established Parkinson's genes that the ranking also surfaced, not part
of the acceptance check:

| Gene | Ensembl ID | Rank |
| --- | --- | ---: |
| PARK7 | ENSG00000116288 | 5 |
| VPS35 | ENSG00000069329 | 20 |
| PLA2G6 | ENSG00000184381 | 2 |
| MAPT | ENSG00000186868 | 4 |
| TMEM175 | ENSG00000127419 | 14 |

## 4. Manual inspection of the top 10 (Context.md §36 task 9)

Written by hand — whether a gene is genuinely established or merely
well-published is a judgement, not a computation.

**1. LRRK2** — Established. The most common genetic cause of late-onset PD and an active drug-development target. Correctly ranked first.

**2. PLA2G6** — Established (PARK14). Causes autosomal-recessive early-onset parkinsonism. Strong genetics, less public attention than LRRK2 — the score reflects evidence rather than fame.

**3. GBA1** — Established. Heterozygous variants are the single largest genetic risk factor for PD. Note it has no functional-genomics evidence here, so its score comes from genetics, diversity and literature.

**4. MAPT** — Established risk locus. The H1 haplotype is a replicated PD risk factor, though MAPT is better known for tauopathies — a reminder that a locus can be shared across diseases.

**5. PARK7** — Established (DJ-1). Causes autosomal-recessive early-onset PD. Its retired symbol is why HGNC alias resolution matters (see tests/test_identifiers.py).

**6. SNCA** — Established. Encodes alpha-synuclein, the primary component of Lewy bodies, and the first PD gene identified. Its clinical_precedence evidence was correctly excluded as the label.

**7. ITPKB** — Plausible. A replicated GWAS locus for PD. Less mechanistically characterised than the genes above — a reasonable candidate for follow-up rather than a known answer.

**8. PSAP** — Plausible. Prosaposin; lysosomal biology links it to the GBA1 pathway. Carries the strongest functional-genomics evidence in the top 10.

**9. NR4A2** — Plausible. A transcription factor required for dopaminergic neuron development. Long-discussed in PD with contested genetic support.

**10. GAK** — Plausible. A GWAS locus adjacent to TMEM175 — note that GWAS implicates a *region*, and assigning the signal to the right gene is exactly the ambiguity Context.md §31.4 warns about.


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

| Gene | Rank | Rank without literature | Change |
| --- | --- | --- | --- |
| PINK1 | 15 | 24 | -9 |
| PRKN | 19 | 28 | -9 |
| VPS35 | 20 | 29 | -9 |
| BST1 | 13 | 20 | -7 |
| TMEM175 | 14 | 21 | -7 |
| APOE | 11 | 16 | -5 |

A target that falls sharply here was being carried by publication volume. One
that holds its position is supported by genetics and functional evidence that
stand on their own — LRRK2, PLA2G6, GBA1, MAPT and PARK7 do not move at all.

### This qualifies the result in section 3

Without literature evidence the established genes rank: LRRK2 #1, GBA1 #3, SNCA #8, PINK1 #24, PRKN #28.

That is **3 of 5 in the top 20** rather than 5; PINK1 and PRKN drop out once publication evidence is removed.

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
8. **Results are tied to release 26.06.** Open Targets updates
   continuously; re-running against a later release may reorder this table.

## 7. Reproducing this report

```bash
uv run python scripts/build_dataset.py     # data/processed/parkinsons_targets.parquet
uv run python scripts/run_milestone1.py    # this report + the figure
```

Configuration lives in `configs/model.yaml` (`milestone_1_weights`) and
`configs/features.yaml` (`evidence_dimensions`, `leakage_guard`). Provenance for
the table is written beside it as `parkinsons_targets.parquet.provenance.json`.
