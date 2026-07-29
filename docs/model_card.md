# Model Card

Template per Context.md §33 and Project_info.md §42. **No model has been trained
yet** — this records what must be filled in when one is.

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

## Metrics to report

Per disease, then aggregated (§19.3). Primary: NDCG@10. Also
Precision@{5,10}, Recall@{10,20}, MAP, MRR, and PR-AUC — not ROC-AUC alone,
which flatters under this class imbalance.

Baselines to beat: Open Targets overall score, the weighted rule-based score, and
random ranking.

Required ablations: `no_literature` (measures publication bias), `no_network`,
`genetics_only`.

## To be completed at training time

- [ ] Model type and hyperparameters
- [ ] Training date, code commit, random seed
- [ ] Dataset version (currently Open Targets 26.06)
- [ ] Per-disease and aggregate metrics
- [ ] Ablation results
- [ ] Calibration
- [ ] Global feature importance
- [ ] Manual review of top-10 predictions for Parkinson's disease
- [ ] Failure modes observed
