# Milestone 3 — Progress Record

Implementation record for Context.md §21: *"Build a Streamlit application with
a disease selector, ranked target table, target detail page, evidence charts,
explanation section and limitations section."* Planned in
[milestone3_plan.md](milestone3_plan.md) before implementation started, in the
same spirit as milestone2.md §1-2 — the constraints and decisions that shape
the build, recorded before any code makes them look inevitable. This document
records what was actually built, what the real running app surfaced that the
plan didn't anticipate, and the acceptance-check results.

**Status: complete.** All eight plan steps done, the six-check acceptance
gate passes (`scripts/check_app.py`), 373 tests passing (up from 356 before
this milestone), `ruff` and `mypy` clean. The app was driven end-to-end with a
real browser (Playwright) against the real ten-disease pipeline, not just unit
tests — which is how §2 below's two bugs were found.

---

## 1. What changed from the plan, and why

The plan (§1) enumerated which of Context §21/§38's interface elements are
buildable from what Milestone 2 produced: five of eleven evidence/filter
elements are not (pathway, expression, network, relevant-tissue,
target-family), and every page renders an explicit "not yet integrated"
placeholder for them rather than a blank or a zero.

One addition beyond the plan's original scope, found while building the
filters: **§38.3 also asks for a "Safety concern" filter**, which the plan's
gap table (§1) already marked buildable (`prio__has_safety_event`) but the
Step 4 write-up didn't carry through into `RankingFilters`. Added as
`exclude_safety_concerns`, null-safe (a null flag means "not assessed", never
excluded) — the one filter this milestone adds beyond what the plan's Step 4
text originally specified.

One simplification the plan's §4.2 got wrong before implementation and
corrected mid-build, after measuring: SHAP explanations do not need
precomputing. `explain_target(model, features, disease_id, target_id)`
filters *features* down to the requested row before doing anything else, and
`shap.TreeExplainer` is constructed with no `data=` argument, so it runs
path-dependent perturbation — every SHAP value and the `base_value` come from
the trained trees, not from whatever other rows happen to be passed alongside
the one being explained. Measured directly: a single row's SHAP is
bit-identical (max abs diff 0.0) to that same row's SHAP computed over its
whole disease, and costs ~30ms instead of ~5.6s. So `services.evidence_summary`
calls `explain_target` with *features* already sliced to one row — no
precomputed SHAP store, no "not precomputed for this target" placeholder, no
top-N depth limit. Every target gets a live explanation.

---

## 2. Two bugs the real app surfaced that no unit test caught

Both were found only by driving the running app with Playwright end to end —
neither showed up in the 350+ unit tests written alongside the services, and
both are recorded here because they are the kind of gap a CLI smoke test
(what got the services layer to "looks correct" before this) does not catch.

### 2.1 A pyarrow/mimalloc segfault, not a Python exception

Switching the selected disease in the sidebar reliably crashed the Streamlit
server with `SIGSEGV` — no Python traceback, no error in the app, just the
process dying. macOS crash reports
(`~/Library/Logs/DiagnosticReports/python3.11-*.ips`) showed the same stack on
every occurrence: `pandas._libs.lib.maybe_convert_objects` →
`pyarrow.lib.array` → `arrow::BaseBinaryBuilder::Resize` →
`MimallocAllocator::AllocateAligned` → `mi_thread_init` → segfault. Streamlit
runs each session in its own thread, and pyarrow's mimalloc allocator needs
per-thread heap initialization; something in Streamlit's own rendering of a
`list[dict]` passed to `st.dataframe` (converted internally via pandas, then
to Arrow) was triggering allocator init from a thread mimalloc hadn't
registered — in this environment's pinned versions (pyarrow 25.0.0, pandas
3.0.5, both very recent major versions on Apple Silicon).

Two-part fix: pass native `pl.DataFrame` objects to every `st.dataframe` call
instead of `list[dict]` — polars serializes straight to Arrow with no pandas
object-array dtype inference in the path — and set
`ARROW_DEFAULT_MEMORY_POOL=system` before the Streamlit subprocess starts
(`scripts/run_app.py`), which avoids pyarrow's mimalloc allocator entirely.
Reproduced and re-verified fixed via the identical Playwright script both
times: crashed reliably before, ten repeated disease switches with zero
crashes after. Whichever of the two changes is load-bearing wasn't isolated
further — both are cheap and correct regardless.

**This does not indicate anything wrong in this project's own code.** It is
an environment/dependency-version interaction (pinned pyarrow + pandas on this
platform), not a bug in the services layer, the app pages, or the data
pipeline. Recorded here because it is exactly the kind of failure that is
invisible to a service-level test suite and only shows up when the actual
process is driven as a user would.

### 2.2 `EvidenceCard.source_links` — referenced by the UI, never added to the dataclass

`services/evidence_summary.py`'s `build_evidence_card` computed
`source_references(target_id, disease_id)` and folded a single formatted
string into `limitations` — but `app/pages/target_evidence.py` was written
against a `card.source_links` dict attribute that was never added to
`EvidenceCard`. Every unit test for the service passed (none of them asserted
on `source_links`, since it wasn't part of the tested contract), and the
earlier CLI smoke test (`build_evidence_card(...)` called directly and its
`supporting`/`contradicting`/`missing`/`limitations` fields printed) never
touched the attribute either — the exact blind spot the CLI-only check has
that the browser-driven one doesn't. `AttributeError` surfaced only when
Playwright clicked through to the target evidence page. Fixed by adding
`source_links: dict[str, str]` to `EvidenceCard` and populating it properly
instead of string-folding it into `limitations`; the corresponding test
(`tests/test_evidence_summary.py::test_source_links_are_attached`) now
asserts on it directly.

**Standing lesson for this project, matching milestone1.md §4 and
milestone2.md §9's own pattern**: a contract that no test exercises is not
known to work, whether the untested surface is a leakage guard or a
dataclass field a UI reads. Both bugs here were fixed the same day they were
found, before this milestone was reported done.

---

## 3. Acceptance check

`scripts/check_app.py` (logic in `src/target_prioritization/app_checks.py`,
matching the package/script split `milestone1.py`/`milestone2.py` already
use), run against the real ten-disease pipeline:

| Check | Result |
| --- | --- |
| 1. Leakage boundary — no label-derived column reaches `WeightedBaseline.score`, and the probe is confirmed able to detect one if it did | PASS |
| 2. All ten configured diseases return a well-formed ranking, no nulls in displayed columns | PASS |
| 3. Every returned row's source links resolve to `platform.opentargets.org` | PASS |
| 4. Missing-evidence panel is non-empty wherever a `missing__*` flag is set | PASS |
| 5. Fold routing — held-out score matches its own fold model, and differs from the in-sample refit | PASS |
| 6. Every unbuildable element has a stated placeholder reason; the two unbuildable filters raise | PASS |

### 3.1 Context.md §22 — the twelve MVP acceptance criteria

Milestone 3 is the last MVP piece, so §22 is checkable in full for the first
time:

| § | Criterion | Where satisfied |
| ---: | --- | --- |
| 1 | Accept ≥ ten diseases | `configs/diseases.yaml`, ten resolved |
| 2 | Retrieve/load candidate targets | 89,666 rows (Milestone 2) |
| 3 | Consistent disease–target feature table | `disease_target_features.parquet` |
| 4 | Train ≥ one baseline model | Four (Milestone 2) |
| 5 | **Rank targets for a held-out disease** | Step 1's ten fold models — check 5 above is the proof |
| 6 | Disease-level ranking metrics | `baseline_metrics.json` |
| 7 | Show top targets in a UI | Three Streamlit pages |
| 8 | Explain the main factors | Exact contributions + live SHAP |
| 9 | Link displayed evidence to its source | Check 3 |
| 10 | Communicate uncertainty and limitations | §1 placeholders, popularity caveat on every XGBoost-sorted view, checks 4 and 6 |
| 11 | Reproduce via documented scripts | `train_model.py` → `build_app_data.py` → `run_app.py` |
| 12 | Track dataset and model versions | `dataset_version`/`extraction_date` stamped throughout, provenance sidecars |

All twelve satisfied.

---

## 4. Deliverables

| Path | What it is |
| --- | --- |
| `app/streamlit_app.py`, `app/common.py`, `app/pages/*.py` | The application |
| `src/target_prioritization/services/{disease_search,target_ranking,evidence_summary}.py` | The three services |
| `src/target_prioritization/app_data.py` | App-facing precompute logic |
| `src/target_prioritization/app_checks.py` | Acceptance-check logic |
| `models/trained/folds/xgboost_lodo_*.json` (+ `.meta.json` sidecars) | Ten held-out fold models |
| `data/processed/app_scores.parquet` (+ provenance) | Precomputed app-facing scores and metadata |
| `scripts/build_app_data.py`, `scripts/check_app.py`, `scripts/run_app.py` | Build, gate, launch |

---

## 5. Progress checklist

- [x] Step 1 — fold-model persistence (`models/train.py`:
      `save_fitted_xgboost`/`load_fitted_xgboost`; `milestone2.py` saves one
      per LODO fold). Re-ran `scripts/train_model.py`;
      `baseline_metrics.json` diffed byte-identical against the committed
      copy, confirming the change added persistence without disturbing
      Milestone 2's arithmetic.
- [x] Step 2 — `services/disease_search.py` (17 tests)
- [x] Step 3 — `app_data.py` + `scripts/build_app_data.py` (12 tests;
      89,666-row artifact built and verified against the real release)
- [x] Step 4 — `services/target_ranking.py`, score-first-join-second (24
      tests; includes a monkeypatch-based leakage-boundary test independent
      of the acceptance script)
- [x] Step 5 — `services/evidence_summary.py` (9 tests, including the
      source_links regression found in §2.2)
- [x] Step 6 — `viz.py`'s figure-returning split (verified M1's PNG stays
      byte-identical; 6 new tests) + three Streamlit pages, driven live with
      Playwright
- [x] Step 7 — `scripts/run_app.py` (artifact checks + the pyarrow fix from
      §2.1)
- [x] Acceptance check — `app_checks.py` + `scripts/check_app.py` (8 tests;
      passes against the real pipeline)
- [x] `ruff check .` and `mypy src` clean

373 tests passing (up from 356 at the start of this milestone).

---

## 6. Next

Out of scope here, per milestone3_plan.md §9: FastAPI's `/rank` (§28 Step 11
specifies Streamlit; the typed contract in `api/` stays a ~30-line addition
for later), the §20.4 LLM explanation layer (every claim it would render is
already structured data), live GraphQL disease search (declined — see §1 of
the plan), §30.13 uncertainty estimation.

The natural next milestone is Context.md §28 Step 9: Reactome, GTEx and
STRING integration. That is what would make the pathway, expression, network,
relevant-tissue and target-family elements — the ones this milestone renders
as explicit placeholders throughout the app — actually buildable, closing the
largest remaining gap this record's §1 table lists.
