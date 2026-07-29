# Dataset Card

Context.md §33 reproducibility record for the data underlying this project.

## Snapshot

| Field | Value |
| --- | --- |
| Open Targets release | **26.06** (pinned) |
| Downloaded | 2026-07-29 |
| Profile | `core` |
| Files | 50 (~3.0 GB) |
| Integrity | 42 Open Targets files verified against the release SHA-1 manifest; all 50 have SHA-256 sidecars |

Regenerate with `python scripts/download_data.py --profile core`, re-check with
`--verify`.

## Sources

| Source | Version | Licence | Role |
| --- | --- | --- | --- |
| Open Targets Platform | 26.06 | CC0 1.0 | Associations, targets, diseases, drugs, tractability, safety |
| STRING | v12.0 | CC BY 4.0 | Protein–protein interactions |
| HGNC | *unversioned* | Public domain | Gene symbols and aliases |
| Reactome | *unversioned* | CC0 1.0 | Pathways (483 MB — `Ensembl2Reactome_All_Levels.txt` is multi-species and far larger than its human subset) |
| GTEx | v10 | GTEx Portal terms | Tissue expression |

Reactome and HGNC publish only a `current/` URL. For those the fetch timestamp in
the manifest is the sole version anchor, and a later re-download may differ
silently (Context.md §32.7).

## Measured contents

| Table | Rows |
| --- | ---: |
| `target` | 78,691 |
| `disease` | 47,080 |
| `association_by_datasource_direct` | 7,842,921 |
| `clinical_target` | 13,307 |
| `target_prioritisation` | 78,691 |

Datasources present in `association_by_datasource_direct` (by row count): impc,
europepmc, gwas_credible_sets, expression_atlas, **clinical_precedence**,
cancer_gene_census, eva, genomics_england, crispr_screen, gene_burden, orphanet,
uniprot_literature, uniprot_variants, gene2phenotype, clingen, reactome, intogen,
eva_somatic, crispr, cancer_biomarkers.

## Diseases

Ten diseases (Context.md §23), resolved against release 26.06 by
`scripts/resolve_diseases.py`.

| Disease | ID | Candidate targets |
| --- | --- | ---: |
| Parkinson's disease *(milestone 1)* | MONDO_0005180 | 8,727 |
| Alzheimer's disease | MONDO_0004975 | 13,289 |
| Type 2 diabetes | MONDO_0005148 | 9,906 |
| Rheumatoid arthritis | MONDO_0008383 | 7,226 |
| Crohn's disease | MONDO_0005011 | 6,252 |
| Ulcerative colitis | MONDO_0005101 | 7,154 |
| Psoriasis | MONDO_0005083 | 6,963 |
| Multiple sclerosis | MONDO_0005301 | 4,340 |
| Breast carcinoma | MONDO_0004989 | 15,586 |
| Non-small cell lung carcinoma | MONDO_0005233 | 10,918 |

All ten resolved to MONDO rather than EFO identifiers in this release. Note that
`EFO_0000384`, cited for Crohn's disease in Project_info.md §1.2, **does not exist
in 26.06** — it has been superseded by `MONDO_0005011`.

## Processing applied

| Step | Effect |
| --- | --- |
| GTEx version stripping | `ENSG…​.7` → `ENSG…`; 45 PAR_Y duplicates removed; 58,988 genes × 68 tissues remain |
| Reactome species filter | 3,767,604 → 178,495 rows (95% non-human, dropped) |
| STRING ENSP → ENSG | 19,699/19,699 proteins mapped (100%) |
| STRING edge collapse | 13,715,404 raw edges → 1,858,944 at score ≥ 400 → 929,898 undirected gene-level edges |
| HGNC symbol lookup | 100,733 symbol rows including previous and alias symbols; 1,107 symbols are ambiguous and carry a priority rank |

## Known biases

Coverage is uneven across diseases (4,340 to 15,586 candidate targets) and heavily
skewed toward well-studied genes. `impc` (mouse phenotypes) and `europepmc`
(literature) together account for over 80% of all association rows, so evidence
volume is not the same as evidence quality. See [limitations.md](limitations.md).
