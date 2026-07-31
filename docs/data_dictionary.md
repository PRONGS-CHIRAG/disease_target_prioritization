# Data Dictionary

Target schema for `data/processed/disease_target_features.parquet`, one row per
`(disease_id, target_id)`. From Context.md §27 and §14, and Project_info.md §17.

## Identification

| Column | Type | Description |
| --- | --- | --- |
| `disease_id` | str | Open Targets disease ID, e.g. `MONDO_0005180` |
| `disease_name` | str | Human-readable disease name |
| `target_id` | str | **Internal key.** Unversioned Ensembl gene ID |
| `gene_symbol` | str | HGNC approved symbol |
| `gene_name` | str | Full gene name |
| `dataset_version` | str | Open Targets release, e.g. `26.06` |
| `extraction_date` | str | UTC ISO-8601 date the row was built |

## Feature columns

Prefixes: `assoc_ds__` per-datasource association, `prio__` target
prioritisation, `expr__` GTEx, `net__` STRING, `path__` Reactome, `diversity__`
derived, `missing__` missingness indicators.

| Group | Examples | Source |
| --- | --- | --- |
| genetics | `assoc_ds__gwas_credible_sets_score`, `assoc_ds__gene_burden_score`, `genetics__n_datasources` | Open Targets |
| literature | `assoc_ds__europepmc_score` *(log-transformed)* | Open Targets |
| pathways | `path__n_pathways` (distinct root Reactome categories) | Reactome |
| expression | `expr__relevant_tissue_tpm`, `expr__tissue_specificity` | GTEx v10 |
| network | `net__degree`, `net__pagerank`, `net__betweenness` (sampled) | STRING v12 |
| druggability | `prio__has_pocket`, `prio__has_ligand`, `prio__is_in_membrane` | Open Targets |
| safety | `prio__genetic_constraint`, `prio__mouse_ko_score`, `prio__has_safety_event` | Open Targets |
| evidence diversity | `diversity__n_evidence_types`, `diversity__pct_categories_present` | Derived |

Full list: `configs/features.yaml`. Each of the six groups also contributes a
`dim__<group>` aggregate (`[0, 1]`, illustrative — same caveat as
`configs/model.yaml`'s `baseline_weights`) for `baseline_weights`/`WeightedBaseline`
to consume. Four columns Context.md §14.3/§14.5 describe —
`path__overlap_with_known_disease_genes`, `path__n_disease_relevant_pathways`,
`net__n_disease_gene_neighbours`, `net__min_distance_to_disease_gene` — are
deliberately not built: they need a per-disease "known disease genes" seed set
this repo has no leakage-reviewed definition for (milestone4_plan.md §2.1).

## Missingness

Every group carries `missing__<group>` (0/1). Context.md §32.3: a missing value
means "not studied", a zero means "studied and found absent". Imputing one as the
other systematically penalises understudied genes — which are precisely the ones
a prioritization tool should be able to surface.

## Label

| Column | Type | Description |
| --- | --- | --- |
| `label` | int | 1 if a drug against this target reached Phase 3+ for this disease |
| `max_clinical_stage` | str | Raw stage string, kept for auditing |
| `label_source` | str | `open_targets/clinical_target` |

Written to `data/processed/labels.parquet`, joined only at training time and
never merged into the feature frame.

## Excluded — leakage

Never present in the model matrix:

| Column | Reason |
| --- | --- |
| `assoc_ds__clinical_precedence*` | Is the label |
| `assoc_overall__*` | Aggregates the label evidence |
| `prio__max_clinical_stage` | Derived from clinical status |

Enforced by `features/build_features.assert_no_leakage`, which raises rather than
warns, and which also fails if a `required` rule stops matching — see
`tests/test_features.py`.
