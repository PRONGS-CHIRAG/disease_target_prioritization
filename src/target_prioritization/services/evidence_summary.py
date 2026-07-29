"""Evidence cards and grounded natural-language summaries (Context.md §20.4).

Context.md §20.4 constrains the optional LLM layer tightly. It may only:

* use retrieved evidence, never its own knowledge
* cite the source of each claim
* separate data from interpretation
* mention missing and contradictory evidence

and it must **not** generate the prioritization score itself during the MVP.
The score comes from the model; the LLM only renders the structured evidence
into prose. Anything else reintroduces exactly the unverifiable claims this
system exists to avoid.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["EvidenceCard", "EvidenceItem", "build_evidence_card"]


@dataclass(slots=True)
class EvidenceItem:
    """One piece of evidence with its provenance."""

    category: str
    value: float | str | None
    source: str
    source_url: str | None = None
    # Records the release the value came from, so a card stays interpretable
    # after the databases move on (Context.md §32.7).
    dataset_version: str | None = None


@dataclass(slots=True)
class EvidenceCard:
    """The full evidence picture for one disease-target pair (§21)."""

    disease_id: str
    target_id: str
    gene_symbol: str
    score: float
    supporting: list[EvidenceItem] = field(default_factory=list)
    contradicting: list[EvidenceItem] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)


def build_evidence_card(disease_id: str, target_id: str) -> EvidenceCard:
    """Assemble the evidence card for one disease-target pair.

    Populates ``contradicting`` and ``missing`` as seriously as ``supporting``:
    Context.md §30.12 asks for contradiction detection, and a card that lists
    only confirming evidence is a worse decision aid than no card.
    """
    raise NotImplementedError("Milestone 3 — Context.md §21")
