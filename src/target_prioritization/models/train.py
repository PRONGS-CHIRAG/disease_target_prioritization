"""Model training (Context.md §17, §33).

Order matters: logistic regression, then random forest, then XGBoost, each
compared against the weighted baseline. A boosted model that cannot beat the
transparent baseline usually indicates a data problem rather than a modelling
one, and skipping ahead hides that.

Every run must record what Context.md §33 requires — dataset version, extraction
date, disease list, feature and label definitions, split, parameters, seed,
metrics, code commit and known limitations — into ``models/metadata/``.

**Fold-fitted preprocessing.** :func:`train_model` fits imputation and
scaling fresh on whatever *features* it is given — it has no notion of a
"fold" itself. Leave-one-disease-out fitting is achieved entirely by what the
*caller* passes in: slice ``features``/``labels`` to the training rows before
calling this, then call ``.predict_proba`` on the held-out rows. Fitting the
imputer on the full dataset once and reusing it across every fold would leak
the held-out disease's value distribution into training — a quieter version
of the same leakage this project's guard exists to catch elsewhere.

**Null handling differs by model, because the models differ in what they can
consume.** XGBoost takes NaN natively — and should: Context.md §32.3 treats a
null as "not studied", which XGBoost can learn to split on directly.
Logistic regression and random forest cannot accept NaN at all, so both get
median imputation; logistic regression additionally gets standard scaling,
which the other two don't need (trees split on order, not on scale).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any, Protocol

import numpy as np
import polars as pl
import xgboost as xgb
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from target_prioritization.config import FeaturesConfig, load_features
from target_prioritization.features.build_features import select_feature_columns
from target_prioritization.models.baseline import SCORE_COLUMN, WeightedBaseline
from target_prioritization.utils.logging import get_logger

__all__ = [
    "FittedModel",
    "TrainedModel",
    "load_fitted_xgboost",
    "save_fitted_xgboost",
    "train_model",
    "write_run_metadata",
]

log = get_logger(__name__)

# Trained in this order (configs/model.yaml `models`); a later model that
# cannot beat an earlier one flags a data problem, not a modelling one.
MODEL_ORDER = ["weighted_baseline", "logistic_regression", "random_forest", "xgboost"]


class TrainedModel(Protocol):
    """Minimal interface the rest of the pipeline depends on."""

    def predict_proba(self, features: pl.DataFrame) -> list[float]: ...


@dataclass(slots=True)
class FittedModel:
    """A trained model plus exactly what's needed to score new rows the same
    way it was trained: which feature columns, in which order, through which
    fitted preprocessing (if any).

    ``weighted_baseline`` is not really "fitted" in the sklearn sense — it
    wraps Milestone 1's :class:`WeightedBaseline` so the rule-based score
    goes through the identical ``predict_proba`` interface as every ML model,
    letting one LODO loop (Phase 7) drive all four without special-casing.
    """

    name: str
    feature_columns: list[str]
    estimator: Any = None
    preprocessor: Any = None
    weighted_baseline: WeightedBaseline | None = None
    params: dict[str, Any] = field(default_factory=dict)

    def predict_proba(self, features: pl.DataFrame) -> list[float]:
        if self.weighted_baseline is not None:
            scored = self.weighted_baseline.score(features)
            return scored.get_column(SCORE_COLUMN).to_list()

        x = features.select(self.feature_columns).to_numpy()
        if self.preprocessor is not None:
            x = self.preprocessor.transform(x)
        proba = self.estimator.predict_proba(x)[:, 1]
        return [float(p) for p in proba]


def _positive_rate_scale_pos_weight(y: np.ndarray) -> float:
    """XGBoost's `scale_pos_weight`, computed from THIS fold's training
    labels only (never from the full dataset) — the same fold-only rule
    every other piece of fold-fitted state in this module follows."""
    n_positive = int(y.sum())
    n_negative = len(y) - n_positive
    return n_negative / n_positive if n_positive else 1.0


def train_model(
    features: pl.DataFrame,
    labels: pl.DataFrame,
    model_name: str,
    params: dict[str, Any] | None = None,
    *,
    seed: int = 42,
    config: FeaturesConfig | None = None,
) -> FittedModel:
    """Train one model on whatever rows *features*/*labels* contain.

    No disease-grouping logic lives here — pass in an already-sliced
    training fold (see the module docstring). Rows with a null label
    (Context.md §34 — UNKNOWN clinical stage) are dropped before fitting;
    they are neither positive nor negative.

    Args:
        features: Feature matrix, including ``disease_id``/``target_id`` for
            the join and every ``assoc_ds__``/``dim__``/``prio__``/etc.
            feature column. Re-checked with ``assert_no_leakage`` (via
            :func:`~target_prioritization.features.build_features.select_feature_columns`)
            immediately before fitting — checking at both this boundary and
            feature-assembly time is cheap; a leaked label is not.
        labels: ``disease_id``, ``target_id``, ``label``.
        model_name: One of :data:`MODEL_ORDER`.
        params: Model hyperparameters, e.g. ``configs/model.yaml``
            ``models.<name>.params``. For ``weighted_baseline`` this IS the
            weight dict (``milestone_1_weights``), not sklearn-style
            hyperparameters.
        seed: Passed to every model with a random component. Not used by
            ``weighted_baseline``, which has none.

    Raises:
        LeakageError: If a denylisted column reaches the matrix.
        ValueError: If *model_name* is not recognised, or
            ``weighted_baseline`` is requested with no weights.
    """
    config = config or load_features()

    if model_name == "weighted_baseline":
        weights = params or {}
        if not weights:
            raise ValueError(
                "weighted_baseline requires weights via `params` "
                "(configs/model.yaml milestone_1_weights)"
            )
        return FittedModel(
            name=model_name,
            feature_columns=[],
            weighted_baseline=WeightedBaseline(weights),
            params=dict(weights),
        )

    joined = features.join(
        labels.filter(pl.col("label").is_not_null()).select(["disease_id", "target_id", "label"]),
        on=["disease_id", "target_id"],
        how="inner",
    )
    if joined.is_empty():
        raise ValueError("No labelled rows to train on after joining features and labels")

    # check_stale=False: `joined` comes from build_feature_table, which
    # already ran drop_denylisted_datasources — the denylisted columns are
    # correctly absent here, not stale. Liveness against the unfiltered
    # source columns was already verified once, upstream, when the feature
    # table was built (build_features.verify_guard_liveness).
    feature_columns = select_feature_columns(joined, guard=config.leakage_guard, check_stale=False)
    x = joined.select(feature_columns).to_numpy()
    y = joined.get_column("label").to_numpy().astype(int)

    clf_params = dict(params or {})

    if model_name == "logistic_regression":
        preprocessor = SimpleImputer(strategy="median")
        x_imputed = preprocessor.fit_transform(x)
        scaler = StandardScaler()
        x_processed = scaler.fit_transform(x_imputed)
        # Compose into one transformer object so predict_proba only has one
        # `.transform()` call to make, in the fitted order.
        pipeline = _ImputeThenScale(preprocessor, scaler)
        estimator = LogisticRegression(random_state=seed, **clf_params)
        estimator.fit(x_processed, y)
        return FittedModel(
            name=model_name,
            feature_columns=feature_columns,
            estimator=estimator,
            preprocessor=pipeline,
            params=clf_params,
        )

    if model_name == "random_forest":
        preprocessor = SimpleImputer(strategy="median")
        x_processed = preprocessor.fit_transform(x)
        estimator = RandomForestClassifier(random_state=seed, **clf_params)
        estimator.fit(x_processed, y)
        return FittedModel(
            name=model_name,
            feature_columns=feature_columns,
            estimator=estimator,
            preprocessor=preprocessor,
            params=clf_params,
        )

    if model_name == "xgboost":
        clf_params.pop("scale_pos_weight", None)  # always recomputed per fold, below
        scale_pos_weight = _positive_rate_scale_pos_weight(y)
        estimator = xgb.XGBClassifier(
            random_state=seed, scale_pos_weight=scale_pos_weight, **clf_params
        )
        estimator.fit(x, y)  # raw x, NaN and all — XGBoost handles it natively
        return FittedModel(
            name=model_name,
            feature_columns=feature_columns,
            estimator=estimator,
            preprocessor=None,
            params={**clf_params, "scale_pos_weight": scale_pos_weight},
        )

    raise ValueError(f"Unknown model_name {model_name!r}; expected one of {MODEL_ORDER}")


@dataclass(slots=True)
class _ImputeThenScale:
    """Compose a fitted imputer and a fitted scaler behind one `.transform`."""

    imputer: SimpleImputer
    scaler: StandardScaler

    def transform(self, x: np.ndarray) -> np.ndarray:
        return np.asarray(self.scaler.transform(self.imputer.transform(x)))


def write_run_metadata(path: Path, metadata: dict[str, Any]) -> None:
    """Persist the reproducibility record for a training run (§33)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(metadata, indent=2, sort_keys=True, default=str) + "\n")
    log.info("run_metadata_written", path=str(path))


def save_fitted_xgboost(model: FittedModel, path: Path) -> None:
    """Persist an XGBoost :class:`FittedModel` (Milestone 3, Context.md §21).

    Milestone 2 only ever persisted the final model refit on all ten
    diseases (``xgboost_baseline.json``) — good for production scoring, but
    its predictions on any of the ten configured diseases are in-sample: that
    disease's own rows were part of its training data. The app instead needs,
    per disease, the fold model that held that disease out, so a displayed
    score matches what ``baseline_metrics.json``'s leave-one-disease-out
    numbers actually measured.

    Only ``xgboost`` is supported. ``weighted_baseline`` needs no
    persistence — it is reconstructed from ``configs/model.yaml`` weights on
    every call. ``logistic_regression``/``random_forest`` have no
    XGBoost-style native single-file format and are out of scope for the app
    (Milestone 2 §2's primary/secondary choice was weighted_baseline and
    xgboost only).

    Writes *path* (the booster, via XGBoost's own serialization) plus a
    ``<path>.meta.json`` sidecar recording ``feature_columns`` (the column
    order ``predict_proba`` requires) and ``params`` (including the
    per-fold ``scale_pos_weight`` :func:`train_model` computed from that
    fold's own labels — the one field that legitimately differs between
    folds, and worth checking when confirming ten distinct models were
    actually saved rather than ten copies of one).

    Raises:
        ValueError: If *model* is not an ``xgboost`` FittedModel.
    """
    if model.name != "xgboost":
        raise ValueError(f"save_fitted_xgboost only supports xgboost models, got {model.name!r}")
    path.parent.mkdir(parents=True, exist_ok=True)
    model.estimator.save_model(str(path))
    meta_path = path.with_name(path.name + ".meta.json")
    meta_path.write_text(
        json.dumps(
            {"name": model.name, "feature_columns": model.feature_columns, "params": model.params},
            indent=2,
            sort_keys=True,
            default=str,
        )
        + "\n"
    )
    log.info("fitted_xgboost_saved", path=str(path))


@cache
def load_fitted_xgboost(path: Path) -> FittedModel:
    """Load an XGBoost :class:`FittedModel` written by :func:`save_fitted_xgboost`.

    Cached by *path* (milestone5_plan.md §4.2) — the one exception to that
    plan's "services stays frozen" boundary, added because
    ``services.evidence_summary._xgboost_held_out_items`` calls this
    directly with no injection seam, unlike ``build_evidence_card``'s
    ``features=``/``weights=``/``diseases=`` parameters. Without it, a
    long-running API process reloads a ~2.9 MB booster from disk on every
    evidence request. A *process restart* is required to pick up a
    retrained model at the same path — acceptable for a server process, the
    same tradeoff the parquet caches in ``api/cache.py`` make.

    Raises:
        FileNotFoundError: If *path* or its ``.meta.json`` sidecar is missing.
    """
    meta_path = path.with_name(path.name + ".meta.json")
    if not path.exists() or not meta_path.exists():
        raise FileNotFoundError(f"Fitted XGBoost model not found at {path} (with sidecar {meta_path})")
    meta = json.loads(meta_path.read_text())
    estimator = xgb.XGBClassifier()
    estimator.load_model(str(path))
    return FittedModel(
        name="xgboost",
        feature_columns=meta["feature_columns"],
        estimator=estimator,
        preprocessor=None,
        params=meta.get("params", {}),
    )
