"""FastAPI application (Context.md §24, §25).

Serves precomputed rankings. The MVP scores offline and loads the results;
scoring per request would make the API depend on the full feature pipeline.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException

from target_prioritization import __version__
from target_prioritization.api.schemas import (
    EvidenceBreakdown,
    HealthResponse,
    RankedTargetResponse,
    RankingRequest,
    RankingResponse,
)
from target_prioritization.config import load_diseases
from target_prioritization.data.open_targets import release_tag
from target_prioritization.services.target_ranking import (
    RankedTarget,
    RankingFilters,
    rank_for_disease,
)

app = FastAPI(
    title="Disease-Target Prioritization API",
    version=__version__,
    description=(
        "Ranks candidate therapeutic targets for a disease from integrated public "
        "evidence. Research-support tool: scores are prioritization hypotheses, not "
        "validated findings, and must not inform medical decisions (Context.md §31)."
    ),
)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Liveness check."""
    return HealthResponse(status="ok")


def _disease_name(disease_id: str) -> str:
    """Display name for *disease_id*, falling back to the ID itself.

    A missing name isn't a 404 on its own — ``rank_for_disease`` below is
    what actually validates *disease_id* against the built feature table;
    this is purely cosmetic for the response body.
    """
    for disease in load_diseases().resolved:
        if disease.efo_id == disease_id:
            return disease.name
    return disease_id


def _to_response(target: RankedTarget) -> RankedTargetResponse:
    """``RankedTarget`` (service layer) -> ``RankedTargetResponse`` (API).

    ``EvidenceBreakdown`` anticipates all six §17.1 dimensions plus safety;
    ``RankedTarget.evidence`` only carries the milestone-1 five
    (``_DISPLAY_DIMENSIONS`` in services/target_ranking.py) until Milestone 4
    wires up pathways/expression/network, so those three (and safety, which
    the score deliberately has no weight for) are reported as null rather
    than omitted from the contract.
    """
    evidence = target.evidence
    return RankedTargetResponse(
        rank=target.rank,
        target_id=target.target_id,
        gene_symbol=target.gene_symbol or target.target_id,
        gene_name=target.gene_name or "",
        score=target.score,
        evidence=EvidenceBreakdown(
            genetics=evidence.get("genetics"),
            literature=evidence.get("literature"),
            pathways=None,
            expression=None,
            network=None,
            druggability=evidence.get("druggability"),
            safety=None,
        ),
        evidence_completeness=target.app_evidence_completeness or 0.0,
        missing_evidence=target.missing_evidence,
        source_links=target.source_links,
    )


@app.post("/rank", response_model=RankingResponse)
def rank(request: RankingRequest) -> RankingResponse:
    """Rank candidate targets for a disease.

    A thin wrapper over :func:`~target_prioritization.services.target_ranking.rank_for_disease`
    — the same scoring path the Streamlit app uses (milestone3_plan.md §2:
    "services are built as a standalone layer so the API stays a ~30-line
    addition later").
    """
    filters = RankingFilters(
        min_genetics_evidence=request.min_genetics_evidence,
        require_druggable=request.require_druggable,
    )
    try:
        ranked = rank_for_disease(request.disease_id, filters=filters, top_n=request.top_n)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return RankingResponse(
        disease_id=request.disease_id,
        disease_name=_disease_name(request.disease_id),
        targets=[_to_response(target) for target in ranked],
        dataset_version=release_tag(),
        model_version=__version__,
    )
