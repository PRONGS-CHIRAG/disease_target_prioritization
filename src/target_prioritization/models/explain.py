"""Model explanations (Context.md §20).

Scientific users need to see the evidence, not a number. Context.md §20.2
requires per-target SHAP values, the strongest positive and negative factors,
which evidence types are present, which are *missing*, and source references.

The missing-evidence part is not decoration: Context.md §32.3 warns that a
target can look weak simply because nobody has studied it, and a UI that shows
only positive contributions actively misleads.

**``weighted_baseline`` has no SHAP values, on purpose.** Its contributions
already sum EXACTLY to the score (``models/baseline.py``,
``WeightedBaseline.explain``) — an exact decomposition, which is strictly
better than SHAP's approximation. :func:`shap_values` and
:func:`global_feature_importance` raise for it; :func:`explain_target`
delegates to ``WeightedBaseline.explain`` instead, so callers get one
consistent function regardless of which model they're explaining.

**The output space differs by model — checked per model, not assumed
uniform.** For XGBoost and logistic regression, ``TreeExplainer``'s /
``LinearExplainer``'s default output is *margin* (log-odds) space:
``base_value + sum(shap_value)`` reconstructs the raw margin, and a sigmoid
on top reproduces ``predict_proba`` (verified to ``atol=1e-4``). For random
forest, ``TreeExplainer``'s default output is already *probability* space —
sklearn's ``RandomForestClassifier.predict_proba`` IS the raw tree-vote
average with no separate link function, so there is no margin for
``TreeExplainer`` to report in the first place; ``base_value +
sum(shap_value)`` reconstructs ``predict_proba`` directly, with no sigmoid
(verified to ``atol=1e-10``, tighter than the other two because there is no
extra transform to round-trip through). Getting this backwards silently
produces plausible-looking but wrong numbers, so it is checked per model in
this module's test suite rather than assumed uniform across three different
libraries' explainer implementations.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import polars as pl
import shap

from target_prioritization.features.genetics import DIMENSION_PREFIX, MISSING_PREFIX
from target_prioritization.models.train import FittedModel
from target_prioritization.utils.logging import get_logger

__all__ = ["explain_target", "global_feature_importance", "shap_values", "source_references"]

log = get_logger(__name__)

# Context.md §20.3's example ends with a "Limitations" section; these are the
# standing ones that apply to every explanation regardless of model or target.
STANDING_LIMITATIONS = [
    "This is a prioritization score, not a probability of therapeutic success "
    "(Context.md §15, §31.1).",
    "The label reflects reaching an advanced clinical trial, not proven safety or "
    "efficacy — a high score does not show the target is safe to modify "
    "(Context.md §14.7, §31.7).",
    "Cross-disease target popularity contributes to this score for most positives "
    "(milestone2.md §1) — check whether this target is also a positive for other "
    "configured diseases before treating a high score as disease-specific evidence.",
    "Absence of a feature means Open Targets has not captured that evidence for "
    "this disease, not that the underlying biology is absent (Context.md §32.3).",
    "Experimental validation is still required before acting on this score.",
]


def source_references(target_id: str, disease_id: str) -> dict[str, str]:
    """Open Targets Platform URLs for the target, the disease and their evidence.

    Public (Milestone 3, Context.md §21 "data-source links") — shared with
    ``services.target_ranking`` and ``services.evidence_summary`` so every
    surface that renders a source link uses the identical URL construction.
    """
    return {
        "target": f"https://platform.opentargets.org/target/{target_id}",
        "disease": f"https://platform.opentargets.org/disease/{disease_id}",
        "evidence": f"https://platform.opentargets.org/evidence/{target_id}/{disease_id}",
    }


def _require_shap_compatible(model: FittedModel) -> None:
    if model.weighted_baseline is not None:
        raise ValueError(
            "weighted_baseline has no SHAP values — its contributions already sum "
            "exactly to the score (WeightedBaseline.explain); use that instead."
        )
    if model.name not in ("logistic_regression", "random_forest", "xgboost"):
        raise ValueError(f"No SHAP explainer wired up for model {model.name!r}")


def _processed_matrix(model: FittedModel, features: pl.DataFrame) -> np.ndarray:
    x = features.select(model.feature_columns).to_numpy()
    if model.preprocessor is not None:
        x = model.preprocessor.transform(x)
    return np.asarray(x, dtype=np.float64)


def _surviving_feature_columns(model: FittedModel) -> list[str]:
    """``model.feature_columns``, minus any column an imputer silently
    dropped for being all-null within the fold this model was trained on
    (the per-fold sparsity ``build_feature_table`` logs — models/train.py's
    module docstring, milestone2.md Phase 2). ``SimpleImputer`` records a
    NaN in ``statistics_`` for a column it drops rather than imputes, which
    is what distinguishes "kept, imputed to this value" from "dropped
    entirely" — checked, not assumed, since the wrong list here would
    silently mislabel every remaining SHAP value with the wrong feature name.

    XGBoost has no imputer (native NaN handling), so every declared column
    survives unconditionally.
    """
    if model.preprocessor is None:
        return model.feature_columns

    imputer = getattr(model.preprocessor, "imputer", model.preprocessor)
    kept = ~np.isnan(imputer.statistics_)
    return [c for c, k in zip(model.feature_columns, kept, strict=True) if k]


def _shap_for_positive_class(model: FittedModel, x: np.ndarray) -> tuple[np.ndarray, float]:
    """Raw SHAP values and base value for the positive class.

    Output space depends on the model — see the module docstring: margin
    (log-odds) for logistic_regression and xgboost, probability directly for
    random_forest.

    SHAP's return shape differs by explainer and by sklearn/xgboost version —
    verified empirically rather than assumed (module docstring): XGBoost's
    binary ``TreeExplainer`` returns a plain 2D array with a scalar
    ``expected_value``; sklearn's ``RandomForestClassifier`` returns a 3D
    array with a trailing class axis and a 2-element ``expected_value``;
    ``LinearExplainer`` on logistic regression returns 2D with a scalar
    ``expected_value``. This normalizes all three to ``(n_rows, n_features)``
    plus a single float.
    """
    if model.name == "logistic_regression":
        explainer = shap.LinearExplainer(model.estimator, x)
    else:  # random_forest, xgboost
        explainer = shap.TreeExplainer(model.estimator)

    raw = np.asarray(explainer.shap_values(x))
    expected = np.atleast_1d(explainer.expected_value)

    if raw.ndim == 3:  # (n_rows, n_features, n_classes)
        raw = raw[:, :, 1]
        base = float(expected[1])
    else:
        base = float(expected[0])

    return raw, base


def shap_values(model: FittedModel, features: pl.DataFrame) -> pl.DataFrame:
    """SHAP values per feature per row, long format.

    Args:
        model: Must be ``logistic_regression``, ``random_forest`` or
            ``xgboost`` — not ``weighted_baseline`` (see module docstring).
        features: Rows to explain. Must have ``disease_id``, ``target_id``
            plus every column in ``model.feature_columns``.

    Returns:
        ``disease_id``, ``target_id``, ``feature``, ``shap_value``,
        ``base_value``. ``base_value`` is the same for every row of one call
        (the explainer's expected value); repeated rather than returned
        separately so the frame is self-contained — ``base_value +
        sum(shap_value over feature)`` reconstructs the model's raw margin
        output for that row (module docstring).

    Raises:
        ValueError: If *model* is ``weighted_baseline``, or *features* is empty.
    """
    _require_shap_compatible(model)
    if features.is_empty():
        raise ValueError("No rows to explain")

    x = _processed_matrix(model, features)
    raw, base = _shap_for_positive_class(model, x)
    feature_columns = _surviving_feature_columns(model)
    if len(feature_columns) != raw.shape[1]:
        raise AssertionError(
            f"SHAP output has {raw.shape[1]} columns but "
            f"{len(feature_columns)} surviving feature names were resolved — "
            "the two must match for feature-name attribution to be correct."
        )

    n_rows, n_features = raw.shape
    disease_ids = features.get_column("disease_id").to_numpy()
    target_ids = features.get_column("target_id").to_numpy()

    return pl.DataFrame(
        {
            "disease_id": np.repeat(disease_ids, n_features),
            "target_id": np.repeat(target_ids, n_features),
            "feature": feature_columns * n_rows,
            "shap_value": raw.reshape(-1).astype(np.float64),
            "base_value": base,
        }
    )


def global_feature_importance(model: FittedModel, features: pl.DataFrame) -> pl.DataFrame:
    """Global feature importance across all predictions (§20.1).

    Mean absolute SHAP value per feature, descending — the standard
    "how much does this feature move predictions, on average, in either
    direction" summary.

    Raises:
        ValueError: If *model* is ``weighted_baseline`` — its weights in
            ``configs/model.yaml`` already ARE the global importance,
            directly, with no approximation needed.
    """
    long = shap_values(model, features)
    return (
        long.group_by("feature")
        # Rounded for the same reason evaluate.py rounds every metric: the
        # underlying SHAP/numpy reduction's summation order isn't fixed
        # across runs (multi-threaded BLAS), so unrounded means differ in
        # the last couple of ULPs run to run, breaking byte-identical
        # reruns without changing anything that matters at this precision.
        .agg(pl.col("shap_value").abs().mean().round(10).alias("mean_abs_shap"))
        # Tied features (mean_abs_shap == 0.0 is common — a feature with no
        # observed variance in this fold contributes nothing) need a
        # deterministic secondary key, or their relative order depends on
        # group_by's hash-bucket iteration order, which varies run to run
        # (the same failure shape as evaluate.py's score/target_id tie-break).
        .sort(["mean_abs_shap", "feature"], descending=[True, False])
    )


def explain_target(
    model: FittedModel,
    features: pl.DataFrame,
    disease_id: str,
    target_id: str,
    *,
    top_n: int = 5,
) -> dict[str, Any]:
    """Structured explanation for one disease-target pair.

    Returns a dict carrying the score, the strongest positive and negative
    contributions, evidence present, **evidence missing**, source links and
    the standing limitations. The shape mirrors the example in Context.md
    §20.3.

    Args:
        features: The candidate table for *disease_id* — passed as the
            SHAP background for ML models (a single-row background gives
            SHAP nothing to compare against), or as the scoring frame for
            ``weighted_baseline``. Rows outside *disease_id* are ignored.
        top_n: How many positive/negative factors to report.

    Raises:
        KeyError: If ``(disease_id, target_id)`` is not in *features*.
    """
    disease_features = features.filter(pl.col("disease_id") == disease_id)
    row_frame = disease_features.filter(pl.col("target_id") == target_id)
    if row_frame.is_empty():
        raise KeyError(f"({disease_id!r}, {target_id!r}) not present in features")
    row = row_frame.row(0, named=True)

    score = model.predict_proba(row_frame)[0]

    if model.weighted_baseline is not None:
        scored = model.weighted_baseline.score(disease_features)
        target_explanation = model.weighted_baseline.explain(scored, target_id)
        positive = [
            {"feature": f"{DIMENSION_PREFIX}{dim}", "contribution": value}
            for dim, value in target_explanation.top_contributors(top_n)
            if value > 0
        ]
        # Weights are non-negative by construction (WeightedBaseline rejects
        # negative weights), so there is no "negative contribution" concept
        # for this model — an empty list here is correct, not a gap.
        negative: list[dict[str, Any]] = []
        evidence_present = [
            dim for dim, value in target_explanation.dimension_values.items() if value is not None
        ]
        evidence_missing = target_explanation.missing_dimensions
    else:
        long = shap_values(model, disease_features)
        target_shap = long.filter(pl.col("target_id") == target_id).sort(
            "shap_value", descending=True
        )
        positive = [
            {"feature": r["feature"], "contribution": r["shap_value"]}
            for r in target_shap.head(top_n).iter_rows(named=True)
            if r["shap_value"] > 0
        ]
        negative = [
            {"feature": r["feature"], "contribution": r["shap_value"]}
            for r in target_shap.tail(top_n).sort("shap_value").iter_rows(named=True)
            if r["shap_value"] < 0
        ]
        dim_columns = [c for c in disease_features.columns if c.startswith(DIMENSION_PREFIX)]
        evidence_present = [
            c.removeprefix(DIMENSION_PREFIX) for c in dim_columns if row.get(c) is not None
        ]
        evidence_missing = [
            c.removeprefix(MISSING_PREFIX)
            for c in disease_features.columns
            if c.startswith(MISSING_PREFIX) and row.get(c) == 1
        ]

    return {
        "target_id": target_id,
        "gene_symbol": row.get("gene_symbol"),
        "disease_id": disease_id,
        "disease_name": row.get("disease_name"),
        "model_name": model.name,
        "score": float(score),
        "top_positive_factors": positive,
        "top_negative_factors": negative,
        "evidence_present": evidence_present,
        "evidence_missing": evidence_missing,
        "source_references": source_references(target_id, disease_id),
        "limitations": list(STANDING_LIMITATIONS),
    }
