# Milestone 1 — What Was Built, How, and Where It Lives

Implementation record for Context.md §36: *"Build a non-ML target ranking
prototype for one disease using Open Targets data."*

**Status: complete.** All ten §36 tasks done, all four deliverables produced,
159 tests passing. The acceptance check passes — but with an important caveat
documented in section 5 below that I'd want a reader to see before trusting the
headline number.

---

## 1. The objective, and why it's shaped this way

Milestone 1 is deliberately small. Its purpose is **diagnostic, not scientific**:
the weights are hand-set and the arithmetic is inspectable, so if established
Parkinson's genes surface near the top, the data pipeline is sound. A
gradient-boosted model failing the same way would tell us nothing about where the
fault was. Context.md §36 is explicit that no ML model should be added before
this works.

**Scope decision: Open Targets only.** §36 says "using Open Targets data" and
§28 Step 9 schedules external datasets *after* the baseline works. Reactome,
GTEx and STRING are downloaded and validated but deliberately unused here.

---

## 2. The ten §36 tasks

| # | Task | How it was done | Where |
| --- | --- | --- | --- |
| 1 | Resolve the disease identifier | Already done in the scaffolding pass; `MONDO_0005180` resolved from the pinned release, not hand-typed | [configs/diseases.yaml](configs/diseases.yaml), [scripts/resolve_diseases.py](scripts/resolve_diseases.py) |
| 2 | Retrieve associated targets | DuckDB query over `association_by_datasource_direct`, filtered to the disease | [open_targets.py](src/target_prioritization/data/open_targets.py) `load_targets_for_disease` |
| 3 | Extract evidence scores | Long-format evidence collapsed into five scored dimensions | [genetics.py](src/target_prioritization/features/genetics.py) `build_dimension_scores` |
| 4 | Normalize target identifiers | Ensembl gene ID throughout; symbols joined from the same release | [identifiers.py](src/target_prioritization/data/identifiers.py), `load_target_metadata` |
| 5 | Create a candidate-target table | 8,690 rows, one per target, with provenance stamped | [build_features.py](src/target_prioritization/features/build_features.py) `build_disease_features` |
| 6 | Calculate a transparent weighted score | Weighted sum; contributions sum exactly to the score | [baseline.py](src/target_prioritization/models/baseline.py) `WeightedBaseline.score` |
| 7 | Rank the top 20 | Deterministic ordering; ties break on score → symbol → `target_id` (see 5a) | `WeightedBaseline.rank` |
| 8 | Visualize the evidence breakdown | Stacked horizontal bars, validated palette | [viz.py](src/target_prioritization/viz.py) |
| 9 | Manually inspect the top 10 | Hand-written notes per gene — a judgement, not a computation | [reporting.py](src/target_prioritization/reporting.py) `GENE_NOTES` |
| 10 | Document the limitations | Eight limitations, generated alongside the numbers they qualify | report section 6 |

---

## 3. How the score works

Five dimensions, all from Open Targets:

```
score = 0.40 * genetics            gwas_credible_sets, eva, gene_burden,
                                   genomics_england, clingen, uniprot_variants,
                                   gene2phenotype, orphanet
      + 0.20 * evidence_diversity  min(n_distinct_evidence_types / 4, 1)
      + 0.15 * functional          crispr_screen, impc, expression_atlas
      + 0.15 * literature          europepmc, uniprot_literature
      + 0.10 * druggability        mean(hasPocket, hasLigand, hasSmallMoleculeBinder)
```

Configured in [configs/model.yaml](configs/model.yaml) (`milestone_1_weights`)
and [configs/features.yaml](configs/features.yaml) (`evidence_dimensions`) — the
dimension-to-datasource mapping is config rather than code so someone who knows
the biology but not Python can review it.

### Three decisions that drove the design, each from measurement

I queried the release before designing anything. Three findings changed the plan:

**71% of candidates have literature evidence and nothing else** (6,196 of 8,690).
A naive weighted score would have ranked genes by how often they're written
about. This is why literature carries only 0.15 and why the ablation in section 5
exists.

**The established genes are the ones with the most evidence *types*** — LRRK2 has
7, GBA1 and SNCA 6. Context.md §14.9 predicts diversity beats volume; here it's
measurably true, so `evidence_diversity` became a first-class scored dimension
rather than a reported statistic.

**Open Targets carries no pathway evidence for Parkinson's at all** — its
`reactome` datasource has zero rows for this disease. So the §17.1 example
formula's pathway term wasn't merely deferred, it was impossible. This is what
settled the Open-Targets-only scope question.

### Deviations from Context.md §17.1, stated openly

§17.1's example formula has `pathway_score`, `tissue_expression_score` and
`network_score`. All three need datasets §28 Step 9 schedules for later, and the
pathway one is unavailable for this disease regardless. I replaced them with
`evidence_diversity` and `functional`, kept the weights summing to 1.0, and left
the original `baseline_weights` in `model.yaml` marked as the not-yet-reachable
target formula.

### What is deliberately *not* scored

**Safety.** Computed and reported, never summed into the score. Context.md §14.7
and §31.7 forbid presenting safety data as toxicity prediction, and §17.1's
formula has no safety term. The columns ride along for display.

**Sparse tractability flags.** `hasTEP` covers 41 targets and
`hasHighQualityChemicalProbes` 929, against 18,869 for the three flags actually
used. At that coverage a flag encodes "has anyone looked at this" rather than "is
this druggable" — scoring it would reward attention a second time.

---

## 4. The leakage guard, and a design flaw it exposed

The label for Milestone 2 will be "target of a clinically-advanced drug for this
disease". The `clinical_precedence` datasource **is that evidence**: measured
across the release, all 107,593 of its (disease, target) pairs are also label
pairs. It's dropped before any feature is computed.

Removing it also removes **37 targets whose only evidence was that datasource** —
they have nothing left to score. That's why 8,727 candidates become 8,690 scored
rows. Logged explicitly rather than left to be inferred from a row count.

**Flaw 1: the guard failed a correctly-working pipeline.** The guard fails when a
`required` rule matches nothing, on the theory that an upstream rename has
silently disarmed it. But once `drop_denylisted_datasources` correctly removes
the datasource *before* the pivot, the column legitimately doesn't exist — so the
guard reported a working pipeline as broken.

Fixed by asking the staleness question the right way round.
`verify_guard_liveness` checks the columns the **sources could produce**, before
filtering, so the question is "does the evidence this rule blocks still exist
upstream?" rather than "did we build it?". The final assertion then checks
violations only.

**Flaw 2: the guard was failing open, and I only found it by probing.** The final
assertion filtered candidate columns by prefix — `assoc_ds__`, `dim__`, `prio__`.
In this pipeline `build_dimension_scores` aggregates straight off the long frame,
so no `assoc_ds__` column is ever built, and `build_druggability_features` emitted
raw camelCase (`hasPocket`, `maxClinicalStage`) with no `prio__` prefix. Two of
the three prefixes matched nothing, and the assertion was inspecting 5 columns
while logging a confident `leakage_guard_passed`.

I tested it rather than assuming: adding `maxClinicalStage` — the exact column
the `prioritisation_max_clinical_stage` rule exists to block — to
`safety_columns` put it in the output parquet **with values**, guard silent.

Two changes:

- `prio_column()` renames prioritisation fields to `prio__snake_case` on load, so
  the denylist patterns and the produced column names actually meet.
- The final assertion now checks **every column not on a small non-feature
  allowlist**, instead of a prefix whitelist. An allowlist of non-features fails
  closed — a stray entry just means one extra column gets checked. A whitelist of
  feature prefixes fails open on any name nobody anticipated.

Re-running the probe now raises
`LeakageError: [prioritisation_max_clinical_stage] prio__max_clinical_stage`, and
the normal run checks 18 columns rather than 5. Both flaws are covered in
[tests/test_dimensions.py](tests/test_dimensions.py).

The lesson worth keeping: the guard *had* real protection the whole time — from
`drop_denylisted_datasources` and the config-load validator — so nothing ever
actually leaked. But the layer I was describing as the second half of a
defence-in-depth pair was doing nothing, and only a deliberate leak attempt
revealed it. A guard that has never been shown to fire is not known to work.

---

## 5. Results — including the part that qualifies them

All five established Parkinson's genes reach the top 20:

| Gene | Rank | Rank without literature |
| --- | ---: | ---: |
| LRRK2 | 1 | 1 |
| GBA1 | 3 | 3 |
| SNCA | 6 | 8 |
| PINK1 | 15 | **24** |
| PRKN | 19 | **28** |

The ranking also surfaced PLA2G6 (#2, PARK14), MAPT (#4), PARK7 (#5, DJ-1) and
VPS35 (#20, PARK17) — all genuine Parkinson's genes, none of them told to the
scorer.

**The caveat that matters.** Re-scoring without literature evidence (Context.md
§32.2 requires this) drops PINK1 and PRKN out of the top 20 entirely — **3 of 5,
not 5 of 5**. The headline result is partly carried by publication volume.

That doesn't make literature worthless; PINK1 and PRKN are genuinely important,
and their publication record reflects that. It means **this method cannot
distinguish a gene that is well-published because it matters from one that merely
appears in many abstracts**. Separating those needs labels and a held-out
evaluation — Milestone 2.

LRRK2, PLA2G6, GBA1, MAPT and PARK7 don't move at all when literature is removed.
Those are the targets this baseline supports on genetic and functional evidence
standing alone.

---

## 5a. Two bugs caught by checking rather than assuming

Both were silent — the pipeline ran cleanly and produced plausible output in
each case. Recording them because the way they were found matters more than the
fixes.

**The ablation reported the exact opposite of the truth.** It named the *most
stable* targets as the biggest fallers. `with_row_index` yields `UInt32`, so
subtracting ranks wrapped a nine-place fall into 4,294,967,287, and sorting
ascending put the unchanged rows first. Caught by reading the output and asking
why the "largest falls" all showed zero movement. Fixed by casting to `Int64`;
the regression test asserts a fall is negative and that no change exceeds the
candidate count.

**The output was not reproducible.** Running `build_dataset.py` twice produced
parquet files differing byte-for-byte. The scores and the top 20 were identical,
so nothing visible was wrong — but Context.md §33 requires reproducibility, and
the claim would have been false.

The cause: ties were broken on score then gene symbol, and **gene symbol is not
unique**. Open Targets 26.06 has two `calpastatin` entries with different Ensembl
IDs (one protein-coding, one lncRNA). Rows tied on both score and symbol had no
defined order, and DuckDB's parallel scan returned them differently each run.
Fixed by adding `target_id` as a final, unique sort key. Verified by hashing the
parquet across three consecutive runs.

Caught only because I diffed two runs instead of trusting that a deterministic-
looking pipeline was deterministic.

---

## 6. Deliverables

| Path | What it is |
| --- | --- |
| [data/processed/parkinsons_targets.parquet](data/processed/) | 8,690 ranked candidates with per-dimension contributions, plus a `.provenance.json` sidecar |
| [notebooks/01_parkinsons_open_targets.ipynb](notebooks/01_parkinsons_open_targets.ipynb) | Executable walkthrough. Outputs are stripped by `nbstripout` per the project's pre-commit config; run it to regenerate |
| [reports/figures/parkinsons_top_targets.png](reports/figures/parkinsons_top_targets.png) | Stacked evidence breakdown for the top 20 |
| [reports/parkinsons_baseline_report.md](reports/parkinsons_baseline_report.md) | Full findings, manual inspection, ablation, limitations |

The report is **generated, not hand-written**, so its prose cannot drift from the
numbers it describes. The one hand-written part — the per-gene notes for the top
10 — is marked as such, because whether a gene is genuinely established or merely
well-published is a judgement no script should make.

---

## 7. Files added or changed

**New**

| File | Purpose |
| --- | --- |
| `src/target_prioritization/milestone1.py` | Pipeline orchestration, acceptance check, ablation movement |
| `src/target_prioritization/reporting.py` | Report generation + the hand-written gene notes |
| `src/target_prioritization/viz.py` | Evidence-breakdown figure |
| `scripts/run_milestone1.py` | Runs everything; exits non-zero if acceptance fails |
| `tests/test_baseline.py` | 26 tests — weighted-sum arithmetic, ablation, underflow regression |
| `tests/test_dimensions.py` | 21 tests — max-within-dimension, null-not-zero, guard liveness |
| `milestone1.md` | This file |

**Modified**

| File | Change |
| --- | --- |
| `configs/model.yaml` | Added `milestone_1_weights` + `evidence_diversity_saturation` |
| `configs/features.yaml` | Added `evidence_dimensions`, `druggability_flags`, `safety_columns` |
| `src/.../config.py` | `EvidenceDimension` model; validators for disjoint dimensions and weight sums |
| `src/.../data/open_targets.py` | `load_target_metadata`, `load_target_prioritisation`, `pivot_evidence` |
| `src/.../features/genetics.py` | Implemented dimension aggregation and evidence diversity |
| `src/.../features/druggability.py` | Implemented tractability and safety columns |
| `src/.../features/build_features.py` | `build_disease_features`, `drop_denylisted_datasources`, `verify_guard_liveness` |
| `src/.../models/baseline.py` | Implemented `score`, `rank`, `explain`, `ablate` |
| `scripts/build_dataset.py` | Implemented |

**Removed**: `notebooks/01_data_exploration.ipynb` — an empty stub that collided
with §36's named deliverable at the same `01_` index.

---

## 8. Reproducing it

```bash
uv run python scripts/build_dataset.py     # the parquet
uv run python scripts/run_milestone1.py    # figure + report, exits 1 if acceptance fails
uv run pytest -q                           # 159 tests
```

Both scripts are deterministic — verified by hashing the parquet across three
consecutive runs, not assumed. Ties break on score, then gene symbol, then
`target_id` (unique). The pinned Open Targets release (26.06) is recorded in the
parquet and its provenance sidecar.

The one field that legitimately changes between runs is `extraction_date`, which
is the point of it.

---

## 9. What Milestone 1 does *not* establish

Worth being blunt, because a passing acceptance check invites over-reading:

- **It is not a measured performance figure.** With no labels and no held-out
  set, "5 of 5 in the top 20" is a sanity check. Ranking metrics are Milestone 2.
- **It cannot discover anything new.** Candidates are targets Open Targets
  already associates with Parkinson's, so the method re-ranks known associations
  by construction (§13). Novel-candidate generation is §30.8.
- **It is one disease.** Nothing here shows the approach generalizes; that's what
  the other nine diseases in `configs/diseases.yaml` are for.
- **The weights are arbitrary.** A different but equally defensible set would
  reorder the table.

## 10. Next

Milestone 2 (Context.md §37): expand to all ten diseases, define labels from
`clinical_target`, split by disease, train logistic regression and XGBoost, and
compute the ranking metrics that turn this sanity check into a measurement.
