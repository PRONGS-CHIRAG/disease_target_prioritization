# Limitations

From Context.md §31 and Project_info.md §44. These are not boilerplate: several
of them determine how the output must be presented, and the UI is required to
surface them (Context.md §21, §31.12).

## What a score does and does not mean

1. **A high score does not prove a target will produce an effective drug.** The
   score ranks candidates by weight of public evidence. Clinical success depends
   on many factors outside this data.
2. **Association is not causation.** A gene associated with a disease may be a
   consequence of it, or share a cause with it.
3. **Genetic evidence rarely gives direction.** Knowing a gene matters does not
   say whether to inhibit or activate it — and the wrong direction can be harmful.
4. **A biologically important target may not be druggable**, and a druggable
   target may still be unsafe.

## What the data does and does not cover

5. **Absence of evidence is not evidence of absence.** A low score often means
   "understudied", not "unpromising". Read the evidence-completeness indicator
   alongside every score (Context.md §32.3).
6. **Literature evidence rewards attention, not importance.** Famous genes
   accumulate publications, so literature features are log-transformed, treated
   as one evidence type among several, and included in an ablation that measures
   how much of the performance they carry (Context.md §32.2).
7. **Negative labels are uncertain.** A target without an approved drug is not
   established to be a bad target; it may be early, or simply never tried.
8. **Databases are incomplete and biased** toward well-studied biology,
   well-studied populations, and diseases with commercial interest.
9. **Predictions change when databases update.** Results are reproducible only
   against a pinned release — currently Open Targets 26.06. Reactome and HGNC
   publish unversioned "current" URLs, so for those the fetch date in the
   manifest is the only version anchor.

## Method limitations

10. **The training label is a proxy.** "Has an approved or clinically-advanced
    drug" measures what the industry has already pursued, which encodes past
    commercial and scientific priorities as much as biological merit.
11. **Circularity is a live risk.** Open Targets aggregates the same evidence the
    features come from. The denylist in `configs/features.yaml` addresses the
    direct path; the ablations in `configs/model.yaml` are there to test whether
    subtler versions remain.
12. **Ten diseases is a small evaluation set.** Leave-one-disease-out over ten
    diseases gives noisy estimates, and two of the ten are cancers whose evidence
    structure differs substantially from the rest (Context.md §23).
13. **Cancer and non-cancer results should be read separately.** Somatic mutation
    evidence dominates cancer associations and has no equivalent elsewhere.

## Scope

14. **Not a medical device.** Not for diagnosis, treatment selection, or any
    patient-level decision.
15. **No wet-lab or clinical validation** has been performed on any output here.
16. **This is a learning and portfolio project**, not a production system, and is
    not intended to match the tools used inside pharmaceutical companies.

## Interface limitations (Milestone 3/4)

17. **Four columns Context.md §14.3/§14.5 describe are still not built** —
    `path__overlap_with_known_disease_genes`, `path__n_disease_relevant_pathways`,
    `net__n_disease_gene_neighbours`, `net__min_distance_to_disease_gene` all
    need a per-disease "known disease genes" seed set this repo has no
    leakage-reviewed definition for (milestone4_plan.md §2.1). The other
    eleven pathway/expression/network columns Context.md §21/§38 ask for are
    built as of Milestone 4 (Reactome, GTEx, STRING).
18. **The two scores shown side by side disagree structurally, and the gap
    widened at Milestone 4, not narrowed.** The default (weighted baseline)
    is fully transparent but the weaker ranker (NDCG@10 0.288); the
    alternative (held-out XGBoost) is stronger in aggregate (0.901, up from
    0.696 at Milestone 2) but its novel-only score — the part that isolates
    disease-specific signal from cross-disease popularity — fell from 0.009
    to **exactly 0.000** once Reactome/GTEx/STRING features were added.
    `net__weighted_degree` (STRING interaction count) is now this model's
    single highest-SHAP feature (milestone2.md §1, docs/model_card.md). The
    app shows both, with the caveat attached to the XGBoost view rather than
    picked for the user.
19. **Target-family filtering, which the interface specification asks for,
    is not available.** It needs `target.targetClass`, unrelated to
    Reactome/GTEx/STRING. Rather than silently ignoring a filter a user
    believes is being applied, the ranking service raises if it is set.
    (Relevant-tissue filtering *is* available as of Milestone 4.)
20. **GTEx v10 has no synovial-tissue data at all**, discovered while
    building the relevant-tissue expression feature (expression.py). Every
    other configured disease's relevant tissues resolve; rheumatoid
    arthritis's `expr__relevant_tissue_tpm` is computed from its other two
    configured tissues (blood, spleen) with the `synovium` miss logged
    explicitly, not silently dropped or treated as zero expression.
21. **`net__degree`/`net__pagerank`/`net__betweenness` are confounded with
    study effort**, the same publication-bias risk literature features
    already carry (item 6) — a well-studied protein accumulates recorded
    STRING interactions for the same reason it accumulates papers. Milestone
    4's own measurement (item 18) shows this is not a hypothetical concern.
22. **`net__betweenness` is a sampled estimate** (500 of ~19,700 graph nodes,
    seeded), not exact — exact betweenness centrality on a graph this size is
    computationally infeasible. Reproducible for a fixed seed, not exact.
23. **`dim__pathways`/`dim__network`/`dim__expression` (the columns that make
    `configs/model.yaml`'s `baseline_weights` computable) are illustrative
    normalizations**, same caveat as the weights themselves — a saturating
    transform and percentile ranks, not validated scales.
