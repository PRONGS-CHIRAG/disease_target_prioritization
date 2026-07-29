"""FastAPI application (Context.md §24, §25).

Serves precomputed rankings. The MVP scores offline and loads the results;
scoring per request would make the API depend on the full feature pipeline.
"""

from __future__ import annotations

from fastapi import FastAPI

from target_prioritization import __version__
from target_prioritization.api.schemas import HealthResponse, RankingRequest, RankingResponse

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


@app.post("/rank", response_model=RankingResponse)
def rank(request: RankingRequest) -> RankingResponse:
    """Rank candidate targets for a disease."""
    raise NotImplementedError("Milestone 3 — Context.md §21")
