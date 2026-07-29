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
| Milestone 1 — Parkinson's rule-based baseline (Context §36) | Not started |
| Milestone 2 — multi-disease ML baseline (Context §37) | Not started |
| Milestone 3 — Streamlit app (Context §21) | Not started |

Implemented and tested today: configuration, path/provenance utilities, the dataset
downloader, identifier normalization, and the leakage guard. Everything under
`features/`, `models/`, `services/`, `api/` and `app/` is a typed stub with a
documented contract.

## Quick start

```bash
uv venv --python 3.11
uv pip install -e ".[dev]"

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

## Two things worth knowing before extending this

**1. The label is in the features unless you stop it.**

The MVP label is "target of an approved or clinically-advanced drug for this
disease" (Context §15), built from `clinical_target`. The `clinical_precedence`
datasource inside `association_by_datasource_direct` is *the same evidence* —
measured against release 26.06, all 107,593 of its (disease, target) pairs are
also label pairs. Training on it produces a model that reproduces its own target
variable and reports excellent metrics.

`configs/features.yaml` denylists it. `features/build_features.py` raises
`LeakageError` rather than warning, and the guard also fails when a `required`
rule stops matching anything — because an upstream rename is exactly how a guard
silently stops guarding. That happened already: releases before 26.06 called this
datasource `chembl`.

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

## Layout

```
configs/     data_sources, diseases, features (+ leakage denylist), model
data/        raw (immutable) → interim → processed
src/target_prioritization/
  config.py  pydantic-validated config loading
  data/      download, identifiers, per-source readers
  features/  feature groups + the leakage guard
  models/    baseline, train, predict, evaluate, explain
  services/  disease search, ranking, evidence cards
  api/       FastAPI
app/         Streamlit
scripts/     download_data, resolve_diseases, validate_data, …
docs/        data dictionary, model card, dataset card, limitations, glossary
```

## Development

```bash
uv run ruff check . && uv run mypy src && uv run pytest -q
uv run pre-commit install
```

## Licence

Code: see [LICENSE](LICENSE). Data retains its upstream licence — Open Targets and
Reactome CC0 1.0, STRING CC BY 4.0, HGNC public domain, GTEx under the GTEx Portal
terms. Each is recorded per file in the manifests.
