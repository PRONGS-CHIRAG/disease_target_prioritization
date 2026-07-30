# Model Card

Per Context.md §33 and Project_info.md §42. Describes the Milestone 2
(Context.md §37) XGBoost model, `models/trained/xgboost_baseline.json`,
refit on all ten configured diseases after leave-one-disease-out evaluation.
Generated from `reports/evaluation/baseline_metrics.json`; see
[../reports/evaluation/baseline_report.md](../reports/evaluation/baseline_report.md)
for the full analysis.

## Intended use

**Intended:** generating a ranked shortlist of candidate therapeutic targets for a
disease, as a research-support aid, with the supporting evidence inspectable.

**Not intended:** medical diagnosis, treatment selection, any patient-level
decision, or as evidence that a target is validated. See
[limitations.md](limitations.md).

## Problem formulation

Binary classification over disease–target pairs, converted to a per-disease
ranking (Context.md §9.5). Learning-to-rank is deferred until the classification
baseline works and its ranking metrics are understood.

## Label

**Positive:** target of a drug at Phase 3 or beyond for that disease, from
`clinical_target.maxClinicalStage` (`APPROVAL`, `PREAPPROVAL`, `PHASE_3`,
`PHASE_2_3`).

**Negative:** other targets associated with the same disease without such
evidence. Hard negatives from the same disease biology, not random genes
(Context.md §32.5).

**Excluded:** `UNKNOWN` stage — not assumed negative.

The label is a proxy for "has been pursued", not for "is a good target".

## Leakage controls

Denylisted from the feature matrix, enforced by `LeakageError`:

| Column | Why |
| --- | --- |
| `assoc_ds__clinical_precedence*` | Is the label. All 107,593 pairs are label pairs. |
| `assoc_overall__*` | Aggregates the clinical evidence behind the label |
| `prio__max_clinical_stage` | Derived from clinical development status |

Split: leave-one-disease-out, grouped on `disease_id`. Random row splits are
prohibited (Context.md §19.4).

## Metrics (Context.md §19.3 — per disease, then aggregated)

Leave-one-disease-out, 10 folds. Primary metric: NDCG@10.

| Method | NDCG@10 (primary) | NDCG@10 (novel-only) | Beats random |
| --- | ---: | ---: | ---: |
| Weighted baseline | 0.288 | 0.050 | 9/10 |
| Logistic regression | 0.501 | 0.067 | 10/10 |
| Random forest | 0.529 | 0.000 | 10/10 |
| **XGBoost (this model)** | **0.696** | **0.009** | 10/10 |
| OT overall score | 0.752 | 0.093 | 10/10 |
| Random | 0.031 | 0.000 | — |
| Target popularity | 0.873 | 0.000 | 10/10 |

**Read the two NDCG@10 columns together, not separately.** "Novel-only"
re-scores against [`novel_only_labels`](../src/target_prioritization/models/evaluate.py),
which relabels every positive that recurs across the ten configured diseases
to negative. This model's score falls from 0.696 to 0.009 under that
condition — most of its apparent ranking quality is explained by learning
which targets are drug targets *somewhere*, not by disease-specific
evidence. The `target_popularity` baseline (no learning at all, just a count
of cross-disease positives) outscores this model on the primary metric.
Treat this model's ranking as "plausibly druggable, well-precedented target"
more than "target specifically relevant to the queried disease."

Full per-disease breakdown: `reports/evaluation/baseline_metrics.json`.

## Ablation: literature evidence (Context.md §32.2)

| | NDCG@10 |
| --- | ---: |
| With literature | 0.696 |
| Without literature | 0.743 |

Removing literature — and `n_evidence_types`/`dim__evidence_diversity`, which
also count literature datasources among a target's evidence-type count, so
they're dropped alongside the direct columns to avoid leaking literature
presence through the back door — *improves* NDCG@10 by 0.047. See
[baseline_report.md §5](../reports/evaluation/baseline_report.md) for the
full explanation; this is not the modest positive contribution Milestone 1's
finding for the rule-based score would suggest.

`no_network` is not applicable in this milestone (no STRING data — Context.md
§28 Step 9 is still pending); `genetics_only` was not run.

## Global feature importance (mean |SHAP|, margin space)

Computed by `run_milestone_2` on the production model (`explain.py`,
`global_feature_importance`) and written to
`reports/evaluation/baseline_metrics.json` → `global_feature_importance` on
every run — see the top-10 table in
[baseline_report.md §7](../reports/evaluation/baseline_report.md). Not
reproduced here as a static list: this section previously hand-copied a
top-5 snapshot, which could silently go stale the next time the model was
retrained. The pattern that table shows is stable across runs: the top
features are largely **target-intrinsic** (is this protein druggable, how
constrained is the gene, how much has it been studied) rather than
disease-specific — consistent with the novel-only collapse above.

## Calibration

Not assessed. Brier score is reported per model in
`baseline_metrics.json` for the three models with genuine [0, 1] probability
outputs (logistic regression, random forest, XGBoost), but no reliability
diagram or recalibration was performed.

## Training details

| | |
| --- | --- |
| Model type | `xgboost.XGBClassifier`, `binary:logistic` |
| Hyperparameters | `configs/model.yaml` → `models.xgboost.params` |
| Random seed | 42 |
| Dataset version | Open Targets 26.06 |
| Training data | All 10 configured diseases, 89,666 candidate rows, 2,233 positives (2.49% prevalence) |
| `scale_pos_weight` | Computed from the training data at fit time, per fold under evaluation and once for the final refit — never fixed in config |
| Code commit, training date | `models/metadata/milestone2_<timestamp>.json` (one record per run; generated locally, gitignored — not part of the committed repo) |

## Manual review

Not performed for this milestone — Milestone 1's Parkinson's-specific manual
review (`milestone1.md` §4) covered the rule-based score only. A comparable
per-disease qualitative review of the ML models' top predictions is future
work.

## Known failure modes

- **Cross-disease popularity dominance** (above) — the central finding of
  this milestone.
- **Undefined for zero-positive-in-fold metrics** where they'd occur;
  handled by exclusion from the aggregate mean rather than crashing, logged
  via `metric_undefined_for_some_diseases`.
- **`target_popularity`'s score is not a probability** — it is a raw count,
  correctly reported as undefined for Brier score rather than forced into
  [0, 1].
