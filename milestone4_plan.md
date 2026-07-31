# Milestone 4 — Implementation Plan

Plan for Context.md §28 Step 9 (Reactome/GTEx/STRING integration) and the
pathway/expression/network elements of §21/§38 that milestone3_plan.md §1 and
§9 named as "not buildable" and "the natural Milestone 4." A separate
`milestone4.md` will record what was actually built.

**Status: planned, not started.** Written before implementation, in the same
spirit as milestone2.md §1–2 and milestone3_plan.md: the measurements and
constraints that shape the design, recorded before any code makes them look
inevitable.

One piece of this milestone's original scope is already done, ahead of this
plan: milestone3_plan.md §9 listed FastAPI's `/rank` separately from Reactome/
GTEx/STRING ("the API stays a ~30-line addition later") precisely because it
has no dependency on any of this. It was implemented as a standalone
30-line wrapper over `services/target_ranking.rank_for_disease`
(`api/main.py`, `tests/test_api.py`) before this document was written, and
isn't discussed further here.

---

## 1. What becomes buildable, and what still doesn't

Reactome, GTEx and STRING are downloaded, validated (`docs/dataset_card.md`)
and have working readers (`data/reactome.py`, `data/gtex.py`,
`data/string_db.py`). The gap milestone3_plan.md §1 measured is entirely in
the feature-computation layer: `features/pathways.py`, `network.py`,
`expression.py` are `NotImplementedError` stubs. Closing that gap does not
close all of it — four of the fifteen columns `configs/features.yaml`
declares for these three groups need a per-disease "known disease genes" seed
set that this repo has no leakage-reviewed definition for (§2 below), and
`target_family` needs `target.targetClass`, which is unrelated to any of
these three sources.

| Spec item | Source | Status after this milestone |
| --- | --- | --- |
| `path__n_pathways` | §14.3 | **Buildable** — root-category count per gene (§4.1) |
| `expr__max_tpm`, `expr__median_tpm`, `expr__n_tissues_detected`, `expr__tissue_specificity` | §14.4 | **Buildable** — pure per-gene GTEx statistics |
| `expr__relevant_tissue_tpm` | §14.4, §21 filters | **Buildable** — see §2.3's tissue-matching fix |
| `net__degree`, `net__weighted_degree`, `net__pagerank`, `net__mean_edge_confidence` | §14.5, §18.1 | **Buildable** — pure topology |
| `net__betweenness` | §14.5, §18.1 | **Buildable as a sampled estimate** — exact betweenness is infeasible at this graph size (§2.2) |
| Relevant-tissue filter | §21, §38.3 | **Buildable** — `RankingFilters.relevant_tissue` stops raising |
| `diversity__genetics_and_pathway`, `diversity__genetics_and_expression` | §14.9 | **Buildable** — co-occurrence flags, declared in `features.yaml` since Milestone 1 and never implemented |
| `baseline_weights` (§17.1's six-dimension formula) | model.yaml | **Reachable and reportable** — not the new default (§2.4) |
| `path__overlap_with_known_disease_genes`, `path__n_disease_relevant_pathways`, `net__n_disease_gene_neighbours`, `net__min_distance_to_disease_gene` | §14.3, §14.5 | **Still not built** — need a "known disease genes" seed set; deferred, see §2.1 |
| Target-family / target-class filter | §21, §38.3 | **Still not buildable** — needs `target.targetClass`, unrelated to this milestone's three sources |

---

## 2. Decisions taken

| Question | Decision |
| --- | --- |
| Seed-dependent columns (4 of 15) | **Defer, don't invent a seed source under time pressure.** Build the 11 seed-free columns; remove the 4 from `features.yaml` with a comment pointing here |
| `baseline_weights` vs `milestone_1_weights` as default | **Keep `milestone_1_weights` as the app/training default.** Make `baseline_weights` reachable and run it through the same LODO harness as a reported comparison, not a replacement |
| `net__betweenness` | **Sampled approximation**, `k=500`, seeded from `model.yaml`'s `random_seed` |
| Disease-agnostic recomputation | **Memoize inside `network.py`/`expression.py`**, not by threading new parameters through `build_features.py`'s call signatures |

### 2.1 Why the seed-dependent columns are deferred, not built

`pathway_overlap_with_known_disease_genes` and the two `net__*_disease_gene_*`
columns all need a per-disease "known disease gene" set for guilt-by-association.
The only precedent in this repo — five hardcoded Parkinson's genes in
`milestone1.py:56-67` — is documented at `viz.py:218` as "a pipeline sanity
check, not a label used in scoring." It was never meant to generalize to ten
diseases as a feature input, and doing so now (either by seeding from the
`dim__genetics` evidence dimension, or by hand-curating nine more disease gene
lists) is a real methodological choice this repo has no reviewed answer for:
seeding from genetics evidence makes three of six §17.1 terms partly a
function of a fourth (genetics), and would need a reported correlation check
against `dim__genetics` before it could be trusted; hand-curating nine gene
lists is a research task with its own citation trail, independent of any code
in this repository. Building the other 11 columns and documenting this gap
explicitly (rather than picking one under time pressure) is the more honest
option, and consistent with this project's own preference for a stated gap
over a silently-shaky feature (Context.md §34).

The underlying utility functions — `pathway_overlap_with_known_genes`,
`distance_to_disease_genes` — are still implemented and tested. They take a
`disease_genes: list[str]` argument rather than deciding where that list comes
from, so the deferred question is isolated to "what list to pass," not to
whether the computation itself works.

### 2.2 `net__betweenness` needs a sampled estimate

The STRING gene-level graph has ~19.7k nodes and ~929,898 edges at
`min_score=400` (`docs/dataset_card.md`). Exact betweenness centrality is
O(V·E) — on this graph, hours to days in NetworkX. `networkx.betweenness_centrality(G,
k=500, seed=<model.yaml random_seed>)` samples 500 source nodes instead of all
~19.7k, bringing it to a tractable O(k·E). `k` and the seed are recorded in
provenance alongside the run (Context.md §33) so the estimate is
reproducible, not just fast.

### 2.3 GTEx tissue-name matching needs to be token-based, and `synovium` has no match at all

Checked directly against the real files before writing any matching code:
`configs/diseases.yaml`'s `relevant_tissues` are free text (`"brain"`,
`"sigmoid colon"`, `"adipose tissue"`, `"synovium"`); GTEx v10's 68 tissue
columns are underscore-joined and differently ordered (`Brain_Substantia_nigra`,
`Colon_Sigmoid`, `Adipose_Subcutaneous`). Naive substring matching resolves
most of them but fails two ways: `"sigmoid colon"` doesn't substring-match
`Colon_Sigmoid` (word order), and `"adipose tissue"` doesn't match either
adipose column at all (the word "tissue" isn't in either GTEx name). Both
resolve under **token-set containment** (split on non-alphanumeric characters,
match if every query token appears in the candidate) — `"adipose"` alone then
matches both `Adipose_Subcutaneous` and `Adipose_Visceral_Omentum`, aggregated
by mean.

One tissue does not resolve under any matching scheme: **GTEx v10 has no
synovial tissue at all**, so rheumatoid arthritis's `"synovium"` has zero
possible matches. `expression.py`'s existing docstring says "an unmatched
tissue name is an error rather than a silent zero" — written before this was
checked against the real vocabulary. That contract is corrected here: an
unmatched tissue is logged explicitly (`log_dropped`, Context.md §34) and the
disease's `expr__relevant_tissue_tpm` is left null with `missing__expression`
set, rather than a hard pipeline failure that would block every disease's
build over one disease's missing tissue.

### 2.4 `baseline_weights` becomes reachable but not the default

`baseline_weights` (§17.1's six-dimension formula) needs `dim__pathways`,
`dim__network`, `dim__expression` — aggregate `[0, 1]` columns that don't
exist until this milestone builds them (illustrative normalizations, same
spirit as the existing `dim__evidence_diversity`). Once they exist,
`WeightedBaseline` picks them up with no code change (it resolves `dim__<name>`
generically). But `model.yaml` itself calls the §17.1 weights "illustrative,
not scientifically validated," while `milestone_1_weights`' substitution of
`evidence_diversity` + `functional` was empirically validated against the five
established Parkinson's genes (milestone1.md §3). Making `baseline_weights`
reachable and running it through the same leave-one-disease-out harness as a
reported comparison honors the original formula without demoting a measured
result in favor of an illustrative one on no evidence it's actually better.
The `no_network` ablation (`model.yaml` line ~206, currently "not applicable"
per `docs/model_card.md`) becomes runnable for the first time as part of this
comparison.

---

## 3. Leakage boundary for this milestone

Nothing here changes the leakage guard's mechanism (`build_features.py`'s
allowlist-of-non-features check) — the new `path__`/`net__`/`expr__` columns
flow through it exactly as `drug__`/`prio__` columns already do, and
`verify_guard_liveness` needs no new rules since none of the three sources are
Open-Targets association datasources. What does need explicit attention is
§2.1's seed-gene question: had this milestone built the four deferred columns
using `dim__genetics` as a seed source, they would not have been *label*
leakage (the denylist protects `clinical_precedence`, not the genetics
datasources), but they would have been a softer, undocumented form of feature
duplication — three of six weighted terms partly re-deriving a fourth. Not
building them until that tradeoff is reviewed is the safer default, matching
this project's general bias toward a stated gap over a silently-correlated
feature.

---

## 4. Architecture

### 4.1 Reactome: root-category counting instead of raw pathway counts

`pathways.py`'s existing docstring already names the problem: Reactome is a
hierarchy, so a naive "number of pathways containing this gene" counts the
same biology at every level of granularity and rewards well-annotated genes
over biologically central ones. `data/reactome.py`'s
`load_pathway_relations()` (parent/child edges) makes it possible to walk
each pathway up to its root category instead. `path__n_pathways` is
redefined as **the count of distinct root categories** a gene's pathway
memberships map to — a gene annotated to 50 leaf pathways under 2 root
categories scores 2, not 50. This is a redefinition of what the column
measures relative to a naive count, stated plainly in the column's
docstring and in `milestone4.md`, not silently substituted.

### 4.2 Disease-agnostic computation is memoized, not threaded through call signatures

STRING network topology and GTEx per-gene statistics (everything except
`expr__relevant_tissue_tpm`) don't depend on which disease is being built, but
`build_disease_features` is called once per disease by `build_feature_table`
(ten times per full run). Rather than changing `build_features.py`'s call
pattern or `build_disease_features`'s signature to thread precomputed frames
through (which would also have to stay backward-compatible with
`milestone1.py`'s single-disease call path), `network.py` and `expression.py`
memoize the expensive part internally (`functools.lru_cache` around graph
loading + centrality, and around the GTEx base table) so repeated calls
within a process are cheap without changing any existing signature.

---

## 5. Build order

**Step 1 — `features/pathways.py`.** Root-category `path__n_pathways`,
`missing__pathways`; `pathway_overlap_with_known_genes` implemented and tested
but not called by the aggregator (§2.1). `tests/test_pathways.py`.

**Step 2 — `features/network.py`.** `load_graph`, `net__degree`,
`net__weighted_degree`, `net__pagerank`, `net__betweenness` (sampled, §2.2),
`net__mean_edge_confidence`, `missing__network`; `distance_to_disease_genes`
implemented and tested but not called by the aggregator (§2.1).
`tests/test_network.py`.

**Step 3 — `features/expression.py`.** `tissue_specificity` (Tau index),
the token-set tissue-name matcher (§2.3), `expr__max_tpm`, `expr__median_tpm`,
`expr__n_tissues_detected`, `expr__tissue_specificity`,
`expr__relevant_tissue_tpm`, `missing__expression`. `tests/test_expression.py`.

**Step 4 — Wire into `build_features.py`.** Join all three into
`build_disease_features`, before the leakage-guard call. Extend
`build_evidence_diversity` (`genetics.py`) to compute
`diversity__genetics_and_pathway` / `diversity__genetics_and_expression`.
Remove the four deferred columns from `configs/features.yaml` with a comment.

**Step 5 — `dim__pathways`/`dim__network`/`dim__expression` and the
`baseline_weights` comparison.** Illustrative `[0,1]` normalizations; run
`baseline_weights` through the LODO harness alongside `milestone_1_weights`;
record the comparison and the `no_network` ablation result.

**Step 6 — Un-gate the app and services layer.**
`services/target_ranking.py`: empty `UNAVAILABLE_EVIDENCE_CATEGORIES`; un-gate
`relevant_tissue` in `_reject_unbuildable_filters`/`_apply_filters` (keep
`target_family` raising). `app_checks.py`'s `check_placeholders`: invert to
assert the placeholders are gone and `relevant_tissue` now filters. App pages:
remove the GTEx/Reactome/STRING entries from `target_evidence.py`'s
`_NOT_BUILDABLE` and update the "N of 6" captions across
`target_ranking.py`/`disease_overview.py`.

**Step 7 — Rebuild and document.** Re-run `scripts/train_model.py` →
`scripts/evaluate_model.py` → `scripts/build_app_data.py` →
`scripts/check_app.py` → `scripts/run_app.py`. Update `README.md`,
`docs/limitations.md`, `docs/model_card.md`, `docs/dataset_card.md`,
`docs/data_dictionary.md`. Write `milestone4.md`.

---

## 6. Acceptance check

Extends `scripts/check_app.py`'s existing checks (milestone3_plan.md §6)
rather than replacing them:

1. **`check_placeholders` inverted**: `UNAVAILABLE_EVIDENCE_CATEGORIES` is
   empty; `relevant_tissue` filters without raising; `target_family` still
   raises (it remains genuinely unbuildable this milestone).
2. Every target's `path__n_pathways`/`net__degree`/`expr__max_tpm`-family
   columns are either populated or explicitly null with the matching
   `missing__*` flag set — never silently absent.
3. The leakage guard still passes on the rebuilt feature table (existing
   check, re-run against the new columns).
4. `net__betweenness`'s `k` and seed are recorded in provenance and are
   reproducible across two runs (same seed → same values).
5. Rheumatoid arthritis's `synovium` miss is logged with a reason, and
   `expr__relevant_tissue_tpm` is still computed from its other matched
   tissues (`blood`, `spleen`) rather than nulled outright — only fully null
   when *every* configured tissue for a disease fails to match, which does
   not happen for any of the ten.

## 7. Tests

New: `tests/test_pathways.py`, `tests/test_network.py`,
`tests/test_expression.py` — synthetic fixtures in the style of
`tests/test_dimensions.py`, not the real multi-hundred-MB source files.
Updated: `tests/test_build_feature_table.py` (new columns present, guard
still passes, repeated calls hit the cache rather than re-reading STRING/GTEx
from disk), `tests/test_target_ranking.py` (`UNAVAILABLE_EVIDENCE_CATEGORIES`
excludes the three built categories, `relevant_tissue` filters for real),
`tests/test_app_checks.py` (rewritten `check_placeholders` expectations).

## 8. Deliverables

| Path | What it is |
| --- | --- |
| `src/target_prioritization/features/pathways.py`, `network.py`, `expression.py` | Implemented (11 of 15 declared columns; 4 deferred, §2.1) |
| `src/target_prioritization/features/build_features.py`, `genetics.py` | Wired in; two new diversity co-occurrence columns |
| `configs/features.yaml`, `configs/model.yaml` | Four deferred columns removed with a comment; `baseline_weights` reachable |
| `src/target_prioritization/services/target_ranking.py`, `app_checks.py`, `app/pages/*.py` | Placeholders removed; `relevant_tissue` filter live |
| `reports/evaluation/`, `docs/model_card.md` | `baseline_weights` vs `milestone_1_weights` comparison; `no_network` ablation result |
| `milestone4.md` | Implementation record |

## 9. Explicitly out of scope

The four seed-dependent columns (§2.1); `target_family`/target-class
filtering (needs `target.targetClass`, unrelated to Reactome/GTEx/STRING);
switching the app/training default away from `milestone_1_weights`; the
§20.4 LLM explanation layer; live GraphQL disease search; §30.13 uncertainty
estimation. FastAPI `/rank` is not in scope here because it was already
completed separately (see this document's header).
