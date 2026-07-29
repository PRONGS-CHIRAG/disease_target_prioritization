"""API request/response models (Context.md §24: FastAPI + Pydantic)."""

from __future__ import annotations

from pydantic import BaseModel, Field

__all__ = ["EvidenceBreakdown", "HealthResponse", "RankedTargetResponse", "RankingRequest"]


class RankingRequest(BaseModel):
    disease_id: str = Field(description="Open Targets disease ID, e.g. MONDO_0005180")
    top_n: int = Field(default=50, ge=1, le=500)
    min_genetics_evidence: float | None = Field(default=None, ge=0, le=1)
    require_druggable: bool = False


class EvidenceBreakdown(BaseModel):
    genetics: float | None = None
    literature: float | None = None
    pathways: float | None = None
    expression: float | None = None
    network: float | None = None
    druggability: float | None = None
    safety: float | None = None


class RankedTargetResponse(BaseModel):
    rank: int
    target_id: str
    gene_symbol: str
    gene_name: str
    score: float = Field(description="Prioritization score, NOT a probability of success")
    evidence: EvidenceBreakdown
    evidence_completeness: float = Field(
        description="Fraction of evidence categories with data. Context.md §32.3 — "
        "a low value means understudied, not unpromising."
    )
    missing_evidence: list[str] = Field(default_factory=list)
    source_links: dict[str, str] = Field(default_factory=dict)


class RankingResponse(BaseModel):
    disease_id: str
    disease_name: str
    targets: list[RankedTargetResponse]
    dataset_version: str
    model_version: str
    # Returned with every response, not tucked away in docs (Context.md §31).
    limitations: list[str] = Field(
        default_factory=lambda: [
            "A high score does not prove that a target will yield an effective drug.",
            "Database evidence may be incomplete or biased toward well-studied genes.",
            "Association does not prove causation.",
            "Absence of evidence is not evidence of absence.",
            "Not intended for medical diagnosis or treatment decisions.",
        ]
    )


class HealthResponse(BaseModel):
    status: str
    dataset_version: str | None = None
    model_loaded: bool = False
