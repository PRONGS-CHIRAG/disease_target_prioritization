"""API request/response models (Context.md §24: FastAPI + Pydantic;
milestone5_plan.md §4.1).

Every field here mirrors a dataclass in ``services/`` or a constant in
``presentation.py`` — this module adds no new data, only an HTTP-shaped view
of what those already compute. Where a field is display-only (a label, a
denominator, a not-buildable reason) it exists so the frontend never
hardcodes a copy that can drift from ``configs/model.yaml``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

__all__ = [
    "DiseaseDetailResponse",
    "DiseaseSummaryResponse",
    "EvidenceBreakdown",
    "EvidenceCategoryStatus",
    "EvidenceItemResponse",
    "EvidenceRequest",
    "EvidenceResponse",
    "HealthResponse",
    "MetaResponse",
    "RankedTargetResponse",
    "RankingFiltersRequest",
    "RankingRequest",
    "RankingResponse",
    "ScenarioPresetResponse",
]

# Returned with every response that carries scores or evidence, never tucked
# away in docs only (Context.md §31, invariant 8 — milestone5_plan.md §3).
_LIMITATIONS_FIELD = Field(
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


# ---------------------------------------------------------------------------
# /api/meta
# ---------------------------------------------------------------------------


class ScenarioPresetResponse(BaseModel):
    slug: str
    label: str
    weights: dict[str, float]


class MetaResponse(BaseModel):
    """Every UI-facing constant the frontend needs at boot, fetched once
    (milestone5_plan.md §4.1) so no scenario preset, dimension label, or
    limitations string is hand-duplicated in TypeScript."""

    scenario_presets: list[ScenarioPresetResponse]
    safety_first: ScenarioPresetResponse
    custom_slug: str
    custom_label: str
    dimension_keys: list[str]
    dimension_labels: dict[str, str]
    evidence_categories: list[str]
    unavailable_evidence_categories: dict[str, str]
    not_buildable: dict[str, str]
    default_weights: dict[str, float]
    limitations: list[str] = _LIMITATIONS_FIELD


# ---------------------------------------------------------------------------
# /api/diseases
# ---------------------------------------------------------------------------


class DiseaseSummaryResponse(BaseModel):
    disease_id: str
    name: str
    description: str | None = None
    therapeutic_areas: list[str] = Field(default_factory=list)
    n_associated_targets: int | None = None


class EvidenceCategoryStatus(BaseModel):
    category: str
    built: bool
    note: str = ""


class DiseaseDetailResponse(DiseaseSummaryResponse):
    evidence_categories_built: int
    evidence_categories_total: int
    evidence_coverage: list[EvidenceCategoryStatus]
    dataset_version: str | None = None
    extraction_date: str | None = None


# ---------------------------------------------------------------------------
# /api/rank
# ---------------------------------------------------------------------------


class RankingFiltersRequest(BaseModel):
    """Mirrors ``services.target_ranking.RankingFilters`` field for field —
    including ``target_family``, which stays unbuildable (invariant 6): the
    field exists so a client that sets it gets a 400 with the reason,
    rather than the request silently omitting a filter the caller believes
    is applied.
    """

    min_genetics_evidence: float | None = Field(default=None, ge=0, le=1)
    require_druggable: bool = False
    relevant_tissue: bool = Field(
        default=False,
        description="Detectable expression in the disease's configured tissues — a switch, "
        "not a free-text tissue (RankingFilters.relevant_tissue's docstring).",
    )
    min_evidence_completeness: float | None = Field(default=None, ge=0, le=1)
    exclude_safety_concerns: bool = False
    target_family: str | None = Field(
        default=None,
        description="Not buildable in this release (needs target.targetClass). Setting this "
        "returns HTTP 400 rather than silently ignoring it.",
    )


class RankingRequest(BaseModel):
    disease_id: str = Field(description="Open Targets disease ID, e.g. MONDO_0005180")
    top_n: int = Field(default=50, ge=1, le=500)
    weights: dict[str, float] | None = Field(
        default=None,
        description="Scenario weights (Context.md §38.5). Any positive combination — "
        "normalized server-side; the normalized values used are echoed back in "
        "`weights_used`. Defaults to configs/model.yaml's milestone_1_weights.",
    )
    sort_by: Literal["weighted_baseline", "xgboost_held_out"] = "weighted_baseline"
    filters: RankingFiltersRequest = Field(default_factory=RankingFiltersRequest)


class EvidenceBreakdown(BaseModel):
    """All five of WeightedBaseline's scored dimensions, plus the three
    categories that are computed (Milestone 4) but never enter the
    weighted-baseline formula the ranking table's default scenario controls
    are restricted to (presentation.DIMENSION_KEYS) — those three, and
    safety (no scored weight per Context.md §14.7), report null here by
    design, not by omission. `evidence_completeness` on the parent response
    is what actually reflects all six built categories; the evidence-detail
    endpoint (`/api/evidence`) is where a target's pathway/expression/
    network standing is surfaced (its `missing` list) and where safety
    appears as a contradicting-evidence flag.
    """

    genetics: float | None = None
    evidence_diversity: float | None = None
    functional: float | None = None
    literature: float | None = None
    druggability: float | None = None
    pathways: float | None = None
    expression: float | None = None
    network: float | None = None
    safety: float | None = None


class RankedTargetResponse(BaseModel):
    rank: int = Field(description="Position among ALL candidates for this disease, before "
                       "filters truncate the list — gaps are expected (invariant 9).")
    target_id: str
    gene_symbol: str
    gene_name: str
    score: float = Field(description="The active sort's score (NOT a probability of success)")
    sort_by: Literal["weighted_baseline", "xgboost_held_out"]
    weighted_baseline_score: float
    xgboost_score_held_out: float | None = None
    evidence: EvidenceBreakdown
    evidence_completeness: float = Field(
        description="Fraction (0-1) of the six built evidence categories present for this "
        "target. Never render as a bare fraction (invariant 2) — use "
        "evidence_completeness_count / evidence_completeness_total."
    )
    evidence_completeness_count: int
    evidence_completeness_total: int
    missing_evidence: list[str] = Field(default_factory=list)
    n_other_diseases_positive: int | None = None
    source_links: dict[str, str] = Field(default_factory=dict)


class RankingResponse(BaseModel):
    disease_id: str
    disease_name: str
    sort_by: Literal["weighted_baseline", "xgboost_held_out"]
    weights_used: dict[str, float] = Field(
        description="Normalized weights actually applied — display THESE next to the score, "
        "never the raw slider values a client may have sent."
    )
    targets: list[RankedTargetResponse]
    total_candidates: int = Field(
        description="Every candidate target for this disease before any filter or top_n "
        "truncation — the denominator for a partial export label (milestone5_plan.md §2.7)."
    )
    dataset_version: str
    model_version: str
    limitations: list[str] = _LIMITATIONS_FIELD


# ---------------------------------------------------------------------------
# /api/evidence
# ---------------------------------------------------------------------------


class EvidenceRequest(BaseModel):
    disease_id: str
    target_id: str
    weights: dict[str, float] | None = None


class EvidenceItemResponse(BaseModel):
    category: str
    value: float | str | None = None
    source: str
    source_url: str | None = None
    dataset_version: str | None = None


class EvidenceResponse(BaseModel):
    disease_id: str
    target_id: str
    gene_symbol: str
    gene_name: str
    score: float = Field(description="Weighted-baseline score — the evidence card's score is "
                          "always this one, never the XGBoost score (services.evidence_summary "
                          "module docstring); XGBoost's contribution is surfaced separately, "
                          "tagged by source, in `supporting`/`contradicting`.")
    weights_used: dict[str, float]
    contributions: dict[str, float] = Field(
        description="contrib__<dimension> — sums exactly to `score` (WeightedBaseline.explain; "
        "no approximation). The evidence-breakdown bar chart's data."
    )
    dimension_values: dict[str, float | None] = Field(
        description="Raw dim__<dimension> values, nulls preserved (invariant 1) — the evidence "
        "radar's data. A null here means no evidence was recorded, not a zero score."
    )
    supporting: list[EvidenceItemResponse] = Field(default_factory=list)
    contradicting: list[EvidenceItemResponse] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    xgboost_score_held_out: float | None = None
    n_other_diseases_positive: int | None = None
    rank: int | None = Field(default=None, description="This target's rank among every "
                              "candidate for the disease under `weights_used`.")
    total_candidates: int | None = None
    label_n_drugs: int | None = Field(
        default=None,
        description="Existing-drug/clinical-stage evidence the training label is built from "
        "(Context.md §15) — for context only, never a ranking input (invariant 3).",
    )
    label_drug_names: str | None = None
    label_max_clinical_stage: int | None = None
    not_buildable: dict[str, str] = Field(
        default_factory=dict,
        description="Items Context.md §21/§37/§38.4 ask for that nothing in the pipeline "
        "computes yet (direction of effect, confidence level) — render as a labelled "
        "placeholder, never a blank or a zero.",
    )
    source_links: dict[str, str] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)
