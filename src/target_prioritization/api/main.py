"""FastAPI application (Context.md §24, §25; milestone5_plan.md).

Serves precomputed rankings and live-computed (but cheap: a weighted sum
and, for the evidence endpoint, one live SHAP call) evidence. This is the
adapter layer milestone5_plan.md §1 completes to reach parity with the
Streamlit app — every endpoint here is a thin wrapper over
``services/target_ranking.py`` or ``services/evidence_summary.py``; no
scoring logic lives in this module.

Routes are split ``/api/*`` (this module) vs. everything else, which the
built frontend's static export owns (milestone5_plan.md §2.3) — mounted
last, and only if the export exists, so the API still runs standalone in
dev before ``frontend/`` is built.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import polars as pl
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from target_prioritization import __version__
from target_prioritization.api.cache import cached_app_data, cached_features
from target_prioritization.api.schemas import (
    DiseaseDetailResponse,
    DiseaseSummaryResponse,
    EvidenceBreakdown,
    EvidenceCategoryStatus,
    EvidenceDetailResponse,
    EvidenceItemResponse,
    EvidenceRequest,
    EvidenceResponse,
    HealthResponse,
    InteractionPartnerResponse,
    LiteratureSummaryResponse,
    MetaResponse,
    PathwayGroupResponse,
    PathwayRefResponse,
    RankedTargetResponse,
    RankingRequest,
    RankingResponse,
    ScenarioPresetResponse,
    TissueValueResponse,
)
from target_prioritization.config import load_diseases, load_model_config
from target_prioritization.data.open_targets import release_tag
from target_prioritization.features.genetics import DIMENSION_PREFIX
from target_prioritization.milestone2 import FOLD_MODELS_DIRNAME, fold_model_filename
from target_prioritization.models.baseline import CONTRIBUTION_PREFIX, WeightedBaseline
from target_prioritization.models.train import load_fitted_xgboost
from target_prioritization.presentation import (
    CUSTOM_LABEL,
    CUSTOM_SLUG,
    DIMENSION_KEYS,
    DIMENSION_LABELS,
    NOT_BUILDABLE,
    SAFETY_FIRST_LABEL,
    SAFETY_FIRST_SLUG,
    SCENARIO_PRESETS,
)
from target_prioritization.services.disease_search import DiseaseSearchResult, search_diseases
from target_prioritization.services.evidence_detail import build_evidence_detail
from target_prioritization.services.evidence_summary import EvidenceItem, build_evidence_card
from target_prioritization.services.target_ranking import (
    APP_EVIDENCE_CATEGORIES,
    UNAVAILABLE_EVIDENCE_CATEGORIES,
    RankedTarget,
    RankingFilters,
    normalize_weights,
    rank_for_disease,
)
from target_prioritization.utils.logging import get_logger
from target_prioritization.utils.paths import PROJECT_ROOT, TRAINED_MODELS

log = get_logger(__name__)

# The Next.js static export (milestone5_plan.md §2.2, §4.5) — absent in a
# dev checkout before `make frontend-build` runs, present in the Docker
# image built by Phase 7's Dockerfile.
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "out"

# The single fixed weight profile the container health check needs to be a
# real signal (Context.md §33's baseline reproducibility, not the app
# itself): xgboost_baseline.json is the in-sample model saved once by
# scripts/train_model.py, distinct from the ten per-disease held-out fold
# models `/api/rank`/`/api/evidence` actually serve.
_BASELINE_MODEL_PATH = TRAINED_MODELS / "xgboost_baseline.json"


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Warm every cache once at startup (milestone5_plan.md §4.2) rather
    than on the first request that happens to need it — startup cost moves
    off the request path, and the container health check's grace period
    should be set to at least this long."""
    try:
        cached_features()
        cached_app_data()
    except FileNotFoundError as exc:
        log.warning("startup_cache_warm_skipped_features_or_app_data", error=str(exc))

    for disease in load_diseases().resolved:
        fold_path = TRAINED_MODELS / FOLD_MODELS_DIRNAME / fold_model_filename(disease.key)
        try:
            load_fitted_xgboost(fold_path)
        except Exception as exc:
            # A single unreadable fold model (missing file, truncated
            # .meta.json sidecar, corrupt booster)
            # must not prevent the API from serving weighted-baseline
            # rankings for every OTHER disease; services.evidence_summary's
            # own `_xgboost_held_out_items` already degrades the same way
            # per-request (`except (KeyError, FileNotFoundError)`, "the
            # weighted-baseline half of the card is still useful on its
            # own") — this mirrors that at startup, just broadened to catch
            # more than FileNotFoundError since the sidecar can fail to
            # parse instead of failing to exist.
            log.warning("startup_cache_warm_skipped_fold_model", disease_key=disease.key, error=str(exc))
    yield


app = FastAPI(
    title="Disease-Target Prioritization API",
    version=__version__,
    description=(
        "Ranks candidate therapeutic targets for a disease from integrated public "
        "evidence. Research-support tool: scores are prioritization hypotheses, not "
        "validated findings, and must not inform medical decisions (Context.md §31)."
    ),
    lifespan=lifespan,
)

# Off by default — same-origin in both dev (Next's rewrite proxy) and prod
# (single container, static export served by this app). Only needed by
# someone running `next dev` and `uvicorn` on two ports with no proxy
# (milestone5_plan.md §4.5); set DTP_CORS_ORIGINS to a comma-separated list
# to enable it.
_cors_origins = [o for o in os.environ.get("DTP_CORS_ORIGINS", "").split(",") if o]
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )


def _model_loaded() -> bool:
    return _BASELINE_MODEL_PATH.exists()


def _build_health() -> HealthResponse:
    return HealthResponse(status="ok", dataset_version=release_tag(), model_loaded=_model_loaded())


@app.get("/health", response_model=HealthResponse)
def root_health() -> HealthResponse:
    """Bare-root liveness check for container orchestrators
    (milestone5_plan.md §2.3) — identical to ``GET /api/health``."""
    return _build_health()


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return _build_health()


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


def _to_disease_summary(result: DiseaseSearchResult) -> DiseaseSummaryResponse:
    return DiseaseSummaryResponse(
        disease_id=result.disease_id,
        name=result.name,
        description=result.description,
        therapeutic_areas=result.therapeutic_areas,
        n_associated_targets=result.n_associated_targets,
    )


@app.get("/api/meta", response_model=MetaResponse)
def meta() -> MetaResponse:
    """Every scenario preset, dimension label and limitations string the
    frontend needs — fetched once at boot so none of it is hand-duplicated
    in TypeScript (milestone5_plan.md §2.6)."""
    model_config = load_model_config()
    default_weights = dict(model_config.milestone_1_weights)
    return MetaResponse(
        scenario_presets=[
            ScenarioPresetResponse(slug=p.slug, label=p.label, weights=p.weights) for p in SCENARIO_PRESETS
        ],
        safety_first=ScenarioPresetResponse(
            slug=SAFETY_FIRST_SLUG, label=SAFETY_FIRST_LABEL, weights=default_weights
        ),
        custom_slug=CUSTOM_SLUG,
        custom_label=CUSTOM_LABEL,
        dimension_keys=DIMENSION_KEYS,
        dimension_labels=DIMENSION_LABELS,
        evidence_categories=APP_EVIDENCE_CATEGORIES,
        unavailable_evidence_categories=UNAVAILABLE_EVIDENCE_CATEGORIES,
        not_buildable=NOT_BUILDABLE,
        default_weights=default_weights,
    )


@app.get("/api/diseases", response_model=list[DiseaseSummaryResponse])
def list_diseases() -> list[DiseaseSummaryResponse]:
    return [_to_disease_summary(r) for r in search_diseases("")]


@app.get("/api/diseases/search", response_model=list[DiseaseSummaryResponse])
def search_diseases_endpoint(q: str = "") -> list[DiseaseSummaryResponse]:
    return [_to_disease_summary(r) for r in search_diseases(q)]


@app.get("/api/diseases/{disease_id}", response_model=DiseaseDetailResponse)
def disease_detail(disease_id: str) -> DiseaseDetailResponse:
    match = next((r for r in search_diseases("") if r.disease_id == disease_id), None)
    if match is None:
        raise HTTPException(
            status_code=404,
            detail=f"{disease_id} is not in the precomputed set of ten configured diseases.",
        )

    evidence_coverage = [
        EvidenceCategoryStatus(
            category=category,
            built=category not in UNAVAILABLE_EVIDENCE_CATEGORIES,
            note=UNAVAILABLE_EVIDENCE_CATEGORIES.get(category, ""),
        )
        for category in APP_EVIDENCE_CATEGORIES
    ]
    try:
        cached_features()
        built_count = len(APP_EVIDENCE_CATEGORIES) - len(UNAVAILABLE_EVIDENCE_CATEGORIES)
    except FileNotFoundError:
        built_count = 0

    dataset_version: str | None = None
    extraction_date: str | None = None
    try:
        app_data = cached_app_data()
        versions = app_data.get_column("dataset_version").drop_nulls().to_list()
        dates = app_data.get_column("extraction_date").drop_nulls().to_list()
        dataset_version = versions[0] if versions else None
        extraction_date = dates[0] if dates else None
    except FileNotFoundError:
        pass

    return DiseaseDetailResponse(
        disease_id=match.disease_id,
        name=match.name,
        description=match.description,
        therapeutic_areas=match.therapeutic_areas,
        n_associated_targets=match.n_associated_targets,
        evidence_categories_built=built_count,
        evidence_categories_total=len(APP_EVIDENCE_CATEGORIES),
        evidence_coverage=evidence_coverage,
        dataset_version=dataset_version,
        extraction_date=extraction_date,
    )


def _to_ranked_target_response(target: RankedTarget, sort_by: str) -> RankedTargetResponse:
    evidence = target.evidence
    total = len(APP_EVIDENCE_CATEGORIES)
    completeness = target.app_evidence_completeness or 0.0
    return RankedTargetResponse(
        rank=target.rank,
        target_id=target.target_id,
        gene_symbol=target.gene_symbol or target.target_id,
        gene_name=target.gene_name or "",
        score=target.score,
        sort_by=sort_by,  # type: ignore[arg-type]
        weighted_baseline_score=target.weighted_baseline_score,
        xgboost_score_held_out=target.xgboost_score_held_out,
        evidence=EvidenceBreakdown(
            genetics=evidence.get("genetics"),
            evidence_diversity=evidence.get("evidence_diversity"),
            functional=evidence.get("functional"),
            literature=evidence.get("literature"),
            druggability=evidence.get("druggability"),
            # Never populated on the ranking table — pathways/expression/
            # network are not among the weighted dimensions the scenario
            # controls are restricted to (presentation.DIMENSION_KEYS), and
            # safety has no scored weight at all (Context.md §14.7). Their
            # per-target standing shows up in `missing_evidence` here and
            # as real values on `/api/evidence` (EvidenceBreakdown's
            # docstring).
            pathways=None,
            expression=None,
            network=None,
            safety=None,
        ),
        evidence_completeness=completeness,
        evidence_completeness_count=round(completeness * total),
        evidence_completeness_total=total,
        missing_evidence=target.missing_evidence,
        n_other_diseases_positive=target.n_other_diseases_positive,
        source_links=target.source_links,
    )


@app.post("/api/rank", response_model=RankingResponse)
def rank(request: RankingRequest) -> RankingResponse:
    """Rank candidate targets for a disease — the same scoring path the
    Streamlit app uses (milestone3_plan.md §2), now reaching every filter,
    the scenario weights, and the sort toggle (milestone5_plan.md §1)."""
    raw_weights = request.weights or dict(load_model_config().milestone_1_weights)
    try:
        weights_used = normalize_weights(raw_weights)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    filters = RankingFilters(
        min_genetics_evidence=request.filters.min_genetics_evidence,
        relevant_tissue="relevant_tissue" if request.filters.relevant_tissue else None,
        require_druggable=request.filters.require_druggable,
        min_evidence_completeness=request.filters.min_evidence_completeness,
        target_family=request.filters.target_family,
        exclude_safety_concerns=request.filters.exclude_safety_concerns,
    )

    try:
        features = cached_features()
        app_data = cached_app_data()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    try:
        ranked = rank_for_disease(
            request.disease_id,
            filters=filters,
            top_n=request.top_n,
            weights=weights_used,
            sort_by=request.sort_by,
            features=features,
            app_data=app_data,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        # `target_family` set (invariant 6) or an internal sort_by/weights
        # problem normalize_weights above didn't already catch.
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    total_candidates = features.filter(pl.col("disease_id") == request.disease_id).height

    return RankingResponse(
        disease_id=request.disease_id,
        disease_name=_disease_name(request.disease_id),
        sort_by=request.sort_by,
        weights_used=weights_used,
        targets=[_to_ranked_target_response(t, request.sort_by) for t in ranked],
        total_candidates=total_candidates,
        dataset_version=release_tag(),
        model_version=__version__,
    )


def _to_evidence_item(item: EvidenceItem) -> EvidenceItemResponse:
    return EvidenceItemResponse(
        category=item.category,
        value=item.value,
        source=item.source,
        source_url=item.source_url,
        dataset_version=item.dataset_version,
    )


@app.post("/api/evidence", response_model=EvidenceResponse)
def evidence(request: EvidenceRequest) -> EvidenceResponse:
    """The target-detail evidence card (Context.md §21, §37) — the exact
    weighted-baseline contribution breakdown plus the held-out XGBoost
    fold model's live SHAP explanation, matching
    ``services.evidence_summary.build_evidence_card`` (milestone3_plan.md
    §2), extended with the raw ``contrib__``/``dim__`` values the
    evidence-breakdown chart and radar need (milestone5_plan.md §2.5)."""
    raw_weights = request.weights or dict(load_model_config().milestone_1_weights)
    try:
        weights_used = normalize_weights(raw_weights)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        features = cached_features()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    try:
        card = build_evidence_card(
            request.disease_id, request.target_id, features=features, weights=weights_used
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    row_frame = features.filter(
        (pl.col("disease_id") == request.disease_id) & (pl.col("target_id") == request.target_id)
    )
    row = row_frame.row(0, named=True)

    baseline = WeightedBaseline(weights_used)
    scored_row = baseline.score(row_frame).row(0, named=True)
    contributions = {dim: scored_row[f"{CONTRIBUTION_PREFIX}{dim}"] for dim in weights_used}
    dimension_values = {dim: row.get(f"{DIMENSION_PREFIX}{dim}") for dim in weights_used}

    try:
        app_data = cached_app_data()
    except FileNotFoundError:
        app_data = None

    rank_value: int | None = None
    total_candidates: int | None = None
    try:
        full_ranking = rank_for_disease(
            request.disease_id, top_n=None, weights=weights_used, features=features, app_data=app_data
        )
        total_candidates = len(full_ranking)
        rank_value = next((r.rank for r in full_ranking if r.target_id == request.target_id), None)
    except (KeyError, FileNotFoundError):
        pass

    xgboost_score_held_out = None
    n_other_diseases_positive = None
    label_n_drugs = None
    label_drug_names = None
    label_max_clinical_stage = None
    if app_data is not None:
        app_row = app_data.filter(
            (pl.col("disease_id") == request.disease_id) & (pl.col("target_id") == request.target_id)
        )
        if not app_row.is_empty():
            r = app_row.row(0, named=True)
            xgboost_score_held_out = r.get("xgboost_score_held_out")
            n_other_diseases_positive = r.get("n_other_diseases_positive")
            label_n_drugs = r.get("label__n_drugs")
            label_drug_names = r.get("label__drug_names")
            label_max_clinical_stage = r.get("label__max_clinical_stage")

    return EvidenceResponse(
        disease_id=request.disease_id,
        target_id=request.target_id,
        gene_symbol=card.gene_symbol or request.target_id,
        gene_name=row.get("gene_name") or "",
        score=card.score,
        weights_used=weights_used,
        contributions=contributions,
        dimension_values=dimension_values,
        supporting=[_to_evidence_item(i) for i in card.supporting],
        contradicting=[_to_evidence_item(i) for i in card.contradicting],
        missing=card.missing,
        xgboost_score_held_out=xgboost_score_held_out,
        n_other_diseases_positive=n_other_diseases_positive,
        rank=rank_value,
        total_candidates=total_candidates,
        label_n_drugs=label_n_drugs,
        label_drug_names=label_drug_names,
        label_max_clinical_stage=label_max_clinical_stage,
        not_buildable=NOT_BUILDABLE,
        source_links=card.source_links,
        limitations=card.limitations,
    )


@app.get("/api/evidence/detail", response_model=EvidenceDetailResponse)
def evidence_detail(disease_id: str, target_id: str) -> EvidenceDetailResponse:
    """The browsable half of Context.md §21's target-detail view.

    Named Reactome pathways, per-tissue GTEx expression and high-confidence
    STRING partners — the rows behind ``path__n_pathways``, ``expr__*`` and
    ``net__*``, which the feature table only carries as aggregates.

    A GET with query parameters rather than a POST like ``/api/evidence``:
    this response does not depend on the scenario weights, so it is safely
    cacheable and needs no body. Kept off ``/api/evidence`` so ``/compare``,
    which renders four evidence cards and none of this, does not pay for it.
    """
    try:
        detail = build_evidence_detail(disease_id, target_id, features=cached_features())
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        # The detail artifacts are committed, so this means an incomplete
        # checkout or image rather than a pipeline that has not been run.
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return EvidenceDetailResponse(
        disease_id=detail.disease_id,
        disease_name=detail.disease_name,
        target_id=detail.target_id,
        gene_symbol=detail.gene_symbol,
        pathway_groups=[
            PathwayGroupResponse(
                root_pathway_id=group.root_pathway_id,
                root_pathway_name=group.root_pathway_name,
                pathways=[
                    PathwayRefResponse(pathway_id=ref.pathway_id, name=ref.name, url=ref.url)
                    for ref in group.pathways
                ],
            )
            for group in detail.pathway_groups
        ],
        n_root_categories=detail.n_root_categories,
        tissues=[
            TissueValueResponse(
                tissue=t.tissue, median_tpm=t.median_tpm, is_relevant=t.is_relevant
            )
            for t in detail.tissues
        ],
        relevant_tissues_matched=detail.relevant_tissues_matched,
        relevant_tissues_unmatched=detail.relevant_tissues_unmatched,
        partners=[
            InteractionPartnerResponse(
                target_id=partner.target_id,
                gene_symbol=partner.gene_symbol,
                score=partner.score,
                is_candidate=partner.is_candidate,
            )
            for partner in detail.partners
        ],
        partner_min_score=detail.partner_min_score,
        literature=LiteratureSummaryResponse(
            europepmc_score=detail.literature.europepmc_score,
            europepmc_evidence_count=detail.literature.europepmc_evidence_count,
            search_url=detail.literature.search_url,
        ),
        not_buildable=NOT_BUILDABLE,
        dataset_version=detail.dataset_version,
    )


# Mounted LAST and only if the frontend has been built (milestone5_plan.md
# §2.2, §2.3) — every /api/* route above takes priority; StaticFiles never
# shadows them because FastAPI matches routes in registration order.
if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
