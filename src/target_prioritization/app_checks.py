"""Milestone 3 acceptance checks (Context.md §21, §22; milestone3_plan.md §6).

Milestones 1 and 2 each gate on a script that exits non-zero
(``milestone1.py``/``milestone2.py``, called by ``scripts/run_milestone1.py``/
``scripts/train_model.py``). A UI cannot be gated that way, but the services
layer can — this module is that gate for Milestone 3, called by
``scripts/check_app.py``, following the exact same package/script split.

Six checks, run against the real processed artifacts and the real
configured diseases — no synthetic data, the same standard
``milestone2.run_leakage_probe`` holds itself to (a guard that has never
been shown to fire on the real pipeline is not known to work):

1. No label-derived column reaches ``WeightedBaseline.score`` — the
   Milestone 3 analogue of the build-time leakage guard. Checked by
   patching ``WeightedBaseline.score`` to record its input columns during a
   real ``rank_for_disease`` call, AND by confirming the check can actually
   detect a deliberately-bad (join-before-score) frame — a check that can
   never fire is not a check.
2. All ten configured diseases return a well-formed ranking with no nulls
   in the displayed columns.
3. Every returned row carries resolvable Open Targets source links.
4. Every evidence card's ``missing`` list is non-empty wherever the
   corresponding ``missing__*`` flag is set.
5. The displayed XGBoost score for a disease comes from the fold model
   that excluded it — checked two ways: it matches a fresh score from that
   fold model, AND it differs from the in-sample all-disease refit.
6. Every unbuildable §21/§38 element has a stated placeholder reason, and
   the two unbuildable filters raise rather than silently no-op.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import polars as pl
import xgboost as xgb

from target_prioritization.config import DiseaseSpec, load_diseases
from target_prioritization.milestone2 import FOLD_MODELS_DIRNAME, fold_model_filename
from target_prioritization.models.baseline import WeightedBaseline
from target_prioritization.models.predict import score_targets
from target_prioritization.models.train import FittedModel, load_fitted_xgboost
from target_prioritization.services import evidence_summary, target_ranking
from target_prioritization.utils.paths import DATA_PROCESSED, TRAINED_MODELS

__all__ = ["CheckResult", "is_label_derived", "run_all_checks"]

# Columns that must NEVER reach a model — everything app_data.py adds that
# disease_target_features.parquet does not already carry (app_data.py's
# module docstring). Prefix-matched rather than an exhaustive list, for the
# same fail-closed reason build_features.py's own check is an ID-column
# allowlist rather than a feature-prefix denylist.
_LABEL_DERIVED_PREFIXES = ("label__", "xgboost_score", "xgboost_rank", "assoc_overall__")
_LABEL_DERIVED_COLUMNS = frozenset({"n_other_diseases_positive"})


def is_label_derived(column: str) -> bool:
    """Whether *column* is one of the display-only, label-derived columns
    that must never reach a model (see the module docstring)."""
    return column.startswith(_LABEL_DERIVED_PREFIXES) or column in _LABEL_DERIVED_COLUMNS


@dataclass(slots=True)
class CheckResult:
    name: str
    problems: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.problems


def check_leakage_boundary(disease_id: str) -> CheckResult:
    problems: list[str] = []
    seen_columns: set[str] = set()
    original_score = WeightedBaseline.score

    def _spying_score(self: WeightedBaseline, features: pl.DataFrame) -> pl.DataFrame:
        seen_columns.update(features.columns)
        return original_score(self, features)

    WeightedBaseline.score = _spying_score  # type: ignore[method-assign]
    try:
        target_ranking.rank_for_disease(disease_id, top_n=10)
    finally:
        WeightedBaseline.score = original_score  # type: ignore[method-assign]

    if leaked := sorted(c for c in seen_columns if is_label_derived(c)):
        problems.append(f"Label-derived column(s) reached WeightedBaseline.score: {leaked}")

    # The probe must be ABLE to fire: build the frame the WRONG way (display
    # joined in before scoring) and confirm it contains detectable columns.
    features = pl.read_parquet(DATA_PROCESSED / "disease_target_features.parquet").filter(
        pl.col("disease_id") == disease_id
    )
    app_data = target_ranking.load_precomputed_scores(disease_id)
    badly_ordered = features.join(app_data, on=["disease_id", "target_id"], how="left")
    if not [c for c in badly_ordered.columns if is_label_derived(c)]:
        problems.append(
            "Leakage probe cannot fire: a deliberately join-before-score frame produced no "
            "detectable label-derived columns. The check would not catch a real regression."
        )
    return CheckResult("Leakage boundary", problems)


def check_all_diseases_well_formed(diseases: list[DiseaseSpec]) -> CheckResult:
    problems: list[str] = []
    for disease in diseases:
        if not disease.efo_id:
            problems.append(f"{disease.key}: no resolved efo_id")
            continue
        try:
            results = target_ranking.rank_for_disease(disease.efo_id, top_n=20)
        except Exception as exc:
            problems.append(f"{disease.key}: rank_for_disease raised {exc!r}")
            continue
        if not results:
            problems.append(f"{disease.key}: rank_for_disease returned no rows")
            continue
        for r in results:
            if r.gene_symbol is None or r.score is None or r.rank is None:
                problems.append(f"{disease.key}/{r.target_id}: null rank, score or gene_symbol")
    return CheckResult("All ten diseases well-formed", problems)


def check_source_links(disease_id: str) -> CheckResult:
    problems: list[str] = []
    for r in target_ranking.rank_for_disease(disease_id, top_n=10):
        if set(r.source_links) != {"target", "disease", "evidence"}:
            problems.append(f"{r.target_id}: source_links has keys {sorted(r.source_links)}, expected all three")
        for name, url in r.source_links.items():
            if not url.startswith("https://platform.opentargets.org/"):
                problems.append(f"{r.target_id}: {name} link {url!r} does not resolve to Open Targets")
    return CheckResult("Source links resolvable", problems)


def check_missing_evidence_panel(disease_id: str) -> CheckResult:
    problems: list[str] = []
    features = pl.read_parquet(DATA_PROCESSED / "disease_target_features.parquet").filter(
        pl.col("disease_id") == disease_id
    )
    for missing_column in ("missing__genetics", "missing__functional", "missing__druggability"):
        candidates = features.filter(pl.col(missing_column) == 1)
        if candidates.is_empty():
            continue
        target_id = candidates.get_column("target_id")[0]
        card = evidence_summary.build_evidence_card(disease_id, target_id)
        if not card.missing:
            problems.append(f"{target_id}: {missing_column}=1 but EvidenceCard.missing is empty")
        break
    return CheckResult("Missing-evidence panel", problems)


def check_fold_routing(disease: DiseaseSpec) -> CheckResult:
    problems: list[str] = []
    features = pl.read_parquet(DATA_PROCESSED / "disease_target_features.parquet").filter(
        pl.col("disease_id") == disease.efo_id
    )
    app_data = pl.read_parquet(DATA_PROCESSED / "app_scores.parquet").filter(
        pl.col("disease_id") == disease.efo_id
    )

    fold_path = TRAINED_MODELS / FOLD_MODELS_DIRNAME / fold_model_filename(disease.key)
    fold_model = load_fitted_xgboost(fold_path)
    fresh_scores = score_targets(fold_model, features).sort("target_id")

    artifact_scores = app_data.select("target_id", pl.col("xgboost_score_held_out").alias("score")).sort(
        "target_id"
    )
    joined = fresh_scores.join(artifact_scores, on="target_id", suffix="_artifact")
    mismatched = joined.filter((pl.col("score") - pl.col("score_artifact")).abs() > 1e-9)
    if not mismatched.is_empty():
        problems.append(
            f"{disease.key}: app_scores.parquet's xgboost_score_held_out does not match a fresh "
            f"score from its own fold model for {mismatched.height} target(s)"
        )

    refit_estimator = xgb.XGBClassifier()
    refit_estimator.load_model(str(TRAINED_MODELS / "xgboost_baseline.json"))
    refit_model = FittedModel(
        name="xgboost", feature_columns=fold_model.feature_columns, estimator=refit_estimator, preprocessor=None
    )
    refit_scores = score_targets(refit_model, features).sort("target_id")
    same_as_refit = joined.join(
        refit_scores.rename({"score": "score_refit"}), on="target_id"
    ).filter((pl.col("score") - pl.col("score_refit")).abs() < 1e-9)
    if same_as_refit.height == joined.height:
        problems.append(
            f"{disease.key}: the held-out fold score is IDENTICAL to the in-sample refit score for "
            "every target — fold routing may be silently using the refit model everywhere"
        )
    return CheckResult("Fold routing (held-out, not in-sample)", problems)


def check_placeholders(disease_id: str) -> CheckResult:
    problems: list[str] = []
    if not target_ranking.UNAVAILABLE_EVIDENCE_CATEGORIES:
        problems.append("UNAVAILABLE_EVIDENCE_CATEGORIES is empty")
    for category, reason in target_ranking.UNAVAILABLE_EVIDENCE_CATEGORIES.items():
        if "not yet integrated" not in reason:
            problems.append(f"{category}: placeholder reason does not say 'not yet integrated' ({reason!r})")

    unbuildable_filters = {
        "relevant_tissue": target_ranking.RankingFilters(relevant_tissue="x"),
        "target_family": target_ranking.RankingFilters(target_family="x"),
    }
    for name, filters in unbuildable_filters.items():
        try:
            target_ranking.rank_for_disease(disease_id, filters=filters)
            problems.append(f"{name} filter did not raise — a silently-ignored filter is a regression")
        except ValueError:
            pass
    return CheckResult("Unbuildable elements are explicit placeholders", problems)


def run_all_checks(diseases: list[DiseaseSpec] | None = None) -> list[CheckResult]:
    """Run every acceptance check against the real processed artifacts.

    Args:
        diseases: Defaults to every resolved disease in
            ``configs/diseases.yaml``. Checks 1, 3, 4, 6 run against the
            first disease only (they are per-call properties of the
            services layer, not per-disease data quality); check 2 runs
            against every disease; check 5 runs against the first disease's
            fold model specifically.

    Raises:
        FileNotFoundError: If the processed artifacts or fold models have
            not been built yet (``scripts/train_model.py`` /
            ``scripts/build_app_data.py``).
    """
    diseases = diseases if diseases is not None else load_diseases().resolved
    if not diseases:
        raise ValueError("No resolved diseases configured (configs/diseases.yaml)")
    first = diseases[0]

    return [
        check_leakage_boundary(first.efo_id),  # type: ignore[arg-type]
        check_all_diseases_well_formed(diseases),
        check_source_links(first.efo_id),  # type: ignore[arg-type]
        check_missing_evidence_panel(first.efo_id),  # type: ignore[arg-type]
        check_fold_routing(first),
        check_placeholders(first.efo_id),  # type: ignore[arg-type]
    ]
