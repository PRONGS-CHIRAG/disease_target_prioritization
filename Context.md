# Disease–Target Prioritization System

## 1. Project Overview

This project aims to build an AI-powered disease–target prioritization system for early-stage drug discovery.

The system takes a disease as input and produces a ranked list of genes or proteins that may be promising therapeutic targets for that disease.

The project combines biological evidence from multiple public datasets, machine-learning models, graph-based information, and explainability methods.

The main goal is not to discover a drug directly. The goal is to support researchers in answering the following question:

> Given a disease, which genes or proteins should we investigate first as potential therapeutic targets?

This project is also intended as a practical learning project for understanding the biology, data, and machine-learning methods used in computational drug discovery.

---

## 2. Project Motivation

Drug discovery typically follows a broad process:

```text
Disease understanding
        ↓
Target identification
        ↓
Target validation
        ↓
Drug discovery
        ↓
Preclinical studies
        ↓
Clinical trials
```

A therapeutic target is usually a biological entity, such as a protein or gene, whose activity can potentially be modified by a drug.

Selecting the wrong target can lead to expensive failures later in drug development. Therefore, researchers need methods for combining genetic, molecular, pathway, expression, literature, and drug evidence when selecting targets.

Relevant evidence is distributed across many databases and scientific publications. This makes target selection slow, complex, and difficult to reproduce.

The proposed system will integrate these evidence sources into one structured workflow.

---

## 3. Core Objective

The core objective is to create a system that:

1. Accepts a disease as input.
2. identifies candidate genes or proteins associated with that disease.
3. Collects multiple types of biological evidence for each candidate.
4. Calculates or predicts a prioritization score.
5. Ranks the candidate targets.
6. Explains why each target received its score.
7. Provides links or references to the supporting evidence.

---

## 4. Example Input and Output

### Input

```text
Parkinson's disease
```

### Example output

| Rank | Gene  | Prioritization Score | Main Evidence                                            |
| ---: | ----- | -------------------: | -------------------------------------------------------- |
|    1 | LRRK2 |                 0.96 | Human genetics, known disease association, drug evidence |
|    2 | SNCA  |                 0.94 | Genetics, expression, pathways, literature               |
|    3 | GBA1  |                 0.91 | Genetic association, disease mechanism, literature       |
|    4 | PRKN  |                 0.87 | Rare disease genetics, mitochondrial pathway             |
|    5 | PINK1 |                 0.84 | Mitochondrial biology, genetic evidence                  |

The interface should also provide an explanation such as:

```text
LRRK2 received a high score because it has strong human genetic evidence,
multiple associations with Parkinson's disease, relevant biological pathways,
substantial scientific literature, and existing therapeutic development activity.
```

The example scores above are illustrative and must not be treated as validated scientific conclusions.

---

## 5. Intended Users

Potential users include:

* Drug discovery researchers
* Translational scientists
* Computational biologists
* Bioinformaticians
* Pharmaceutical companies
* Biotechnology startups
* Academic research laboratories
* Research and development teams
* Innovation and strategy teams in life-science companies

---

## 6. Project Scope

### Included in the initial scope

* Disease search
* Disease identifier resolution
* Candidate gene retrieval
* Biological evidence integration
* Feature engineering
* Target ranking
* Baseline machine-learning models
* Ranking evaluation
* Evidence-based explanations
* Simple interactive user interface
* Links to original data sources

### Excluded from the initial scope

* Drug molecule generation
* Protein structure prediction
* Molecular docking
* Clinical-trial outcome prediction
* Personalized patient recommendations
* Medical diagnosis
* Treatment recommendations
* Wet-lab validation
* Fully automated scientific decision-making
* Commercial-grade regulatory compliance

The system is a research-support and learning tool. It must not present predictions as medically or experimentally validated facts.

---

## 7. Important Biological Concepts

Only the biology needed to understand and build the project should be studied.

### 7.1 DNA

DNA stores biological information using sequences of four bases:

```text
A, T, C, G
```

### 7.2 Gene

A gene is a region of DNA that contains information used to create a functional product, often a protein.

### 7.3 Protein

Proteins perform many biological functions. Most traditional drugs act on proteins rather than directly on genes.

### 7.4 Disease-associated gene

A disease-associated gene is a gene for which evidence suggests some relationship with a disease.

This does not automatically mean that the gene is a good drug target.

### 7.5 Therapeutic target

A therapeutic target is usually a protein, gene, RNA molecule, or biological process that can potentially be modified to produce a beneficial therapeutic effect.

### 7.6 Gene expression

Gene expression describes how actively a gene is being used in a cell or tissue.

For example, a target for a neurological disease may be more relevant if it is expressed in the brain.

### 7.7 Pathway

A biological pathway is a group of interacting genes, proteins, or molecules involved in a biological process.

### 7.8 Genetic variant

A genetic variant is a difference in DNA sequence between individuals.

Some variants are associated with an increased or decreased risk of disease.

### 7.9 Genome-wide association study

A genome-wide association study, or GWAS, identifies genetic variants that occur more frequently in people with a particular disease or trait.

### 7.10 Protein–protein interaction

Proteins frequently interact with other proteins. These interactions can be represented as a network.

### 7.11 Druggability

Druggability describes how feasible it may be to modify a target using a drug.

A target may be biologically important but technically difficult or unsafe to target.

### 7.12 Safety

A potential target may cause harmful effects if it is essential in healthy tissues or involved in many unrelated biological processes.

---

## 8. Software Analogy

The project can be understood using a software-system analogy.

| Biology concept             | Software analogy                                |
| --------------------------- | ----------------------------------------------- |
| DNA                         | Source-code repository                          |
| Chromosome                  | Large source-code package                       |
| Gene                        | Function or module                              |
| Protein                     | Running service or executable component         |
| Genetic variant             | Code modification                               |
| Gene expression             | How frequently a service is executed            |
| Biological pathway          | Workflow involving multiple services            |
| Disease                     | System malfunction                              |
| Therapeutic target          | Component selected for intervention             |
| Drug                        | Patch, configuration change, or control command |
| Protein interaction network | Service dependency graph                        |

This analogy is simplified but useful for developing an initial mental model.

---

## 9. Machine-Learning Formulation

The problem can be formulated in several ways.

### 9.1 Ranking

Given a disease and a set of candidate targets, rank the targets from most to least promising.

This is the preferred long-term formulation.

### 9.2 Binary classification

Predict whether a disease–target pair is promising or not promising.

```text
Input: disease–target pair
Output: probability that the target is relevant
```

This is easier to implement for an initial baseline.

### 9.3 Link prediction

Represent diseases, genes, proteins, drugs, and pathways as a graph.

Predict missing disease–target links.

### 9.4 Knowledge graph completion

Construct a heterogeneous graph containing multiple entity and relationship types.

Predict new relationships such as:

```text
Disease → associated_with → Gene
Disease → treated_by → Drug
Drug → targets → Protein
Gene → participates_in → Pathway
```

### 9.5 Recommended starting formulation

Start with a tabular disease–target classification or scoring model.

Convert the scores into rankings for each disease.

After the baseline works, experiment with proper learning-to-rank and graph-based models.

---

## 10. Primary Data Sources

The exact APIs, licenses, schemas, and download procedures must be checked before implementation because biomedical databases change over time.

### 10.1 Open Targets Platform

Open Targets should be the primary data source for the MVP.

It integrates evidence connecting diseases with genes and proteins.

Potential evidence categories include:

* Genetic associations
* Somatic mutations
* Known drugs
* Literature
* Pathways
* Animal models
* Expression-related evidence
* Disease–target association scores
* Target tractability
* Safety information

Potential uses:

* Candidate target generation
* Feature extraction
* Disease–target association labels
* Drug evidence
* Target metadata
* Initial ranking baseline

Important warning:

Do not train a model to reproduce an Open Targets score using exactly the same components and then claim that the result independently validates Open Targets.

The training labels and model features must be designed carefully to avoid circularity and data leakage.

---

### 10.2 DisGeNET

DisGeNET contains disease–gene and variant–disease associations.

Potential uses:

* Independent disease–gene evidence
* Candidate gene discovery
* Cross-database validation
* Feature generation
* Positive association examples

Important considerations:

* Licensing and access conditions must be reviewed.
* Association scores may be influenced by publication frequency.
* Disease identifiers must be mapped carefully.

---

### 10.3 Gene Ontology

Gene Ontology provides structured descriptions of gene and protein functions.

Main categories include:

* Biological process
* Molecular function
* Cellular component

Potential uses:

* Functional annotations
* Disease-relevant functional similarity
* Text features
* Ontology embeddings
* Enrichment analysis

---

### 10.4 Reactome

Reactome provides curated biological pathway information.

Potential uses:

* Number of pathways associated with a gene
* Membership in disease-relevant pathways
* Pathway similarity
* Network features
* Pathway enrichment
* Explanations for predictions

---

### 10.5 STRING

STRING provides known and predicted protein–protein interactions.

Potential uses:

* Protein interaction network construction
* Node degree
* Centrality
* Neighbourhood similarity
* Distance to known disease genes
* Graph embeddings
* Graph neural networks

Important consideration:

STRING confidence scores should be retained so low-confidence and high-confidence interactions can be distinguished.

---

### 10.6 GTEx

GTEx provides gene-expression information across human tissues.

Potential uses:

* Expression in disease-relevant tissues
* Tissue specificity
* Maximum expression
* Median expression
* Expression breadth
* Safety-related proxy features

Example:

For a neurological disease, expression in brain tissues may be more informative than overall expression across all tissues.

---

### 10.7 Ensembl

Ensembl provides genomic annotations and stable gene identifiers.

Potential uses:

* Gene metadata
* Ensembl gene identifiers
* Gene coordinates
* Transcript information
* Identifier mapping

---

### 10.8 HGNC

HGNC provides standardized human gene symbols and identifiers.

Potential uses:

* Canonical gene symbols
* Alias resolution
* Identifier normalization
* Duplicate prevention

---

### 10.9 UniProt

UniProt provides protein-level annotations.

Potential uses:

* Protein function
* Protein location
* Sequence information
* Disease annotations
* Protein family
* Functional descriptions

---

### 10.10 ChEMBL

ChEMBL contains bioactivity and drug-discovery data.

Potential uses:

* Existing compounds for a target
* Target–compound relationships
* Bioactivity values
* Druggability-related features
* Target development maturity
* Drug repurposing extensions

---

### 10.11 PubMed

PubMed indexes biomedical literature.

Potential uses:

* Disease–gene publication counts
* Recent research evidence
* Paper retrieval
* Literature summaries
* Evidence citations
* Temporal trend analysis

Publication count alone must not be treated as proof of biological relevance because famous genes receive more research attention.

---

### 10.12 ClinicalTrials.gov

Potential uses:

* Targets connected with clinical-stage interventions
* Trial-stage evidence
* Drug-development status
* Historical validation
* Translational evidence

Mapping clinical trials to molecular targets may require additional processing.

---

## 11. Dataset Priority

### MVP datasets

Use a limited number of sources initially:

1. Open Targets
2. HGNC or Ensembl for gene normalization
3. Reactome
4. GTEx
5. STRING

Open Targets may already include some related evidence, but the goal is to learn how to combine independent sources.

### Post-MVP datasets

Add later:

* DisGeNET
* Gene Ontology
* UniProt
* ChEMBL
* PubMed
* ClinicalTrials.gov
* GWAS Catalog
* DepMap
* Human Protein Atlas
* OMIM, subject to access conditions
* Single-cell expression datasets
* Additional omics datasets

---

## 12. Identifier Normalization

Identifier normalization is one of the most important data-engineering tasks.

The same gene may appear as:

* HGNC symbol
* Ensembl gene ID
* Entrez Gene ID
* UniProt ID
* Older gene symbol
* Database-specific identifier

Recommended internal identifier:

```text
Ensembl Gene ID
```

Also retain:

* HGNC symbol
* Gene name
* UniProt ID where available
* Original source identifier
* Identifier mapping version

For diseases, possible identifiers include:

* MONDO
* EFO
* MeSH
* ICD
* UMLS
* Orphanet
* Disease Ontology identifiers

Recommended approach:

Use the disease identifier used by Open Targets as the main disease ID for the MVP and maintain mapping tables for other ontologies.

---

## 13. Candidate Generation

Before ranking targets, the system must generate a candidate set.

Possible candidate sources:

* All targets already connected to the disease in Open Targets
* Targets in disease-relevant pathways
* Protein-interaction neighbours of known disease genes
* Genes associated with related diseases
* Genes expressed in relevant tissues
* Targets linked through GWAS evidence

For the MVP, use:

```text
All disease-associated targets returned by Open Targets
```

This reduces complexity and allows the project to focus on feature engineering, ranking, evaluation, and explanation.

Later versions can generate novel candidates beyond known disease associations.

---

## 14. Proposed Features

Each row in the modelling dataset represents one disease–target pair.

```text
disease_id + target_id
```

### 14.1 Genetics features

Possible features:

* Genetic association score
* Number of associated variants
* Number of independent genetic studies
* GWAS evidence count
* Rare-variant evidence count
* Mendelian disease evidence
* Fine-mapping probability
* Colocalization evidence
* Distance from associated variant to gene

---

### 14.2 Literature features

Possible features:

* Number of disease–gene publications
* Number of recent publications
* Publication growth rate
* Number of review articles
* Number of clinical publications
* Literature evidence score

These features must be log-transformed or normalized because publication counts can be highly skewed.

---

### 14.3 Pathway features

Possible features:

* Number of Reactome pathways
* Number of disease-relevant pathways
* Pathway overlap with known disease genes
* Pathway enrichment score
* Functional similarity to established disease genes

---

### 14.4 Expression features

Possible features:

* Expression in disease-relevant tissue
* Maximum expression across tissues
* Median expression
* Tissue specificity
* Number of tissues with detectable expression
* Expression in potentially safety-critical tissues

---

### 14.5 Protein-network features

Possible features:

* Protein interaction degree
* Betweenness centrality
* Closeness centrality
* PageRank
* Number of interactions with known disease genes
* Minimum network distance to known disease genes
* Average interaction confidence
* Community membership
* Network embedding values

---

### 14.6 Druggability features

Possible features:

* Known small-molecule binding evidence
* Known antibody tractability
* Presence of existing compounds
* Number of active compounds
* Number of approved drugs
* Number of clinical-stage drugs
* Target family
* Membrane or extracellular localization
* Open Targets tractability categories

---

### 14.7 Safety features

Possible features:

* Expression across many healthy tissues
* Essentiality evidence
* Known safety liabilities
* Mouse knockout phenotype severity
* Number of biological processes
* Number of interacting proteins
* Known adverse target associations

Safety features should be interpreted carefully and should not be presented as definitive toxicity predictions.

---

### 14.8 Disease-context features

Possible features:

* Disease category
* Relevant tissue
* Genetic contribution to disease
* Number of known targets
* Number of approved drugs
* Disease rarity
* Disease similarity to other diseases

---

### 14.9 Evidence diversity features

Evidence diversity may be more informative than evidence quantity alone.

Possible features:

* Number of independent evidence types
* Number of independent data sources
* Genetics plus expression agreement
* Genetics plus pathway agreement
* Genetics plus drug evidence agreement
* Percentage of evidence categories present

---

## 15. Label Definition

Label design is a major scientific challenge.

Possible positive labels include:

* Targets of approved drugs for the disease
* Targets of drugs that reached late-stage clinical trials
* Expert-curated therapeutic targets
* Strongly supported targets from a trusted database
* Targets with successful genetic and pharmacological validation

Possible negative labels include:

* Random genes
* Genes with no known disease relationship
* Targets associated with failed drugs
* Targets studied but not supported
* Hard negative candidates from the same disease biology

Random genes are usually too easy to distinguish from known targets. They can produce misleadingly high model performance.

Recommended MVP label:

```text
Positive:
Targets of approved or clinically advanced drugs for the disease.

Negative:
Other disease-associated candidate targets without approved or clinically
advanced drug evidence for that disease.
```

This label is imperfect because a target without an approved drug is not necessarily a bad target.

Therefore, predictions should be described as prioritization scores rather than objective truth.

---

## 16. Avoiding Data Leakage

Data leakage is a major risk.

Examples of leakage:

* Using an Open Targets overall score as both the label and a feature
* Using approved-drug evidence as a feature when approved-drug status defines the label
* Randomly splitting rows when the same disease appears in both training and test sets
* Including future evidence when evaluating historical prediction performance
* Using database fields created from the outcome being predicted

Mitigation strategies:

* Remove label-defining evidence from the features
* Split data by disease
* Evaluate on unseen diseases
* Use temporal validation when possible
* Record dataset versions and timestamps
* Separate candidate generation data from evaluation labels
* Inspect each feature for direct or indirect label leakage

---

## 17. Baseline Models

### 17.1 Rule-based score

Create a weighted score before training an ML model.

Example:

```text
score =
    0.30 × genetics_score
  + 0.20 × pathway_score
  + 0.15 × tissue_expression_score
  + 0.15 × network_score
  + 0.10 × literature_score
  + 0.10 × druggability_score
```

This baseline is transparent and useful for validating the data pipeline.

The weights are illustrative and should not be presented as scientifically validated.

---

### 17.2 Logistic regression

Benefits:

* Simple
* Fast
* Easy to interpret
* Useful as a classification baseline
* Provides probabilities

---

### 17.3 Random forest

Benefits:

* Handles nonlinear relationships
* Works with mixed tabular features
* Provides feature importance
* Requires limited preprocessing

---

### 17.4 XGBoost

Benefits:

* Strong performance on structured data
* Handles nonlinear interactions
* Handles missing values
* Supports feature importance and SHAP
* Appropriate for a strong MVP model

---

### 17.5 LightGBM

Benefits:

* Fast
* Memory efficient
* Suitable for large datasets
* Supports ranking objectives

---

### 17.6 Learning-to-rank models

Potential models:

* LambdaMART
* XGBoost ranking
* LightGBM ranker
* Pairwise ranking models
* Listwise ranking models

These should be explored after the classification baseline works.

---

## 18. Graph-Based Extensions

### 18.1 Network features

The first graph-based extension should use manually computed graph features:

* Degree
* PageRank
* Centrality
* Neighbourhood overlap
* Distance to known disease genes

### 18.2 Graph embeddings

Possible methods:

* Node2Vec
* DeepWalk
* LINE
* Metapath2Vec

### 18.3 Graph neural networks

Possible models:

* Graph convolutional network
* Graph attention network
* GraphSAGE
* Relational graph convolutional network
* Heterogeneous graph transformer

A GNN should not be added merely because it is more advanced. It should be compared against strong tabular and ranking baselines.

---

## 19. Evaluation Strategy

### 19.1 Classification metrics

* ROC-AUC
* Precision
* Recall
* F1 score
* Precision–recall AUC
* Calibration metrics

Precision–recall AUC is particularly important when positive examples are rare.

### 19.2 Ranking metrics

Primary ranking metrics:

* Precision@5
* Precision@10
* Recall@10
* Recall@20
* Mean Average Precision
* Mean Reciprocal Rank
* NDCG@10
* NDCG@20
* Hit rate

### 19.3 Disease-level evaluation

Metrics must be calculated separately for each disease and then aggregated.

Do not calculate only one global metric across all disease–target pairs.

### 19.4 Recommended validation split

Preferred options:

1. Leave-one-disease-out validation
2. Disease-group split
3. Temporal split
4. Unseen disease test set

Avoid relying only on a random row-level split.

### 19.5 Biological validation

For selected diseases:

* Compare top predictions with known targets
* Review supporting biological pathways
* Check genetic evidence
* Check relevant tissue expression
* Inspect current drug-development activity
* Review predictions with domain experts when possible

---

## 20. Explainability

The system must explain predictions because scientific users need to understand the evidence.

### 20.1 Global explanations

Show:

* Overall feature importance
* Most influential evidence categories
* Model behaviour across diseases
* Feature distributions
* Missing-data patterns

### 20.2 Local explanations

For each target, show:

* SHAP values
* Strongest positive factors
* Strongest negative factors
* Available evidence types
* Missing evidence
* Source references

### 20.3 Example explanation

```text
Target: LRRK2
Disease: Parkinson's disease
Prioritization score: 0.92

Positive evidence:
- Strong human genetic association
- Evidence from multiple independent studies
- Expression in disease-relevant tissues
- Participation in relevant biological pathways
- Existing drug-development activity

Limitations:
- The model score does not prove that modifying the target will be safe
- Some evidence categories are influenced by publication volume
- Experimental validation is still required
```

### 20.4 LLM explanation layer

An LLM may be used to transform structured evidence into readable explanations.

The LLM must:

* Use only retrieved evidence
* Cite the relevant data source
* Clearly distinguish data from interpretation
* Avoid inventing biological claims
* Avoid presenting model predictions as established facts
* Mention missing or contradictory evidence

The LLM should not generate the prioritization score itself during the MVP.

---

## 21. Minimum Viable Product

The MVP should answer one question well:

> Given a disease, which known candidate targets appear most promising based on integrated public evidence?

### MVP workflow

```text
User enters disease
        ↓
System resolves disease identifier
        ↓
System retrieves candidate targets
        ↓
System loads precomputed target features
        ↓
Model calculates prioritization scores
        ↓
Targets are ranked
        ↓
User sees evidence and explanations
```

### MVP interface

The application should include:

#### Disease search

* Search by disease name
* Autocomplete suggestions
* Standard disease identifier
* Disease description

#### Ranked target table

Columns:

* Rank
* Gene symbol
* Gene name
* Prioritization score
* Genetics evidence
* Pathway evidence
* Expression evidence
* Network evidence
* Druggability evidence
* Evidence completeness

#### Target detail view

Show:

* Target description
* Model score
* Evidence breakdown
* SHAP explanation
* Relevant pathways
* Tissue expression
* Protein interaction summary
* Existing drug information
* Supporting literature
* Data-source links
* Limitations

#### Filters

Possible filters:

* Minimum genetics evidence
* Relevant tissue
* Druggability
* Existing drug status
* Evidence completeness
* Target family

---

## 22. MVP Acceptance Criteria

The MVP is complete when it can:

1. Accept at least ten selected diseases.
2. Retrieve or load candidate targets for each disease.
3. Create a consistent disease–target feature table.
4. Train at least one baseline model.
5. Rank targets for an unseen or held-out disease.
6. Calculate disease-level ranking metrics.
7. Show the top targets in a user interface.
8. Explain the main factors behind each prediction.
9. Link the displayed evidence to its source.
10. Clearly communicate uncertainty and limitations.
11. Reproduce the pipeline using documented scripts.
12. Track dataset and model versions.

---

## 23. Recommended MVP Disease Set

Start with diseases that have relatively rich public data.

Possible examples:

* Parkinson's disease
* Alzheimer's disease
* Type 2 diabetes
* Rheumatoid arthritis
* Crohn's disease
* Ulcerative colitis
* Breast cancer
* Non-small-cell lung cancer
* Psoriasis
* Multiple sclerosis

The final set should contain diseases from different therapeutic areas to test model generalization.

Cancer and non-cancer diseases may need separate analysis because cancer target biology and evidence structures can differ substantially.

---

## 24. Technical Stack

### Programming language

```text
Python
```

### Data processing

* Pandas
* Polars
* NumPy
* PyArrow
* DuckDB

### Machine learning

* Scikit-learn
* XGBoost
* LightGBM
* Optuna

### Explainability

* SHAP
* Permutation importance
* Partial dependence plots

### Graph processing

* NetworkX
* igraph
* PyTorch Geometric for later versions

### Data storage

MVP options:

* Parquet files
* DuckDB
* SQLite

Later options:

* PostgreSQL
* Neo4j
* Dedicated vector database where appropriate

### Backend

* FastAPI
* Pydantic

### Frontend

Recommended MVP:

* Streamlit

Possible later frontend:

* React or Next.js

### Visualization

* Plotly
* Matplotlib
* Cytoscape.js for later network visualization

### Experiment tracking

* MLflow
* Weights & Biases
* DVC for dataset versioning

### Testing

* Pytest
* Ruff
* MyPy
* Pre-commit hooks

---

## 25. Proposed System Architecture

```text
Public biological databases
        ↓
Data ingestion scripts
        ↓
Raw data storage
        ↓
Identifier normalization
        ↓
Cleaned source tables
        ↓
Disease–target feature pipeline
        ↓
Feature store
        ↓
Training pipeline
        ↓
Model registry
        ↓
Prediction API
        ↓
Streamlit interface
```

---

## 26. Proposed Repository Structure

```text
disease-target-prioritization/
│
├── context.md
├── README.md
├── pyproject.toml
├── requirements.txt
├── .env.example
├── .gitignore
│
├── configs/
│   ├── data_sources.yaml
│   ├── features.yaml
│   ├── model.yaml
│   └── diseases.yaml
│
├── data/
│   ├── raw/
│   ├── interim/
│   ├── processed/
│   └── external/
│
├── notebooks/
│   ├── 01_data_exploration.ipynb
│   ├── 02_identifier_mapping.ipynb
│   ├── 03_feature_analysis.ipynb
│   ├── 04_baseline_model.ipynb
│   └── 05_model_explanations.ipynb
│
├── src/
│   └── target_prioritization/
│       ├── __init__.py
│       │
│       ├── data/
│       │   ├── open_targets.py
│       │   ├── reactome.py
│       │   ├── string_db.py
│       │   ├── gtex.py
│       │   └── identifiers.py
│       │
│       ├── features/
│       │   ├── genetics.py
│       │   ├── expression.py
│       │   ├── pathways.py
│       │   ├── network.py
│       │   ├── druggability.py
│       │   └── build_features.py
│       │
│       ├── models/
│       │   ├── baseline.py
│       │   ├── train.py
│       │   ├── predict.py
│       │   ├── evaluate.py
│       │   └── explain.py
│       │
│       ├── services/
│       │   ├── disease_search.py
│       │   ├── target_ranking.py
│       │   └── evidence_summary.py
│       │
│       ├── api/
│       │   ├── main.py
│       │   └── schemas.py
│       │
│       └── utils/
│           ├── logging.py
│           ├── validation.py
│           └── paths.py
│
├── app/
│   └── streamlit_app.py
│
├── models/
│   ├── trained/
│   └── metadata/
│
├── reports/
│   ├── figures/
│   ├── evaluation/
│   └── model_cards/
│
├── tests/
│   ├── test_identifiers.py
│   ├── test_features.py
│   ├── test_training.py
│   └── test_api.py
│
└── scripts/
    ├── download_data.py
    ├── build_dataset.py
    ├── train_model.py
    ├── evaluate_model.py
    └── run_app.py
```

---

## 27. Initial Data Schema

A simplified modelling table may look like this:

| Column                  | Description                          |
| ----------------------- | ------------------------------------ |
| disease_id              | Standard disease identifier          |
| disease_name            | Human-readable disease name          |
| target_id               | Ensembl gene identifier              |
| gene_symbol             | HGNC gene symbol                     |
| genetics_score          | Human genetic evidence               |
| literature_score        | Literature evidence                  |
| pathway_score           | Disease-relevant pathway evidence    |
| tissue_expression_score | Expression in relevant tissues       |
| network_score           | Protein-network evidence             |
| druggability_score      | Estimated target tractability        |
| safety_score            | Safety-related evidence              |
| evidence_type_count     | Number of independent evidence types |
| missing_feature_count   | Number of missing evidence groups    |
| label                   | Training label                       |
| dataset_version         | Source-data version                  |
| extraction_date         | Date of data extraction              |

---

## 28. First Implementation Plan

### Step 1: Select diseases

Create a configuration file containing approximately ten diseases.

For each disease, store:

* Display name
* Open Targets disease ID
* Disease category
* Relevant tissue or organ
* Notes

### Step 2: Retrieve Open Targets data

For each disease:

* Retrieve associated targets
* Retrieve evidence categories
* Retrieve known drug information
* Store raw responses
* Flatten responses into tables

### Step 3: Normalize identifiers

* Map targets to Ensembl IDs
* Retain HGNC symbols
* Resolve aliases
* Remove duplicates
* Record unresolved identifiers

### Step 4: Build the first feature table

Initial features:

* Genetics evidence
* Literature evidence
* Pathway evidence
* Known-drug evidence
* Evidence-type count
* Target tractability
* Missing-evidence count

### Step 5: Create a rule-based baseline

Create a transparent weighted score and inspect whether known targets appear near the top.

### Step 6: Define labels

Create positive labels using approved or clinically advanced target–disease relationships.

Remove directly label-defining features from the model input.

### Step 7: Train baseline models

Train:

* Logistic regression
* Random forest
* XGBoost

### Step 8: Evaluate by disease

Calculate:

* Precision@10
* Recall@20
* NDCG@10
* Mean Average Precision
* Precision–recall AUC

### Step 9: Add one external dataset

Recommended first external dataset:

```text
Reactome or GTEx
```

Reactome may be easier for the first integration.

### Step 10: Add explainability

Use:

* SHAP
* Evidence breakdown
* Missing-evidence indicators
* Source references

### Step 11: Build the interface

Build a Streamlit application with:

* Disease selector
* Ranked target table
* Target detail page
* Evidence charts
* Explanation section
* Limitations section

---

## 29. Development Phases

### Phase 1: Biology foundation

Learn:

* DNA
* Genes
* Proteins
* Genetic variants
* Gene expression
* Pathways
* Protein interactions
* Therapeutic targets
* Druggability
* Target safety

Deliverable:

```text
Short biology notes and a glossary.
```

### Phase 2: Data exploration

Explore:

* Open Targets
* Disease identifiers
* Gene identifiers
* Evidence categories
* Missing values
* Score distributions
* Candidate counts per disease

Deliverable:

```text
Exploratory notebook and documented data schema.
```

### Phase 3: Data pipeline

Build:

* Data-download scripts
* Identifier normalization
* Feature extraction
* Validation checks
* Processed Parquet files

Deliverable:

```text
Reproducible disease–target dataset.
```

### Phase 4: Baseline ranking

Build:

* Rule-based score
* Logistic regression
* Random forest
* XGBoost
* Disease-level evaluation

Deliverable:

```text
Baseline ranking report.
```

### Phase 5: Evidence integration

Add:

* Reactome
* GTEx
* STRING

Deliverable:

```text
Multi-source feature table and ablation analysis.
```

### Phase 6: Explainability

Add:

* SHAP
* Evidence cards
* Supporting-source links
* Limitations
* Missing-evidence warnings

Deliverable:

```text
Target-level explanation report.
```

### Phase 7: MVP application

Build:

* Streamlit frontend
* Ranking service
* Target detail page
* Evidence visualization
* Model metadata display

Deliverable:

```text
Working end-to-end web application.
```

### Phase 8: Advanced modelling

Experiment with:

* LightGBM ranking
* LambdaMART
* Node2Vec
* Knowledge graphs
* Graph neural networks

Deliverable:

```text
Comparison between tabular, ranking, and graph models.
```

---

## 30. Additional Features After the MVP

### 30.1 Literature retrieval

For each target:

* Retrieve recent PubMed papers
* Classify papers by evidence type
* Show titles, dates, and abstracts
* Generate grounded summaries
* Highlight contradictory evidence

### 30.2 Natural-language explanations

Generate explanations for non-specialist users.

Example:

```text
This target ranks highly because human genetic studies connect it to the
disease, it is active in the relevant tissue, and it participates in pathways
related to the disease mechanism.
```

### 30.3 Interactive knowledge graph

Visualize:

* Disease
* Genes
* Proteins
* Pathways
* Drugs
* Tissues
* Publications

### 30.4 Drug repurposing

For high-ranked targets:

* Identify approved drugs acting on the target
* Show current indications
* Show development stage
* Highlight possible repurposing hypotheses

This must be presented as research information, not treatment advice.

### 30.5 Tissue-specific ranking

Allow users to prioritize targets for:

* Brain
* Liver
* Lung
* Blood
* Skin
* Intestine
* Other tissues

### 30.6 Evidence comparison

Allow users to compare two targets across:

* Genetics
* Expression
* Pathways
* Network evidence
* Druggability
* Safety
* Existing drugs

### 30.7 Temporal analysis

Train using evidence available before a historical date and test whether the model recovers targets that later entered clinical development.

This is one of the most valuable future validation methods.

### 30.8 Novel-target discovery

Expand candidate generation beyond already-associated genes by using:

* Protein-network neighbours
* Pathway membership
* Disease similarity
* Graph link prediction
* Knowledge graph embeddings

### 30.9 Multi-omics integration

Potential data types:

* Transcriptomics
* Proteomics
* Epigenomics
* Single-cell RNA sequencing
* CRISPR screening
* Metabolomics

### 30.10 User feedback

Allow researchers to:

* Save targets
* Add notes
* Mark evidence as useful
* Create target shortlists
* Export reports
* Compare model predictions with expert judgment

### 30.11 Evidence report export

Generate a downloadable report containing:

* Disease summary
* Ranked targets
* Evidence tables
* Model explanation
* Supporting references
* Limitations
* Dataset and model versions

### 30.12 Contradiction detection

Highlight cases where:

* Genetic evidence supports a target
* Expression evidence is weak
* Safety evidence is concerning
* Drug trials have failed
* Literature conclusions conflict

### 30.13 Uncertainty estimation

Add:

* Confidence intervals
* Model ensembles
* Prediction calibration
* Out-of-distribution warnings
* Evidence-completeness scores

---

## 31. Model and Product Limitations

The system must clearly communicate the following limitations:

1. A high model score does not prove that a target will produce an effective drug.
2. Database evidence may be incomplete or biased.
3. Literature-based evidence may favour well-studied genes.
4. Association does not prove causation.
5. Genetic evidence may not reveal the direction in which a target should be modified.
6. A biologically relevant target may not be druggable.
7. A druggable target may still be unsafe.
8. Negative labels are usually uncertain.
9. Clinical success depends on many factors beyond target selection.
10. Experimental and clinical validation remain necessary.
11. Predictions may change when databases are updated.
12. The tool is not intended for medical diagnosis or treatment decisions.

---

## 32. Scientific and Engineering Risks

### 32.1 Circular prediction

Risk:

The model simply recreates the database score used to construct its labels.

Mitigation:

* Separate labels from features
* Perform ablation studies
* Use external validation
* Use temporal evaluation

### 32.2 Publication bias

Risk:

Frequently studied genes receive higher scores.

Mitigation:

* Log-transform publication counts
* Use literature as one evidence type rather than the main signal
* Measure performance with and without literature features

### 32.3 Missing data

Risk:

A target appears weak because it has not been studied.

Mitigation:

* Add missingness indicators
* Display evidence completeness
* Do not interpret absence of evidence as evidence of absence

### 32.4 Disease imbalance

Risk:

Some diseases have thousands of known associations while others have few.

Mitigation:

* Evaluate by disease
* Use group-aware splits
* Consider disease-specific normalization

### 32.5 Easy negatives

Risk:

Random negative genes make model performance look unrealistically high.

Mitigation:

* Use hard negatives from biologically plausible candidates
* Evaluate ranking among disease-associated genes

### 32.6 Identifier errors

Risk:

Incorrect gene or disease mappings create false associations.

Mitigation:

* Use stable identifiers
* Validate mappings
* Track aliases
* Report unresolved records

### 32.7 Data-version drift

Risk:

Results cannot be reproduced after databases update.

Mitigation:

* Save raw data
* Record source version
* Record extraction date
* Version features and models

---

## 33. Reproducibility Requirements

Every experiment should record:

* Dataset source
* Dataset version
* Extraction date
* Disease list
* Candidate-generation method
* Feature definitions
* Label definition
* Train, validation, and test split
* Model parameters
* Random seed
* Evaluation metrics
* Code commit
* Model artifact
* Known limitations

---

## 34. Coding Principles

The codebase should follow these principles:

* Use modular Python packages rather than placing everything in notebooks.
* Use notebooks primarily for exploration and visualization.
* Keep raw data immutable.
* Separate raw, interim, and processed data.
* Validate schemas at pipeline boundaries.
* Add type hints.
* Add unit tests for identifier mapping and feature generation.
* Store configuration outside the code.
* Use structured logging.
* Avoid hard-coded file paths.
* Cache expensive API requests.
* Respect database rate limits.
* Document all derived features.
* Keep model training reproducible.
* Never silently discard failed mappings or missing values.

---

## 35. Initial Success Criteria

The project will be considered successful as a learning and portfolio project when it demonstrates:

* Understanding of the target-prioritization problem
* Integration of multiple biomedical datasets
* Reliable identifier normalization
* Prevention of obvious data leakage
* Strong tabular baselines
* Disease-level ranking evaluation
* Useful target explanations
* A working end-to-end application
* Transparent limitations
* Reproducible code and data processing

The project does not need to outperform production systems used by pharmaceutical companies.

The focus is on building a scientifically thoughtful and technically complete prototype.

---

## 36. Recommended First Milestone

The first milestone should be intentionally small.

### Milestone objective

Build a non-ML target ranking prototype for one disease using Open Targets data.

### Disease

```text
Parkinson's disease
```

### Tasks

1. Resolve the disease identifier.
2. Retrieve associated targets.
3. Extract available evidence scores.
4. Normalize target identifiers.
5. Create a candidate-target table.
6. Calculate a transparent weighted score.
7. Rank the top 20 targets.
8. Visualize the evidence breakdown.
9. Manually inspect the top 10 targets.
10. Document the limitations.

### Deliverables

```text
data/processed/parkinsons_targets.parquet
notebooks/01_parkinsons_open_targets.ipynb
reports/figures/parkinsons_top_targets.png
reports/parkinsons_baseline_report.md
```

No complex machine-learning model should be added before this pipeline works correctly.

---

## 37. Recommended Second Milestone

### Milestone objective

Create a multi-disease modelling dataset and train the first ML baseline.

### Tasks

1. Expand to approximately ten diseases.
2. Build a unified disease–target table.
3. Define positive and hard-negative labels.
4. Remove label-leaking features.
5. Split by disease.
6. Train logistic regression.
7. Train XGBoost.
8. Calculate ranking metrics.
9. Add SHAP explanations.
10. Compare the ML models with the rule-based baseline.

### Deliverables

```text
data/processed/disease_target_features.parquet
models/trained/xgboost_baseline.json
reports/evaluation/baseline_metrics.json
reports/evaluation/baseline_report.md
```

---

## 38. Long-Term Vision

The long-term system could become a decision-support platform that combines:

* Human genetics
* Multi-omics data
* Biological pathways
* Protein networks
* Existing drugs
* Clinical trials
* Scientific literature
* Target safety
* Target tractability
* Expert feedback

The platform could help research teams:

* Generate target shortlists
* Compare biological hypotheses
* Identify gaps in evidence
* Discover repurposing opportunities
* Produce transparent evidence reports
* Track target decisions over time

However, all advanced functionality should be built only after the initial data pipeline, baseline model, evaluation methodology, and explanation system are reliable.

---

## 39. Current Project Decision

The current implementation strategy is:

```text
Start with public structured data.
Build a transparent tabular baseline.
Evaluate ranking at the disease level.
Add explainability.
Build a simple Streamlit interface.
Add graph and LLM features only after the baseline is reliable.
```

The immediate next task is:

> Build the first Parkinson's disease target-ranking dataset using Open Targets and create a transparent rule-based baseline.
