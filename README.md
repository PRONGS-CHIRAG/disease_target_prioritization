# Disease–Target Prioritization

Ranks candidate therapeutic targets for a disease by integrating public biomedical
evidence — human genetics, pathways, tissue expression, protein networks and
tractability — and explains why each target scored the way it did.

> **This is a research-support and learning prototype.** Scores are prioritization
> hypotheses generated from public databases, not validated scientific findings.
> A high score does not mean a target will yield an effective drug. Not for medical
> diagnosis or treatment decisions. See [docs/limitations.md](docs/limitations.md).

Specification: [Context.md](Context.md) and [Project_info.md](Project_info.md).

## Status

| Phase | State |
| --- | --- |
| Data acquisition & repository scaffolding | **Done** |
| Milestone 1 — Parkinson's rule-based baseline (Context §36) | **Done** — [implementation record](milestone1.md) |
| Milestone 2 — multi-disease ML baseline (Context §37) | Not started |
| Milestone 3 — Streamlit app (Context §21) | Not started |

Implemented and tested: configuration, path and provenance utilities, the dataset
downloader, identifier normalization, the leakage guard, the Open Targets readers,
the genetics and druggability feature groups, the weighted baseline with
per-dimension explanations and ablation, and report and figure generation.
169 tests.

Still stubs, and deliberately so: `features/pathways.py`, `expression.py` and
`network.py` need Reactome, GTEx and STRING, which Context §28 Step 9 schedules
*after* the baseline works. `models/train.py`, `predict.py`, `evaluate.py`,
`explain.py`, `services/` and `api/` are typed contracts awaiting Milestones 2–3,
and `app/` currently renders its limitations sidebar and nothing else.

## Milestone 1 — the Parkinson's baseline

A transparent weighted sum over the 8,690 targets Open Targets 26.06 associates
with Parkinson's disease (`MONDO_0005180`). No machine learning, on purpose: the
weights are hand-set and the arithmetic is inspectable, so if established genes
surface near the top then the data pipeline is sound. A gradient-boosted model
failing the same way would say nothing about where the fault was.

```
score = 0.40 · genetics  +  0.20 · evidence_diversity  +  0.15 · functional
      + 0.15 · literature  +  0.10 · druggability
```

Weights live in [configs/model.yaml](configs/model.yaml) and the
dimension-to-datasource mapping in [configs/features.yaml](configs/features.yaml),
so someone who knows the biology but not Python can review it. Within a dimension
the score is the *maximum* across its datasources — a target is as good as its
best evidence of that kind, and averaging would penalise a gene for the
datasources that simply have not studied it.

Three measurements shaped that formula. **6,196 of the 8,690 candidates (71%) have
literature evidence and nothing else**, so a naive score would rank genes by how
often they are written about. **The established genes carry the most distinct
evidence types of any candidate** (LRRK2 seven, GBA1 and SNCA six), which is why
diversity became a scored dimension rather than a reported statistic. And **Open
Targets holds no pathway evidence for this disease at all** — its `reactome`
datasource has zero rows — so the pathway term in the §17.1 example formula was
not merely deferred, it was impossible.

### Result, with the caveat attached

All five established Parkinson's genes reach the top 20. Only three survive the
literature ablation (Context §32.2), and that is the number that qualifies the
headline:

| Gene | Rank | Rank without literature |
| --- | ---: | ---: |
| LRRK2 | 1 | 1 |
| GBA1 | 3 | 3 |
| SNCA | 6 | 8 |
| PINK1 | 15 | **24** |
| PRKN | 19 | **28** |

Nothing in the scoring knows these five genes. The ranking also surfaced PLA2G6
(#2, PARK14), MAPT (#4), PARK7 (#5, DJ-1) and VPS35 (#20, PARK17) unprompted.

![Evidence breakdown for the top 20 Parkinson's targets](reports/figures/parkinsons_top_targets.png)

Segment lengths are the weighted contributions and sum exactly to the score. A
missing segment is missing evidence, not zero evidence.

The ablation means this method **cannot distinguish a gene that is well-published
because it matters from one that merely appears in many abstracts** — and the 71%
of candidates carrying literature alone are exactly where that bites. LRRK2,
PLA2G6, GBA1, MAPT and PARK7 do not move at all when literature is dropped; those
are the targets this baseline supports on genetics and functional evidence
standing alone.

Two more things a passing acceptance check invites over-reading. There are no
labels and no held-out set here, so "5 of 5 in the top 20" is a sanity check and
not a measured performance figure. And the candidates are targets Open Targets
*already* associates with Parkinson's, so the method re-ranks known associations
by construction (§13) — it cannot discover anything new.

Deliverables, all committed so the results can be read without downloading
anything:

| Path | What it is |
| --- | --- |
| [reports/parkinsons_baseline_report.md](reports/parkinsons_baseline_report.md) | Findings, manual inspection of the top 10, ablation, eight limitations |
| [data/processed/parkinsons_targets.parquet](data/processed/) | 8,690 ranked candidates with per-dimension contributions, plus a `.provenance.json` sidecar |
| [reports/figures/parkinsons_top_targets.png](reports/figures/parkinsons_top_targets.png) | The figure above |
| [notebooks/01_parkinsons_open_targets.ipynb](notebooks/01_parkinsons_open_targets.ipynb) | Executable walkthrough; outputs are stripped by `nbstripout`, so run it to regenerate |

The report is generated rather than hand-written, so its prose cannot drift from
the numbers it describes. The one hand-written part — the per-gene notes for the
top 10 — is marked as such, because whether a gene is genuinely established or
merely well-published is a judgement no script should make.

Full implementation record, including the three silent bugs this milestone
surfaced: [milestone1.md](milestone1.md).

## Quick start

```bash
uv venv --python 3.11
uv pip install -e ".[dev]"
```

> **`uv run` currently fails on this project.** Its automatic sync re-resolves the
> dependency set and picks a numba that will not build on Python 3.11. Add
> `--no-sync` to every `uv run` below to use the environment just installed —
> verified working. `uv pip compile` resolves the same `pyproject.toml` cleanly, so
> the fault is in the sync resolution rather than the pins.

```bash
# See what would be downloaded (nothing is written)
uv run python scripts/download_data.py --profile core --dry-run

# Fetch the datasets (~3.0 GB, checksums verified against upstream)
uv run python scripts/download_data.py --profile core

# Resolve disease names to Open Targets IDs and write them into the config
uv run python scripts/resolve_diseases.py

# Confirm every source parses and every identifier join connects
uv run python scripts/validate_data.py

uv run pytest -q
```

Then reproduce Milestone 1 — around a second each, both deterministic:

```bash
# The ranked parquet. --disease <key> for any disease in configs/diseases.yaml
uv run python scripts/build_dataset.py

# Figure + report. Exits non-zero if the acceptance check fails
uv run python scripts/run_milestone1.py
```

Determinism was verified by hashing the parquet across consecutive runs rather
than assumed — ties break on score, then gene symbol, then `target_id`, which is
the only one of the three that is unique. The single field that legitimately
changes between runs is `extraction_date`, which is the point of it.

`make help` lists shortcuts for the setup, download and validation steps above. The
two Milestone 1 scripts have no Make target.

## Data

Pinned to **Open Targets release 26.06**. Every downloaded file gets a
`*.manifest.json` sidecar recording URL, size, SHA-256, fetch timestamp, release
tag and licence; Open Targets files are additionally verified against the SHA-1
manifest published with the release.

| Source | Role | Size |
| --- | --- | ---: |
| Open Targets 26.06 | Associations, targets, diseases, drugs, tractability | 2.4 GB |
| STRING v12 | Protein–protein interactions | 100 MB |
| HGNC | Gene symbols, including retired ones | 16 MB |
| Reactome | Pathways | 483 MB |
| GTEx v10 | Tissue expression | 8 MB |

Measured totals from the 26.06 pull: **3.0 GB across 50 files**.

`--profile full` adds bulk expression and literature evidence (~15 GB total).
Those are excluded from `core` because their signal already arrives through the
per-datasource association scores, at a fraction of the size.

Verified after download: 78,691 targets, 47,080 diseases, 7,842,921 association
rows; all 10 configured diseases resolve and have candidate targets.

Milestone 1 uses Open Targets alone. STRING, Reactome and GTEx are downloaded and
validated but unused until Context §28 Step 9.

## Two things worth knowing before extending this

**1. The label is in the features unless you stop it.**

The MVP label is "target of an approved or clinically-advanced drug for this
disease" (Context §15), built from `clinical_target`. The `clinical_precedence`
datasource inside `association_by_datasource_direct` is *the same evidence* —
measured against release 26.06, all 107,593 of its (disease, target) pairs are
also label pairs. Training on it produces a model that reproduces its own target
variable and reports excellent metrics.

`configs/features.yaml` denylists it and `drop_denylisted_datasources` removes it
before any feature is computed, which also drops the 37 Parkinson's candidates
whose only evidence it was — that is why 8,727 candidates become 8,690 scored
rows.

**The second half of that defence was failing open, and only a probe found it.**
The final assertion selected candidate columns by prefix (`assoc_ds__`, `dim__`,
`prio__`), and two of the three matched nothing this pipeline actually produces:
it was inspecting 5 columns while logging a confident `leakage_guard_passed`.
Adding `maxClinicalStage` — the exact column the denylist exists to block — put it
in the output parquet *with values*, guard silent. Fixed two ways: prioritisation
fields are renamed to `prio__snake_case` on load so the patterns and the produced
column names actually meet, and the assertion now checks every column not on a
small allowlist of non-features. An allowlist of non-features fails closed; a
whitelist of feature prefixes fails open on any name nobody anticipated. The probe
now raises, and a normal run checks 18 columns rather than 5.

Liveness is checked as well, but against what the sources *could* produce before
filtering — "does the evidence this rule blocks still exist upstream?" rather than
"did we build it?", which is the version that does not fire on a correctly-working
pipeline. An upstream rename is exactly how a guard silently stops guarding, and
that has already happened once: releases before 26.06 called this datasource
`chembl`.

Nothing ever leaked — `drop_denylisted_datasources` and the config-load validator
were doing real work the whole time. But the layer being described as the other
half of a defence-in-depth pair was doing nothing. A guard that has never been
shown to fire is not known to work.

**2. Identifiers are where the silent failures live.**

Project_info.md §1.2 gives `EFO_0000384` for Crohn's disease. That ID does not
exist in release 26.06 — Open Targets migrated it to `MONDO_0005011`. Hard-coding
it yields zero targets, which reads as a modelling problem rather than an
identifier problem.

So IDs are resolved from the pinned release by `scripts/resolve_diseases.py`, never
transcribed. Three more traps, each with tests in `tests/test_identifiers.py`:
GTEx ships versioned gene IDs (`ENSG00000186092.7`), STRING keys on protein IDs
rather than gene IDs, and Reactome's mapping file is multi-species — the human
filter drops 95% of its rows.

Gene symbols are not unique either, which is a reproducibility problem rather than
a join problem: release 26.06 has two `calpastatin` entries with different Ensembl
IDs, so sorting on symbol alone left tied rows in whatever order DuckDB's parallel
scan happened to return.

## Layout

```
configs/     data_sources, diseases, features (+ leakage denylist), model
data/        raw (immutable) → interim → processed
src/target_prioritization/
  config.py     pydantic-validated config loading
  data/         download, identifiers, per-source readers
  features/     feature groups + the leakage guard
  models/       baseline, train, predict, evaluate, explain
  milestone1.py Milestone 1 orchestration, acceptance check, ablation
  reporting.py  report generation + the hand-written gene notes
  viz.py        evidence-breakdown figures
  services/     disease search, ranking, evidence cards
  api/          FastAPI
app/         Streamlit
scripts/     download_data, resolve_diseases, validate_data, build_dataset, run_milestone1, …
reports/     generated reports + figures
docs/        data dictionary, model card, dataset card, limitations, glossary
```

## Development

```bash
uv run ruff check . && uv run mypy src && uv run pytest -q
uv run pre-commit install
```

`make check` runs the same three.

## Licence

Code: see [LICENSE](LICENSE). Data retains its upstream licence — Open Targets and
Reactome CC0 1.0, STRING CC BY 4.0, HGNC public domain, GTEx under the GTEx Portal
terms. Each is recorded per file in the manifests.
