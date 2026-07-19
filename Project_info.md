# Explainable Disease–Target Prioritization Using Human Genetics and Functional Genomics

## 1. Project Overview

### 1.1 Project title

**Explainable Disease–Target Prioritization Using Human Genetics and Functional Genomics**

### 1.2 Recommended starting disease

**Crohn’s disease**

Crohn’s disease is a useful starting point because:

* It has substantial human-genetics evidence.
* It involves relatively well-studied immune and inflammatory pathways.
* Multiple established therapeutic targets already exist.
* Known targets can be used to validate the ranking system.
* It is complex enough to be realistic without being as difficult as many cancer projects.
* It is relevant to pharmaceutical and biotechnology research workflows.

The Open Targets disease identifier for Crohn’s disease is:

```text
EFO_0000384
```

### 1.3 Central project question

> Given a disease, which genes or proteins are the most promising therapeutic targets, and what evidence supports or contradicts each target?

### 1.4 Project purpose

The project will build an evidence-based system that ranks genes and proteins as potential therapeutic targets for a selected disease.

The system should combine:

* Human-genetics evidence
* Biological relevance
* Tissue and cell-type context
* Pathway information
* Target tractability
* Safety information
* Existing drug and clinical-development evidence
* Evidence quality and uncertainty

The project should not claim that a target is clinically validated or that a drug will work. It should generate a transparent and scientifically defensible shortlist for further investigation.

---

# 2. Target Identification vs Target Prioritization

These concepts should be kept separate.

## 2.1 Target identification

Target identification means finding genes or proteins that may be related to a disease.

Examples include:

* Genes found near disease-associated genetic variants
* Proteins highly expressed in diseased tissue
* Genes involved in disease-related pathways
* Proteins affected by existing drugs
* Genes identified in CRISPR or functional experiments

## 2.2 Target prioritization

Target prioritization means deciding which of the identified targets are most suitable for further research and therapeutic development.

Prioritization considers questions such as:

* Is the target causally connected to the disease?
* Is it active in a relevant tissue or cell type?
* Can a drug realistically affect it?
* Is changing the target likely to be safe?
* Is there evidence from existing drugs or clinical trials?
* Is the target novel, or is it already heavily studied?

## 2.3 Therapeutic hypothesis

A therapeutic hypothesis goes beyond identifying a target. It proposes how the target should be modified.

Possible hypotheses include:

* Inhibit the target
* Activate the target
* Block the target with an antibody
* Degrade the target protein
* Reduce its gene expression
* Increase its gene expression
* Modify its RNA or splicing

For the first project version, the main focus should be **target prioritization**, with direction-of-effect information included where available.

---

# 3. Main Project Objective

The system should rank candidate targets using five major dimensions.

## 3.1 Disease relevance

Determine whether the target is genuinely associated with the disease.

Relevant questions:

* Is the target supported by human genetics?
* Is it involved in disease-related pathways?
* Is it expressed in affected tissues?
* Is it supported by experimental models?
* Is the evidence replicated across studies?

## 3.2 Causal evidence

Determine whether the evidence suggests that changing the target could influence disease risk or progression.

Relevant questions:

* Are disease-associated genetic variants linked to the target?
* Do fine-mapping results support the target?
* Does an eQTL or pQTL signal colocalize with the disease association?
* Do rare damaging variants in the gene affect disease risk?
* Is the direction of effect known?

## 3.3 Biological context

Determine whether the target is relevant in the correct biological environment.

Relevant questions:

* Is it active in disease-relevant tissues?
* Is it expressed in relevant cell types?
* Is it part of a disease-relevant pathway?
* Is it upstream or downstream in the pathway?
* Does it interact with other important disease proteins?

## 3.4 Tractability

Determine whether the target can realistically be affected by a therapeutic intervention.

Relevant questions:

* Does it have a known small-molecule binding site?
* Is it accessible to an antibody?
* Is it located on the cell surface?
* Is it secreted?
* Can RNA-based or gene-based therapies affect it?
* Are chemical probes or tool compounds available?

## 3.5 Safety

Determine whether modifying the target may cause unacceptable effects.

Relevant questions:

* Is the gene essential for normal cell survival?
* Is the target expressed widely in healthy tissues?
* Are humans tolerant of loss-of-function variants?
* Do animal knockouts produce severe effects?
* Have existing drugs against the target caused safety problems?
* Does the target affect several unrelated biological systems?

---

# 4. Expected Project Outputs

The final system should produce:

* A ranked list of approximately 20–50 candidate targets
* An overall prioritization score for each target
* Separate scores for:

  * Genetics
  * Biological relevance
  * Tractability
  * Safety
  * Clinical evidence
* Supporting evidence for every score
* Contradictory or negative evidence
* Missing-data indicators
* Confidence or evidence-strength indicators
* Relevant publications and study identifiers
* Source-dataset information
* Dataset release version
* Model version
* Explanation of why one target ranks above another
* A structured evidence report for each target

A target should not receive a high score without the user being able to inspect the evidence behind it.

---

# 5. Minimum Biology and Genetics Required

The objective is not to become a biology expert. The objective is to learn enough biology to:

* Understand the datasets
* Design meaningful features
* Avoid biologically incorrect interpretations
* Explain model results
* Recognize uncertainty and conflicting evidence

The required knowledge can be divided into six modules.

---

# 6. Biology Module 1: Genes, DNA, RNA and Proteins

## 6.1 Concepts to learn

Learn the following concepts at a high level:

* DNA
* Chromosomes
* Genes
* Genetic variants
* RNA
* Messenger RNA
* Transcription
* Translation
* Proteins
* Protein function
* Protein-coding genes
* Non-coding genes
* Gene expression
* Gene regulation
* Gene symbols
* Ensembl gene identifiers
* Loss-of-function variants
* Gain-of-function variants

## 6.2 Basic information flow

The simplified biological information flow is:

```text
DNA
↓ Transcription
RNA
↓ Translation
Protein
↓
Biological function
```

A gene is a region of DNA. Many genes contain instructions for producing proteins. Proteins perform functions such as:

* Sending signals
* Receiving signals
* Catalysing chemical reactions
* Transporting molecules
* Regulating immune responses
* Maintaining cell structure
* Controlling gene expression

## 6.3 Why this matters for drug discovery

Most conventional therapeutic targets are proteins.

Common target types include:

* Enzymes
* Receptors
* Ion channels
* Transporters
* Signalling proteins
* Secreted proteins
* Transcription factors

For the first version of the project, restrict the candidate targets to:

> Human protein-coding genes and their corresponding proteins

## 6.4 Example

`IL23R` is a gene.

The gene encodes part of the interleukin-23 receptor protein.

This receptor participates in immune signalling. Changes in its function may influence inflammatory diseases such as Crohn’s disease.

## 6.5 Learning checkpoint

You understand enough when you can explain:

* The difference between a gene and a protein
* Why drugs usually target proteins rather than DNA directly
* What gene expression means
* What loss of function and gain of function mean
* Why one gene may have different effects in different tissues

---

# 7. Biology Module 2: Disease Mechanisms, Cells and Pathways

## 7.1 Concepts to learn

Learn the following concepts:

* Disease phenotype
* Disease mechanism
* Acute disease
* Chronic disease
* Complex disease
* Single-gene disease
* Tissue
* Organ
* Cell type
* Biological pathway
* Signalling pathway
* Receptor
* Enzyme
* Cytokine
* Biomarker
* Inflammation
* Immune response
* Upregulation
* Downregulation
* Homeostasis

## 7.2 Disease phenotype

A phenotype is an observable characteristic.

Disease phenotypes may include:

* Symptoms
* Tissue damage
* Abnormal laboratory values
* Changes in gene expression
* Altered immune responses
* Structural abnormalities

## 7.3 Complex disease

Crohn’s disease is a complex disease.

This means that it is influenced by a combination of:

* Many genetic variants
* Immune-system behaviour
* Environmental exposures
* Microbiome composition
* Lifestyle factors
* Tissue-specific biological processes

There is usually no single gene that completely explains a complex disease.

## 7.4 Pathways

A biological pathway is a connected sequence of molecular events.

A simplified pathway may look like:

```text
External signal
↓
Cell-surface receptor
↓
Intracellular signalling protein
↓
Transcription factor
↓
Gene-expression change
↓
Cellular response
```

A target’s position in a pathway matters.

An upstream target may have a broad effect across several downstream processes. A downstream target may have a narrower and more specific effect.

## 7.5 Crohn’s disease concepts to understand

Learn the high-level roles of:

* Intestinal epithelial cells
* Intestinal barrier function
* Immune cells
* T cells
* Macrophages
* Cytokines
* Innate immunity
* Adaptive immunity
* Chronic inflammation
* Microbial recognition
* Gut microbiome as a disease modifier

You do not need to memorize every immune-cell subtype or cytokine.

## 7.6 Learning checkpoint

You understand enough when you can answer:

* Which organs and tissues are affected?
* Which cell types are involved?
* Which pathways are disrupted?
* Is a target upstream or downstream in a pathway?
* Could modifying the target also affect healthy tissues?
* Is the biological signal likely to be a cause or a consequence of disease?

---

# 8. Genetics Module 3: Human Genetics

Human genetics is the most important biological area for this project.

## 8.1 Genetic variants

A genetic variant is a difference in DNA sequence between individuals.

Common types include:

* Single-nucleotide variants
* Insertions
* Deletions
* Copy-number variants
* Structural variants

## 8.2 SNP

A single-nucleotide polymorphism, or SNP, is a common variation at a single DNA position.

Example:

```text
Person 1: A
Person 2: G
```

at the same location in the genome.

## 8.3 Allele

An allele is one possible version of a genetic variant.

For a SNP with possible bases `A` and `G`, the two alleles are:

* A allele
* G allele

## 8.4 Effect size

Effect size represents the strength of an association.

In disease studies, it may be represented using:

* Odds ratio
* Beta coefficient
* Hazard ratio

For an odds ratio:

* Greater than 1 may indicate increased disease risk.
* Less than 1 may indicate reduced disease risk.
* Close to 1 may indicate little or no effect.

## 8.5 P-value

The p-value estimates how surprising the observed association would be if there were no real association.

A very small p-value provides stronger statistical evidence against the null hypothesis.

However:

* A small p-value does not prove causality.
* A small p-value does not indicate a large biological effect.
* Very large studies can detect very small effects.

## 8.6 Genome-wide association study

A genome-wide association study, or GWAS, searches across the genome for variants associated with a disease or trait.

A GWAS may identify variants associated with:

* Disease risk
* Disease severity
* Biomarker level
* Treatment response
* Protein level
* Gene-expression level

## 8.7 GWAS locus

A GWAS usually identifies a genomic region, called a locus, rather than directly identifying the causal gene.

A significant variant may be:

* Causal itself
* Correlated with the causal variant
* Located close to the causal gene
* Located far from the causal gene
* Affecting gene regulation rather than protein sequence

Therefore, the closest gene is not automatically the correct target.

## 8.8 Linkage disequilibrium

Linkage disequilibrium describes correlation between genetic variants.

Nearby variants may be inherited together. As a result, several variants may appear associated with a disease even when only one is responsible for the biological effect.

## 8.9 Fine-mapping

Fine-mapping estimates which variants inside a GWAS locus are most likely to be causal.

Fine-mapping produces:

* Posterior probabilities
* Credible sets
* Candidate causal variants

## 8.10 Credible set

A credible set is a group of variants that collectively contains a specified probability of including the causal variant.

For example, a 95% credible set represents a group of variants expected to contain the causal variant with approximately 95% probability under the model assumptions.

You do not need to perform fine-mapping yourself for the first project version. Existing fine-mapping results can be used.

## 8.11 eQTL

An expression quantitative trait locus, or eQTL, is a genetic variant associated with the expression level of a gene.

Example:

```text
Variant A
↓
Higher expression of Gene B
```

eQTL effects may be tissue-specific.

A variant may affect a gene in:

* Blood
* Intestinal tissue
* Liver
* Brain
* Immune cells

but not in other tissues.

## 8.12 pQTL

A protein quantitative trait locus, or pQTL, is a genetic variant associated with protein abundance.

pQTL evidence can be useful because proteins are often closer to the druggable biological target than RNA expression.

## 8.13 sQTL

A splicing quantitative trait locus, or sQTL, is a genetic variant associated with RNA splicing.

Splicing determines which parts of RNA are included in the final transcript.

A variant may change:

* Which protein isoform is produced
* Protein structure
* Protein stability
* Protein function

## 8.14 Colocalization

Colocalization asks whether two associations likely share the same causal genetic signal.

For example:

* A disease GWAS association
* An eQTL association for a gene

may occur in the same genomic region.

Colocalization estimates whether both signals are likely caused by the same underlying variant.

This matters because two associations can overlap geographically without sharing a causal mechanism.

## 8.15 Rare variants

Rare variants occur at low frequency in the population.

Rare variants may have larger biological effects than common variants.

Important rare-variant concepts include:

* Predicted loss-of-function variants
* Missense variants
* Protein-truncating variants
* Damaging variants
* Gene-burden tests

## 8.16 Gene-burden tests

A gene-burden test evaluates whether people with a disease carry more rare damaging variants in a gene than people without the disease.

Instead of testing every rare variant individually, variants are grouped by gene.

## 8.17 Mendelian and complex diseases

A Mendelian disease may be primarily caused by damaging variants in one gene.

A complex disease is influenced by:

* Many genetic variants
* Environmental factors
* Biological interactions
* Multiple pathways

Crohn’s disease is a complex disease.

## 8.18 Direction of effect

Direction of effect is essential for developing a therapeutic hypothesis.

Possible findings include:

* Reduced gene function lowers disease risk.
* Reduced gene function increases disease risk.
* Increased expression lowers disease risk.
* Increased expression increases disease risk.

A simplified interpretation may be:

```text
Reduced target function
↓
Reduced disease risk
↓
Target inhibition may be worth investigating
```

However, genetic effects and drug effects are not identical.

A genetic variant may affect a person throughout their lifetime, while a drug may:

* Be given later in life
* Only partially inhibit the target
* Affect specific tissues
* Have off-target effects
* Be administered for a limited period

Direction-of-effect evidence should be treated as support for a hypothesis, not proof.

## 8.19 Genetics learning checkpoint

You understand enough when you can explain:

> A GWAS identifies a disease-associated locus. Fine-mapping narrows the possible causal variants. Molecular-QTL and colocalization analyses connect the signal to a gene. Direction-of-effect evidence then helps determine whether inhibiting or activating the gene may be therapeutically useful.

---

# 9. Biology Module 4: Functional Genomics

Genetics helps estimate whether a target may be causally related to disease. Functional genomics helps explain what the gene does and in which biological context it operates.

## 9.1 Concepts to learn

Learn the following:

* RNA sequencing
* Gene-expression level
* Differential expression
* Tissue-specific expression
* Cell-type-specific expression
* Single-cell RNA sequencing
* Gene knockout
* Gene knockdown
* CRISPR screen
* Gene essentiality
* Animal model
* Protein–protein interaction
* Functional assay

## 9.2 RNA sequencing

RNA sequencing measures RNA molecules in a biological sample.

It can be used to estimate which genes are active and at what level.

## 9.3 Differential expression

Differential-expression analysis compares gene-expression levels between conditions.

Examples:

* Diseased tissue vs healthy tissue
* Treated cells vs untreated cells
* Responders vs non-responders

A differentially expressed gene is not automatically causal.

It may be:

* A cause of disease
* A consequence of disease
* A protective response
* A marker of inflammation
* A result of tissue damage
* A change in cell-type composition

## 9.4 Tissue-specific expression

A target may be relevant only if it is expressed in the tissue affected by the disease.

For Crohn’s disease, relevant tissue context may include:

* Intestinal tissue
* Colon
* Ileum
* Blood
* Immune cells

## 9.5 Single-cell expression

Single-cell RNA sequencing measures gene expression in individual cells or small groups of similar cells.

It can help determine whether a target is expressed in:

* T cells
* B cells
* Macrophages
* Epithelial cells
* Fibroblasts
* Other relevant cell populations

## 9.6 Gene knockout

A gene knockout removes or disables a gene.

Researchers observe what happens when the gene no longer functions.

A knockout may reveal:

* Whether the gene is essential
* Whether it affects disease biology
* Whether it causes toxicity
* Which pathways depend on the gene

## 9.7 Gene knockdown

A gene knockdown reduces gene expression without fully removing the gene.

This may better approximate partial drug inhibition than a complete knockout.

## 9.8 CRISPR screens

CRISPR screens systematically modify many genes to determine which genes affect a phenotype.

Examples include identifying genes required for:

* Cell survival
* Drug resistance
* Immune activation
* Disease-related signalling
* Pathogen entry

## 9.9 Animal models

Animal models may be used to test:

* Disease mechanisms
* Target function
* Drug response
* Toxicity

Animal evidence is useful but does not always translate to humans.

Human-genetics evidence should generally receive greater weight than animal-model evidence when both are available.

## 9.10 Protein–protein interactions

Proteins often function as parts of networks rather than independently.

Protein–protein interaction evidence can identify:

* Pathway membership
* Protein complexes
* Upstream regulators
* Downstream effectors
* Potential indirect targets

## 9.11 Functional-genomics warning

The following statement is incorrect:

> This gene is highly expressed in diseased tissue, so it causes the disease.

The correct interpretation is:

> This gene is associated with the disease state and may participate in the disease mechanism, but additional causal evidence is required.

---

# 10. Biology Module 5: Pharmacology and Druggability

## 10.1 Concepts to learn

Learn the following:

* Drug target
* Target engagement
* Mechanism of action
* Small molecule
* Antibody
* Inhibitor
* Activator
* Agonist
* Antagonist
* Protein degrader
* RNA therapy
* Gene therapy
* Selectivity
* Potency
* On-target effect
* Off-target effect
* Dose
* Therapeutic window
* Clinical phase

## 10.2 Drug target

A drug target is a biological molecule whose modification is expected to produce a therapeutic effect.

Most drug targets are proteins, but targets may also include:

* RNA
* DNA
* Protein complexes
* Microbial proteins
* Cellular structures

## 10.3 Target engagement

Target engagement means that a therapeutic molecule physically or functionally interacts with its intended target inside the relevant biological system.

A drug may show an effect without sufficient evidence that the intended target was responsible.

## 10.4 Mechanism of action

Mechanism of action describes how a therapeutic intervention produces its biological effect.

A mechanism may involve:

* Blocking a receptor
* Inhibiting an enzyme
* Activating a receptor
* Neutralizing a secreted protein
* Degrading a protein
* Reducing RNA expression
* Modifying immune-cell behaviour

## 10.5 Inhibitor

An inhibitor reduces the activity of a target.

Common inhibitor targets include:

* Enzymes
* Kinases
* Proteases
* Receptors
* Transporters

## 10.6 Agonist

An agonist activates a receptor or signalling pathway.

## 10.7 Antagonist

An antagonist blocks a receptor and prevents activation.

## 10.8 Small molecules

Small molecules are relatively low-molecular-weight compounds that can often enter cells.

They may be suitable for:

* Enzymes
* Intracellular proteins
* Receptors
* Ion channels

## 10.9 Antibodies

Antibodies are larger biological molecules.

They are often suitable for:

* Cell-surface receptors
* Secreted proteins
* Cytokines
* Extracellular targets

Antibodies generally cannot easily enter cells.

## 10.10 Tractability

Tractability refers to whether a target can realistically be modified using a therapeutic modality.

Questions include:

* Does the protein have a binding pocket?
* Is it located on the cell surface?
* Is it secreted?
* Is it accessible to an antibody?
* Are related proteins already drugged?
* Are chemical probes available?
* Can the target be affected using RNA or gene therapy?

## 10.11 Clinical precedence

Clinical precedence refers to previous therapeutic development involving the target.

Possible evidence includes:

* Approved drugs
* Phase III trials
* Phase II trials
* Phase I trials
* Preclinical compounds
* Failed clinical trials
* Drugs approved for other diseases

A target with an approved drug has strong technical and clinical precedent.

However, it may be less novel.

A target with no existing drug may be innovative, but it may also be:

* Difficult to drug
* Unsafe
* Biologically weak
* Poorly studied

---

# 11. Biology Module 6: Safety and Evidence Quality

## 11.1 Concepts to learn

Learn the following:

* Essential gene
* Genetic constraint
* Tissue distribution
* On-target toxicity
* Off-target toxicity
* Therapeutic window
* Pleiotropy
* Mouse knockout phenotype
* Human loss-of-function evidence
* Association
* Causation
* Confounding
* Replication
* Publication bias
* Population ancestry
* Missing evidence

## 11.2 Essential genes

An essential gene is required for normal cell or organism survival.

Strong inhibition of an essential gene may cause toxicity.

However, essentiality can depend on:

* Cell type
* Tissue
* Developmental stage
* Environmental context
* Degree of inhibition

## 11.3 Genetic constraint

Genetic constraint estimates how intolerant a gene is to damaging genetic variants.

A gene with very few observed loss-of-function variants in humans may be important for normal biological function.

Strong constraint may suggest:

* Potential safety risk
* Developmental importance
* Essential biological function

It does not automatically mean the target cannot be drugged.

## 11.4 Tissue distribution

A target expressed broadly across healthy tissues may create more safety concerns than a target restricted to a disease-relevant tissue.

However, broad expression does not automatically make a target unsafe.

## 11.5 On-target toxicity

On-target toxicity occurs when modifying the intended target causes an undesirable biological effect.

## 11.6 Off-target toxicity

Off-target toxicity occurs when a drug affects a different biological molecule from the intended target.

A target-prioritization system mainly estimates target-level or on-target risk. Compound-level off-target toxicity is usually assessed later.

## 11.7 Therapeutic window

The therapeutic window is the range between:

* A dose that produces a useful therapeutic effect
* A dose that causes unacceptable toxicity

## 11.8 Pleiotropy

Pleiotropy means that one gene or protein influences multiple biological traits or systems.

A highly pleiotropic target may:

* Affect several organs
* Influence multiple diseases
* Create unexpected side effects
* Produce both beneficial and harmful effects

## 11.9 Association vs causation

An association means that two observations occur together.

Causation means that changing one factor produces a change in another.

Examples of association include:

* A gene is highly expressed in disease.
* A protein level correlates with disease severity.
* A pathway is activated in diseased tissue.

These do not automatically prove that changing the target will improve the disease.

## 11.10 Missing evidence

Missing evidence must not be interpreted as favourable evidence.

Use:

```text
No safety data available
```

instead of:

```text
Target appears safe
```

The system should distinguish:

* Positive evidence
* Negative evidence
* Conflicting evidence
* Missing evidence

---

# 12. Dataset Strategy

## 12.1 Recommended approach

Do not integrate every biomedical dataset at the beginning.

Start with:

1. Open Targets Platform
2. GTEx
3. Human Protein Atlas
4. Reactome

Additional datasets can be added after the basic pipeline works.

---

# 13. Core Dataset: Open Targets Platform

Open Targets should be the primary dataset for the MVP.

It integrates multiple types of information relevant to target prioritization.

## 13.1 Useful Open Targets data

Open Targets provides:

* Disease information
* Target information
* Target–disease associations
* Common-variant genetics
* Rare-variant genetics
* Somatic-mutation evidence
* Known drugs
* Clinical-development phases
* Pathway evidence
* Animal-model evidence
* Literature evidence
* Target tractability
* Genetic constraint
* Baseline expression
* Safety information
* Mouse phenotypes
* Target properties

## 13.2 API access

Use the Open Targets GraphQL API for:

* Initial exploration
* Individual disease queries
* Individual target queries
* Small prototype datasets
* Dashboard data retrieval

## 13.3 Bulk data access

Use Open Targets bulk downloads when:

* Training across many diseases
* Extracting thousands of target–disease pairs
* Building reproducible datasets
* Creating historical snapshots
* Reducing dependence on live API calls

The bulk datasets are commonly provided in formats such as partitioned Parquet files.

## 13.4 Important Open Targets entities

You will work with:

* Disease
* Target
* Drug
* Target–disease association
* Evidence item
* Study
* Variant
* Locus
* Pathway

---

# 14. Supplemental Datasets

## 14.1 GWAS Catalog

Use the GWAS Catalog for:

* Published GWAS associations
* Disease-associated loci
* Study metadata
* Reported genes
* Population and ancestry information
* Independent validation of genetic associations

MVP status:

**Optional for the first version**

## 14.2 GTEx

Use GTEx for:

* Tissue-specific gene expression
* eQTL evidence
* sQTL evidence
* Tissue-specific regulatory effects

MVP status:

**Recommended enrichment dataset**

## 14.3 Human Protein Atlas

Use the Human Protein Atlas for:

* Tissue RNA expression
* Tissue protein expression
* Cell-type expression
* Subcellular localization
* Disease-related expression
* Tissue specificity

MVP status:

**Recommended enrichment dataset**

## 14.4 Reactome

Use Reactome for:

* Biological pathways
* Pathway membership
* Pathway hierarchy
* Pathway enrichment
* Connections between candidate targets

MVP status:

**Recommended enrichment dataset**

## 14.5 ChEMBL

Use ChEMBL for:

* Drug–target relationships
* Drug mechanisms
* Bioactive molecules
* Clinical candidates
* Target classes
* Chemical probes
* Compound activity data

For the first version, much of the relevant drug information can be obtained through Open Targets.

MVP status:

**Add in a later version**

## 14.6 DepMap

Use DepMap for:

* CRISPR gene dependency
* Cancer-cell-line vulnerabilities
* Cancer-specific target validation
* Gene essentiality in cancer models

DepMap is mainly relevant to cancer.

MVP status:

**Skip for Crohn’s disease**

---

# 15. Dataset Summary

| Dataset             | Main use                                  |            MVP priority |
| ------------------- | ----------------------------------------- | ----------------------: |
| Open Targets        | Integrated disease–target evidence        |                Required |
| GTEx                | Tissue expression and regulatory genetics |                    High |
| Human Protein Atlas | RNA and protein expression                |                    High |
| Reactome            | Biological pathways                       |                    High |
| GWAS Catalog        | Published genetic associations            |                  Medium |
| ChEMBL              | Drugs, mechanisms and compounds           |                  Medium |
| DepMap              | Cancer gene dependency                    | Low for Crohn’s disease |

---

# 16. Data Model

The main machine-learning table should contain one row per:

```text
Disease ID + Target ID
```

Example:

```text
EFO_0000384 + ENSG00000162594
```

Each row represents one candidate target for one disease.

---

# 17. Feature Categories

## 17.1 Identification columns

Recommended fields:

```text
disease_id
disease_name
target_id
target_symbol
target_name
target_type
data_release
extraction_timestamp
```

## 17.2 Genetics features

Possible features:

```text
overall_genetic_association_score
common_variant_score
rare_variant_score
somatic_mutation_score
fine_mapping_support
locus_to_gene_score
colocalization_support
eQTL_support
pQTL_support
sQTL_support
number_of_genetic_studies
number_of_independent_loci
maximum_variant_posterior_probability
direction_of_effect_available
direction_of_effect_consistency
```

## 17.3 Biological-relevance features

Possible features:

```text
pathway_evidence_score
animal_model_score
functional_assay_score
literature_evidence_score
number_of_relevant_pathways
number_of_supporting_evidence_sources
number_of_supporting_publications
disease_tissue_expression
disease_cell_type_expression
protein_expression_support
protein_interaction_support
```

## 17.4 Tractability features

Possible features:

```text
small_molecule_tractability
antibody_tractability
other_modality_tractability
known_binding_pocket
cell_surface_target
secreted_protein
enzyme_target
receptor_target
ion_channel_target
chemical_probe_available
known_ligand_available
```

## 17.5 Safety features

Possible features:

```text
genetic_constraint_score
loss_of_function_intolerance
mouse_knockout_severity
gene_essentiality
broad_healthy_tissue_expression
known_safety_event_count
adverse_target_evidence
number_of_paralogues
pleiotropy_score
```

## 17.6 Clinical-development features

Possible features:

```text
highest_clinical_phase
approved_drug_exists
drug_for_same_disease_exists
drug_for_other_disease_exists
number_of_known_drugs
number_of_clinical_trials
number_of_failed_trials
number_of_terminated_trials
clinical_precedence_score
```

## 17.7 Evidence-quality features

Possible features:

```text
number_of_independent_evidence_sources
number_of_independent_studies
evidence_recency
evidence_consistency
conflicting_evidence_count
missing_feature_count
human_evidence_fraction
animal_evidence_fraction
literature_only_flag
```

## 17.8 Provenance features

Every important result should be connected to:

```text
source_dataset
source_dataset_release
evidence_identifier
study_identifier
publication_identifier
evidence_date
retrieval_date
transformation_version
feature_definition_version
model_version
```

These provenance fields are especially relevant to Cellvara because they create an audit-ready evidence trail.

---

# 18. Missing-Data Strategy

Biomedical datasets contain substantial missing information.

Missing values may mean:

* The target has not been studied.
* No evidence has been found.
* The dataset does not cover the target.
* The measurement is technically unavailable.
* The target has no relevant property.
* Data extraction failed.

Do not automatically replace all missing values with zero.

Recommended approach:

1. Preserve the raw missing value.
2. Add a missingness indicator.
3. Decide whether zero has a meaningful interpretation.
4. Document the choice in the data dictionary.
5. Show missing information in the dashboard.

Example:

```text
tractability_score = missing
tractability_score_missing = 1
```

---

# 19. Data Dictionary

Create a file called:

```text
data_dictionary.md
```

For every feature, document:

* Feature name
* Biological meaning
* Source
* Data type
* Expected range
* Whether higher values are favourable
* Missing-value interpretation
* Normalization method
* Leakage risk
* Known limitations
* Transformation logic

Example:

| Feature                       | Meaning                                                      |     Higher is better? | Missing-value meaning                |
| ----------------------------- | ------------------------------------------------------------ | --------------------: | ------------------------------------ |
| `common_variant_score`        | Strength of common-variant genetic association               |                   Yes | No common-variant evidence available |
| `genetic_constraint_score`    | Intolerance to damaging variants                             | Usually no for safety | Constraint information unavailable   |
| `small_molecule_tractability` | Evidence that the target can be affected by a small molecule |                   Yes | Tractability not evaluated           |
| `highest_clinical_phase`      | Most advanced known clinical program                         |     Context-dependent | No known clinical program            |

---

# 20. Machine-Learning Strategy

The project should be developed in stages.

Do not begin with a graph neural network or complex deep-learning model.

---

# 21. Stage 1: Transparent Weighted Ranking

The first model should be a manually defined evidence-ranking system.

## 21.1 Dimension scores

Create five scores:

* Genetics score
* Biological-relevance score
* Tractability score
* Safety score
* Clinical-precedence score

The final score can be defined as:

```text
Final score =
    genetics weight × genetics score
  + biology weight × biological-relevance score
  + tractability weight × tractability score
  + safety weight × safety score
  + clinical weight × clinical-precedence score
```

## 21.2 Example starting weights

| Dimension                    | Weight |
| ---------------------------- | -----: |
| Genetics and causal evidence |    35% |
| Biological relevance         |    20% |
| Tractability                 |    15% |
| Safety                       |    15% |
| Clinical precedence          |    15% |

These weights are not universally scientifically correct.

They should be treated as configurable decision-policy settings.

## 21.3 Why the baseline is important

The transparent baseline helps you:

* Understand every feature
* Detect data-quality problems
* Identify conflicting evidence
* Explain the ranking
* Compare manual reasoning with ML
* Avoid hiding weak assumptions inside a complex model

## 21.4 User-adjustable weights

The dashboard should allow users to modify the weights.

Example scenarios:

### Genetics-first ranking

```text
Genetics: 50%
Biology: 20%
Tractability: 10%
Safety: 10%
Clinical: 10%
```

### Near-term drug-development ranking

```text
Genetics: 25%
Biology: 15%
Tractability: 25%
Safety: 15%
Clinical: 20%
```

### Novel-target ranking

```text
Genetics: 40%
Biology: 25%
Tractability: 15%
Safety: 15%
Clinical: 5%
```

---

# 22. Stage 2: Logistic Regression

Use logistic regression as the first supervised-learning baseline.

## 22.1 Benefits

Logistic regression is:

* Easy to implement
* Easy to interpret
* Useful for detecting feature direction
* Useful for identifying correlated features
* Useful as a comparison for more complex models

## 22.2 Possible prediction target

Example:

```text
Will this target–disease pair reach Phase II or higher?
```

The output is a probability between 0 and 1.

## 22.3 Limitations

Logistic regression may struggle with:

* Nonlinear relationships
* Complex feature interactions
* Missing values
* Different effects across disease categories

---

# 23. Stage 3: Gradient-Boosted Trees

The primary tabular machine-learning model should be one of:

* XGBoost
* LightGBM
* CatBoost

## 23.1 Why gradient boosting is appropriate

The data will be:

* Structured
* Tabular
* Heterogeneous
* Nonlinear
* Incomplete
* Derived from multiple evidence sources

Gradient-boosted trees are usually strong models for this type of data.

## 23.2 Benefits

They can model interactions such as:

```text
Strong genetics
+ relevant tissue expression
+ tractability
= high-priority target
```

They can also model cases such as:

```text
Strong disease association
+ severe safety concern
= lower overall priority
```

## 23.3 Explainability

Use SHAP to examine:

* Global feature importance
* Target-specific explanations
* Positive feature contributions
* Negative feature contributions
* Differences between disease categories

Important:

> SHAP explains the behaviour of the model. It does not prove a biological mechanism.

Every SHAP explanation should be shown together with the underlying biological evidence.

---

# 24. Stage 4: Learning to Rank

The real project objective is ranking, not only classification.

Recommended models include:

* XGBoost Ranker
* LambdaMART
* LightGBM Ranker

## 24.1 Ranking structure

The query group is the disease.

The items are candidate targets.

Example:

```text
Query group: Crohn’s disease

Items:
IL23R
NOD2
JAK2
TYK2
TNF
Target X
Target Y
...
```

The model learns to place promising targets near the top of each disease-specific ranking.

## 24.2 Why ranking may be better than classification

Classification asks:

> Is this target positive or negative?

Ranking asks:

> Which targets should be investigated first?

Drug-discovery teams generally need a prioritized shortlist rather than a simple binary label.

---

# 25. Stage 5: Positive–Unlabelled Learning

A target without an approved drug is not necessarily a negative example.

It may be:

* Understudied
* Newly discovered
* Difficult to drug
* Commercially neglected
* Not yet tested
* Relevant only to a disease subtype
* Waiting for the correct therapeutic modality

Therefore, the dataset contains:

* Known positives
* Unknowns

rather than:

* True positives
* True negatives

Positive–unlabelled learning can be explored as an advanced extension.

---

# 26. Stage 6: Graph Machine Learning

Graph ML should only be attempted after the tabular pipeline works.

## 26.1 Possible graph nodes

* Diseases
* Genes
* Proteins
* Drugs
* Pathways
* Tissues
* Cell types
* Variants
* Studies

## 26.2 Possible graph edges

* Gene associated with disease
* Drug targets protein
* Gene belongs to pathway
* Gene expressed in tissue
* Variant regulates gene
* Protein interacts with protein
* Drug approved for disease
* Target tested in clinical trial

## 26.3 Possible models

* Node2Vec
* GraphSAGE
* Relational graph convolutional network
* TransE
* RotatE
* Knowledge-graph link prediction
* Heterogeneous graph neural network

## 26.4 Graph-learning objective

Possible prediction:

```text
Disease → candidate target
```

The system predicts missing or promising disease–target relationships.

Graph ML should be treated as an extension, not as the first implementation.

---

# 27. Label Design

## 27.1 Possible positive labels

A target–disease pair may be labelled positive when:

* An approved drug exists for the disease.
* A drug reached Phase III.
* A drug reached Phase II.
* A therapeutic program entered clinical development.
* The target has strong expert-curated validation.

## 27.2 Keep labels separate

Create separate outcome columns:

```text
has_approved_drug
reached_phase_3
reached_phase_2
entered_clinical_development
```

Do not immediately combine all outcomes into one label.

## 27.3 Example prediction task

```text
Using evidence available before 2018, predict which target–disease pairs reached Phase II or higher after 2018.
```

This creates a more realistic temporal evaluation.

---

# 28. Data Leakage

Data leakage is one of the largest risks in this project.

## 28.1 Examples of leakage

When predicting clinical progression, do not include:

* Current approval status
* Current highest clinical phase
* Publications written after target validation
* Drug evidence added after the prediction cutoff
* Features derived from the target label
* Trial information that reveals the future outcome

## 28.2 Literature leakage

A target may receive many publications after entering clinical trials or receiving approval.

If the model uses current publication counts to predict previous clinical success, it may learn:

```text
Targets that became successful were later discussed more often.
```

This is not a valid prospective prediction.

## 28.3 Temporal cutoff

Every evidence item should have a timestamp where possible.

For a cutoff year such as 2018:

```text
Training features:
Evidence published or available on or before 31 December 2018

Outcome:
Clinical progress occurring after 31 December 2018
```

## 28.4 Entity leakage

Frequently studied genes may appear across many diseases.

A random row split could place the same gene in both training and test sets.

Use:

* Target-grouped splits
* Disease-grouped splits
* Temporal splits
* Disease-category splits

---

# 29. Model Evaluation

## 29.1 Ranking metrics

Recommended metrics:

* Precision@5
* Precision@10
* Recall@10
* Recall@20
* NDCG@10
* NDCG@20
* Mean reciprocal rank
* Mean average precision

## 29.2 Classification metrics

Recommended metrics:

* Precision
* Recall
* F1 score
* PR-AUC
* ROC-AUC
* Calibration error
* Brier score

PR-AUC may be more useful than ROC-AUC because successful target–disease pairs are relatively rare.

## 29.3 Biological validation

Evaluate whether the model recovers:

* Known established targets
* Clinically validated targets
* Genetically supported targets
* Targets from independent expert lists

## 29.4 Qualitative validation

Inspect categories such as:

1. Established target ranked highly
2. Established target ranked poorly
3. Novel target ranked highly
4. Genetically strong but poorly tractable target
5. Tractable target with weak causal evidence
6. Strong target with possible safety problems
7. Target with substantial missing evidence

---

# 30. Project Development Process

## Phase 1: Disease Orientation

Create a one-page Crohn’s disease profile.

Include:

* Disease definition
* Main affected organs
* Main symptoms
* Relevant tissues
* Important cell types
* Major biological pathways
* Known genetic risk factors
* Existing treatment classes
* Limitations of current treatments
* Open Targets disease identifier

Manually inspect:

* 10 established targets
* 10 emerging targets
* 10 low-ranked targets

Do not train a model until you can explain why these targets differ.

---

# 31. Phase 2: Open Targets Exploration

Use the Open Targets web interface and GraphQL API to explore:

* Crohn’s disease
* Top target associations
* Evidence-source breakdown
* Known drugs
* Genetics evidence
* Target tractability
* Safety information

Questions to answer:

* Which targets rank highest?
* Which evidence sources contribute most?
* Which targets are supported mainly by genetics?
* Which targets are supported mainly by literature?
* Which targets already have approved drugs?
* Which targets have substantial missing data?
* Which targets have contradictory evidence?

---

# 32. Phase 3: Data Extraction Pipeline

Recommended data flow:

```text
Open Targets GraphQL or bulk datasets
↓
Raw source files
↓
Validated intermediate tables
↓
Disease–target feature table
↓
Evidence-ranking pipeline
↓
ML models
↓
Target evidence cards
↓
Dashboard and report
```

## 32.1 Recommended technology stack

* Python
* pandas or Polars
* DuckDB
* PyArrow
* Requests
* Pydantic
* scikit-learn
* XGBoost
* SHAP
* MLflow
* DVC
* Streamlit
* Plotly or Matplotlib
* Jupyter Notebook

## 32.2 Raw-data rules

Do not overwrite raw data.

Store it using versioned folders:

```text
data/raw/open_targets/2026_07/
data/raw/gtex/version_x/
data/raw/reactome/version_x/
```

Record:

* Download date
* Dataset release
* Source URL
* File checksum
* Extraction script version

---

# 33. Phase 4: Feature Engineering

For every feature:

1. Define the biological meaning.
2. Identify the source.
3. Define the transformation.
4. Define the direction.
5. Define missing-value handling.
6. Identify leakage risk.
7. Normalize if necessary.
8. Add provenance.

Example:

```text
Feature:
disease_tissue_expression

Meaning:
Expression level of the target in disease-relevant tissue

Source:
GTEx or Human Protein Atlas

Transformation:
Percentile rank across candidate targets

Higher is better:
Usually yes, but only as biological-context evidence

Limitation:
High expression does not prove causality
```

---

# 34. Phase 5: Transparent Baseline

Build the weighted evidence-ranking system.

The output should include:

* Component scores
* Overall score
* Missingness
* Evidence confidence
* Supporting evidence
* Negative evidence
* User-adjustable weights

Compare your ranking against Open Targets.

Do not simply copy the Open Targets overall association score and present it as your own prioritization model.

---

# 35. Phase 6: Multi-Disease Training Dataset

After the Crohn’s disease baseline works, expand to related immune-mediated diseases.

Possible training diseases:

* Crohn’s disease
* Ulcerative colitis
* Psoriasis
* Rheumatoid arthritis
* Multiple sclerosis
* Ankylosing spondylitis
* Systemic lupus erythematosus
* Atopic dermatitis

This provides more training examples while keeping the biological domain relatively coherent.

Possible evaluation:

* Train on several immune diseases.
* Hold out Crohn’s disease.
* Evaluate the model on Crohn’s disease.
* Compare results with known Crohn’s targets.

---

# 36. Phase 7: Supervised Models

Train models in this order:

1. Logistic regression
2. Random forest
3. XGBoost or LightGBM
4. Learning-to-rank model
5. Positive–unlabelled model
6. Graph model as an extension

For every model, record:

* Dataset version
* Features
* Hyperparameters
* Train/test split
* Evaluation metrics
* Random seed
* Model artifact
* Training timestamp
* Code version

---

# 37. Phase 8: Explainability

Each target page should display:

## 37.1 Summary

* Target name
* Gene symbol
* Overall ranking
* Overall score
* Confidence level
* Existing drug status

## 37.2 Evidence dimensions

* Genetics
* Biology
* Tractability
* Safety
* Clinical precedence

## 37.3 Strongest supporting evidence

Example:

```text
Strong fine-mapped human-genetics evidence
```

## 37.4 Strongest negative evidence

Example:

```text
Broad expression across essential healthy tissues
```

## 37.5 Missing evidence

Example:

```text
No antibody tractability assessment available
```

## 37.6 Direction of effect

Example:

```text
Reduced target activity appears associated with lower disease risk.
This supports investigation of target inhibition.
```

## 37.7 Model explanation

Show:

* SHAP values
* Top positive features
* Top negative features

Also show the underlying biological source for every important feature.

---

# 38. Phase 9: Dashboard

Build a Streamlit dashboard.

## 38.1 Disease overview page

Display:

* Disease name
* Disease description
* Relevant tissues
* Candidate-target count
* Evidence-source coverage
* Data-release information

## 38.2 Target-ranking table

Columns may include:

```text
Rank
Target
Overall score
Genetics score
Biology score
Tractability score
Safety score
Clinical score
Confidence
Known drug status
```

## 38.3 Filters

Allow filtering by:

* Minimum genetics score
* Target class
* Small-molecule tractability
* Antibody tractability
* Known drug status
* Clinical phase
* Safety concern
* Missing-data threshold

## 38.4 Target evidence page

Display:

* Target summary
* Evidence radar chart
* Genetics details
* Tissue expression
* Pathway membership
* Tractability
* Safety
* Existing drugs
* Clinical evidence
* Source references
* Model explanation

## 38.5 Scenario controls

Allow users to change the prioritization weights.

Example:

```text
Research-focused
Clinical-development-focused
Novel-target-focused
Safety-first
Custom
```

---

# 39. Recommended Repository Structure

```text
disease-target-prioritization/
│
├── README.md
├── LICENSE
├── requirements.txt
├── pyproject.toml
├── .gitignore
│
├── configs/
│   ├── diseases.yaml
│   ├── features.yaml
│   ├── ranking_weights.yaml
│   └── model_config.yaml
│
├── data/
│   ├── raw/
│   ├── interim/
│   ├── processed/
│   └── external/
│
├── notebooks/
│   ├── 01_crohns_target_evidence_exploration.ipynb
│   ├── 02_open_targets_data_extraction.ipynb
│   ├── 03_feature_engineering.ipynb
│   ├── 04_weighted_baseline.ipynb
│   ├── 05_supervised_models.ipynb
│   ├── 06_ranking_evaluation.ipynb
│   └── 07_target_case_studies.ipynb
│
├── src/
│   ├── data/
│   │   ├── extract_open_targets.py
│   │   ├── extract_gtex.py
│   │   ├── extract_reactome.py
│   │   └── validate_data.py
│   │
│   ├── features/
│   │   ├── genetics.py
│   │   ├── biology.py
│   │   ├── tractability.py
│   │   ├── safety.py
│   │   └── clinical.py
│   │
│   ├── models/
│   │   ├── weighted_ranker.py
│   │   ├── logistic_model.py
│   │   ├── xgboost_model.py
│   │   ├── learning_to_rank.py
│   │   └── evaluation.py
│   │
│   ├── explainability/
│   │   ├── shap_analysis.py
│   │   └── evidence_cards.py
│   │
│   └── utils/
│       ├── logging.py
│       ├── provenance.py
│       └── config.py
│
├── app/
│   ├── streamlit_app.py
│   └── pages/
│       ├── disease_overview.py
│       ├── target_ranking.py
│       └── target_evidence.py
│
├── models/
├── reports/
├── tests/
│
├── data_dictionary.md
├── model_card.md
├── dataset_card.md
└── limitations.md
```

---

# 40. First Notebook

Create:

```text
notebooks/01_crohns_target_evidence_exploration.ipynb
```

The notebook should:

1. Retrieve the top 100 Crohn’s disease targets.
2. Store target identifiers and names.
3. Extract source-specific association scores.
4. Add known-drug information.
5. Add clinical-development phase.
6. Add tractability.
7. Add genetic constraint.
8. Add tissue-expression information where available.
9. Analyse missing values.
10. Visualize feature distributions.
11. Select 10 targets for detailed evidence profiles.
12. Identify disagreements between evidence dimensions.
13. Export a clean feature table.

Recommended output:

```text
data/processed/crohns_target_features.parquet
```

---

# 41. First Notebook Questions

The notebook should answer:

* Which targets have the strongest human-genetics evidence?
* Which targets rank highly mainly because of literature evidence?
* Which targets already have approved drugs?
* Which targets have strong genetics but weak tractability?
* Which targets are tractable but weakly supported by genetics?
* Which targets have potential safety concerns?
* Which targets have substantial missing evidence?
* Which targets are supported by multiple independent evidence sources?
* Does the Open Targets overall score favour heavily studied genes?
* How does the ranking change when genetics receives a larger weight?

---

# 42. Model Documentation

Create a `model_card.md`.

Include:

* Model purpose
* Intended users
* Intended use
* Prohibited use
* Training dataset
* Feature groups
* Labels
* Evaluation method
* Performance metrics
* Known limitations
* Data leakage controls
* Fairness considerations
* Uncertainty
* Version
* Update history

The model should not be used to:

* Make clinical decisions
* Recommend treatment to patients
* Claim that a target is clinically validated
* Replace laboratory experiments
* Replace expert review
* Automatically select investment decisions without human review

---

# 43. Dataset Documentation

Create a `dataset_card.md`.

Include:

* Dataset sources
* Release dates
* Extraction dates
* Disease coverage
* Target coverage
* Inclusion criteria
* Exclusion criteria
* Feature definitions
* Label definitions
* Missing-data strategy
* Known biases
* Ancestry limitations
* Literature bias
* Historical cutoff
* Licensing information

---

# 44. Important Scientific Limitations

## 44.1 Genetic support does not guarantee success

Human-genetics evidence may improve confidence in a target, but it does not guarantee:

* Drug efficacy
* Target tractability
* Safety
* Correct dose
* Correct patient population
* Clinical success

## 44.2 Expression does not prove causality

Differential expression may be a disease consequence rather than a cause.

## 44.3 Animal evidence may not translate

A target that works in an animal model may fail in humans.

## 44.4 Genetic perturbation differs from drug intervention

A lifelong genetic effect may differ from temporary pharmacological inhibition.

## 44.5 Existing drugs introduce popularity bias

Targets with approved drugs usually have:

* More publications
* More experiments
* Better annotations
* More pathway evidence
* More commercial attention

The model may learn research popularity rather than biological value.

## 44.6 Dataset integration introduces uncertainty

Different sources may use:

* Different disease definitions
* Different gene identifiers
* Different experimental methods
* Different populations
* Different evidence-quality standards

## 44.7 Disease heterogeneity

Crohn’s disease may include multiple biological subtypes.

A target may be useful for one patient subgroup but not another.

---

# 45. Evidence Hierarchy

A possible starting hierarchy is:

## Higher-confidence evidence

* Human rare-variant evidence
* Fine-mapped human genetic association
* Molecular-QTL colocalization
* Consistent direction-of-effect evidence
* Successful clinical intervention
* Replicated human functional evidence

## Medium-confidence evidence

* Strong pathway evidence
* Relevant tissue expression
* Human biomarker associations
* Functional assays
* Protein-interaction evidence
* Animal models

## Lower-confidence evidence when used alone

* Literature co-occurrence
* Differential expression without causal support
* Computational network proximity
* Text-mined associations
* Unreplicated experiments

This hierarchy is contextual rather than universal.

---

# 46. Eight-Week Roadmap

## Week 1: Minimum biology and disease overview

Learn:

* Genes and proteins
* Disease mechanisms
* Human genetics
* GWAS
* eQTL
* Colocalization
* Drug targets
* Tractability

Deliverables:

* Crohn’s disease one-page profile
* Biology glossary
* List of known Crohn’s disease target classes

## Week 2: Manual evidence exploration

Tasks:

* Explore Open Targets manually.
* Inspect approximately 30 targets.
* Compare established, emerging and low-ranked targets.
* Define the evidence taxonomy.

Deliverables:

* Target comparison table
* Initial feature list
* Notes on conflicting evidence

## Week 3: Data extraction

Tasks:

* Build GraphQL queries.
* Extract disease–target associations.
* Extract target properties.
* Save raw responses.
* Add data validation.

Deliverables:

* Reproducible extraction script
* Raw-data manifest
* Initial target table

## Week 4: Feature engineering

Tasks:

* Build genetics features.
* Build biology features.
* Build tractability features.
* Build safety features.
* Build clinical features.
* Document missing values.

Deliverables:

* Feature table
* Data dictionary
* Missingness report

## Week 5: Transparent ranking system

Tasks:

* Normalize features.
* Define component scores.
* Define initial weights.
* Implement user-adjustable ranking.
* Compare results with Open Targets.

Deliverables:

* Weighted ranker
* Top-target report
* Sensitivity analysis

## Week 6: Supervised ML

Tasks:

* Expand to related diseases.
* Define labels.
* Create leakage-safe splits.
* Train logistic regression.
* Train XGBoost.
* Compare performance.

Deliverables:

* Baseline model results
* Evaluation report
* Feature-importance analysis

## Week 7: Ranking and explainability

Tasks:

* Train a learning-to-rank model.
* Calculate ranking metrics.
* Add SHAP explanations.
* Produce target evidence cards.
* Analyse model errors.

Deliverables:

* Ranking model
* Explainability report
* Five detailed target case studies

## Week 8: Application and final report

Tasks:

* Build Streamlit dashboard.
* Add ranking filters.
* Add target evidence pages.
* Add data and model versioning.
* Document limitations.

Deliverables:

* Working application
* README
* Model card
* Dataset card
* Final presentation or article

---

# 47. Existing Systems to Study

## 47.1 Open Targets Platform

Study how Open Targets separates:

* Target–disease association
* Evidence sources
* Known drugs
* Tractability
* Safety
* Target properties
* Clinical precedence

Open Targets is the closest existing platform to the proposed project.

## 47.2 Open Targets Genetics and Gentropy

Study the process:

```text
GWAS association
↓
Fine-mapped locus
↓
Candidate causal variants
↓
Variant-to-gene evidence
↓
Locus-to-Gene model
↓
Candidate causal genes
```

Important concepts include:

* Fine-mapping
* Credible sets
* Colocalization
* Variant-to-gene distance
* Functional consequence
* Molecular QTLs
* Locus-to-Gene scoring

## 47.3 GTEx

Study how genetic variants affect gene expression in different human tissues.

Focus on:

* Tissue-specific expression
* eQTLs
* sQTLs
* Regulatory effects
* Tissue relevance

## 47.4 Human Protein Atlas

Study how RNA and protein expression differ across:

* Tissues
* Cell types
* Organs
* Disease states
* Subcellular locations

## 47.5 Reactome

Study:

* Pathway organization
* Gene-to-pathway mapping
* Pathway hierarchy
* Pathway enrichment
* Interactions between biological processes

## 47.6 DepMap

Study DepMap only as an example of functional target validation, particularly if the project later expands to cancer.

---

# 48. Research Papers in Recommended Reading Order

## Paper 1: The next-generation Open Targets Platform

**Purpose:** Understand the overall Open Targets system, evidence integration and target–disease associations.

Reference:

* Ochoa et al.
* *The next-generation Open Targets Platform: reimagined, redesigned, rebuilt*
* Nucleic Acids Research, 2023

Read:

* Abstract
* Platform overview
* Data integration sections
* Main figures
* Discussion

## Paper 2: Open Targets Genetics

**Purpose:** Understand how GWAS and functional-genomics evidence are connected to genes.

Reference:

* Ghoussaini et al.
* *Open Targets Genetics: systematic identification of trait-associated genes using large-scale genetics and functional genomics*
* Nucleic Acids Research, 2021

Focus on:

* Fine-mapping
* Colocalization
* Variant-to-gene mapping
* Disease-associated loci
* Genetics evidence integration

## Paper 3: Locus-to-Gene prioritization

**Purpose:** Understand how machine learning can prioritize likely causal genes at GWAS loci.

Reference:

* Mountjoy et al.
* *An open approach to systematically prioritize causal variants and genes at all published human GWAS trait-associated loci*
* Nature Genetics, 2021

Focus on:

* Locus-to-Gene features
* Gradient-boosting model
* Training labels
* Validation
* Limitations

## Paper 4: Human genetics and drug-development success

**Purpose:** Understand why human-genetics evidence is valuable for target selection.

Reference:

* Nelson et al.
* *The support of human genetic evidence for approved drug indications*
* Nature Genetics, 2015

Focus on:

* Genetic support
* Approved indications
* Clinical-development probability
* Interpretation limitations

## Paper 5: Follow-up analysis of genetically supported targets

**Purpose:** Understand a more careful analysis of the relationship between genetics and clinical success.

Reference:

* King et al.
* *Are drug targets with genetic support twice as likely to be approved? Revised estimates of the impact of genetic support for drug mechanisms on the probability of drug approval*
* PLOS Genetics, 2019

Focus on:

* Phase II success
* Phase III success
* Bias adjustment
* Comparison with earlier estimates

## Paper 6: GTEx atlas

**Purpose:** Understand tissue-specific genetic regulation.

Reference:

* GTEx Consortium
* *The GTEx Consortium atlas of genetic regulatory effects across human tissues*
* Science, 2020

Read:

* Abstract
* Overview figures
* Tissue-specific findings
* Discussion

Detailed statistical methods are optional for the first project version.

## Paper 7: Machine-learning-assisted genetic priority score

**Purpose:** Study a more advanced genetics-driven target-prioritization system.

Reference:

* Chen et al.
* *Expanding drug targets for 112 chronic diseases using a machine-learning-assisted genetic priority score*
* Nature Communications, 2024

Read after completing the transparent baseline.

Focus on:

* Feature engineering
* Genetic-priority scoring
* Disease coverage
* Model validation
* New target hypotheses

---

# 49. Recommended Online Resources

## Open Targets Platform

* Platform: `https://platform.opentargets.org`
* Documentation: `https://platform-docs.opentargets.org`
* GraphQL API documentation: `https://platform-docs.opentargets.org/data-access/graphql-api`
* Dataset documentation: `https://platform-docs.opentargets.org/data-access/datasets`

## Open Targets Genetics and Gentropy

* Gentropy documentation: `https://opentargets.org/gentropy`
* Locus-to-Gene documentation: `https://platform-docs.opentargets.org/gentropy/locus-to-gene-l2g`
* Fine-mapping documentation: `https://platform-docs.opentargets.org/gentropy/fine-mapping`
* Colocalization documentation: `https://platform-docs.opentargets.org/gentropy/colocalisation`

## Other datasets

* GWAS Catalog: `https://www.ebi.ac.uk/gwas`
* GTEx: `https://gtexportal.org`
* Human Protein Atlas: `https://www.proteinatlas.org`
* Reactome: `https://reactome.org`
* ChEMBL: `https://www.ebi.ac.uk/chembl`
* DepMap: `https://depmap.org`

---

# 50. Suggested Learning Resources by Topic

## Genes and proteins

Learn enough to understand:

* DNA to RNA to protein
* Protein function
* Genetic variants
* Gene regulation

Suggested sources:

* Khan Academy biology
* NCBI Bookshelf introductory genetics chapters
* EMBL-EBI training materials

## Human genetics and GWAS

Learn:

* SNPs
* Alleles
* Odds ratios
* GWAS
* Linkage disequilibrium
* Fine-mapping
* eQTLs
* Colocalization

Suggested sources:

* GWAS Catalog documentation
* Open Targets Genetics documentation
* EMBL-EBI GWAS training
* GTEx educational material

## Pharmacology

Learn:

* Drug targets
* Mechanism of action
* Inhibitors
* Agonists
* Antagonists
* Antibodies
* Small molecules
* Clinical phases

Suggested sources:

* Open Targets target-prioritization documentation
* ChEMBL training material
* Introductory pharmacology lectures

## Pathways

Learn:

* Signalling pathways
* Receptors
* Enzymes
* Upstream and downstream effects
* Pathway enrichment

Suggested source:

* Reactome pathway browser and educational resources

---

# 51. Project Success Criteria

The project is successful when it can:

1. Retrieve target candidates for Crohn’s disease.
2. Combine several evidence types.
3. Produce a reproducible feature table.
4. Rank targets transparently.
5. Explain every target score.
6. Identify missing and conflicting evidence.
7. Compare manual and ML rankings.
8. Recover established therapeutic targets.
9. Highlight plausible emerging targets.
10. Document uncertainty and limitations.
11. Prevent obvious temporal leakage.
12. Produce an evidence report suitable for expert review.

---

# 52. Recommended First Milestone

The first major milestone should not be a trained ML model.

It should be:

```text
A reproducible evidence table and transparent ranking of the top 100 Crohn’s disease targets
```

The corresponding notebook should be:

```text
01_crohns_target_evidence_exploration.ipynb
```

The notebook should export:

```text
crohns_target_features.parquet
crohns_target_ranking.csv
crohns_evidence_summary.md
```

---

# 53. Recommended Final Product

The final product can be described as:

> An explainable disease–target prioritization application that combines human genetics, functional genomics, tractability, safety and clinical evidence to help researchers review and rank potential therapeutic targets.

The application should provide:

```text
Disease selection
↓
Candidate-target retrieval
↓
Evidence extraction
↓
Feature generation
↓
Transparent weighted ranking
↓
Machine-learning ranking
↓
Evidence and uncertainty explanation
↓
Structured target-prioritization report
```

---

# 54. Connection to Cellvara

This project is highly relevant to Cellvara because it demonstrates how AI can support regulated scientific decision-making without pretending to replace experts.

The Cellvara-relevant capabilities demonstrated by the project include:

* Evidence aggregation
* Scientific data integration
* Explainable recommendations
* Source traceability
* Dataset versioning
* Model versioning
* Missing-evidence detection
* Contradiction detection
* Role-specific decision support
* Audit-ready reporting
* Human review of AI recommendations
* Clear separation between evidence and conclusions

The project should be positioned as:

> AI-assisted evidence review and target prioritization

rather than:

> AI automatically discovers the best drug target

---

# 55. Final Recommended Scope

## MVP

Include:

* Crohn’s disease
* Open Targets data
* Top 100 candidate targets
* Genetics evidence
* Biological evidence
* Tractability
* Safety
* Clinical precedence
* Weighted ranking
* Evidence cards
* Streamlit dashboard

## Version 2

Add:

* GTEx
* Human Protein Atlas
* Reactome
* Multiple immune diseases
* Logistic regression
* XGBoost
* SHAP
* Temporal evaluation

## Version 3

Add:

* Learning to rank
* Positive–unlabelled learning
* Direction-of-effect modelling
* Historical dataset snapshots
* Graph-based representations
* Automated evidence-report generation
* Cellvara-style audit and governance layer

---

# 56. Glossary

| Term                         | Simplified meaning                                       |
| ---------------------------- | -------------------------------------------------------- |
| Gene                         | DNA region containing biological instructions            |
| Protein                      | Functional molecule often produced from a gene           |
| Target                       | Biological molecule a therapy attempts to modify         |
| Variant                      | Difference in DNA sequence                               |
| SNP                          | Common single-base DNA variation                         |
| GWAS                         | Study searching for variants associated with a trait     |
| Locus                        | Genomic region associated with a trait                   |
| Linkage disequilibrium       | Correlation between nearby genetic variants              |
| Fine-mapping                 | Estimation of likely causal variants                     |
| Credible set                 | Group of variants likely to contain the causal variant   |
| eQTL                         | Variant associated with gene-expression level            |
| pQTL                         | Variant associated with protein abundance                |
| sQTL                         | Variant associated with RNA splicing                     |
| Colocalization               | Test of whether two associations share a causal signal   |
| Loss of function             | Reduced or absent gene/protein activity                  |
| Gain of function             | Increased or altered gene/protein activity               |
| Pathway                      | Connected sequence of biological events                  |
| Tractability                 | Whether a target can realistically be drugged            |
| Mechanism of action          | How a therapy produces its effect                        |
| Inhibitor                    | Molecule that reduces target activity                    |
| Agonist                      | Molecule that activates a receptor                       |
| Antagonist                   | Molecule that blocks receptor activation                 |
| Genetic constraint           | Intolerance of a gene to damaging variants               |
| Pleiotropy                   | One gene affecting multiple biological traits            |
| On-target toxicity           | Harm caused through the intended target                  |
| Off-target toxicity          | Harm caused through unintended targets                   |
| Clinical precedence          | Previous clinical development involving a target         |
| Target engagement            | Evidence that a therapy interacts with its target        |
| SHAP                         | Method for explaining model predictions                  |
| NDCG                         | Metric measuring ranking quality                         |
| Positive–unlabelled learning | Learning from known positives and unknown examples       |
| Data leakage                 | Training information that improperly reveals the outcome |

---

# 57. Immediate Next Actions

1. Read the minimum material on genes, proteins, GWAS, eQTLs and drug targets.
2. Create the Crohn’s disease one-page profile.
3. Explore the Open Targets Crohn’s disease page.
4. Select 30 targets for manual comparison.
5. Define the first version of the feature table.
6. Create the repository structure.
7. Build the Open Targets GraphQL extraction notebook.
8. Export the top 100 Crohn’s disease targets.
9. Create the transparent weighted-ranking baseline.
10. Document every feature and assumption before training an ML model.
