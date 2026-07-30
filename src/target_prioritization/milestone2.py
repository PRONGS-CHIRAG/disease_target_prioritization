"""Milestone 2 pipeline: multi-disease ML baseline (Context.md §37).

Orchestrates the ten §37 tasks end to end, the way ``milestone1.py`` does for
§36: build the multi-disease table, define labels, split, train, evaluate,
explain, compare. Lives in the package rather than ``scripts/`` for the same
reason Milestone 1's does — importable and testable (Context.md §34).

**Every model is scored out-of-fold under leave-one-disease-out** (Context.md
§19.4): for each held-out disease, the four trained models are fit only on
the other nine, and the three non-learned baselines are computed only from
the other nine's labels (``target_popularity``) or need no fitting at all
(``open_targets_overall_score``, ``random_ranking``). The ten folds' held-out
predictions are concatenated into one out-of-fold frame per model — the
standard cross-validated-prediction pattern — and evaluated exactly once,
per :func:`~target_prioritization.models.evaluate.evaluate_ranking`'s
per-disease-then-aggregate rule (§19.3).

**Every evaluation runs twice**: once against the primary labels, and once
against :func:`~target_prioritization.models.evaluate.novel_only_labels`,
which relabels every positive that recurs across diseases to negative. The
gap between the two results is milestone2.md §1's central finding made
measurable — a model whose ranking quality collapses on the novel-only pass
was substantially riding cross-disease target popularity, not
disease-specific signal.

Deliverables produced:

=================================================  ==========================
``data/processed/disease_target_features.parquet``  multi-disease feature table
``data/processed/labels.parquet``                   labels + provenance
``models/trained/xgboost_baseline.json``            final model, refit on all 10
``reports/evaluation/baseline_metrics.json``        every metric, every model
``reports/evaluation/baseline_report.md``            findings and limitations
=================================================  ==========================
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import polars as pl

from target_prioritization.config import (
    DiseaseSpec,
    FeaturesConfig,
    ModelConfig,
    load_diseases,
    load_features,
    load_model_config,
)
from target_prioritization.data import open_targets
from target_prioritization.data.labels import build_labels
from target_prioritization.features.build_features import LeakageError, build_feature_table
from target_prioritization.models.baselines import (
    score_open_targets_overall,
    score_random_ranking,
    score_target_popularity,
)
from target_prioritization.models.evaluate import (
    evaluate_ranking,
    leave_one_disease_out_splits,
    novel_only_labels,
)
from target_prioritization.models.explain import global_feature_importance
from target_prioritization.models.predict import score_targets
from target_prioritization.models.train import (
    FittedModel,
    save_fitted_xgboost,
    train_model,
    write_run_metadata,
)
from target_prioritization.utils.logging import get_logger
from target_prioritization.utils.paths import (
    DATA_PROCESSED,
    EVALUATION_DIR,
    MODEL_METADATA,
    TRAINED_MODELS,
    ensure_dir,
)

__all__ = [
    "BASELINE_NAMES",
    "FEATURES_NAME",
    "FOLD_MODELS_DIRNAME",
    "LABELS_NAME",
    "METRICS_NAME",
    "REPORT_NAME",
    "TRAINED_MODEL_NAMES",
    "XGBOOST_MODEL_NAME",
    "Milestone2Result",
    "fold_model_filename",
    "run_leakage_probe",
    "run_milestone_2",
]

log = get_logger(__name__)

# Trained in this order, matching configs/model.yaml `models` (Context.md §17):
# a later model that cannot beat an earlier one flags a data problem, not a
# modelling one.
TRAINED_MODEL_NAMES = ["weighted_baseline", "logistic_regression", "random_forest", "xgboost"]

# Non-learned comparison baselines (models/baselines.py, Context.md §37 task 10).
BASELINE_NAMES = ["open_targets_overall_score", "random_ranking", "target_popularity"]

ALL_METHOD_NAMES = [*TRAINED_MODEL_NAMES, *BASELINE_NAMES]

FEATURES_NAME = "disease_target_features.parquet"
LABELS_NAME = "labels.parquet"
XGBOOST_MODEL_NAME = "xgboost_baseline.json"
METRICS_NAME = "baseline_metrics.json"
REPORT_NAME = "baseline_report.md"

# Milestone 3 (Context.md §21): held-out fold models, one per disease, saved
# alongside the all-disease refit above. `xgboost_baseline.json` is in-sample
# for every disease it can score — the app needs the model that EXCLUDED each
# disease, so a displayed score matches what baseline_metrics.json's
# leave-one-disease-out numbers actually measured. See milestone3_plan.md §2.1.
FOLD_MODELS_DIRNAME = "folds"


def fold_model_filename(disease_key: str) -> str:
    """Filename (not full path) for the fold model that held out *disease_key*."""
    return f"xgboost_lodo_{disease_key}.json"


@dataclass(slots=True)
class Milestone2Result:
    """Everything the milestone produced, for the report and the notebook."""

    features: pl.DataFrame
    labels: pl.DataFrame
    scored_by_model: dict[str, pl.DataFrame]
    evaluation: dict[str, dict[str, Any]]
    evaluation_novel_only: dict[str, dict[str, Any]]
    literature_ablation: dict[str, Any]
    final_xgboost: FittedModel
    global_feature_importance: pl.DataFrame
    provenance: dict[str, Any] = field(default_factory=dict)
    # disease_id -> path of the fold model that held that disease out
    # (Milestone 3, Context.md §21). Empty when write_outputs=False, since the
    # fold models are only written to disk, never kept as in-memory objects
    # for all ten folds at once.
    fold_model_paths: dict[str, str] = field(default_factory=dict)

    def aggregate(self, metric: str, novel_only: bool = False) -> dict[str, float | None]:
        source = self.evaluation_novel_only if novel_only else self.evaluation
        return {name: result["aggregate"].get(metric) for name, result in source.items()}

    @property
    def acceptance_beats_random(self) -> dict[str, tuple[int, int]]:
        """Per evaluated model (excluding random_ranking itself): (diseases
        won, diseases total) on NDCG@10 against random_ranking. Task-1 of the
        acceptance check.

        Iterates over whatever is actually in ``self.evaluation`` rather than
        the canonical :data:`ALL_METHOD_NAMES` list, so this works correctly
        on a partial result too (e.g. in tests) rather than assuming every
        one of the seven methods was necessarily evaluated.
        """
        random_per_disease = self.evaluation["random_ranking"]["per_disease"]
        out: dict[str, tuple[int, int]] = {}
        for name, result in self.evaluation.items():
            if name == "random_ranking":
                continue
            per_disease = result["per_disease"]
            wins = 0
            total = 0
            for disease_id, row in per_disease.items():
                other = random_per_disease.get(disease_id, {})
                a, b = row.get("ndcg_at_10"), other.get("ndcg_at_10")
                if a is None or b is None:
                    continue
                total += 1
                if a > b:
                    wins += 1
            out[name] = (wins, total)
        return out

    @property
    def acceptance_passed(self) -> bool:
        """§37 acceptance check 1: every model beats random_ranking on NDCG@10
        in >= 9 of 10 diseases (milestone2.md §6). Checks 2, 4 and 5 are
        report/process requirements, not exit-code conditions — see
        milestone2.md §6 for why check 2 in particular cannot be one."""
        return all(wins >= 9 for wins, total in self.acceptance_beats_random.values() if total)


def _weights_for(model_name: str, model_config: ModelConfig) -> dict[str, Any]:
    if model_name == "weighted_baseline":
        return dict(model_config.milestone_1_weights)
    return dict(model_config.models[model_name]["params"])


def _drop_literature_columns(features: pl.DataFrame, config: FeaturesConfig) -> pl.DataFrame:
    """Features with every literature-derived column removed (Context.md §32.2).

    Milestone 1 found literature to be simultaneously the most common and
    least discriminating signal (milestone1.md §3: 71% of Parkinson's
    candidates had literature evidence and nothing else). This measures
    whether that finding survives into the ML models under proper
    leave-one-disease-out evaluation, rather than Milestone 1's rank-movement
    proxy.

    ``n_evidence_types`` / ``dim__evidence_diversity`` (genetics.py,
    ``build_evidence_diversity``) are dropped too, not just the direct
    ``assoc_ds__*`` literature columns. Both are a count of distinct
    datasources per target *including* the literature datasources — so a
    model can recover "this target has literature evidence" from the
    diversity term even with the direct columns gone, silently understating
    literature's measured contribution. Dropping the diversity term as well
    means this ablation also removes any genuine non-literature diversity
    signal, so the reported effect is the literature contribution net of
    that loss, not literature in isolation.
    """
    datasources = config.evidence_dimensions["literature"].datasources
    drop = {f"assoc_ds__{ds}_{suffix}" for ds in datasources for suffix in ("score", "evidence_count")}
    drop |= {"dim__literature", "missing__literature", "n_evidence_types", "dim__evidence_diversity"}
    return features.drop([c for c in drop if c in features.columns])


def run_leakage_probe(features: pl.DataFrame, labels: pl.DataFrame, config: FeaturesConfig) -> None:
    """Deliberately inject a denylisted column and confirm training rejects it.

    Mirrors Milestone 1's probe (milestone1.md §4): a guard that has never
    been shown to fire is not known to work. Run against the REAL feature
    table, not a synthetic one — ``tests/test_train.py`` already covers this
    with synthetic data, but this is what proves the guard still fires on
    the actual production pipeline, on every run, not just in CI.

    Raises:
        AssertionError: If training does NOT raise — i.e. the probe failed
            to detect the leak, which would mean the guard is not working.
    """
    leaking = features.with_columns(pl.lit(0.99).alias("assoc_ds__clinical_precedence_score"))
    try:
        train_model(leaking, labels, "logistic_regression", {"max_iter": 100}, config=config)
    except LeakageError:
        log.info("leakage_probe_passed", note="deliberately-injected leak was correctly rejected")
        return
    raise AssertionError(
        "Leakage probe FAILED: training did not reject a deliberately-injected "
        "assoc_ds__clinical_precedence_score column. The guard is not working."
    )


def run_milestone_2(
    diseases: list[DiseaseSpec] | None = None,
    *,
    write_outputs: bool = True,
) -> Milestone2Result:
    """Run the full Milestone 2 pipeline.

    Args:
        diseases: Diseases to include. Defaults to every resolved disease in
            ``configs/diseases.yaml`` (all ten).
        write_outputs: Write the parquet/model/metadata deliverables to disk.

    Returns:
        A :class:`Milestone2Result` carrying every model's out-of-fold
        predictions, evaluation (primary and novel-only), the literature
        ablation, and the final production XGBoost model.
    """
    diseases = diseases if diseases is not None else load_diseases().resolved
    model_config = load_model_config()
    features_config = load_features()

    log.info("milestone_2_start", n_diseases=len(diseases))

    con = open_targets.connect()
    try:
        features, feature_provenance = build_feature_table(diseases, features_config, con=con)
        labels, label_provenance = build_labels(diseases, features_config, con=con)
    finally:
        con.close()

    run_leakage_probe(features, labels, features_config)

    splits = leave_one_disease_out_splits(features)
    disease_ids = sorted(features.get_column("disease_id").unique().to_list())
    key_by_disease_id = {d.efo_id: d.key for d in diseases}

    scored_frames: dict[str, list[pl.DataFrame]] = {name: [] for name in ALL_METHOD_NAMES}
    literature_ablated_frames: list[pl.DataFrame] = []
    fold_model_paths: dict[str, str] = {}

    for (train_idx, test_idx), disease_id in zip(splits, disease_ids, strict=True):
        train_features = features[train_idx]
        test_features = features[test_idx]
        train_labels = labels.filter(pl.col("disease_id") != disease_id)

        for name in TRAINED_MODEL_NAMES:
            model = train_model(
                train_features,
                train_labels,
                name,
                _weights_for(name, model_config),
                seed=model_config.random_seed,
                config=features_config,
            )
            scored_frames[name].append(score_targets(model, test_features))

            # Milestone 3 (Context.md §21): persist the fold model that held
            # THIS disease out, alongside the final refit below — this is
            # what lets the app show a held-out score rather than the
            # in-sample one (milestone3_plan.md §2.1).
            if name == "xgboost" and write_outputs:
                fold_path = TRAINED_MODELS / FOLD_MODELS_DIRNAME / fold_model_filename(
                    key_by_disease_id[disease_id]
                )
                save_fitted_xgboost(model, fold_path)
                fold_model_paths[disease_id] = str(fold_path.relative_to(TRAINED_MODELS.parent))

        scored_frames["open_targets_overall_score"].append(
            score_open_targets_overall(test_features, disease_id)
        )
        scored_frames["random_ranking"].append(
            score_random_ranking(test_features, disease_id, seed=model_config.random_seed)
        )
        scored_frames["target_popularity"].append(score_target_popularity(test_features, labels, disease_id))

        # Literature ablation (Context.md §32.2), XGBoost only — the model
        # that won the primary comparison is the one worth ablating.
        train_no_lit = _drop_literature_columns(train_features, features_config)
        test_no_lit = _drop_literature_columns(test_features, features_config)
        ablated_model = train_model(
            train_no_lit,
            train_labels,
            "xgboost",
            model_config.models["xgboost"]["params"],
            seed=model_config.random_seed,
            config=features_config,
        )
        literature_ablated_frames.append(score_targets(ablated_model, test_no_lit))

        log.info("lodo_fold_done", held_out=disease_id)

    combined = {name: pl.concat(frames, how="vertical") for name, frames in scored_frames.items()}
    literature_ablated = pl.concat(literature_ablated_frames, how="vertical")

    ranking_metrics = model_config.evaluation.ranking_metrics
    classification_metrics = model_config.evaluation.classification_metrics
    novel_labels = novel_only_labels(labels)

    evaluation = {
        name: evaluate_ranking(scored, labels, ranking_metrics, classification_metrics)
        for name, scored in combined.items()
    }
    evaluation_novel_only = {
        name: evaluate_ranking(scored, novel_labels, ranking_metrics, classification_metrics)
        for name, scored in combined.items()
    }
    literature_ablation = {
        "with_literature": evaluation["xgboost"]["aggregate"],
        "without_literature": evaluate_ranking(literature_ablated, labels, ranking_metrics, classification_metrics)[
            "aggregate"
        ],
    }

    # Final production model (§37 deliverable): refit on ALL ten diseases,
    # not just nine — LODO fitting exists to evaluate honestly, not to ship.
    final_xgboost = train_model(
        features,
        labels,
        "xgboost",
        model_config.models["xgboost"]["params"],
        seed=model_config.random_seed,
        config=features_config,
    )

    # SHAP global importance (§37 task 9) computed here rather than left as a
    # library the pipeline never calls — the model card's importance table is
    # sourced from baseline_metrics.json's `global_feature_importance` so it
    # is regenerated on every run instead of drifting from whichever ad-hoc
    # run last produced it.
    feature_importance = global_feature_importance(final_xgboost, features)

    provenance = {
        "n_diseases": len(diseases),
        "disease_ids": disease_ids,
        "feature_table": feature_provenance,
        "labels": {k: v for k, v in label_provenance.items() if k != "diseases"},
        "labels_per_disease": label_provenance["diseases"],
        "random_seed": model_config.random_seed,
        "dataset_version": open_targets.release_tag(),
        "extraction_date": datetime.now(UTC).date().isoformat(),
        "split_strategy": model_config.split.strategy,
        "models": {
            name: (
                model_config.milestone_1_weights
                if name == "weighted_baseline"
                else model_config.models[name]["params"]
            )
            for name in TRAINED_MODEL_NAMES
        },
        "fold_model_paths": fold_model_paths,
    }

    result = Milestone2Result(
        features=features,
        labels=labels,
        scored_by_model=combined,
        evaluation=evaluation,
        evaluation_novel_only=evaluation_novel_only,
        literature_ablation=literature_ablation,
        final_xgboost=final_xgboost,
        global_feature_importance=feature_importance,
        provenance=provenance,
        fold_model_paths=fold_model_paths,
    )

    log.info(
        "milestone_2_evaluation",
        ndcg_at_10=result.aggregate("ndcg_at_10"),
        ndcg_at_10_novel_only=result.aggregate("ndcg_at_10", novel_only=True),
        acceptance_passed=result.acceptance_passed,
        beats_random=result.acceptance_beats_random,
    )

    if write_outputs:
        ensure_dir(DATA_PROCESSED)
        features_path = DATA_PROCESSED / FEATURES_NAME
        features.write_parquet(features_path)
        (features_path.with_name(features_path.name + ".provenance.json")).write_text(
            json.dumps(feature_provenance, indent=2, sort_keys=True, default=str) + "\n"
        )

        labels_path = DATA_PROCESSED / LABELS_NAME
        labels.write_parquet(labels_path)
        (labels_path.with_name(labels_path.name + ".provenance.json")).write_text(
            json.dumps(label_provenance, indent=2, sort_keys=True, default=str) + "\n"
        )

        ensure_dir(TRAINED_MODELS)
        model_path = TRAINED_MODELS / XGBOOST_MODEL_NAME
        final_xgboost.estimator.save_model(str(model_path))
        log.info("wrote_model", path=str(model_path))

        ensure_dir(EVALUATION_DIR)
        metrics_path = EVALUATION_DIR / METRICS_NAME
        metrics_payload = {
            "evaluation": evaluation,
            "evaluation_novel_only": evaluation_novel_only,
            "literature_ablation": literature_ablation,
            "global_feature_importance": feature_importance.to_dicts(),
            "acceptance_beats_random": {k: list(v) for k, v in result.acceptance_beats_random.items()},
            "acceptance_passed": result.acceptance_passed,
        }
        metrics_path.write_text(json.dumps(metrics_payload, indent=2, sort_keys=True, default=str) + "\n")
        log.info("wrote_metrics", path=str(metrics_path))

        ensure_dir(MODEL_METADATA)
        run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        write_run_metadata(
            MODEL_METADATA / f"milestone2_{run_id}.json",
            {
                "run_id": run_id,
                **provenance,
                "aggregate_metrics": {name: ev["aggregate"] for name, ev in evaluation.items()},
                "code_commit": _current_git_commit(),
                "limitations": [
                    "Cross-disease target popularity accounts for most of the ranking signal "
                    "for most models (milestone2.md §1) — see evaluation_novel_only.",
                    "Labels are an imperfect proxy for therapeutic value (Context.md §15).",
                    "Ten diseases only; generalisation to unconfigured diseases is untested.",
                ],
            },
        )

    return result


def _current_git_commit() -> str | None:
    """Best-effort git commit hash for the run-metadata record (Context.md §33)."""
    import subprocess

    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL, text=True
        ).strip()
    except Exception:
        return None
