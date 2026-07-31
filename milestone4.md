# Milestone 4 — Progress Record

Implementation record for Context.md §28 Step 9: *Reactome, GTEx and STRING
integration* — the gap milestone3_plan.md §1 and milestone3.md §6 named as
"the natural Milestone 4." Planned in [milestone4_plan.md](milestone4_plan.md)
before implementation started, in the same spirit as milestone2.md §1-2 and
milestone3_plan.md — the measurements and constraints that shape the design,
recorded before any code makes them look inevitable. This document records
what was actually built and what the real pipeline measured, including a
headline finding the plan predicted but could not confirm until the full
rebuild ran.

**Status: complete.** `features/pathways.py`, `network.py`, `expression.py`
implemented (11 of 15 Context.md §14.3/§14.5 columns; 4 deferred, §1 below);
wired into `build_features.py`; `configs/model.yaml`'s `baseline_weights`
reachable and compared against the production default; the app and services
layer un-gated; FastAPI's `/rank` implemented independently beforehand (it has
no dependency on any of this — milestone3_plan.md §9 already said so). All 6
`scripts/check_app.py` checks pass against the real ten-disease pipeline, 430
tests passing (up from 373 before this milestone), `ruff` and `mypy` clean.

---

## 1. What was deferred, and what the plan's predictions turned out to be

Per milestone4_plan.md §2.1, four columns are **not** built:
`path__overlap_with_known_disease_genes`, `path__n_disease_relevant_pathways`,
`net__n_disease_gene_neighbours`, `net__min_distance_to_disease_gene`. All
four need a per-disease "known disease genes" seed set this repo has no
leakage-reviewed definition for — the only precedent (five hardcoded
Parkinson's genes in `milestone1.py`) is documented at `viz.py:218` as a
pipeline sanity check, not a reusable feature input. The underlying utility
functions (`pathway_overlap_with_known_genes`, `distance_to_disease_genes`)
are implemented and tested regardless — they take a `disease_genes: list[str]`
argument rather than deciding where it comes from, so this gap is isolated to
"what gene list to pass," not to whether the computation works. Eleven
columns across pathways/expression/network *are* built, plus two evidence-
diversity co-occurrence columns (`diversity__genetics_and_pathway`,
`diversity__genetics_and_expression`) declared since Milestone 1 and never
computed until now.

Three predictions from the plan, checked against the real 89,666-row rebuild:

- **§2.2's betweenness feasibility concern was correct**: exact betweenness on
  a 19,492-node, 929,898-edge graph would have been infeasible. The sampled
  estimate (`k=500`, seeded from `model.yaml`'s `random_seed`) computed
  cleanly — roughly 175 seconds once per process, thanks to the memoization
  §4.2 designed for. *(A real bug in the sampling's reproducibility, not
  predicted by the plan, is recorded in §2 below.)*
- **§2.3's tissue-matching predictions held exactly**: all 9 of 10 diseases'
  `relevant_tissues` resolve; rheumatoid arthritis's `synovium` does not,
  confirmed against the real GTEx v10 file — it has no synovial tissue at
  all. `expr__relevant_tissue_tpm` for rheumatoid arthritis is still mostly
  populated, computed from its other two configured tissues (`blood`,
  `spleen`); only the `synovium` component is missing, logged explicitly.
- **§2.4's caution about `baseline_weights` was borne out, in both
  directions.** Made reachable and run through the same evaluation harness as
  `milestone_1_weights` (`scripts/compare_baseline_weights.py`, a new script —
  §5): `baseline_weights` scores *higher* on primary NDCG@10 (0.302 vs. 0.288)
  but *lower* on novel-only (0.024 vs. 0.050) than `milestone_1_weights`. This
  is exactly the tradeoff that justified not switching the default: neither
  profile dominates the other, and `milestone_1_weights` remains the one with
  an empirical justification (milestone1.md §3) rather than an illustrative
  one.

---

## 2. Three things a real review caught before the rebuild ran

None of these were visible from the initial implementation or from unit
tests written alongside it — all three were caught in an external review
pass before the full pipeline was ever run, which is the reason they did not
end up baked into a committed artifact.

### 2.1 `net__betweenness` was not actually reproducible

`load_gene_level_edges` ends in a polars `group_by`, which gives no row-order
guarantee. `load_graph` built its `networkx.Graph` by iterating that
unordered frame directly — so the graph's **node insertion order** was
whatever polars happened to return, and `betweenness_centrality(G, k=500,
seed=...)` samples its 500 source nodes from `G.nodes` in insertion order.
Two runs with the identical seed could silently sample different nodes and
produce different `net__betweenness` values, violating Context.md §33
without ever raising an error. Fixed by sorting the edge frame
(`edges.sort(["gene1", "gene2"])`) before insertion, so node order is
deterministic regardless of the upstream frame's row order. Verified two
ways: a new test (`test_graph_node_order_is_independent_of_edge_row_order`)
builds the same edges in reversed row order and asserts identical node
order — confirmed to fail without the fix (checked directly, then reverted);
and the existing seeded-reproducibility test now exercises a real property
instead of trivially reusing one in-memory graph object.

### 2.2 `dim__network` and `dim__expression` were population-size-dependent

The first implementation ranked `net__pagerank` / `expr__relevant_tissue_tpm`
as a percentile **within the disease's own candidate set** — 8,690 candidates
for Parkinson's, up to 15,578 for breast carcinoma. STRING topology and GTEx
expression are disease-invariant gene properties; ranking them against a
population that changes size between diseases would have made an otherwise
constant gene property numerically different depending on which disease's
row was read, and shifted systematically between a leave-one-disease-out
fold's train and test populations — exactly the kind of feature XGBoost's
`select_feature_columns` would pick up automatically and exploit as a
population-size artifact rather than a signal. Fixed by ranking against the
**full graph** (all 19,492 STRING genes, computed once in the same cached
function as pagerank/betweenness) and the **full GTEx table** (all ~59k
genes) instead. Two new tests
(`test_dim_network_does_not_depend_on_the_calling_candidate_set`,
`test_dim_expression_does_not_depend_on_the_calling_candidate_set`) assert a
gene's `dim__network`/`dim__expression` is identical whether it's scored
alone or alongside every other candidate.

### 2.3 `"pathway"` vs. `"pathways"` would have silently broken missing-evidence reporting

`services/target_ranking.py`'s `APP_EVIDENCE_CATEGORIES` used the singular
`"pathway"`, while the feature columns this milestone produces are
`missing__pathways` / `dim__pathways` (plural, matching `configs/features.yaml`'s
group name and `configs/model.yaml`'s `baseline_weights` key). Had
`UNAVAILABLE_EVIDENCE_CATEGORIES` been emptied without also fixing this,
`_app_evidence_completeness` would have raised `ColumnNotFoundError` looking
for `missing__pathway` at app runtime, and `missing_evidence_categories`
would have silently never reported pathway evidence as missing for any
target (`row.get` on a nonexistent key returns `None`, never `== 1`) — the
exact §32.3 failure mode this project's checks exist to catch, and it would
not have raised anything. Fixed by renaming the entry to `"pathways"` before
emptying the dict, with a test suite update
(`tests/test_target_ranking.py`, `tests/test_evidence_summary.py`) that
exercises the real six-category completeness math against synthetic frames
carrying the plural column name.

**Standing lesson, matching milestone2.md §9 and milestone3.md §2's own
pattern**: a naming mismatch between a display-layer constant and the actual
column name is invisible to any test that constructs its own fixture with
consistent (if wrong) names on both sides — it only surfaces against a
contract the two sides don't independently control. All three of these were
caught by an external review of the diff against the real column names and
real data shapes before the expensive rebuild ran, not by the unit tests
written alongside the code, which is why this section exists.

---

## 3. Results

### 3.1 Coverage, across all ten diseases (89,666 rows)

| Group | Missing rate | Note |
| --- | ---: | --- |
| `missing__pathways` | 34.9% | No Reactome annotation at all for that gene |
| `missing__network` | 8.4% | Gene absent from the STRING graph at `min_score=400` |
| `missing__expression` | 0.8% | Gene absent from the GTEx median-TPM table |

`path__n_pathways` (root-category count) is not degenerate: 1–19 across the
population, mean 2.22, median 2 (28,803 genes at 1 root category, 13,870 at
2, tailing off to 30 genes at 19) — `dim__pathways`'s saturating transform
(ceiling 5) has real spread to work with, not a near-constant value.

### 3.2 XGBoost got measurably *more* popularity-dominated, not less

| Method | NDCG@10 (primary) | NDCG@10 (novel-only) |
| --- | ---: | ---: |
| Weighted baseline (`milestone_1_weights`, unchanged) | 0.288 | 0.050 |
| **XGBoost — Milestone 4** | **0.901** | **0.000** |
| XGBoost — Milestone 2 (for comparison) | 0.696 | 0.009 |
| Target popularity (no learning) | 0.873 | 0.000 |

Milestone 2's headline finding (milestone2.md §1: XGBoost's ranking is mostly
cross-disease target popularity) is *sharper* after this milestone, not
resolved by it. `net__weighted_degree` (STRING interaction count weighted by
confidence) is now the single highest-SHAP feature of the whole model —
ahead of `prio__has_ligand`, which held that position at Milestone 2:

| Feature | mean \|SHAP\| |
| --- | ---: |
| `net__weighted_degree` | 1.086 |
| `prio__has_ligand` | 0.873 |
| `net__mean_edge_confidence` | 0.569 |
| `dim__druggability` | 0.497 |
| `assoc_ds__europepmc_evidence_count` | 0.490 |
| `net__degree` | 0.430 |
| `expr__median_tpm` | 0.340 |
| `prio__genetic_constraint` | 0.312 |
| `expr__tissue_specificity` | 0.274 |
| `dim__network` | 0.257 |

Four of the top ten are Milestone 4 features, three of them network-derived.
`net__degree`/`net__pagerank`/`net__betweenness` are confounded with study
effort by construction (`network.py`'s own docstring, Context.md §32.2) — a
well-studied protein has more recorded STRING interactions for the same
reason it has more papers — and novel-only NDCG@10 falling to *exactly*
0.000 is the measured consequence, not a hypothetical risk.

### 3.3 The weighted baseline barely notices the same features that dominate XGBoost

`scripts/compare_baseline_weights.py` (new — runs `configs/model.yaml`'s
`evaluation.ablations` for the first time; declared since Milestone 2 but
never wired to a runner):

| Profile | NDCG@10 (primary) | NDCG@10 (novel-only) |
| --- | ---: | ---: |
| `milestone_1_weights` (unchanged, still the default) | 0.288 | 0.050 |
| `baseline_weights` | 0.302 | 0.024 |
| `baseline_weights`, `no_literature` | 0.254 | 0.015 |
| `baseline_weights`, `no_network` | 0.302 | 0.023 |
| `baseline_weights`, `genetics_only` | 0.240 | 0.040 |

Dropping `network` from `baseline_weights` moves primary NDCG@10 by
**less than 0.001** — essentially nothing — for the linear weighted baseline,
in contrast to network topology becoming XGBoost's single most important
signal. A fixed linear weight of 0.15 can't overweight a popularity-correlated
feature the way a tree ensemble's splits can; this is architecture-dependent
exploitation of the same underlying confound, not a property of the feature
itself. `genetics_only` scores worse than `milestone_1_weights` on both
metrics, confirming milestone1.md §3's finding (evidence diversity plus
functional evidence beats genetics alone) still holds under the six-dimension
formula. Full breakdown:
[reports/evaluation/baseline_weights_comparison.json](reports/evaluation/baseline_weights_comparison.json).

---

## 4. Acceptance check

`scripts/check_app.py`, all six checks, against the real rebuilt pipeline:

| Check | Result |
| --- | --- |
| Leakage boundary | PASS |
| All ten diseases well-formed | PASS |
| Source links resolvable | PASS |
| Missing-evidence panel | PASS |
| Fold routing (held-out, not in-sample) | PASS |
| Milestone 4 categories built; `target_family` still explicit | PASS |

The sixth check is this milestone's rewrite of Milestone 3's `check_placeholders`
(§2.3 above) — inverted from "placeholders exist and are stated" to
"`UNAVAILABLE_EVIDENCE_CATEGORIES` is empty, `relevant_tissue` filters rather
than raises, `target_family` still raises."

---

## 5. Deliverables

| Path | What it is |
| --- | --- |
| `src/target_prioritization/features/{pathways,network,expression}.py` | Implemented (11 of 15 columns; 4 deferred, §1) |
| `src/target_prioritization/features/build_features.py`, `genetics.py` | Wired in; `add_cross_dimension_diversity` |
| `configs/features.yaml`, `configs/model.yaml` | Four deferred columns removed with a comment; `baseline_weights` reachable |
| `src/target_prioritization/services/target_ranking.py`, `app_checks.py` | Placeholders removed; `relevant_tissue` filter live; `target_family` still explicit |
| `app/pages/*.py` | "Not yet integrated" captions removed for the three built categories |
| `src/target_prioritization/api/main.py`, `api/schemas.py` | `/rank` implemented (independent of the above — see header) |
| `scripts/compare_baseline_weights.py` | New — `baseline_weights` vs. `milestone_1_weights`, plus the three `evaluation.ablations` |
| `reports/evaluation/baseline_weights_comparison.json` | New — §3.3's full numbers |
| `tests/test_pathways.py`, `test_network.py`, `test_expression.py`, `test_api.py` | New |
| `tests/test_target_ranking.py`, `test_evidence_summary.py`, `test_app_checks.py` | Updated for the six-category world |

---

## 6. Progress checklist

- [x] `features/pathways.py` — root-category `path__n_pathways`, tested
- [x] `features/network.py` — degree/weighted-degree/pagerank/betweenness/mean-confidence, tested
- [x] `features/expression.py` — max/median/specificity/detected/relevant-tissue, tested
- [x] Wired into `build_features.build_disease_features`
- [x] `diversity__genetics_and_pathway` / `diversity__genetics_and_expression`
- [x] `dim__pathways`/`dim__network`/`dim__expression`, population-independent (§2.2)
- [x] `baseline_weights` reachable; ablations runnable for the first time
- [x] `services/target_ranking.py`, `app_checks.py`, `app/pages/*.py` un-gated
- [x] FastAPI `/rank` (done independently, before this milestone's plan was written)
- [x] Full pipeline rebuilt: `train_model.py`, `evaluate_model.py`, `build_app_data.py`, `check_app.py` — all pass
- [x] `ruff check` and `mypy src` clean
- [x] 430 tests passing (up from 373)

---

## 7. Next

Still out of scope, unchanged from milestone4_plan.md §9: the four
seed-dependent columns (§1 — needs a reviewed "known disease genes" source);
`target_family`/target-class filtering (needs `target.targetClass`, unrelated
to Reactome/GTEx/STRING); the §20.4 LLM explanation layer; live GraphQL
disease search; §30.13 uncertainty estimation. Not attempted here: switching
the app/training default away from `milestone_1_weights` — §3.3's numbers are
a reason to keep that decision, not revisit it, at least until `baseline_weights`
or a successor profile is measured to actually beat it rather than trade one
metric for another.

A natural next step this milestone's own measurement points to directly:
Milestone 2's popularity-dominance finding is now worse, concretely traceable
to `net__weighted_degree`/`net__pagerank`. Whether that argues for excluding
raw network centrality from XGBoost's feature set entirely (keeping it for
the weighted baseline, where it demonstrably doesn't dominate), or for a
degree-normalized network feature that isn't itself a study-effort proxy, is
an open question this milestone's data makes newly answerable but does not
answer.
