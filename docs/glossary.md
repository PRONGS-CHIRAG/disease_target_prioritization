# Glossary

Phase 1 deliverable (Context.md §29). Biology terms as they are used in this
project — enough to work with the data without misreading it.

## Molecular basics

**Gene** — a stretch of DNA carrying instructions for a functional product,
usually a protein. Identified internally by Ensembl gene ID (`ENSG…`).

**Protein** — the functional product. Most conventional drugs act on proteins,
not on genes. Identified by UniProt accession or Ensembl protein ID (`ENSP…`).

**Gene expression** — how actively a gene is being transcribed in a given tissue.
Measured here as median TPM per tissue from GTEx.

**Pathway** — a set of interacting genes and proteins carrying out a biological
process. Source: Reactome.

## Genetics

**Variant** — a difference in DNA sequence between individuals.

**SNP** — a single-base variant, the most common kind.

**GWAS** — genome-wide association study; scans variants across many people to
find those occurring more often in cases than controls.

**Credible set** — the variants at a locus that statistically could be the causal
one. GWAS points at a region, not a gene, and this is part of narrowing it down.

**eQTL** — a variant that affects a gene's expression level. Helps connect a
non-coding GWAS signal to the gene it acts through.

**Colocalization** — evidence that a disease signal and an expression signal at
the same locus share one causal variant, rather than coinciding.

**Gene burden test** — tests whether rare damaging variants in a gene are
collectively more common in cases. Complements GWAS, which handles common variants.

## Target concepts

**Therapeutic target** — a protein, gene or process that could be modified to
produce a beneficial effect.

**Target identification** — finding genes plausibly related to a disease.

**Target prioritization** — ordering those candidates by how promising they are.
This project does the second.

**Tractability** — whether a target can realistically be engaged by a drug: does
it have a binding pocket, is it accessible to an antibody, are there known
chemical probes.

**Clinical precedence** — whether drugs against this target have reached the
clinic. Used here as the **label**, and therefore excluded from the features.

**Genetic constraint** — how strongly a gene is depleted of damaging variants in
healthy people. Highly constrained genes are important, which cuts both ways: a
promising target and a safety concern.

**Essentiality** — whether cells die without the gene. An essential gene is a
risky target.

**Pleiotropy** — one gene affecting many unrelated traits. Raises the chance that
modulating it produces unintended effects.

## Identifiers

| Namespace | Example | Used for |
| --- | --- | --- |
| Ensembl gene | `ENSG00000188906` | **Internal key** for genes |
| Ensembl protein | `ENSP00000298910` | STRING network nodes |
| HGNC symbol | `LRRK2` | Human-readable display |
| UniProt | `Q5S007` | Protein annotation |
| MONDO / EFO | `MONDO_0005180` | **Internal key** for diseases |
| ChEMBL | `CHEMBL1234` | Drugs |
| Reactome | `R-HSA-373076` | Pathways |
