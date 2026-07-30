# Milestone 2 — Plan and Progress Record

Implementation record for Context.md §37: *"Create a multi-disease modelling
dataset and train the first ML baseline."*

**Status: complete.** All ten §37 tasks done, all four deliverables produced,
298 tests passing, acceptance check passes. §1-2 below were written *before*
implementation started, as measurements that shaped the design; §10 records
what the finished pipeline actually measured — including that `target_popularity`,
a baseline with no learning at all, outranks every trained model on the
primary metric. §9 records four corrections a post-implementation review
found. Full analysis: [reports/evaluation/baseline_report.md](reports/evaluation/baseline_report.md).

---

## 1. The objective, and the measurement that shapes it

Milestone 1 built a transparent, hand-weighted score for one disease and
showed it surfaces known Parkinson's genes. Milestone 2's job is to turn that
sanity check into a measurement: expand to ten diseases, define real labels
from clinical development evidence, train ML baselines, and evaluate them with
proper ranking metrics under a split that cannot be gamed by memorising which
targets belong to which disease.

Before designing anything, the label was measured across all ten diseases in
`configs/diseases.yaml`, against release 26.06:

| Disease | Candidates (post-denylist) | Positives (stage ≥ PHASE_3, descendants expanded) | Candidates dropped — clinical evidence only | Positive in ≥1 other disease too |
| --- | ---: | ---: | ---: | ---: |
| Parkinson's | 8,690 | 238 | 37 | 82% |
| Alzheimer's | 13,275 | 267 | 14 | 92% |
| Type 2 diabetes | 9,851 | 257 | 55 | 78% |
| Rheumatoid arthritis | 7,139 | 231 | 87 | 91% |
| Crohn's | 6,212 | 87 | 40 | 98% |
| Ulcerative colitis | 7,046 | 105 | 108 | 97% |
| Psoriasis | 6,896 | 111 | 67 | 89% |
| Multiple sclerosis | 4,170 | 165 | 170 | 96% |
| Breast carcinoma | 15,578 | 342 | 8 | 94% |
| NSCLC | 10,809 | 430 | 109 | 78% |
| **Total** | **89,666** | **2,233** | **695** | **2.5% prevalence** |

One more gap, found while implementing rather than while measuring: candidate
generation queries only a disease's *own* Open Targets id, but the label
(above) expands to ontology descendants. A target can therefore be a
family-positive — a phase-3 drug for a *descendant* disease — while Open
Targets never associates it with the parent disease under any datasource,
not even the denylisted one. Left alone, such a target would vanish from
`labels.parquet` with nothing recording why. Measured: 18 targets total
across all ten diseases (11 of them breast carcinoma's), each logged via
`log_dropped` and counted in provenance as
`n_family_positive_outside_own_candidate_set`, per disease and in total.

**The finding that drives the plan: 78–98% of each disease's positives are
also positives in at least one other disease in the set** (rightmost column
above — each shared target counted once per disease it recurs in). The
finished pipeline (§10) reports a second, stricter version of the same fact:
65% of *distinct* positive targets — each one counted once, not once per
disease — recur in more than one configured disease. Both are true; they
differ only in denominator. Leave-one-disease-
out evaluation hides the held-out disease's *labels*, but it cannot hide that
TNF, IL6R and EGFR are drug targets somewhere else in the training set. A
model can post an excellent NDCG@10 having learned only "this is a druggable,
well-studied protein" — a disease-agnostic, target-intrinsic signal — without
learning anything disease-specific at all.

This is the same failure shape Milestone 1 kept surfacing: a number that
looks right while the mechanism behind it is empty (§5a there: the wrapped
ablation ranks, the leakage guard checking 5 columns and calling it clean).
So it is measured directly rather than left as a caveat:

- A **`target_popularity` baseline** is added to `baselines_for_comparison`:
  rank each held-out disease's candidates by the number of *training-fold*
  diseases in which the target is a positive. If it beats logistic regression
  or XGBoost, that is the headline result of Milestone 2, not a footnote.
- **Every per-disease ranking metric is stratified** into positives also seen
  in a training-fold disease vs. positives novel to the held-out disease. The
  novel subset is the only place genuinely disease-specific signal can show
  up; if the model's advantage over `target_popularity` evaporates there, the
  report says so.

---

## 2. Decisions, and why

Three label-design questions were resolved by measurement before coding
started, each with a sensitivity check recorded rather than silently assumed.

**XGBoost.** `libxgboost.dylib` failed to load in this venv — missing
`libomp`, the same OpenMP runtime LightGBM and `shap`'s numba backend need.
Fixed with `brew install libomp`; verified end-to-end (not assumed): a real
`XGBClassifier` fit and a `shap.TreeExplainer` pass both ran cleanly
afterward. §37's `models/trained/xgboost_baseline.json` deliverable stands as
named — no fallback model needed.

**Label disease scope: expand to ontology descendants.** `clinical_target`
records disease IDs from `clinical_report`, which are frequently child terms
(e.g. HER2-positive breast carcinoma under breast carcinoma). A phase-3 drug
for the child is a phase-3 drug for the parent. The sensitivity check
(`n_positive_direct_only` vs. `n_positive`) compares direct-id-only and
descendant-expanded positive counts over the *same* population — both
restricted to the disease's own candidate set — so the delta isolates what
expansion actually changes, rather than mixing in an unrelated
population-size difference (an earlier draft of this comparison made that
mistake; caught before publishing rather than after). Measured: breast
carcinoma goes from 90 to 342 positives (3.8×); psoriasis 98 → 111;
rheumatoid arthritis 219 → 231; NSCLC 426 → 430; the other six diseases are
unaffected (no relevant descendants in their families, or none with
qualifying trials). Every disease also has a small population of
family-positive targets that never make it into `labels.parquet` at all —
`n_family_positive_outside_own_candidate_set` (18 release-wide, 11 of them
breast carcinoma's — candidate generation queries only a disease's own id,
the label doesn't) and `n_family_positive_dropped_clinical_only` (positives
whose only Open Targets evidence is the denylisted datasource). All three
counts, plus `n_family_positive` as the reconciling total, are recorded per
disease so `n_positive + outside_candidate_set + dropped_clinical_only ==
n_family_positive` holds exactly — verified by a dedicated test
(`test_family_positive_buckets_reconcile_exactly`), not just asserted in
prose.

**Grey zone: threshold stays at `positive_min_clinical_stage: 3`.** Stages 0–2
(preclinical through phase 2) are negatives; `UNKNOWN` (335 rows release-wide)
is excluded from both classes, never coerced to negative. This matches the
existing `configs/features.yaml` config and §15's negative definition
verbatim — no config change needed here. Affects roughly 320 grey-zone targets
across all ten diseases. A threshold-2 sensitivity run is reported alongside,
since it disproportionately helps the data-poor diseases (Crohn's 87 → ~103
positives).

**Clinical-only positives are dropped, loudly.** A target whose *only*
Open Targets evidence is the denylisted `clinical_precedence` datasource has
no features to rank on — keeping it as an all-null row would inflate the
recall denominator with something the model structurally cannot place. This
follows the same logic Milestone 1 already applies (§4 there: 37 Parkinson's
candidates dropped for the same reason). The cost is not uniform: multiple
sclerosis loses 165 of 330 positives (50%), ulcerative colitis 101 of 206
(49%), while Alzheimer's loses only 13 of 280 (5%). The losses are not random
— surviving positives skew toward targets with genetics or functional
evidence in addition to clinical evidence, i.e. toward *already well-studied*
targets. Per-disease counts go into label provenance and the report; this is
exactly the kind of row-count change §34 requires be visible rather than
inferred.

**External datasets: still out of scope.** §28 Step 9 sequences Reactome,
GTEx and STRING *after* Step 8 (train + evaluate baselines), and §37 never
mentions them. Milestone 2 is Open Targets only, same scope decision Milestone
1 made and for the same reason.

---

## 3. The ten §37 tasks

| # | Task | Plan | Where |
| --- | --- | --- | --- |
| 1 | Expand to ~ten diseases | All ten in `configs/diseases.yaml`, already resolved | — |
| 2 | Build a unified disease–target table | `build_feature_table()`, widened beyond Milestone 1's five dimensions to per-datasource columns | `features/build_features.py` |
| 3 | Define positive and hard-negative labels | `clinical_target`, descendants expanded, threshold 3, `UNKNOWN` excluded, clinical-only candidates dropped | new `data/labels.py` |
| 4 | Remove label-leaking features | Reuses Milestone 1's guard; `assoc_overall__*` kept out of the joined matrix entirely | `features/build_features.py` |
| 5 | Split by disease | Leave-one-disease-out, 10 folds | `models/evaluate.py` |
| 6 | Train logistic regression | Per-fold-fitted imputation + scaling in a `Pipeline` | `models/train.py` |
| 7 | Train XGBoost | Native NaN handling, `n_jobs` pinned for determinism | `models/train.py` |
| 8 | Calculate ranking metrics | Per-disease then aggregated (§19.3), never pooled; stratified by cross-disease positive overlap | `models/evaluate.py` |
| 9 | Add SHAP explanations | `TreeExplainer` (XGBoost), `LinearExplainer` (logistic regression) | `models/explain.py` |
| 10 | Compare ML models with the rule-based baseline | Plus `open_targets_overall_score`, `random_ranking`, `target_popularity` | `milestone2.py` |

---

## 4. Feature table design

Widened beyond the five Milestone 1 dimensions to the full matrix §14/§27
describe — per-datasource `assoc_ds__<name>_score` / `_evidence_count` via the
already-implemented `pivot_evidence`, plus the dimension scores, evidence
diversity, druggability, safety and `missing__<group>` indicators. SHAP needs
interpretable individual columns, not five pre-aggregated ones.

Three hazards specific to leave-one-disease-out, handled at build time:

- **Disease-constant features are excluded from the default matrix.**
  `disease__n_associated_targets`, `disease__therapeutic_area`,
  `disease__is_cancer` are constant within a disease. In training folds they
  behave as fold identifiers rather than signal; at test time they're a
  single constant value the model has never seen vary. Run as an explicit
  ablation (with vs. without) rather than silently included.
- **Per-fold sparse-datasource handling.** `crispr_screen` covers 3 of 10
  diseases, `intogen` 1, `gene2phenotype` 1. A column that is all-null or
  zero-variance within a training fold is dropped for that fold, with the
  count logged — an untrained column contributes nothing and can only add
  noise to fold-specific null-handling.
- **`assoc_overall__*` never joins into the feature frame.** It is loaded
  separately and used only as the `open_targets_overall_score` evaluation
  baseline. Any label-derived column carries a `label` prefix so the existing
  `label*` denylist rule catches it — a name like `is_positive` would
  otherwise slip past every existing rule.

---

## 5. Evaluation design

Ten leave-one-disease-out folds, per config.yaml's `split.strategy`. Metrics
computed per disease first, then aggregated — never pooled, per §19.3 and the
existing docstring in `models/evaluate.py`.

- **Ties break on score → `target_id`.** Logistic regression over the 71%
  literature-only rows (Milestone 1's finding, §3 of milestone1.md) will
  produce exact score ties, and ranking metrics computed over an
  undefined tie order are order-dependent — the same class of bug as the
  `calpastatin` non-determinism Milestone 1 caught (milestone1.md §5a).
  Verified by hashing `baseline_metrics.json` across three runs, not assumed.
- **Recall@k is reported beside positive counts, not compared raw across
  diseases.** Recall@20 ceilings at 5.8% for breast carcinoma (342 positives)
  and 23% for Crohn's (87) purely from denominator size. NDCG@10 stays the
  primary metric per `configs/model.yaml`.
- **Brier score is either computed on unweighted predictions or dropped with
  a note.** `class_weight: balanced` and fold-derived `scale_pos_weight`
  distort the probability scale; scored naively, Brier would measure the
  reweighting rather than calibration.
- **Stratified metrics**: every per-disease ranking metric also computed
  restricted to positives *not* seen as positive in any training-fold
  disease — the subset where disease-specific signal, if it exists, would
  show up.

---

## 6. Acceptance check

Falsifiable, exits non-zero, same spirit as `scripts/run_milestone1.py`:

1. Every trained model beats `random_ranking` on NDCG@10 in ≥ 9 of 10
   diseases.
2. XGBoost ≥ logistic regression ≥ weighted baseline on mean NDCG@10 — or the
   report states explicitly which comparison failed and why. §17's training
   order exists so a boosted model that can't beat a transparent one flags a
   data problem, not a modelling one; skipping past a failure here would
   defeat the point of ordering the models at all.
3. A deliberate leakage probe (adding a denylisted column back in) raises
   `LeakageError`, mirroring the check Milestone 1 added after finding its
   guard was checking 5 columns instead of 18 (milestone1.md §4). A guard
   never shown to fire is not known to work.
4. `target_popularity` is reported alongside every trained model on every
   metric. If it wins, that is stated as the milestone's finding, not
   smoothed over.
5. `reports/evaluation/baseline_metrics.json` is byte-identical across three
   consecutive runs.

---

## 7. Deliverables

```text
data/processed/disease_target_features.parquet
data/processed/labels.parquet                    (not in §37's list, but required to build the above)
models/trained/xgboost_baseline.json
models/metadata/<run>.json                        (§33 reproducibility record)
reports/evaluation/baseline_metrics.json
reports/evaluation/baseline_report.md
```

**Out of scope, deliberately**: Reactome/GTEx/STRING integration (§28
Step 9), the LightGBM learning-to-rank model (§17.6, already
`enabled: false` in `configs/model.yaml`), the Streamlit interface
(Milestone 3, §21), novel-candidate generation (§30.8).

---

## 8. Progress checklist

- [x] Phase 0 — config extensions (`LabelConfig.expand_to_descendants`,
      `target_popularity` baseline, `n_jobs` pinned, Brier score decision),
      README libomp note
- [x] Phase 1 — `data/labels.py`, `labels.parquet`, `tests/test_labels.py`
      (18 tests). Found and fixed a gap beyond the original measurement plan:
      18 targets release-wide are family-positive but outside a disease's own
      candidate set — see §2's addendum.
- [x] Phase 2 — `build_feature_table()`, `disease_target_features.parquet`
      (89,666 rows × 62 columns; features and labels candidate sets verified
      to match exactly, zero mismatch either direction)
- [x] Phase 3 — `models/evaluate.py` (LODO splits, ranking metrics, ties,
      stratification; 41 tests, every ranking formula checked against
      hand-computed values)
- [x] Phase 4 — `models/train.py`, `models/predict.py` (logreg → RF →
      XGBoost, fold-fitted preprocessing, run metadata; 19 tests). Found and
      fixed a pre-existing gap: `select_feature_columns` didn't exclude
      `biotype`, so a string column would have reached `.fit()`.
- [x] Phase 5 — comparison baselines (`weighted_baseline`,
      `open_targets_overall_score`, `random_ranking`, `target_popularity`;
      12 tests)
- [x] Phase 6 — `models/explain.py` (SHAP, global + per-target; 18 tests,
      including a reconstruction check per model type — random forest's
      `TreeExplainer` output is natively probability-space, not margin-space
      like XGBoost's and logistic regression's, which is easy to get backwards)
- [x] Phase 7 — `milestone2.py` orchestration, `scripts/train_model.py`,
      `scripts/evaluate_model.py`, generated report, README status update,
      `docs/model_card.md`. Found and fixed two issues surfaced only by
      running the real 10-fold pipeline: `brier_score_loss` crashes on
      `target_popularity`'s out-of-[0,1] raw-count score (now returns None,
      consistent with every other "undefined" case in `evaluate.py`), and
      `sklearn.metrics`' internal floating-point summation order varies
      run-to-run under multi-threaded BLAS by ~1 part in 10^16 — harmless
      numerically, but broke the byte-identical-rerun requirement until
      metric values were rounded to 10 decimal places.

298 tests passing (up from 169 at the start of this milestone, per the
README's count before it).

---

## 9. Post-review corrections

A second-pass review of the finished implementation (not the original
build) found four issues worth recording here, since three of them changed
numbers already published in this document, the README and the model card:

- **The literature ablation (§10, `reports/evaluation/baseline_report.md`
  §5) was leaking literature signal past the "ablated" model.** It dropped
  the direct `assoc_ds__europepmc_*` / `assoc_ds__uniprot_literature_*`
  columns but not `n_evidence_types` / `dim__evidence_diversity`
  (`genetics.py`, `build_evidence_diversity`) — both count literature
  datasources among a target's "distinct evidence types", so the "ablated"
  model could still read literature presence off the diversity term. Fixed
  by dropping both from the ablation too (`milestone2.py`,
  `_drop_literature_columns`). The corrected result **reverses the sign**
  reported earlier: removing literature (plus the diversity term it fed)
  *improves* NDCG@10 from 0.696 to 0.743, rather than costing 0.043 as
  originally measured. Since the diversity term also carries non-literature
  signal, this measures literature's contribution net of that loss, not in
  isolation — noted in the generated report rather than smoothed over.
- **SHAP explainability (§37 task 9) was a tested library `explain.py` never
  called from the pipeline** — the model card's global-importance list was
  computed by hand, off-pipeline, contradicting this project's own "the
  report is generated, not hand-written, so its prose cannot drift" standard
  (§7, `reporting2.py`). Fixed: `run_milestone_2` now computes
  `global_feature_importance` on the final production model and writes it to
  `baseline_metrics.json`; the generated report gained a section from it;
  the model card no longer hand-lists specific features, only points at the
  generated table. Two determinism bugs surfaced while wiring this in and
  were fixed the same way §37's other floating-point non-determinism was
  (rounding, deterministic tie-break) — see `explain.py`,
  `global_feature_importance`.
- **Two different recurrence percentages appeared for the same claim**: this
  document's §1 table says 78–98% (per-disease, a shared target counted once
  per disease), the generated report said 65% (each target counted once,
  regardless of how many diseases it recurs in). Both are correct; neither
  document said so. Fixed by adding the denominator clause to both places
  (§1 above, and `reporting2.py`'s report §2) and to the README.
- `models/metadata/` is gitignored, but the model card and the generated
  report both referenced a path inside it as if it were part of the
  committed repo. Fixed by noting in both places that the directory is
  generated locally per run and not committed.

All four fixes are reflected in the current `reports/evaluation/baseline_report.md`,
`docs/model_card.md` and this document. Re-verified after: full test suite
(298 passing), `ruff`, `mypy`, and two independent full pipeline runs diffed
byte-identical on both `reports/evaluation/baseline_metrics.json` and
`models/trained/xgboost_baseline.json`.

---

## 10. Results

The full 10-fold leave-one-disease-out run (`scripts/evaluate_model.py`,
~90 seconds) confirmed §1's hypothesis, more sharply than the design-time
estimate suggested:

| Method | NDCG@10 (primary) | NDCG@10 (novel-only) |
| --- | ---: | ---: |
| Target popularity | **0.873** | 0.000 |
| OT overall score | 0.752 | 0.093 |
| XGBoost | 0.696 | 0.009 |
| Random forest | 0.529 | 0.000 |
| Logistic regression | 0.501 | 0.067 |
| Weighted baseline | 0.288 | 0.050 |
| Random | 0.031 | 0.000 |

**`target_popularity` — a baseline with no learning at all, just a count of
how many other diseases a target is positive in — outranks every trained
model, including XGBoost.** Restricting evaluation to positives that do
*not* recur across diseases (`novel_only_labels`) collapses every method's
NDCG@10 toward zero; XGBoost falls from 0.696 to 0.009. On the evidence
measured here, the ML models learned mostly "this is a druggable,
well-precedented target" rather than anything disease-specific.

This is stated as the headline finding, not smoothed into a footnote, per
the acceptance-check design in §6: the ordering check (XGBoost ≥ logistic
regression ≥ weighted baseline) was deliberately kept out of the pass/fail
gate specifically because enforcing it would have hidden this result. The
one falsifiable exit-code check — every method beats `random_ranking` on
NDCG@10 in ≥ 9/10 diseases — passed for all six non-random methods (5/6 at
10/10, `weighted_baseline` at 9/10).

Determinism verified by diffing `reports/evaluation/baseline_metrics.json`
across two full runs (byte-identical), not assumed — the same standard
Milestone 1 held itself to.

Full analysis, per-disease breakdown, literature ablation and limitations:
[reports/evaluation/baseline_report.md](reports/evaluation/baseline_report.md).

## 11. Next

Milestone 3 (Context.md §21): Streamlit interface — disease search, ranked
target table, target detail view with explanations, filters. Should surface
the primary/novel-only distinction from §10 directly in the UI rather than
presenting a single score, given how much of it §10 shows to be
cross-disease popularity rather than disease-specific evidence.
