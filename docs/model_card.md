# Model Card

Per Context.md §33 and Project_info.md §42. Describes the Milestone 2
(Context.md §37) XGBoost model, `models/trained/xgboost_baseline.json`,
refit on all ten configured diseases after leave-one-disease-out evaluation
— retrained on Milestone 4's expanded feature set (Reactome/GTEx/STRING;
milestone4_plan.md), same architecture and hyperparameters. Generated from
`reports/evaluation/baseline_metrics.json`; see
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
| Logistic regression | 0.487 | 0.062 | 10/10 |
| Random forest | 0.865 | 0.000 | 10/10 |
| **XGBoost (this model)** | **0.901** | **0.000** | 10/10 |
| OT overall score | 0.752 | 0.093 | 10/10 |
| Random | 0.031 | 0.000 | — |
| Target popularity | 0.873 | 0.000 | 10/10 |

**Read the two NDCG@10 columns together, not separately.** "Novel-only"
re-scores against [`novel_only_labels`](../src/target_prioritization/models/evaluate.py),
which relabels every positive that recurs across the ten configured diseases
to negative. Most of this model's apparent ranking quality is explained by
learning which targets are drug targets *somewhere*, not by disease-specific
evidence — worse now than at Milestone 2 (0.696/0.009), not better: Milestone
4's Reactome/GTEx/STRING features (`net__weighted_degree`, `expr__*`,
`path__*`) are disease-invariant gene properties, and XGBoost leaned on them
hard enough to push novel-only NDCG@10 to **exactly 0.000**, while the
primary score rose to 0.901. `net__weighted_degree` is now this model's
single highest-SHAP feature (below) — the network analogue of the same
cross-disease-popularity problem literature and target-count features
already had, now measurably worse. The `target_popularity` baseline (no
learning at all, just a count of cross-disease positives) still outscores
this model's *training signal*, even though this model's primary NDCG now
edges past it. Treat this model's ranking as "plausibly druggable,
well-studied, well-connected target" more than "target specifically relevant
to the queried disease" — more so than at Milestone 2, not less.

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

`no_network` and `genetics_only` (`configs/model.yaml`'s `evaluation.ablations`,
declared since Milestone 2 but never wired to a runner until now) are run
against `baseline_weights` via `scripts/compare_baseline_weights.py`, since
`no_network` only means something once a `network` weight exists to drop
(`milestone_1_weights` has no `network` key at all — this is why it was "not
applicable" before Milestone 4). Results:
`reports/evaluation/baseline_weights_comparison.json`. This is a
weight-drop-and-renormalize ablation on the weighted baseline, a different
mechanism from the literature ablation above (which drops feature *columns*
and retrains XGBoost from scratch) — see that script's docstring for why.

## Global feature importance (mean |SHAP|, margin space)

Computed by `run_milestone_2` on the production model (`explain.py`,
`global_feature_importance`) and written to
`reports/evaluation/baseline_metrics.json` → `global_feature_importance` on
every run — see the top-10 table in
[baseline_report.md §7](../reports/evaluation/baseline_report.md). Not
reproduced here as a static list: this section previously hand-copied a
top-5 snapshot, which could silently go stale the next time the model was
retrained. The pattern that table shows is stable across runs, and Milestone
4 sharpened it rather than changing it: the top features are largely
**target-intrinsic** (is this protein druggable, how constrained is the
gene, how much has it been studied, and — new since Milestone 4 — how many
STRING interactions it has and how highly expressed it is) rather than
disease-specific. `net__weighted_degree` (STRING interaction count weighted
by confidence) is now the single highest-SHAP feature of any kind, ahead of
`prio__has_ligand` — consistent with, and the concrete cause of, the
novel-only collapse to 0.000 above.

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
  Milestone 2, sharpened by Milestone 4: novel-only NDCG@10 went from 0.009
  to exactly 0.000 once disease-invariant network/expression/pathway
  features were added, with `net__weighted_degree` now the top SHAP feature.
- **Undefined for zero-positive-in-fold metrics** where they'd occur;
  handled by exclusion from the aggregate mean rather than crashing, logged
  via `metric_undefined_for_some_diseases`.
- **`target_popularity`'s score is not a probability** — it is a raw count,
  correctly reported as undefined for Brier score rather than forced into
  [0, 1].
