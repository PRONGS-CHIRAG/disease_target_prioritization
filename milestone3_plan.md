# Milestone 3 — Implementation Plan

Plan for Context.md §21 (MVP interface), §28 Step 11, and Project_info.md §37–38
(explainability page and dashboard): *build the Streamlit application*.

**Status: planned, not started.** This document is written before implementation,
in the same spirit as milestone2.md §1–2 — the measurements and constraints that
shape the design, recorded before any code makes them look inevitable. A separate
`milestone3.md` will record what was actually built.

---

## 1. The constraint that shapes everything: a third of the spec has no data behind it

Context.md §21 and Project_info.md §38 were written as a target picture for the
finished system. Measured against what is on disk after Milestone 2, roughly a
third of the specified interface cannot be built at all. Enumerating that first
is not a caveat — it is the plan, because every remaining decision follows from
which columns exist.

The multi-disease feature table (`data/processed/disease_target_features.parquet`,
89,666 × 62) carries five evidence dimensions, four missing-indicators, seven
Open Targets prioritisation fields and one safety count.

| Spec item | Source | Status |
| --- | --- | --- |
| Rank, gene symbol, gene name | §21 table | **Buildable** — `gene_symbol`, `gene_name` |
| Genetics evidence | §21 table, §38.2 | **Buildable** — `dim__genetics` |
| Druggability / tractability | §21 table, §38.2 | **Buildable** — `dim__druggability` |
| Biology / functional | §38.2 "Biology score" | **Buildable** — `dim__functional` |
| Literature | §14.2 | **Buildable** — `dim__literature` |
| Evidence diversity | §14.9 | **Buildable** — `dim__evidence_diversity`, `n_evidence_types` |
| Evidence completeness | §21 table, §32.3 | **Buildable** — from `missing__*`, see §2 below |
| Small-molecule tractability filter | §38.3 | **Buildable** — `prio__has_small_molecule_binder` |
| Safety concern filter | §38.3 | **Buildable as a flag**, not a score — `safety__n_flags`, `prio__has_safety_event` |
| **Pathway evidence** | §21 table + detail, §38.4 | **Not buildable** — `features/pathways.py` is a 38-line stub; §28 Step 9 defers Reactome |
| **Expression evidence / tissue expression** | §21 table + detail, §38.4 | **Not buildable** — `features/expression.py` is a 45-line stub; needs GTEx |
| **Network evidence / PPI summary** | §21 table + detail, §38.4 | **Not buildable** — `features/network.py` is a 53-line stub; needs STRING |
| **Relevant-tissue filter** | §21 filters, §38.3 | **Not buildable** — `configs/diseases.yaml` declares `relevant_tissues`, but no per-target expression exists to filter against |
| **Target family / target class filter** | §21 filters, §38.3 | **Not buildable as specified** — `configs/features.yaml` lists `drug__target_class` but the build does not produce it. `biotype` exists and is not the same thing |
| **Antibody tractability filter** | §38.3 | **Not buildable** — `isInMembrane` / `isSecreted` are configured but not built |
| **Direction of effect** | §37.6 | **Not buildable** — nothing in the pipeline computes it |
| **Confidence level** | §37.1 | **Undefined** — no calibrated uncertainty exists; §30.13 defers it |
| **Clinical score / known drug status / clinical phase** | §38.2, §38.3, §21 filters | **Buildable but it is the training label** — see §3 |

Three consequences, taken as decisions rather than left open:

**Missing dimensions render as explicit placeholders, not as zeros and not by
omission.** A "Pathway evidence — not yet integrated (Reactome, §28 Step 9)" cell
is spec-faithful and honest. A blank column invites the reader to conclude the
evidence was looked for and not found, which is exactly the §32.3 error the
project exists to avoid.

**A second, differently-scoped `evidence_completeness` is computed for display,
not the one `WeightedBaseline.score` already produces.** The baseline's own
`evidence_completeness` is a share of its *five weighted dimensions*
(`milestone_1_weights`: genetics, evidence_diversity, functional, literature,
druggability), essentially always near-complete. The display-facing version
is defined over a different, deliberately chosen six: `{genetics, functional,
pathway, expression, network, druggability}` — the union of §21's ranked-table
evidence columns and §38.2's, restricted to categories that are actual
absence-of-evidence signals rather than a safety flag or the training label.
Three of those six (pathway, expression, network) are categorically absent for
every target — not a per-target null, a whole category this milestone does not
build — so the ceiling is 3/6 for essentially every target, which is the
honest number and makes the absence-of-evidence point far better than a
sidebar bullet does. **Two columns with the same name and different
denominators is exactly the kind of trap this project's leakage guard exists
to catch elsewhere**, so the display version gets its own distinct name, and
whatever renders it states the denominator on screen ("3 of 6 categories —
pathway, expression and network not yet integrated"), not a bare fraction.
Literature is deliberately excluded from this six: it is not a column in
either §21's or §38.2's ranked-table, unlike in `WeightedBaseline`'s own five.

**Disease search covers the ten configured diseases only.** `services/disease_search.py`'s
docstring already anticipates the live GraphQL fallback; the plan declines it.
Release 26.06 has 47,080 diseases and precomputed features for ten. A live lookup
resolves any of them and then renders an empty table, and it reintroduces the
version-drift hole §32.7 warns about. Searching outside the set returns "not in
this release's precomputed set", never an empty ranking.

---

## 2. Decisions taken

| Question | Decision |
| --- | --- |
| Primary score | **Both, weighted baseline as the default view.** Its contributions sum exactly to the score (`WeightedBaseline.explain`, strictly better than SHAP's approximation), and it is the only model for which §38.5 scenario controls are possible at all — XGBoost cannot be re-weighted at inference. XGBoost is shown alongside it |
| In-sample scores | **Persist the leave-one-disease-out fold models.** Each disease is scored by the model that never saw it, matching the published 0.696 NDCG@10. Requires a change to the Milestone 2 training path and a re-run |
| FastAPI | **Out of scope.** §28 Step 11 specifies Streamlit. `api/main.py`'s `/rank` keeps raising `NotImplementedError`; the README status table says so. Services are still built as a standalone layer so the API stays a ~30-line addition later |

### 2.1 Why the in-sample question had to be settled

`models/trained/xgboost_baseline.json` is the final model refit on all ten
diseases (`milestone2.py:326`, `milestone2.py:400`). The fold models are trained
inside the LODO loop and discarded. So the only persisted XGBoost predicts
in-sample for every disease the app can display, while `baseline_metrics.json`
quotes held-out numbers. Showing one score and citing the other metric is a
mismatch no self-check catches, and it flatters the model in exactly the
direction Milestone 2's headline finding warns about.

### 2.2 The XGBoost score never appears without its caveat

Milestone 2 measured XGBoost at 0.696 NDCG@10 primary and **0.009 novel-only** —
its ranking is mostly cross-disease target popularity, not disease-specific
biology. That finding belongs next to the number in the UI, not in a sidebar the
reader scrolls past. The concrete, per-target form of it is the cheapest
high-value element in this milestone: **519 of the 796 targets that are positive
anywhere are positive in more than one of the ten diseases**, and several
(e.g. `ENSG00000073756`, `ENSG00000113161`) are positive in all ten. A "positive
for N other configured diseases" badge on each row turns the milestone's
aggregate finding into something a user can check per target.

---

## 3. The leakage boundary — the one thing that must not be got wrong

§21 asks for an "existing drug status" filter, §38.2 for "clinical score" and
"known drug status" columns, §38.3 for "clinical phase". All four come from
`max_clinical_stage` in `labels.parquet`. **That is the training label.**

Two distinct failures follow, and neither trips an existing check:

*Display.* A user sorting the table by known-drug-status is sorting by the answer
key. The top of the table looks spectacular by construction, and nothing on
screen says why.

*Path.* The leakage guard (`features/build_features.py`) runs in the
feature-build path. The app is a **new** path to the same parquet that bypasses
it entirely. `explain_target(model, features, ...)` calls
`model.predict_proba(row_frame)` on whatever frame it is handed. The README
already documents this guard failing open once, silently, while logging
`leakage_guard_passed`.

**Design rule, enforced by the acceptance check in §6: score first, join second.**
Label-derived columns (`label`, `label_source`, `max_clinical_stage`,
`label_reason`, and anything derived from them — including the
`n_diseases_positive` badge of §2.2) never appear in a frame passed to
`score_targets`, `explain_target`, `shap_values` or `WeightedBaseline.score`.

The ordering is what enforces this, not the storage location. `rank_for_disease`
scores on a frame carrying feature columns only, and *then* joins the display
frame on `(disease_id, target_id)` as its last step before returning. Scoring
and display never share a frame at any point. The services layer keeps the two
as separate types so the boundary is visible in the signatures — but the type
split alone is not the guarantee; the join being last is.

This matters because §2.2's popularity badge and the existing-drug summaries are
both label-derived and both live in the precomputed artifact that
`rank_for_disease` loads. Storing them separately would not have helped: the
weighted baseline is recomputed *live* on whatever frame the service assembles,
so an assembly-then-score ordering puts a label-derived column in front of a
model no matter where it was stored.

The check's allowlist is the columns the model itself declares
(`explain.py:_surviving_feature_columns`), not a hand-maintained list. That is
self-maintaining and fails closed on any future column nobody anticipated — the
same argument the README already makes for the build-time guard. And it asserts
on the *frame*, not on the arithmetic: `WeightedBaseline.score` reads only
`dim__*` today, so nothing leaks numerically even if a label column rode along,
but a check that tested the numbers would stop being the guard described here.

Where clinical status is displayed at all, it is labelled in the UI as *the
training label* — the thing the model was fit to reproduce — not as corroborating
evidence for the score.

---

## 4. Architecture

### 4.1 The app must not require the 3 GB raw download

Everything the app reads comes from `data/processed/`, `models/trained/`,
`reports/evaluation/` and `configs/`. This is not currently true of everything
the spec wants: disease descriptions (§21 disease search, §38.1), target
descriptions (§21 detail) and existing-drug information (§21 detail) all live in
the raw Open Targets tables, and `models/baselines.py:score_open_targets_overall`
queries raw parquet through DuckDB.

So Step 3 below adds a precompute step that bakes those into an app-facing
artifact. The app then runs from a few tens of MB, which also makes it
deployable and makes the UI tests independent of a 3 GB fixture.

### 4.2 Two scoring modes, deliberately split

| Score | Mode | Why |
| --- | --- | --- |
| XGBoost (LODO, held-out) | **Precomputed** into `data/processed/app_scores.parquet` | Needs the fold models and a SHAP background; per-request scoring would make the app depend on the full feature pipeline, which the `services/` stubs already ruled out |
| Weighted baseline | **Recomputed live** per request | §38.5 scenario controls change the weights, so it must recompute. It is a weighted sum over five columns across ~9k rows per disease — trivially fast |

**SHAP explanations are computed live, not precomputed — measured, not assumed.**
`explain_target(model, features, disease_id, target_id)` filters *features* to
*disease_id* and then to *target_id* before doing anything else, and
`shap.TreeExplainer(model.estimator)` is constructed with no `data=` argument —
it runs path-dependent perturbation, so `expected_value` and every SHAP value
come from statistics baked into the trained trees, not from whatever rows are
passed alongside the one being explained. Measured directly: SHAP for a single
target row is bit-identical (max abs diff 0.0, identical `base_value`) to that
same target's SHAP computed over its whole disease's ~8,690–15,578 rows, and
costs ~30ms instead of ~5.6s. So `explain_target` is called with *features*
already sliced to the one row being displayed — no code change to `explain.py`,
just what is passed to it — and every target gets a live explanation, not only
a precomputed top-N. **A future reader must not "fix" this back to passing the
whole disease frame**, thinking a background set is required; the measurement
above is why it isn't.

### 4.3 Layering

Services are pure functions over frames, with no Streamlit import. The app is a
thin rendering layer. This is what makes the milestone testable at all — Streamlit
rendering is not worth heavy testing, and services are.

---

## 5. Build order

Services before UI: both the app and any future API sit on them.

**Step 1 — Persist the LODO fold models.**
`milestone2.py`: save each fold's XGBoost to `models/trained/folds/xgboost_lodo_<disease_key>.json`
alongside the existing all-disease refit, and record the fold→file mapping in the
run metadata. Re-run `scripts/train_model.py` and re-verify determinism by
diffing `baseline_metrics.json` against the committed copy — it must stay
byte-identical, since this step adds persistence and changes no arithmetic. That
diff is the check that this step did not disturb Milestone 2.

**Step 2 — `services/disease_search.py`.**
`search_diseases` and `suggest` over `configs/diseases.yaml` plus the disease
names already in the feature table. Name, synonym and ID matching; returns
`DiseaseSearchResult` including `n_associated_targets`. The search space is
*only* the ten configured diseases — by construction there is no second case
of "a real disease that just isn't in this release's precomputed set" to
represent, since nothing outside the ten is ever looked up at all (no raw
`disease` table read, no live GraphQL). An unmatched query is a plain empty
list, documented as such; the page that renders it, not the service, is where
"no disease found in the precomputed set of ten" gets said.

**Step 3 — The app-facing artifact.**
New `scripts/build_app_data.py` writing `data/processed/app_scores.parquet` (+
provenance sidecar, matching the existing convention). Holds only what is
*not* already in `disease_target_features.parquet` (the ranking service reads
that directly, so nothing here duplicates it): held-out XGBoost score and rank
per (disease, target) from the Step 1 fold models; `score_open_targets_overall`
for comparison, column kept as `assoc_overall__score` — deliberately not
renamed to something innocuous, because that name is exactly what denylist
rule `ot_overall_association_score` matches, and a display-only column with a
harmless name would disarm the trap the Milestone 2 reader set on purpose (if
this ever gets joined into a frame headed for a model by accident, it must
still fire); `n_other_diseases_positive` from
`evaluate.label_positive_prevalence_excluding` (`disease_id`-scoped, so it
already means "positive elsewhere" the same way the popularity baseline does);
disease descriptions, target function descriptions, and existing-drug summaries
lifted from raw, the last of these named so a `*clinical_stage*` or `label*`
pattern would catch it too, matching how `assoc_overall__score` is named. No
SHAP columns — SHAP is computed live per target (§4.2). The six-category
evidence completeness is not stored here either — see Step 4, it belongs with
the ranking service. Deterministic and re-runnable, like every other script in
the repo.

**Step 4 — `services/target_ranking.py`.**
`rank_for_disease` and `load_precomputed_scores`, built on §3's score-first-join-second
ordering: a `_feature_frame` / `_display_frame` split in the signatures, with the
join as the final statement before the return. `RankingFilters` is narrowed to
the filters §1 shows are buildable — including `exclude_safety_concerns`
(§38.3's "Safety concern" filter, buildable from `prio__has_safety_event` even
though safety has no WEIGHT in the score) — with the unbuildable ones
(`relevant_tissue`, `target_family`) left in the dataclass as documented
`None`-only fields rather than silently deleted; the gap should be visible in
the type, and `rank_for_disease` raises if either is set rather than silently
ignoring it. Returns `RankedTarget` with evidence, completeness and
`missing_evidence` populated. Live weighted-baseline recompute path takes a
weights argument for §38.5.

**Step 5 — `services/evidence_summary.py`.**
`build_evidence_card`. `supporting`, `contradicting` and `missing` all populated —
§30.12 asks for contradiction detection, and a card listing only confirming
evidence is a worse decision aid than no card. Every `EvidenceItem` carries
`source` and `source_url` (the Open Targets platform links `explain.py`
already builds) and `dataset_version`. No LLM layer: §20.4 permits one, but it is
not required for the MVP and every claim it would render is already structured.

**Step 6 — Pages.**
- `app/pages/disease_overview.py` (§38.1): name, description, relevant tissues from config, candidate count, evidence-source coverage, release info.
- `app/pages/target_ranking.py` (§21, §38.2, §38.3): the table, filters, the score toggle, and §38.5 scenario controls as weight presets (research-focused / clinical-development-focused / novel-target-focused / safety-first / custom, per Project_info.md §21.4) driving the live weighted-baseline recompute.
- `app/pages/target_evidence.py` (§21 detail, §37, §38.4): summary, evidence breakdown, radar chart, SHAP panel, missing-evidence panel, source references, limitations.

Two things the reuse here is not free:

*Custom weight sliders must normalize before constructing `WeightedBaseline`.*
Its `__init__` raises `ValueError` unless the weights sum to 1.0 within 1e-6
(`baseline.py:96`), so arbitrary slider values raise rather than rescale — that
strictness is deliberate, so the UI normalizes and **displays the normalized
values**, or the contributions on screen will not match what the user set.

*`viz.plot_evidence_breakdown` is not reusable as-is.* It takes an `output_path`,
writes a PNG, calls `plt.close(fig)` and returns the `Path` — it cannot hand a
page a figure. It also requires `contrib__*`, which exists only on a *scored*
frame, and hard-codes a Parkinson's title and footnote. Step 6 adds a
figure-returning variant with the disease-specific text parameterised, and
`plot_evidence_breakdown` becomes a thin wrapper over it so Milestone 1's output
stays byte-identical.
- `app/streamlit_app.py`: search entry point and navigation; keep the existing limitations sidebar.

**Step 7 — `scripts/run_app.py`.**
Stop being a stub that prints and exits 1. Verify the required artifacts exist
with an actionable message naming the script to run if not, then launch. `make app`
already exists and should route through it.

**Step 8 — Documentation.**
`milestone3.md` implementation record, README status table and a Milestone 3
section, `docs/limitations.md` extended with the interface-specific ones from §1.

---

## 6. Acceptance check

Milestones 1 and 2 each gate on a script that exits non-zero. A UI cannot be
gated that way, but the services layer can, and one check matters more than the
rest.

`scripts/check_app.py`, exiting non-zero on any failure:

1. **No label-derived column appears in any frame passed to a model.** The Milestone 3 analogue of the leakage guard, and the reason this check exists. Asserted by instrumenting the service call path, not by inspecting the parquet — the failure mode is a frame assembled at render time, not a column written to disk. Fails closed against the model's own declared columns (§3), not a hand-maintained denylist. Verified to *fire*: a probe that assembles the display join before scoring instead of after must make this check exit non-zero. A guard that has never been shown to fire is not known to work — the README's own words, and the reason the build-time guard's silent failure went unnoticed.
2. All ten configured diseases return a well-formed ranking with no nulls in the displayed columns.
3. Every returned row carries resolvable source links.
4. Every evidence card's `missing` list is non-empty wherever the corresponding `missing__*` flags are set — a card that silently drops missing evidence is the §32.3 failure.
5. The displayed XGBoost score for disease *d* comes from the fold model that excluded *d* — checked two ways, not one: (a) recompute one disease's score from its fold model and assert equality against the artifact, and (b) score that same disease with `xgboost_baseline.json` (the all-disease refit) and assert the result is **different**. (a) alone would still pass if the refit model were wired in everywhere by mistake — (b) is what catches that.
6. Every unbuildable §21/§38 element renders its "not yet integrated" placeholder rather than a zero or a blank.

### 6.1 Context.md §22 — the twelve MVP acceptance criteria

Milestone 3 is the last MVP piece, so §22 becomes checkable for the first time
here. `check_app.py` verifies the whole list rather than only its own six checks,
and the record reports it honestly — including anything that does not pass.

| § | Criterion | Where it is satisfied |
| ---: | --- | --- |
| 1 | Accept at least ten diseases | `configs/diseases.yaml`, ten resolved |
| 2 | Retrieve or load candidate targets | 89,666 rows, Milestone 2 |
| 3 | Consistent disease–target feature table | `disease_target_features.parquet` |
| 4 | Train at least one baseline model | Four, Milestone 2 |
| 5 | **Rank targets for an unseen or held-out disease** | The Step 1 fold models — this is what that decision buys, and check #5 above is the proof |
| 6 | Disease-level ranking metrics | `baseline_metrics.json` |
| 7 | Show top targets in a UI | Step 6 |
| 8 | Explain the main factors | Exact contributions + SHAP, Step 5–6 |
| 9 | Link displayed evidence to its source | Check #3 |
| 10 | Communicate uncertainty and limitations | §1 placeholders, §2.2 caveat, checks #4 and #6 |
| 11 | Reproduce via documented scripts | Steps 1, 3, 7 |
| 12 | Track dataset and model versions | `dataset_version`, provenance sidecars, `models/metadata/` |

## 7. Tests

Services tested as pure functions over small synthetic frames, in the style of
the existing `tests/test_*.py`. Specifically: filter semantics (including that an
unbuildable filter cannot be silently satisfied), the six-category completeness
denominator, `n_other_diseases_positive` against `labels.parquet`, the
empty-list contract for an unmatched search query, fold-model routing (both
directions of check #5), scenario-weight normalization and recomputation
summing to the score, single-row SHAP against whole-disease SHAP for the same
target (the bit-identical property Step 4.2 relies on — a regression here
would silently reintroduce the 5.6s cost or a wrong explanation), the
figure-returning viz variant against Milestone 1's committed PNG, and the
leakage boundary as a unit test independent of the acceptance script. Streamlit
rendering gets smoke tests only.

## 8. Deliverables

| Path | What it is |
| --- | --- |
| `app/streamlit_app.py` + `app/pages/*.py` | The application (§21, §38) |
| `src/target_prioritization/services/*.py` | Three services, implemented |
| `models/trained/folds/xgboost_lodo_*.json` | Ten held-out fold models |
| `data/processed/app_scores.parquet` (+ provenance) | Precomputed app-facing scores and explanations |
| `scripts/build_app_data.py`, `scripts/check_app.py`, `scripts/run_app.py` | Build, gate, launch |
| `milestone3.md` | Implementation record |

## 9. Explicitly out of scope

FastAPI `/rank`; the §20.4 LLM explanation layer; Reactome, GTEx and STRING
integration (§28 Step 9 — which is what would make the pathway, expression,
network and tissue elements of §21/§38 buildable, and is the natural Milestone 4);
live GraphQL disease search; §30.13 uncertainty estimation, which is what
§37.1's "confidence level" would need.
