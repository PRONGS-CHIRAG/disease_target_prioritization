"""Ranking service backing the app (Context.md §21).

Sits between the trained model and the UI: takes a disease, returns ranked
targets with their evidence, and applies the filters listed in Context.md
§21 that are actually buildable (milestone3_plan.md §1).

**Score-first, join-second — the leakage boundary for this whole app**
(milestone3_plan.md §3). `rank_for_disease` scores on a frame carrying
FEATURE columns only (`disease_target_features.parquet`, filtered to one
disease) via `WeightedBaseline.score`. Only *after* that call returns does
the display join happen, bringing in `app_scores.parquet` — the held-out
XGBoost score, the OT overall score, the popularity badge, and the
`label__*` existing-drug/clinical-stage fields. Those columns are never
present in anything handed to `WeightedBaseline.score`, `score_targets`, or
`explain_target`/`shap_values`. This ordering is the actual guarantee; the
separate dataclasses below (`RankingFilters`/`RankedTarget` vs. the raw
frames) make the boundary visible in the code, but the join happening last
is what enforces it. `scripts/check_app.py` probes this directly.

**Two scores, one default.** The weighted baseline is scored live (cheap: a
weighted sum over ~5 columns, thousands of rows) and is the DEFAULT sort —
it is the only one of the two whose weights a user can change (§38.5
scenario controls) and whose contributions decompose exactly
(`WeightedBaseline.explain`). The held-out XGBoost score is precomputed
(`scripts/build_app_data.py`, from the fold model that excluded this
disease — never the in-sample `xgboost_baseline.json`) and shown alongside,
never silently substituted as the primary ranking — milestone2.md §1's
finding (XGBoost's ranking is mostly cross-disease target popularity, novel-
only NDCG@10 0.009) belongs next to that number wherever it is shown.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import polars as pl

from target_prioritization.app_data import APP_DATA_NAME
from target_prioritization.config import load_model_config
from target_prioritization.features.expression import TPM_DETECTION_THRESHOLD
from target_prioritization.features.genetics import DIMENSION_PREFIX, MISSING_PREFIX
from target_prioritization.models.baseline import SCORE_COLUMN, WeightedBaseline
from target_prioritization.models.explain import source_references
from target_prioritization.utils.paths import DATA_PROCESSED

__all__ = [
    "APP_EVIDENCE_CATEGORIES",
    "SAFETY_LIABILITY_VALUE",
    "UNAVAILABLE_EVIDENCE_CATEGORIES",
    "RankedTarget",
    "RankingFilters",
    "load_precomputed_scores",
    "missing_evidence_categories",
    "normalize_weights",
    "rank_for_disease",
]

FEATURES_PATH = DATA_PROCESSED / "disease_target_features.parquet"
APP_DATA_PATH = DATA_PROCESSED / APP_DATA_NAME

# The display-facing evidence-completeness categories (milestone3_plan.md
# §1) — DELIBERATELY DIFFERENT from WeightedBaseline.score's own
# `evidence_completeness`, which is a share of its five WEIGHTED dimensions
# (genetics, evidence_diversity, functional, literature, druggability) and is
# essentially always near-complete. This set is the union of Context.md
# §21's ranked-table evidence columns and §38.2's, restricted to categories
# that are absence-of-evidence signals rather than a safety flag or the
# training label; literature is excluded because it is not a column in
# either table (unlike in WeightedBaseline's own five). Two columns with the
# same name and different denominators is exactly the trap this project's
# leakage guard exists to catch elsewhere, hence the distinct name
# `app_evidence_completeness` on `RankedTarget`, never `evidence_completeness`.
# All six are now built (Milestone 4 wired in Reactome/GTEx/STRING — see
# milestone4_plan.md); UNAVAILABLE_EVIDENCE_CATEGORIES is kept, empty, as the
# hook a future genuinely-unbuildable category would populate, rather than
# removed outright — app_checks.check_placeholders asserts it stays empty.
APP_EVIDENCE_CATEGORIES = ["genetics", "functional", "pathways", "expression", "network", "druggability"]

UNAVAILABLE_EVIDENCE_CATEGORIES: dict[str, str] = {}

# The subset of APP_EVIDENCE_CATEGORIES this milestone actually builds, i.e.
# the ones with a real dim__/missing__ column in disease_target_features.parquet.
_BUILT_CATEGORIES = [c for c in APP_EVIDENCE_CATEGORIES if c not in UNAVAILABLE_EVIDENCE_CATEGORIES]

# WeightedBaseline's own five dimensions (configs/model.yaml milestone_1_weights),
# shown in full on the ranking table regardless of which of the six
# completeness categories they map to.
_DISPLAY_DIMENSIONS = ["genetics", "evidence_diversity", "functional", "literature", "druggability"]

_SORT_KEYS = {"weighted_baseline": SCORE_COLUMN, "xgboost_held_out": "xgboost_score_held_out"}

# target_prioritisation.hasSafetyEvent is signed: -1 is a recorded liability,
# never +1 (data/open_targets.py's docstring). Shared with
# services.evidence_summary, which surfaces the identical flag as
# contradicting evidence on the target detail page.
SAFETY_LIABILITY_VALUE = -1


@dataclass(slots=True)
class RankingFilters:
    """Filters from the MVP interface spec (Context.md §21, §38.3).

    `relevant_tissue` is buildable as of Milestone 4 (milestone4_plan.md):
    set it (any truthy string — the disease's own configured tissues are
    what `expr__relevant_tissue_tpm` was computed against, so this is a
    switch, not a free-text tissue override) to keep only targets with
    detectable expression in the disease-relevant tissue.

    `target_family` is still not buildable — it needs `target.targetClass`,
    which is unrelated to Reactome/GTEx/STRING and is not a column in
    `disease_target_features.parquet`. Left in the type — not deleted — so
    the gap is visible to anyone reading the type, not just this docstring.
    `rank_for_disease` raises if it is set, rather than silently accepting
    and ignoring a filter the caller believes is being applied.

    `exclude_safety_concerns` is also buildable — §38.3's "Safety concern"
    filter maps onto `prio__has_safety_event` (target_prioritisation's
    signed liability flag, -1 = a recorded concern), even though safety has
    no WEIGHT in the score (configs/model.yaml has no safety term,
    deliberately: Context.md §14.7 forbids presenting these as validated
    toxicity predictions). A filter needs no calibrated score to be honest;
    a weighted contribution does.
    """

    min_genetics_evidence: float | None = None
    relevant_tissue: str | None = None
    require_druggable: bool = False
    min_evidence_completeness: float | None = None
    target_family: str | None = None
    exclude_safety_concerns: bool = False


@dataclass(slots=True)
class RankedTarget:
    rank: int
    target_id: str
    gene_symbol: str | None
    gene_name: str | None
    # The active sort's score — whichever of the two `sort_by` selected.
    score: float
    weighted_baseline_score: float
    # None only if scripts/build_app_data.py has not been run yet.
    xgboost_score_held_out: float | None
    # WeightedBaseline's five scored dimensions, straight from the dim__
    # columns (nulls preserved — NOT filled to zero the way scoring does;
    # Context.md §32.3 distinguishes "no evidence" from "weak evidence").
    evidence: dict[str, float | None] = field(default_factory=dict)
    # Six-category DISPLAY completeness (0..1) — see APP_EVIDENCE_CATEGORIES.
    # Deliberately not named `evidence_completeness` alone in prose without
    # its denominator: render as "N of 6 categories", never a bare fraction.
    app_evidence_completeness: float | None = None
    # Every category from APP_EVIDENCE_CATEGORIES absent for this target —
    # the three categorically-unbuilt ones always appear here, plus any of
    # genetics/functional/druggability this specific target has no evidence
    # for (Context.md §32.3).
    missing_evidence: list[str] = field(default_factory=list)
    # milestone2.md §1's finding, made concrete per target (milestone3_plan.md
    # §2.2): how many of the OTHER nine configured diseases this target is
    # also a labelled positive in. None only if build_app_data has not run.
    n_other_diseases_positive: int | None = None
    source_links: dict[str, str] = field(default_factory=dict)


def normalize_weights(weights: dict[str, float]) -> dict[str, float]:
    """Rescale *weights* to sum to 1.0, preserving relative proportions.

    `WeightedBaseline.__init__` raises rather than rescale (models/baseline.py)
    — deliberately strict, so a hand-constructed instance cannot silently
    drift off the 0-1 scale it promises. Scenario weight sliders (Context.md
    §38.5) hand the user arbitrary raw values, so normalization happens HERE,
    explicitly, before constructing a `WeightedBaseline` — and the caller
    must display the *normalized* values back, not the raw slider positions,
    or the contributions shown on screen won't match what the user set.

    Raises:
        ValueError: If *weights* is empty, has a negative value, or sums to
            zero or less.
    """
    if not weights:
        raise ValueError("normalize_weights requires at least one weight")
    if negative := {k: v for k, v in weights.items() if v < 0}:
        raise ValueError(f"Negative weight(s): {negative}")
    total = sum(weights.values())
    if total <= 0:
        raise ValueError("Weights sum to zero or less; cannot normalize")
    return {k: v / total for k, v in weights.items()}


def _app_evidence_completeness(features: pl.DataFrame) -> pl.DataFrame:
    """Six-category display completeness per (disease_id, target_id) — see
    APP_EVIDENCE_CATEGORIES for exactly what the six are and why."""
    present = [
        (1 - pl.col(f"{MISSING_PREFIX}{dim}")).alias(f"_present__{dim}") for dim in _BUILT_CATEGORIES
    ]
    frame = features.select("disease_id", "target_id", *present)
    total_categories = float(len(APP_EVIDENCE_CATEGORIES))
    frame = frame.with_columns(
        (pl.sum_horizontal([pl.col(f"_present__{dim}") for dim in _BUILT_CATEGORIES]) / total_categories).alias(
            "app_evidence_completeness"
        )
    )
    return frame.select("disease_id", "target_id", "app_evidence_completeness")


def missing_evidence_categories(row: dict[str, object]) -> list[str]:
    """Every category from APP_EVIDENCE_CATEGORIES absent for *row* — the
    three categorically-unbuilt ones always included, plus any of
    genetics/functional/druggability this specific row has no evidence for
    (Context.md §32.3). Public: shared with ``services.evidence_summary``,
    which needs the identical missing-category logic for the target detail
    page's "missing evidence" panel."""
    missing = list(UNAVAILABLE_EVIDENCE_CATEGORIES)
    for dim in _BUILT_CATEGORIES:
        if row.get(f"{MISSING_PREFIX}{dim}") == 1:
            missing.append(dim)
    return sorted(missing)


def _load_features() -> pl.DataFrame:
    if not FEATURES_PATH.exists():
        raise FileNotFoundError(
            f"{FEATURES_PATH} not found. Run scripts/train_model.py first."
        )
    return pl.read_parquet(FEATURES_PATH)


def _load_app_data() -> pl.DataFrame:
    if not APP_DATA_PATH.exists():
        raise FileNotFoundError(
            f"{APP_DATA_PATH} not found. Run scripts/build_app_data.py first."
        )
    return pl.read_parquet(APP_DATA_PATH)


def load_precomputed_scores(disease_id: str, *, app_data: pl.DataFrame | None = None) -> pl.DataFrame:
    """The offline-scored half for one disease: held-out XGBoost score/rank,
    the OT overall score, the popularity badge, and the `label__*` fields —
    everything `scripts/build_app_data.py` bakes in. The weighted baseline
    is the other half, scored live by :func:`rank_for_disease`.
    """
    app_data = app_data if app_data is not None else _load_app_data()
    return app_data.filter(pl.col("disease_id") == disease_id)


def _reject_unbuildable_filters(filters: RankingFilters) -> None:
    if filters.target_family:
        raise ValueError(
            "target_family is not buildable in this release (target.targetClass is not a "
            "column in disease_target_features.parquet, and is unrelated to Reactome/GTEx/"
            "STRING — milestone4_plan.md §9). Refusing to silently ignore a filter the "
            "caller believes is being applied."
        )


def _apply_filters(ranked: pl.DataFrame, filters: RankingFilters) -> pl.DataFrame:
    result = ranked
    if filters.min_genetics_evidence is not None:
        result = result.filter(pl.col(f"{DIMENSION_PREFIX}genetics").fill_null(0.0) >= filters.min_genetics_evidence)
    if filters.relevant_tissue:
        # Null-safe: a null expr__relevant_tissue_tpm means "not studied /
        # this disease's tissues don't resolve against GTEx" (rheumatoid
        # arthritis's synovium — expression.py's module docstring), not
        # "confirmed absent" — treated as failing the filter, same as an
        # explicit low value would, never silently passed through.
        result = result.filter(
            pl.col("expr__relevant_tissue_tpm").fill_null(0.0) >= TPM_DETECTION_THRESHOLD
        )
    if filters.require_druggable:
        result = result.filter(pl.col("prio__has_small_molecule_binder") == 1)
    if filters.min_evidence_completeness is not None:
        result = result.filter(pl.col("app_evidence_completeness") >= filters.min_evidence_completeness)
    if filters.exclude_safety_concerns:
        # Null-safe: a null flag means "not assessed" (Context.md §32.3), not
        # "no concern" — only an EXPLICIT -1 is excluded, never a null.
        result = result.filter(
            (pl.col("prio__has_safety_event") == SAFETY_LIABILITY_VALUE).fill_null(False).not_()
        )
    return result


def _row_to_ranked_target(row: dict[str, object], disease_id: str, sort_by: str) -> RankedTarget:
    evidence: dict[str, float | None] = {
        dim: row.get(f"{DIMENSION_PREFIX}{dim}") for dim in _DISPLAY_DIMENSIONS  # type: ignore[misc]
    }
    active_score = row[_SORT_KEYS[sort_by]]
    target_id = row["target_id"]
    assert isinstance(target_id, str)
    return RankedTarget(
        rank=row["rank"],  # type: ignore[arg-type]
        target_id=target_id,
        gene_symbol=row.get("gene_symbol"),  # type: ignore[arg-type]
        gene_name=row.get("gene_name"),  # type: ignore[arg-type]
        score=active_score,  # type: ignore[arg-type]
        weighted_baseline_score=row[SCORE_COLUMN],  # type: ignore[arg-type]
        xgboost_score_held_out=row.get("xgboost_score_held_out"),  # type: ignore[arg-type]
        evidence=evidence,
        app_evidence_completeness=row.get("app_evidence_completeness"),  # type: ignore[arg-type]
        missing_evidence=missing_evidence_categories(row),
        n_other_diseases_positive=row.get("n_other_diseases_positive"),  # type: ignore[arg-type]
        source_links=source_references(target_id, disease_id),
    )


def rank_for_disease(
    disease_id: str,
    filters: RankingFilters | None = None,
    top_n: int | None = 50,
    *,
    weights: dict[str, float] | None = None,
    sort_by: str = "weighted_baseline",
    features: pl.DataFrame | None = None,
    app_data: pl.DataFrame | None = None,
) -> list[RankedTarget]:
    """Ranked targets for one disease, with evidence attached.

    Args:
        disease_id: Open Targets disease ID, e.g. ``MONDO_0005180``.
        filters: Applied AFTER ranking, before truncating to *top_n* — a
            target's `rank` reflects its place among every candidate for
            this disease, not just the ones a filter happens to keep.
        top_n: Keep only the top *n* after filtering. None keeps every row.
        weights: Weighted-baseline dimension weights (Context.md §38.5
            scenario controls). Must already sum to 1.0 — normalize with
            :func:`normalize_weights` first. Defaults to
            ``configs/model.yaml``'s ``milestone_1_weights``.
        sort_by: ``"weighted_baseline"`` (default) or ``"xgboost_held_out"``.
        features: Pass to bypass reading the real
            ``disease_target_features.parquet`` (tests). Must carry FEATURE
            columns only for *disease_id* — see the module docstring for why
            this must never carry a `label__*` or other display-only column.
        app_data: Pass to bypass reading the real ``app_scores.parquet``
            (tests).

    Returns:
        Every candidate target for *disease_id* that survives *filters*,
        ranked and truncated to *top_n*.

    Raises:
        ValueError: If *sort_by* is not recognised, or *filters* sets
            ``relevant_tissue``/``target_family``.
        KeyError: If *disease_id* has no rows in the feature table.
        FileNotFoundError: If *features*/*app_data* are not given and the
            real processed artifacts have not been built yet.
    """
    filters = filters or RankingFilters()
    if sort_by not in _SORT_KEYS:
        raise ValueError(f"Unknown sort_by {sort_by!r}; expected one of {sorted(_SORT_KEYS)}")
    _reject_unbuildable_filters(filters)

    features = features if features is not None else _load_features()
    disease_features = features.filter(pl.col("disease_id") == disease_id)
    if disease_features.is_empty():
        raise KeyError(f"No features for disease_id {disease_id!r}")

    weights = weights if weights is not None else load_model_config().milestone_1_weights
    baseline = WeightedBaseline(weights)

    # ---- SCORE. `disease_features` carries feature columns only — no
    # label-derived column has been joined in yet. ----
    scored = baseline.score(disease_features)
    completeness = _app_evidence_completeness(disease_features)
    scored = scored.join(completeness, on=["disease_id", "target_id"], how="left")

    # ---- JOIN. Only now does anything from app_scores.parquet (held-out
    # XGBoost score, OT overall score, popularity badge, label__* fields)
    # attach — after scoring is complete, never before (module docstring). ----
    disease_app_data = load_precomputed_scores(disease_id, app_data=app_data)
    display = scored.join(disease_app_data, on=["disease_id", "target_id"], how="left")

    sort_column = _SORT_KEYS[sort_by]
    ranked = display.sort([sort_column, "target_id"], descending=[True, False], nulls_last=True).with_columns(
        pl.cum_count("target_id").alias("rank")
    )

    filtered = _apply_filters(ranked, filters)
    if top_n is not None:
        filtered = filtered.head(top_n)

    return [_row_to_ranked_target(row, disease_id, sort_by) for row in filtered.iter_rows(named=True)]
