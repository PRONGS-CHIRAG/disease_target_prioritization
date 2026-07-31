# Multi-Disease Target Prioritization — Milestone 2 Baseline Report

Milestone 2 (Context.md §37): expand the rule-based Milestone 1 baseline to
10 diseases, define labels from clinical development evidence, train
ML baselines, and evaluate everything under leave-one-disease-out —
turning Milestone 1's sanity check into a measurement.

> **These are prioritization hypotheses, not validated findings.** A high
> score does not mean a target will yield an effective drug. See
> [docs/limitations.md](../docs/limitations.md) and section 8 below.

| | |
| --- | --- |
| Diseases | 10 (`configs/diseases.yaml`) |
| Data source | Open Targets Platform release 26.06 |
| Extraction date | 2026-07-30 |
| Candidate rows | 89,666 |
| Positives | 2,233 (2.49% prevalence) |
| Split | Leave-one-disease-out, 10 folds (Context.md §19.4) |
| Primary metric | NDCG@10, per-disease then averaged (Context.md §19.3) |

## 1. The dataset

Label = target of a drug that reached at least phase 3 for the disease (or an
ontology descendant of it — `configs/features.yaml` `label.expand_to_descendants`).
Full label-construction detail, including two gaps found while building this
(clinical-only candidates dropped, family-positives outside a disease's own
candidate set) is in [milestone2.md §1-2](../../milestone2.md).

| Disease | Candidates | Positives | Negatives | Prevalence |
| --- | ---: | ---: | ---: | ---: |
| Alzheimer's disease | 13,275 | 267 | 13,008 | 2.0% |
| breast carcinoma | 15,578 | 342 | 15,236 | 2.2% |
| Crohn's disease | 6,212 | 87 | 6,125 | 1.4% |
| multiple sclerosis | 4,170 | 165 | 4,005 | 4.0% |
| non-small cell lung carcinoma | 10,809 | 430 | 10,379 | 4.0% |
| Parkinson's disease | 8,690 | 238 | 8,452 | 2.7% |
| psoriasis | 6,896 | 111 | 6,785 | 1.6% |
| rheumatoid arthritis | 7,139 | 231 | 6,908 | 3.2% |
| type II diabetes mellitus | 9,851 | 257 | 9,594 | 2.6% |
| ulcerative colitis | 7,046 | 105 | 6,941 | 1.5% |

## 2. The central finding: cross-disease target popularity

**65% of distinct positive targets are positive in more than
one configured disease** (each target counted once, however many diseases it
recurs in — milestone2.md §1's per-disease table reports 78–98%, a different
statistic: the share of *each disease's own* positives that recur elsewhere,
which counts a shared target once per disease rather than once overall, so it
runs higher). Under leave-one-disease-out, a model never sees the held-out
disease's own labels — but it can still rank well by learning "this target is
a positive somewhere else", which is target-intrinsic and disease-agnostic,
not evidence about the held-out disease at all.

**`target_popularity`** — a baseline that scores each candidate by nothing
but the count of *other* diseases where it is a labelled positive
(`models/baselines.py`) — measures this directly:

![Primary vs. novel-only NDCG@10 for every method](figures/milestone2_popularity_comparison.png)

| Method | Primary | Novel-only |
| --- | ---: | ---: |
| Weighted baseline | 0.288 | 0.050 |
| Logistic regression | 0.487 | 0.062 |
| Random forest | 0.865 | 0.000 |
| XGBoost | 0.901 | 0.000 |
| OT overall score | 0.752 | 0.093 |
| Random | 0.031 | 0.000 |
| Target popularity | 0.873 | 0.000 |

Primary-column ranking: XGBoost (0.901) > Target popularity (0.873) > Random forest (0.865) > OT overall score (0.752) > Logistic regression (0.487) > Weighted baseline (0.288) > Random (0.031).

**`target_popularity` outranks every trained model, including XGBoost.** That
is this milestone's headline result, not a footnote.

### The novel-only column is what disease-specific signal actually looks like

The "Novel-only" column re-evaluates every method against
[`novel_only_labels`](../../src/target_prioritization/models/evaluate.py) —
the same candidates, the same ranking, but every positive that recurs across
diseases is relabelled negative first, so only positives unique to their own
disease count as relevant. Every method's NDCG@10 collapses:
OT overall score (0.093) > Logistic regression (0.062) > Weighted baseline (0.050) > Random forest (0.000) > XGBoost (0.000) > Target popularity (0.000).

`target_popularity` goes to exactly 0.0 — mechanically guaranteed, since a
novel-only positive by definition scores 0 under that baseline. XGBoost falls
from 0.901 to 0.000:
on the evidence measured here, the model learned mostly cross-disease
popularity, not disease-specific biology.

## 3. Full metrics

Aggregate (mean across diseases), primary evaluation:

| Method | NDCG@10 | NDCG@20 | Precision@10 | Recall@20 | MAP | MRR | Hit rate | ROC-AUC | PR-AUC |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Weighted baseline | 0.288 | 0.250 | 0.220 | 0.019 | 0.083 | 0.698 | 1.000 | 0.755 | 0.083 |
| Logistic regression | 0.487 | 0.392 | 0.440 | 0.030 | 0.164 | 0.850 | 1.000 | 0.887 | 0.164 |
| Random forest | 0.865 | 0.814 | 0.850 | 0.082 | 0.556 | 0.933 | 1.000 | 0.969 | 0.556 |
| XGBoost | 0.901 | 0.883 | 0.880 | 0.092 | 0.564 | 1.000 | 1.000 | 0.964 | 0.564 |
| OT overall score | 0.752 | 0.767 | 0.770 | 0.090 | 0.290 | 0.800 | 1.000 | 0.887 | 0.290 |
| Random | 0.031 | 0.035 | 0.030 | 0.004 | 0.027 | 0.127 | 0.300 | 0.503 | 0.027 |
| Target popularity | 0.873 | 0.838 | 0.840 | 0.092 | 0.567 | 0.950 | 1.000 | 0.936 | 0.535 |

Recall@k is not comparable across diseases — it ceilings at `min(k, n_positive) / n_positive`,
which varies with each disease's positive count (milestone2.md §5). Brier
score is reported only for models whose score is a genuine [0, 1] probability;
`target_popularity`'s raw count is out of range for it by construction and is
correctly reported as undefined rather than crashing the evaluation
(`reports/evaluation/baseline_metrics.json` has the full per-disease breakdown).

### Per-disease NDCG@10

| Disease | Weighted baseline | Logistic regression | Random forest | XGBoost | OT overall score | Random | Target popularity |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Alzheimer's disease | 0.404 | 0.591 | 1.000 | 1.000 | 0.742 | 0.000 | 0.644 |
| breast carcinoma | 0.359 | 0.672 | 0.915 | 0.870 | 0.320 | 0.110 | 0.870 |
| Crohn's disease | 0.224 | 0.290 | 0.247 | 0.551 | 0.710 | 0.095 | 0.936 |
| multiple sclerosis | 0.066 | 0.290 | 1.000 | 0.931 | 0.861 | 0.110 | 0.870 |
| non-small cell lung carcinoma | 0.606 | 0.934 | 0.934 | 1.000 | 1.000 | 0.000 | 0.934 |
| Parkinson's disease | 0.078 | 0.286 | 1.000 | 1.000 | 0.446 | 0.000 | 0.870 |
| psoriasis | 0.315 | 0.564 | 0.934 | 0.890 | 0.905 | 0.000 | 0.731 |
| rheumatoid arthritis | 0.085 | 0.628 | 0.927 | 0.915 | 0.836 | 0.000 | 1.000 |
| type II diabetes mellitus | 0.523 | 0.479 | 0.867 | 1.000 | 0.701 | 0.000 | 0.870 |
| ulcerative colitis | 0.220 | 0.139 | 0.824 | 0.849 | 1.000 | 0.000 | 1.000 |

## 4. Acceptance check

**PASS.** Every evaluated method beats the random-ranking floor on NDCG@10 in at least 9 of 10 diseases.

| Method | Diseases won / total |
| --- | ---: |
| Weighted baseline | 9 / 10 |
| Logistic regression | 10 / 10 |
| Random forest | 10 / 10 |
| XGBoost | 10 / 10 |
| OT overall score | 10 / 10 |
| Target popularity | 10 / 10 |

This is the only falsifiable, exit-code check (milestone2.md §6). A second
candidate check — XGBoost ≥ logistic regression ≥ weighted baseline on mean
NDCG@10 — is deliberately **not** an exit-code condition: whether that
ordering holds is itself a finding to report, and section 2 shows XGBoost's
apparent lead over the simpler models is substantially explained by
target-popularity rather than model quality, so treating the ordering as a
pass/fail gate would have hidden exactly the result this milestone exists to
surface.

## 5. Literature ablation (Context.md §32.2)

Re-training XGBoost with every literature-derived column removed
(`assoc_ds__europepmc_*`, `assoc_ds__uniprot_literature_*`, `dim__literature`,
`missing__literature`, and — since they count literature datasources among a
target's "distinct evidence types" — `n_evidence_types` and
`dim__evidence_diversity`), under the same leave-one-disease-out evaluation:

| | NDCG@10 |
| --- | ---: |
| With literature | 0.901 |
| Without literature | 0.889 |

Removing literature costs 0.011 NDCG@10 — literature contributes a real but modest amount, consistent with Milestone 1's finding that it is present but not dominant once genetics and functional evidence are available (milestone1.md §5).

## 6. The weighted baseline was never tuned against this label

`milestone_1_weights` (`configs/model.yaml`) were set by hand against a single
criterion: whether five established Parkinson's genes reach the top 20
(milestone1.md §3). They were never fit or validated against the clinical-stage
label Milestone 2 evaluates against, so a low score here is not evidence the
weights are bad — it is evidence they were optimizing for something else.

Its three weakest diseases by NDCG@10: multiple sclerosis (0.066), Parkinson's disease (0.078), rheumatoid arthritis (0.085). Its three strongest:
non-small cell lung carcinoma (0.606), type II diabetes mellitus (0.523), Alzheimer's disease (0.404).

Notably, this is **not** a cancer-vs-non-cancer split — NSCLC and breast
carcinoma (whose cancer-specific datasources sit in `_unmapped`,
`configs/features.yaml`) do not score worse than several non-cancer diseases,
so the datasources genuinely absent from the weighted baseline's scope are not
the dominant effect visible in this comparison.

## 7. Global feature importance (final XGBoost, mean |SHAP|)

Computed on the production model — refit on all 10 diseases, not a
LODO fold — via [`explain.global_feature_importance`](../../src/target_prioritization/models/explain.py).
Values are in margin (log-odds) space, XGBoost's native SHAP output (module
docstring there explains why that space, not probability space, is correct
for this model type). Regenerated on every run from
`reports/evaluation/baseline_metrics.json` → `global_feature_importance`, so
this table cannot drift from the model it describes.

| Feature | Mean absolute SHAP |
| --- | ---: |
| `net__weighted_degree` | 1.0860 |
| `prio__has_ligand` | 0.8735 |
| `net__mean_edge_confidence` | 0.5691 |
| `dim__druggability` | 0.4965 |
| `assoc_ds__europepmc_evidence_count` | 0.4897 |
| `net__degree` | 0.4304 |
| `expr__median_tpm` | 0.3399 |
| `prio__genetic_constraint` | 0.3123 |
| `expr__tissue_specificity` | 0.2742 |
| `dim__network` | 0.2572 |

## 8. Limitations

1. **Cross-disease target popularity, not disease-specific signal, explains
   most of the primary result** (section 2). Report every headline number
   alongside its novel-only counterpart.
2. **The label is an imperfect proxy.** A target without an approved or
   late-stage drug is not necessarily a poor target — it may be understudied,
   recently discovered, or the disease may lack any drug-development program
   at all (Context.md §15).
3. **Ten diseases only.** Generalisation to diseases outside
   `configs/diseases.yaml` is untested; leave-one-disease-out measures
   robustness across *these* ten, not universally.
4. **Reactome/GTEx/STRING topology and expression features are disease-invariant
   gene properties, learned by XGBoost as such.** Milestone 4 (milestone4_plan.md)
   wired in `path__*`/`net__*`/`expr__*`; `net__weighted_degree` is now this
   model's single highest-SHAP feature. Because the same gene has the identical
   topology regardless of which disease is being ranked, this widens the
   cross-disease popularity gap point 1 already describes rather than closing
   it — see `reports/evaluation/baseline_weights_comparison.json` for the
   weighted-baseline-side comparison, which does not have this problem.
5. **Safety is not scored.** `prio__has_safety_event` and related columns are
   present in the feature table but never combined into any model's score
   (Context.md §14.7, §31.7) — a high-ranked target may still be unsafe to
   modify.
6. **Brier score, precision/recall/F1 assume a genuine probability.** Only
   logistic regression, random forest and XGBoost produce one; the other four
   methods' classification-metric numbers in section 3 are reported for
   completeness, not as a fair comparison.
7. **Results are tied to release 26.06.** A later Open Targets
   release may change candidate sets, evidence scores and clinical-stage
   labels enough to reorder these tables.

## 9. Deliverables

| Path | What it is |
| --- | --- |
| [data/processed/disease_target_features.parquet](../../data/processed/) | Multi-disease feature table, 89,666 rows |
| [data/processed/labels.parquet](../../data/processed/) | Labels + per-disease provenance |
| [models/trained/xgboost_baseline.json](../../models/trained/) | Final XGBoost model, refit on all 10 diseases |
| [reports/evaluation/baseline_metrics.json](baseline_metrics.json) | Every metric, every method, per-disease and aggregate |
| `models/metadata/milestone2_<timestamp>.json` | Per-run reproducibility record (Context.md §33) — generated locally by each run, gitignored, not part of the committed repo |

The report is **generated, not hand-written** (`reporting2.py`), so its prose
cannot drift from the numbers it describes.

## 10. Reproducing this report

```bash
uv run python scripts/train_model.py       # data + labels + LODO training
uv run python scripts/evaluate_model.py    # this report + baseline_metrics.json
```

Verified deterministic by diffing `baseline_metrics.json` across two full runs
(byte-identical) rather than assumed — the same standard Milestone 1 held
itself to (milestone1.md §8).
