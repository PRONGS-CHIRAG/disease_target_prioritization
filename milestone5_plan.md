# Milestone 5 — Implementation Plan

Replace the Streamlit MVP (Context.md §21, milestone3.md) with a Next.js
frontend, and complete the FastAPI adapter layer so that frontend can reach
everything the Streamlit app reaches. A separate `milestone5.md` will record
what was actually built.

**Status: planned, not started.** Written before implementation, in the same
spirit as milestone3_plan.md and milestone4_plan.md: the measurements and
constraints that shape the design, recorded before any code makes them look
inevitable.

---

## 1. What "keep the backend the same" means precisely

Two layers are being conflated by the phrase "the backend," and the migration
treats them oppositely.

**Frozen — with exactly one carve-out, named in §4.2:**
`src/target_prioritization/data/`, `features/`, `models/`, `services/`,
`utils/`, `configs/`, the data-pipeline scripts, and every processed
artifact. No scoring behaviour moves. The
weighted baseline, the held-out XGBoost fold models, the SHAP explanations,
the leakage boundary and the six evidence categories are exactly what they are
today. `app_checks.py` (the Milestone 3 acceptance gate) has zero Streamlit
coupling — it gates the *services* layer — so it survives untouched and keeps
gating after Streamlit is gone.

**Completed — this is the actual work:** `src/target_prioritization/api/`.
The HTTP surface today is `GET /health` and `POST /rank`, and it cannot
express most of what the three Streamlit pages do. Measured against the pages:

| Streamlit does | HTTP surface today |
| --- | --- |
| Disease search over the ten configured diseases (`services.disease_search`) | **No endpoint at all** |
| Evidence card with live SHAP (`services.evidence_summary.build_evidence_card`) | **No endpoint at all** |
| Disease overview: description, therapeutic areas, category coverage, release | **No endpoint at all** |
| Five ranking filters (`RankingFilters` has all five) | `RankingRequest` accepts **two** — `min_genetics_evidence`, `require_druggable` |
| Scenario weights (Context.md §38.5) — `rank_for_disease(weights=…)` | **No `weights` field** — the whole feature is unreachable |
| Weighted-baseline / XGBoost sort toggle — `rank_for_disease(sort_by=…)` | **No `sort_by` field** |
| Table columns `weighted_baseline_score`, `xgboost_score_held_out`, `n_other_diseases_positive` | **Dropped** by `RankedTargetResponse` |
| Pathway, expression and network evidence (built in Milestone 4) | `_to_response`'s docstring claims these are null only "until Milestone 4 wires up" pathways/expression/network — false: `_DISPLAY_DIMENSIONS` (`services/target_ranking.py:88`) is a hardcoded 5-element list that structurally never carries these three, and Streamlit's own ranking table doesn't display them either (`app/pages/target_ranking.py`'s row-building only reads genetics/functional/literature/druggability). **Correct fix is not to populate them** — that would be new evidence display beyond parity, which §9 rules out — but to fix the stale docstring and confirm the completeness/missing-evidence path (which already covers all six built categories) is what actually surfaces their per-target standing |
| `top_n` up to 200 on the ranking slider | `RankingRequest.top_n` capped at `le=500` (fine), but see §2.7 on export |

The repo anticipated this. The `/rank` docstring quotes milestone3_plan.md §2:
services were built standalone "so the API stays a ~30-line addition later."
Milestone 5 writes the rest of that addition. Nothing below reaches past
`api/` into the frozen layer.

### 1.1 Two things Streamlit was hiding

`app/common.py` wraps every artifact load in `@st.cache_data` /
`@st.cache_resource`. FastAPI has no equivalent, and the services layer has
none of its own — `_load_features` and `_load_app_data`
(`services/target_ranking.py:219`, `:227`) call `pl.read_parquet` on every
invocation, and `grep -rn "lru_cache" src/target_prioritization/services/`
returns nothing. Consequences once Streamlit's cache is removed:

- Every `/rank` request re-reads 6.6 MB (`disease_target_features.parquet`) +
  4.3 MB (`app_scores.parquet`) from disk.
- Every evidence request reloads a booster from `models/trained/folds/`
  (29 MB across ten folds) to run SHAP.

The second one is **not** a regression the migration introduces — it is
happening today. `app/common.py:109` defines a `@st.cache_resource`-wrapped
`get_fold_model`, but `grep -rn "get_fold_model" app/ tests/ scripts/` matches
only that definition: nothing imports it.
`app/pages/target_evidence.py:19` imports `get_active_weights, get_app_data,
get_features` and nothing else, so every evidence render in Streamlit already
calls `load_fitted_xgboost` cold via `_xgboost_held_out_items`
(`services/evidence_summary.py:144`). `get_fold_model` is dead code that
leaves with `app/`. The parquet caching, by contrast, is real and does have to
be replaced.

There is also **no `CORSMiddleware` anywhere in `src/`** (`grep -rn "CORS" src/`
→ nothing), which the dev setup needs. §4.2 and §4.5 handle all three.

---

## 2. Decisions taken

### 2.1 Streamlit stays until parity, then is deleted in one commit

`app/` keeps working through Phases 0–6 so each new page can be diffed against
the page it replaces. Phase 7 removes `app/`, `scripts/run_app.py`, the
`make app` target and the `streamlit>=1.36` dependency in a single commit.
`scripts/check_app.py`, `src/target_prioritization/app_checks.py` and
`tests/test_app_checks.py` **stay** — they check artifacts and services, not
Streamlit.

### 2.2 One container, one origin, static export

The frontend builds to a fully static bundle (`output: "export"`) that FastAPI
serves with `StaticFiles`. One process, one port, no CORS in production, and no
Node in the runtime image (multi-stage build: `node` builder → `python:3.11-slim`
runtime).

Two consequences worth stating up front, because they constrain routing:

- **No SSR and no React Server Component data fetching.** All data loads
  client-side through TanStack Query. Acceptable here: same origin, ten
  diseases, no auth, no SEO requirement. Every page is a Client Component
  (`"use client"`), which also sidesteps Next 16's async-`params`/
  `searchParams` breaking change (both are now Promises in Server
  Components) entirely — nothing here reads them server-side.
- **No dynamic route segments at all — disease AND target both travel as
  search params.** The plan's original draft proposed
  `/disease/[diseaseId]` with `generateStaticParams` reading the ten
  diseases from `configs/diseases.yaml`, keeping only target as a search
  param (8,690 candidates for Parkinson's alone rules out a `[targetId]`
  segment). Implementation invokes the fallback that draft already
  pre-authorized: reading YAML from the Node build is exactly the
  cross-toolchain coupling it warned about, AND — discovered from
  `node_modules/next/dist/docs/01-app/02-guides/static-exports.md`, which
  `frontend/AGENTS.md` requires reading before writing Next code, since
  this Next version (16) has breaking changes from training data —
  `output: "export"` disallows Rewrites, which §4.5's dev-mode API proxy
  depends on (see §4.5's note). Routes are instead a small fixed set —
  `/overview`, `/ranking`, `/evidence`, `/compare` — each reading
  `?disease=…` (and `?target=…`/`?targets=…`) via `nuqs`. This removes
  `generateStaticParams` from the app entirely: every route is a plain
  static page, trivially compatible with `output: "export"`.

### 2.3 API routes move under `/api`

Static files mount at `/`, so every API route moves to `/api/*` to avoid
collision (`/api/health`, `/api/rank`, …). This **breaks the current paths**
and `tests/test_api.py` is updated with them. The alternative — keeping API
routes at root and serving the UI from `/app` — was rejected because it makes
every frontend link carry a prefix that exists only to dodge a name clash.

A bare `GET /health` alias stays at root for container health checks.

### 2.4 Frontend stack

Next.js 15 (App Router) · TypeScript strict · Tailwind CSS v4 · shadcn/ui ·
TanStack Query (server state) · TanStack Table (the ranking table: 89k rows
across diseases, sorting, column visibility) · Recharts (via shadcn/ui's chart
wrapper) · `nuqs` for typed URL search-param state.

Types are **generated from the OpenAPI schema** FastAPI already emits
(`openapi-typescript` → `frontend/src/lib/api-types.ts`), not hand-written. A
Pydantic field rename then breaks the TypeScript build instead of silently
rendering `undefined`. Regenerating is a `make types` target and a CI check.

The `frontend-design` and `dataviz` skills are loaded at Phase 2 and Phase 5
respectively, before any UI or chart code is written.

### 2.5 Charts render client-side from JSON, and `viz.py` is not touched

`viz.py` returns matplotlib `Figure` objects for `st.pyplot`. Next cannot
consume those, and adding PNG endpoints would recreate the server-rendered UI
this milestone is migrating away from. Both charts are trivial as data:

- **Evidence breakdown** — `WeightedBaseline.score` already writes
  `contrib__{dimension}` columns that sum *exactly* to `prioritization_score`
  (`models/baseline.py:145`). The endpoint returns those five numbers. The
  exactness is the point of the baseline (`baseline.py:193`) and must remain
  visible in the UI: the bars sum to the score, and the page says so.
- **Evidence radar** — the raw `dim__{dimension}` values, nulls preserved.

`viz.py` keeps serving `reports/` and the notebooks, unchanged.

### 2.6 Presentation constants move into the package *first*

`SCENARIO_PRESETS`, `LIMITATIONS`, `SAFETY_FIRST_LABEL`, `CUSTOM_LABEL`
(`app/common.py:29-80`), `_DIMENSION_LABELS` (`app/pages/target_ranking.py:30`)
and `_NOT_BUILDABLE` (`app/pages/target_evidence.py:29`) live in the directory
being deleted. Each carries a comment explaining a spec constraint — the
scenario-preset block alone explains why there is no "clinical" or "safety"
weight (the clinical signal *is* the training label; safety has no scored
dimension per Context.md §14.7).

If they are not lifted out before the frontend is written, TypeScript
hardcodes duplicates and they drift from `configs/model.yaml` the first time
weights change. Phase 0 moves them to
`src/target_prioritization/presentation.py`, with the comments intact, and
repoints Streamlit's imports. No behaviour change; the existing suite must
stay green on that commit alone.

One shape change while moving: `SCENARIO_PRESETS` is currently keyed by prose
labels ("Research-focused (genetics-first)"), but §4.4 needs `?scenario=research`
in a URL. `presentation.py` carries a **stable slug alongside each label**
(`research` / `clinical` / `novel` / `safety_first` / `custom`), so the URL
codec reads slugs rather than inventing its own and drifting from the labels
the moment one is reworded.

### 2.7 CSV export is client-side, and states its own denominator

Exporting exactly the rows on screen guarantees the file matches what the user
is looking at, needs no endpoint, and cannot drift from the table. The
footgun is a user assuming a 50-row CSV is the whole ranking, so the button
reads **"Export 50 of 8,690 candidates (CSV)"** and the filename encodes
disease, sort and top-N. A full-ranking export is out of scope (§9).

### 2.8 The evidence endpoint is a POST

It needs the active scenario weights, which are a dict. Consistent with
`/rank`, avoids encoding five floats as repeated query params, and costs
nothing in shareability — what gets shared is the *Next.js* URL (§4.4), which
carries the weights, not the API URL.

---

## 3. Invariants this migration must not break

These are load-bearing spec requirements, each with a comment in the code
explaining why. A generic "professional dashboard" build breaks several of
them by default. Every one gets a test (§7).

1. **Null is not zero.** `RankedTarget.evidence` preserves nulls deliberately
   — "a dimension at or near zero can mean either weak evidence or NO
   evidence" (Context.md §32.3, `target_ranking.py:144-147`). A `?? 0` in TSX,
   or a chart library rendering `null` as a zero-height bar, silently destroys
   the distinction. **This is the single highest-risk regression in the
   migration.** The rendering convention is fixed now: a null dimension
   renders as an em-dash with a "no evidence recorded" tooltip in tables, and
   as a *visually broken* segment (gap, not zero point) in the radar. One
   shared `<EvidenceValue>` component; no raw `{value}` interpolation of a
   dimension anywhere.
2. **Completeness renders as "N of 6 categories," never a bare fraction**
   (`target_ranking.py:148-151` is explicit about the denominator travelling
   with the number).
3. **Existing-drug and clinical-stage data must not be a ranking-table column
   or filter.** They are what the training label is built from; a sortable
   column would let a user sort by the answer key without realising it
   (`app/pages/target_ranking.py:1-9`). Evidence page only, explicitly
   labelled as the training label. Enforced at the schema level (§4.3).
4. **Scenario weights change the weighted-baseline score only**, never the
   XGBoost score — its weights cannot be adjusted at inference. And
   "Safety-first" changes a **filter**, not weights (`app/common.py:78-79`);
   it must not be collapsed into the weights model just because it sits in the
   same dropdown.
5. **The XGBoost sort carries the popularity caveat** — novel-only NDCG@10
   0.009 vs 0.696 primary (milestone2.md §1). Visible when that sort is
   active, not buried in a docs page.
6. **`target_family` stays unavailable and still raises.**
   `_reject_unbuildable_filters` refuses "to silently ignore a filter the
   caller believes is being applied" (`target_ranking.py:245-252`). The API
   surfaces that as a 400 with the reason; the UI shows the control disabled
   with the reason, rather than hiding it.
7. **Not-buildable items render as "not integrated + why," never blank or
   zero** — direction of effect, calibrated confidence (`_NOT_BUILDABLE`).
8. **Limitations are visible on every page** (Context.md §21, §31.12).
   `/rank` already returns `limitations` in every response; that pattern
   extends to every new endpoint, and the frontend renders a persistent panel
   rather than a dismissible toast.
9. **Filters apply after ranking.** A target's `rank` is its place among every
   candidate for the disease, not among the survivors (`rank_for_disease`
   docstring). The table shows rank 1, 4, 17… with gaps — the UI must not
   renumber rows.
10. **A score displayed on any page must state or carry the weights that
    produced it.** The evidence and compare pages each request their own
    `weights`, independent of the ranking page — a naive implementation
    defaults both to `meta.default_weights`, so a target's score changes with
    no explanation when a user follows "View evidence" from a ranking loaded
    under a non-default scenario (found during Phase 7 review: LRRK2 read
    0.8550 on the ranking row and 0.844 on its evidence page, same target,
    same fetch, different silently-applied weights). Links from a scored view
    to another scored view carry the server-echoed `weights_used` as query
    params (`useLinkedWeights`/`linkedWeightsQueryString`,
    `src/hooks/use-linked-weights.ts`); a view reached without them — a
    bookmark, a fresh page load — falls back to `meta.default_weights` and
    says so in a caption next to the score, rather than presenting the number
    as unconditional.

---

## 4. Architecture

### 4.1 Endpoint map

Every endpoint is a thin adapter over an existing service function. No new
computation.

| Endpoint | Service behind it | Feeds |
| --- | --- | --- |
| `GET /api/health` | `release_tag()`, fold-model presence | Status banner. Populates `dataset_version` and `model_loaded`, which `HealthResponse` already declares but `health()` never sets |
| `GET /api/meta` | `presentation.py` + `configs/model.yaml` | Scenario presets, dimension labels, limitations, `APP_EVIDENCE_CATEGORIES`, `UNAVAILABLE_EVIDENCE_CATEGORIES`, `_NOT_BUILDABLE`, default weights. One fetch at boot; no constant is duplicated in TS |
| `GET /api/diseases` | `search_diseases("")` | Disease picker |
| `GET /api/diseases/search?q=` | `search_diseases`, `suggest` | Typeahead |
| `GET /api/diseases/{id}` | `search_diseases` match + category coverage + `dataset_version`/`extraction_date` from `app_scores` | Disease overview page |
| `POST /api/rank` | `rank_for_disease` — **all five filters**, `weights`, `sort_by`, `top_n` | Ranking page |
| `POST /api/evidence` | `build_evidence_card` + `contrib__*` + `dim__*` + `label__*` + rank-of-N | Evidence page, comparison view |

`EvidenceBreakdown` gains `evidence_diversity` and `functional` fields — the
schema was missing two of the five real weighted dimensions outright, a
genuine bug independent of the pathways/expression/network question.
`pathways`/`expression`/`network`/`safety` stay `None` on the ranking
table's evidence breakdown, correctly (§1's corrected table row): they are
not among `presentation.DIMENSION_KEYS`, matching what Streamlit's own
ranking table shows. Their per-target standing surfaces through
`evidence_completeness`/`missing_evidence` here, and as real `missing`
values plus a safety `contradicting` item on `/api/evidence`.
`RankedTargetResponse` gains `weighted_baseline_score`,
`xgboost_score_held_out`, `n_other_diseases_positive`. `RankingRequest`
gains `weights`, `sort_by`, `relevant_tissue`, `min_evidence_completeness`,
`exclude_safety_concerns`, `target_family` (invariant 6).

Weights arriving from the UI are normalized with
`services.target_ranking.normalize_weights` **and the normalized values are
returned in the response**, because `WeightedBaseline` raises rather than
rescale, and the contributions shown on screen only match the sliders if the
UI displays what was actually used (`normalize_weights` docstring).

### 4.2 Artifacts load once

A FastAPI `lifespan` handler warms both parquets and all ten fold models at
startup. The two halves need different mechanisms, because only one of them
has an injection seam.

**Parquets — no change to the frozen layer.** Both `rank_for_disease` and
`build_evidence_card` accept `features=` (and `app_data=`) precisely so the
real artifacts can be bypassed. `api/` caches the frames with
`functools.lru_cache` and passes them in. Zero lines change in `services/`.

**Fold models — one line changes in the frozen layer.** There is no seam:
`_xgboost_held_out_items` calls `load_fitted_xgboost(model_path)` directly
(`services/evidence_summary.py:144`), and `build_evidence_card`'s keyword-only
parameters are `features`, `weights`, `diseases` — no `model`. Two options:

1. **`@lru_cache` on `models.train.load_fitted_xgboost`** — one decorator, no
   signature change, and every other caller (`app_data.py:75`,
   `app_checks.py:174`) benefits. It is a pure `Path` → model loader, which is
   the ideal shape for it.
2. Add a `model=` parameter to `build_evidence_card`, mirroring the existing
   `features=` seam.

**Option 1 is chosen**, and §1's "frozen" claim carves it out by name rather
than pretending the seam exists. The tradeoff accepted: cached boosters become
shared objects, so it is only safe while nothing refits a loaded model in
place — verified below alongside the frame question. Ten fold models at ~2.9 MB
each bounds the cache at ~29 MB, so `maxsize` needs no tuning.

Two things to verify before relying on any of it:

- Confirm nothing in the services layer mutates a returned frame or a loaded
  model in place (a shared cached `pl.DataFrame` or booster is only safe if
  every consumer reads). Polars operations are non-mutating by default and
  `explain_target` only reads; this is a verification step, not an assumption.
- Startup cost moves off the first request. Report it in `milestone5.md` —
  it also sets the container's health-check grace period.

Without this, the comparison view (§5, Phase 6) is the worst case: four
parallel evidence requests, each reloading a booster and re-reading 11 MB.

**Measured** (Phase 1, real Parkinson's data, artifact caching + fold-model
`@cache` both in place): `/api/evidence` averages ~120ms, dominated by
`rank_for_disease(top_n=None, ...)`'s full re-sort of 8,690 rows for the
rank-of-N figure — three `baseline_scored` calls per request (weighted
score, single-row explain, full-population sort). A memoization pass keyed
by `(disease_id, weights)` was prototyped and reverted: `functools.lru_cache`
on a function that reaches into `cached_features()`/`cached_app_data()`
internally silently stopped honoring `tests/test_api.py`'s
`main.cached_features` monkeypatch (the classic "patch where it's used, not
where it's defined" trap — the cache function is imported by name, so
patching the call site doesn't reach the cached wrapper's own module-level
reference), and switching to an explicit-argument cache would need
correctly-scoped invalidation to avoid serving one test's synthetic frame to
another test reusing the same disease_id. ~120ms × 4 parallel requests,
threadpool-served by uvicorn's sync `def` handlers, is treated as acceptable
without evidence otherwise — Phase 6 re-measures the comparison view itself
under real concurrent load before any caching is reattempted.

### 4.3 The leakage boundary, enforced at the HTTP layer

`rank_for_disease` scores *before* joining anything from `app_scores.parquet`
— the module docstring and `app_checks.py` check 1 both police this. The HTTP
layer adds a second boundary in the same spirit, but it has to be stated as a
**denylist of three specific columns**, not as "no label-derived field":

> `RankedTargetResponse` must expose none of `label__max_clinical_stage`,
> `label__n_drugs`, `label__drug_names` — the three clinical columns in
> `app_scores.parquet` that the training label is built from.

The looser phrasing would be wrong, because `n_other_diseases_positive` **is**
label-derived (how many of the other nine diseases this target is a labelled
positive in — `target_ranking.py:157-160`, milestone3_plan.md §2.2) and is
deliberately shipped: it is the per-target form of milestone2.md §1's
popularity finding, and the Streamlit table already shows it. A test written
against "label-derived" either flags that intended field or gets loosened
until it catches nothing.

The test asserts the three names over the generated OpenAPI document, and
carries a comment recording why `n_other_diseases_positive` is present. Adding
one of the three then fails CI rather than quietly appearing as a sortable
column (invariant 3).

### 4.4 URL state is the single source of truth

```
/disease/MONDO_0005180                       → overview
/disease/MONDO_0005180/ranking
    ?scenario=research&sort=weighted&top=50
    &min_genetics=0.3&druggable=1&completeness=0.5
/disease/MONDO_0005180/evidence?target=ENSG00000188906
/disease/MONDO_0005180/compare?targets=ENSG…,ENSG…,ENSG…
```

Managed with `nuqs` so the params are typed and the browser back button works.
Two things this buys that Streamlit structurally cannot: a ranking under a
specific scenario is a **shareable link**, and the state is inspectable rather
than hidden in `st.session_state`. A `scenario=custom` URL carries explicit
`w_genetics=…` params; a named scenario does not, so a preset's definition can
change in `configs/model.yaml` without stale links silently disagreeing with
the app.

Target IDs are search params, not path segments — §2.2.

### 4.5 Dev vs production

- **Dev:** `next dev` on :3000, `uvicorn --reload` on :8000. `next.config.ts`
  rewrites `/api/*` → `http://localhost:8000/api/*`, so the browser only ever
  sees one origin and **no CORS is needed even in dev**. `CORSMiddleware` is
  still added, restricted to `localhost:3000` and off by default behind an
  env flag, for anyone who runs the two without the proxy.

  Rewrites and `output: "export"` cannot both be active — the static-export
  guide `frontend/AGENTS.md` pointed at lists Rewrites under "Unsupported
  Features," and Next enforces this for `next dev` too whenever the config
  sets `output: "export"`, not only for `next build`. `next.config.ts`
  therefore sets `output` conditionally: `"export"` only when
  `BUILD_STATIC_EXPORT=1` (set by `make frontend-build` / the Dockerfile,
  never by `next dev`), with `rewrites()` defined only in the branch where
  `output` is unset. Dev gets its proxy; the Docker build gets its static
  export; the same config file does both because they never run at once.
- **Prod:** `next build` (with `BUILD_STATIC_EXPORT=1`) → `frontend/out`,
  copied into the Python image, mounted with
  `StaticFiles(directory=…, html=True)` **after** every API route. No
  rewrite is needed here regardless — the browser requests `/api/*` from
  the same FastAPI process serving the page, not through a proxy.
- `.dockerignore` must exclude `data/raw/` (~3 GB). The image needs
  `data/processed/` (11 MB) and `models/trained/` (32 MB) only — and both are
  **git-tracked**, not gitignored: `.gitignore:8-34` ignores `data/**` and
  `models/trained/**` broadly, then explicitly un-ignores the four processed
  parquets and `models/trained/folds/*.json`, and `git ls-files` confirms they
  are committed. So the image builds from a clean checkout with no prior
  pipeline run — worth stating because the broad ignore lines suggest
  otherwise at a glance.
- New Makefile targets: `dev`, `frontend-install`, `frontend-build`, `types`,
  `docker-build`, `docker-run`. `make app` is deleted in Phase 7.

---

## 5. Build order

Each phase leaves the repo green — tests pass, and Streamlit still runs until
Phase 7.

| Phase | Work | Done when |
| --- | --- | --- |
| **0** | Lift presentation constants into `src/target_prioritization/presentation.py`; repoint Streamlit imports | Existing 430 tests pass unchanged; `make app` still works |
| **1** | Complete the API: `/api` prefix, seven endpoints, all five filters, `weights`, `sort_by`, real pathway/expression/network values, lifespan warming + caching, CORS flag | `tests/test_api.py` covers every endpoint; schema-leakage test passes; Streamlit untouched |
| **2** | `frontend/` scaffold: Next 15, TS strict, Tailwind v4, shadcn/ui, TanStack Query, `nuqs`; `openapi-typescript` generation; API client; app shell with persistent limitations panel and disease picker. Load `frontend-design` skill first | `npm run build` produces a static export; picker drives the URL |
| **3** | Disease overview page | Matches `app/pages/disease_overview.py` field for field |
| **4** | Ranking page: TanStack Table, five filters, scenario weights (presets + custom sliders + normalized-value display), sort toggle with the popularity caveat, URL state, CSV export | Matches `app/pages/target_ranking.py`; invariants 1–6, 9 hold |
| **5** | Evidence page: contribution bars, radar, supporting/contradicting, missing evidence, drug info (labelled as the training label), source links. Load `dataviz` skill first | Matches `app/pages/target_evidence.py`; bars sum to the score on screen |
| **6** | Comparison view for 2–4 targets (new surface, no Streamlit precedent) | Parallel evidence fetches; null dimensions still render as gaps, not zeros |
| **7** | Multi-stage Dockerfile, `.dockerignore`, Makefile targets, README + `docs/` updates; **delete** `app/`, `scripts/run_app.py`, `make app`, the `streamlit` dependency | `docker run` serves UI and API on one port; no `streamlit` in `pyproject.toml`; `make check` green |

---

## 6. Acceptance check

Milestones 1–4 each gate on a script that exits non-zero. Milestone 5 follows
that pattern with `scripts/check_frontend.py`, run against the real artifacts:

1. Every endpoint returns 200 for all ten configured diseases.
2. The `/api/rank` response schema exposes none of the three clinical label
   columns (§4.3) — and the check is verified to fire by injecting one of them
   into a response model and confirming it trips.
3. A target with a null `dim__` value round-trips through JSON as `null`, not
   `0` (invariant 1) — and the check is verified to fire on a deliberately
   zero-filled response, since a check that can never fire is not a check
   (the standard `app_checks.py` check 1 already holds itself to).
4. `contrib__*` values in an evidence response sum to the reported score
   within float tolerance.
5. Setting `target_family` returns 400 with the reason, not 200 (invariant 6).
6. Every endpoint's response carries `limitations` (invariant 8).
7. The built static export exists and its `index.html` references no external
   origin.

Plus a Playwright smoke pass (the `playwright-skill` is available) over the
three migrated pages: disease selection → ranking → evidence, asserting a
known-null dimension renders an em-dash rather than "0".

---

## 7. Tests

- **`tests/test_api.py`** — extended per endpoint: filters, weights,
  normalization round-trip, `sort_by`, 404 on unknown disease, 503 when
  artifacts are missing, 400 on `target_family`.
- **`tests/test_api_contract.py`** (new) — the three-name schema-level leakage
  assertion (§4.3) and the null-preservation assertion, both over the
  generated OpenAPI document, so they fail at CI time rather than in the
  browser.
- **`tests/test_presentation.py`** (new) — scenario presets still sum as
  expected and reference only dimensions that exist in `configs/model.yaml`.
- **Frontend unit (Vitest)** — the `<EvidenceValue>` null-rendering
  convention, the completeness "N of 6" formatter, the URL-state codec.
- **Frontend E2E (Playwright)** — the three pages plus the comparison view.
- The existing 430 tests stay green throughout; none of them touch `app/`.

---

## 8. Deliverables

- `src/target_prioritization/presentation.py` — lifted UI constants.
- `src/target_prioritization/api/` — completed router, schemas, caching,
  lifespan, static mount.
- `frontend/` — Next.js app, static export, generated API types.
- `Dockerfile`, `.dockerignore`, updated `Makefile`, `.gitignore`,
  `.pre-commit-config.yaml` (frontend excluded from Python hooks; Prettier +
  ESLint added for TS).
- `scripts/check_frontend.py` + the new test modules.
- `milestone5.md` — the implementation record, including the measured startup
  warm cost (§4.2) and anything the migration found that this plan did not
  anticipate.
- README status-table row, in the same form as Milestones 1–4.
- Removal of `app/`, `scripts/run_app.py`, `make app`, `streamlit`.

---

## 9. Explicitly out of scope

- **Authentication, accounts, saved sessions.** No user model exists and none
  is needed for a public research prototype.
- **Live/on-request scoring.** The API serves precomputed artifacts by design
  (`api/main.py` module docstring); scoring per request would make it depend
  on the full feature pipeline.
- **Full-ranking (8,690-row) CSV export.** The `top_n` cap stays at 500;
  §2.7's labelled partial export is what ships.
- **New evidence, new features, new model behaviour.** The four seed-dependent
  columns deferred in milestone4_plan.md §2.1 stay deferred; `target_family`
  stays unbuildable; direction of effect and calibrated confidence stay
  unbuilt and keep rendering as labelled placeholders.
- **Mobile-first layouts.** Responsive to tablet width; a dense ranking table
  is not a phone experience, and pretending otherwise costs more than it
  returns here.
- **Hosting.** The container is the deliverable; where it runs is a later
  decision.
