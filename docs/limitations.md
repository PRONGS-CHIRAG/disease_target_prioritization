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
