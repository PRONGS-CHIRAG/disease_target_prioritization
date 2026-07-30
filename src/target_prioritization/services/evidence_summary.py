"""Evidence cards for the target detail page (Context.md §21, §37).

Combines the two scores' explanations rather than picking one:
`WeightedBaseline.explain` gives an EXACT decomposition (contributions sum
to the score, no approximation), and the held-out XGBoost fold model gives a
live SHAP explanation. Both appear in `supporting`/`contradicting`, each
tagged with which model produced it (`source="weighted_baseline"` vs.
`source="xgboost_held_out"`) — collapsing them into one undifferentiated
list would let a reader mistake one model's reasoning for the other's.

**SHAP is computed live, not read from a precomputed store** — there isn't
one (milestone3_plan.md §4.2). `explain_target` is called with *features*
already sliced to the single row being explained, not the whole disease:
measured directly, a single row's SHAP is bit-identical to that same row's
SHAP computed over its whole disease (`shap.TreeExplainer` is constructed
with no `data=`, so it runs path-dependent perturbation and
`expected_value` comes from the trained trees, not from whatever rows
happen to be passed alongside), and costs ~30ms instead of ~5.6s. Passing
the whole disease frame here "to be safe" would silently reintroduce that
cost with no accuracy benefit.

Context.md §20.4 constrains the optional LLM explanation layer tightly (use
retrieved evidence only, cite sources, separate data from interpretation,
never generate the score) — that layer is out of scope for this milestone
(milestone3_plan.md §5, §9): every claim an LLM would render into prose is
already available here as structured data, and it is not required for the
MVP.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import polars as pl

from target_prioritization.config import DiseaseSpec, load_diseases, load_model_config
from target_prioritization.milestone2 import FOLD_MODELS_DIRNAME, fold_model_filename
from target_prioritization.models.baseline import WeightedBaseline
from target_prioritization.models.explain import (
    STANDING_LIMITATIONS,
    explain_target,
    source_references,
)
from target_prioritization.models.train import load_fitted_xgboost
from target_prioritization.services.target_ranking import (
    SAFETY_LIABILITY_VALUE,
    missing_evidence_categories,
)
from target_prioritization.utils.logging import get_logger
from target_prioritization.utils.paths import DATA_PROCESSED, TRAINED_MODELS

__all__ = ["EvidenceCard", "EvidenceItem", "build_evidence_card"]

log = get_logger(__name__)

FEATURES_PATH = DATA_PROCESSED / "disease_target_features.parquet"


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
    gene_symbol: str | None
    score: float
    supporting: list[EvidenceItem] = field(default_factory=list)
    contradicting: list[EvidenceItem] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    source_links: dict[str, str] = field(default_factory=dict)


def _load_features() -> pl.DataFrame:
    if not FEATURES_PATH.exists():
        raise FileNotFoundError(f"{FEATURES_PATH} not found. Run scripts/train_model.py first.")
    return pl.read_parquet(FEATURES_PATH)


def _disease_key(disease_id: str, diseases: list[DiseaseSpec]) -> str:
    for disease in diseases:
        if disease.efo_id == disease_id:
            return disease.key
    raise KeyError(f"{disease_id!r} is not a configured disease (configs/diseases.yaml)")


def _weighted_baseline_items(
    row_frame: pl.DataFrame, target_id: str, dataset_version: str | None, weights: dict[str, float]
) -> tuple[list[EvidenceItem], float]:
    """Exact per-dimension contributions from WeightedBaseline.explain, plus
    the score itself — computed once here and reused as the card's ``score``
    (services.target_ranking's default sort, milestone3_plan.md §2).

    Weights are non-negative by construction (WeightedBaseline rejects
    negative weights), so there is no "negative contribution" concept for
    this model (explain.py's identical note about explain_target) — every
    item here is `supporting`, never `contradicting`.
    """
    baseline = WeightedBaseline(weights)
    scored = baseline.score(row_frame)
    explanation = baseline.explain(scored, target_id)
    items = [
        EvidenceItem(
            category=f"weighted_baseline__{dim}",
            value=value,
            source="weighted_baseline",
            dataset_version=dataset_version,
        )
        for dim, value in explanation.top_contributors(5)
        if value > 0
    ]
    return items, float(explanation.score)


def _xgboost_held_out_items(
    disease_id: str,
    target_id: str,
    row_frame: pl.DataFrame,
    diseases: list[DiseaseSpec],
    dataset_version: str | None,
) -> tuple[list[EvidenceItem], list[EvidenceItem]]:
    """Live SHAP-based positive/negative factors from the fold model that
    excluded *disease_id* — never the in-sample xgboost_baseline.json
    (milestone3_plan.md §2.1). Returns ``([], [])`` if the fold model has not
    been built yet (``scripts/train_model.py`` not yet run), logged rather
    than raised — the weighted-baseline half of the card is still useful on
    its own."""
    try:
        key = _disease_key(disease_id, diseases)
        model_path = TRAINED_MODELS / FOLD_MODELS_DIRNAME / fold_model_filename(key)
        model = load_fitted_xgboost(model_path)
    except (KeyError, FileNotFoundError):
        log.warning("xgboost_held_out_explanation_unavailable", disease_id=disease_id, target_id=target_id)
        return [], []

    # `row_frame` is already sliced to the single (disease_id, target_id) row
    # — see the module docstring for why this is both correct and fast.
    explanation = explain_target(model, row_frame, disease_id, target_id)
    supporting = [
        EvidenceItem(
            category=f"xgboost_held_out__{f['feature']}",
            value=f["contribution"],
            source="xgboost_held_out",
            dataset_version=dataset_version,
        )
        for f in explanation["top_positive_factors"]
    ]
    contradicting = [
        EvidenceItem(
            category=f"xgboost_held_out__{f['feature']}",
            value=f["contribution"],
            source="xgboost_held_out",
            dataset_version=dataset_version,
        )
        for f in explanation["top_negative_factors"]
    ]
    return supporting, contradicting


def build_evidence_card(
    disease_id: str,
    target_id: str,
    *,
    features: pl.DataFrame | None = None,
    weights: dict[str, float] | None = None,
    diseases: list[DiseaseSpec] | None = None,
) -> EvidenceCard:
    """Assemble the evidence card for one disease-target pair.

    Populates ``contradicting`` and ``missing`` as seriously as
    ``supporting`` (Context.md §30.12): a card that lists only confirming
    evidence is a worse decision aid than no card. ``contradicting`` draws
    from two places — the held-out XGBoost model's negative SHAP factors,
    and a recorded safety-liability flag
    (`target_prioritisation.hasSafetyEvent`, never folded into either
    score). ``missing`` is the same six-category list
    `services.target_ranking.missing_evidence_categories` computes for the
    ranking table, so the two pages never disagree about what counts as
    missing for a given target.

    Args:
        features: Pass to bypass reading the real
            ``disease_target_features.parquet`` (tests).
        weights: Weighted-baseline dimension weights. Defaults to
            ``configs/model.yaml``'s ``milestone_1_weights`` — must already
            sum to 1.0 (``services.target_ranking.normalize_weights`` first
            if these come from a scenario-control slider, Context.md §38.5).
        diseases: Pass to bypass reading ``configs/diseases.yaml`` (tests).

    Raises:
        KeyError: If ``(disease_id, target_id)`` is not in the feature table.
    """
    features = features if features is not None else _load_features()
    diseases = diseases if diseases is not None else load_diseases().resolved
    weights = weights if weights is not None else load_model_config().milestone_1_weights

    row_frame = features.filter((pl.col("disease_id") == disease_id) & (pl.col("target_id") == target_id))
    if row_frame.is_empty():
        raise KeyError(f"({disease_id!r}, {target_id!r}) not present in the feature table")
    row = row_frame.row(0, named=True)
    dataset_version = row.get("dataset_version")

    # score: the weighted baseline's, matching services.target_ranking's
    # default sort (milestone3_plan.md §2) — the XGBoost held-out score is
    # still surfaced, tagged by source, inside `supporting`/`contradicting`,
    # never silently substituted as THE score.
    weighted_supporting, score = _weighted_baseline_items(row_frame, target_id, dataset_version, weights)
    xgb_supporting, xgb_contradicting = _xgboost_held_out_items(
        disease_id, target_id, row_frame, diseases, dataset_version
    )

    contradicting = list(xgb_contradicting)
    if row.get("prio__has_safety_event") == SAFETY_LIABILITY_VALUE:
        contradicting.append(
            EvidenceItem(
                category="safety_event",
                value=SAFETY_LIABILITY_VALUE,
                source="open_targets/target_prioritisation",
                dataset_version=dataset_version,
            )
        )

    links = source_references(target_id, disease_id)
    return EvidenceCard(
        disease_id=disease_id,
        target_id=target_id,
        gene_symbol=row.get("gene_symbol"),
        score=score,
        supporting=weighted_supporting + xgb_supporting,
        contradicting=contradicting,
        missing=missing_evidence_categories(row),
        limitations=list(STANDING_LIMITATIONS),
        source_links=links,
    )
