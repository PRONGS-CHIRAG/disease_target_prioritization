"""Shared state, caching and scenario-weight presets for the Streamlit app
(Context.md §21, §38.5).

Every page reads the currently selected disease from
``st.session_state["disease_id"]``, set by the sidebar picker in
``streamlit_app.py``. Kept in one module rather than duplicated per page so
the three pages cannot drift on what "selected disease" or "current weights"
means.

Caching: ``st.cache_data`` for the processed parquets (a few tens of MB,
read-only, identical across sessions) and ``st.cache_resource`` for the
fold models (the objects themselves — an ``xgb.XGBClassifier`` isn't a
plain data value Streamlit should hash/copy). Both are keyed by the
argument that actually varies (``disease_id``), so switching diseases in
the sidebar loads exactly the one new fold model rather than all ten.
"""

from __future__ import annotations

import polars as pl
import streamlit as st

from target_prioritization.config import DiseaseSpec, load_diseases
from target_prioritization.milestone2 import FOLD_MODELS_DIRNAME, fold_model_filename
from target_prioritization.models.train import FittedModel, load_fitted_xgboost
from target_prioritization.services.disease_search import DiseaseSearchResult, search_diseases
from target_prioritization.utils.paths import DATA_PROCESSED, TRAINED_MODELS

LIMITATIONS = [
    "A high score does not prove a target will produce an effective drug (Context.md §31.1).",
    "Database evidence is incomplete and biased toward well-studied genes (Context.md §32.2).",
    "Association does not prove causation.",
    "Absence of evidence is not evidence of absence — check evidence completeness before "
    "reading a low score as a weak target (Context.md §32.3).",
    "Cross-disease target popularity drives most of the XGBoost score for most targets "
    "(milestone2.md §1) — a high XGBoost score is a weaker claim than the same score's "
    "novel-only counterpart would be.",
    "Predictions change when the underlying databases are updated (Context.md §32.7).",
    "This is a research-support prototype, not for medical diagnosis or treatment decisions.",
]

# Scenario weight presets (Context.md §38.5, Project_info.md §21.4) mapped onto
# the five dimensions this baseline actually scores (configs/model.yaml
# milestone_1_weights) — Project_info.md §21.4's own examples reference a
# "clinical" and a "safety" weight, neither of which exists here: clinical
# evidence IS the training label (denylisted, never a feature — Context.md
# §16) and safety has no scored dimension at all (Context.md §14.7 forbids
# presenting it as a validated toxicity prediction). "Clinical-development"
# is approximated by druggability, the closest buildable proxy for "can this
# be drugged near-term". "Safety-first" is approximated by leaving the
# default weights and forcing `exclude_safety_concerns` on instead of
# inventing a safety weight that doesn't exist.
SCENARIO_PRESETS: dict[str, dict[str, float]] = {
    "Research-focused (genetics-first)": {
        "genetics": 0.45,
        "evidence_diversity": 0.25,
        "functional": 0.15,
        "literature": 0.10,
        "druggability": 0.05,
    },
    "Clinical-development-focused": {
        "genetics": 0.20,
        "evidence_diversity": 0.10,
        "functional": 0.15,
        "literature": 0.15,
        "druggability": 0.40,
    },
    "Novel-target-focused": {
        "genetics": 0.40,
        "evidence_diversity": 0.30,
        "functional": 0.25,
        "literature": 0.0,
        "druggability": 0.05,
    },
}

# Rendered so the UI never claims a scenario changed the score when it only
# changed a filter — Safety-first is exactly that case.
SAFETY_FIRST_LABEL = "Safety-first (default weights + hide safety concerns)"
CUSTOM_LABEL = "Custom"


@st.cache_data
def get_diseases() -> list[DiseaseSpec]:
    return load_diseases().resolved


@st.cache_data
def get_search_results(query: str) -> list[DiseaseSearchResult]:
    return search_diseases(query)


@st.cache_data
def get_features() -> pl.DataFrame:
    path = DATA_PROCESSED / "disease_target_features.parquet"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. Run scripts/train_model.py first.")
    return pl.read_parquet(path)


@st.cache_data
def get_app_data() -> pl.DataFrame:
    path = DATA_PROCESSED / "app_scores.parquet"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. Run scripts/build_app_data.py first.")
    return pl.read_parquet(path)


@st.cache_resource
def get_fold_model(disease_key: str) -> FittedModel:
    """The held-out XGBoost fold model for one disease — cached as a
    RESOURCE (the fitted estimator, not a plain value) so switching diseases
    doesn't re-parse the same booster file on every rerun."""
    return load_fitted_xgboost(TRAINED_MODELS / FOLD_MODELS_DIRNAME / fold_model_filename(disease_key))


def disease_by_id(disease_id: str) -> DiseaseSpec:
    for disease in get_diseases():
        if disease.efo_id == disease_id:
            return disease
    raise KeyError(f"{disease_id!r} is not a configured disease")


def render_limitations_sidebar() -> None:
    with st.sidebar:
        st.header("Limitations")
        for item in LIMITATIONS:
            st.markdown(f"- {item}")


def render_disease_picker() -> str | None:
    """Sidebar disease search (Context.md §21) — sets and returns
    ``st.session_state["disease_id"]``.

    The search space is only the ten configured diseases
    (services.disease_search's module docstring); an unmatched query shows
    the honest "not in the precomputed set" message rather than an empty
    table with no explanation.
    """
    with st.sidebar:
        st.header("Disease")
        query = st.text_input("Search disease", key="disease_query", placeholder="e.g. Parkinson's disease")
        results = get_search_results(query)
        if not results:
            st.warning("No disease found in the precomputed set of ten configured diseases.")
            return st.session_state.get("disease_id")

        labels = [r.name for r in results]
        default_index = 0
        if (current := st.session_state.get("disease_id")) is not None:
            ids = [r.disease_id for r in results]
            if current in ids:
                default_index = ids.index(current)

        chosen_label = st.selectbox("Matching diseases", labels, index=default_index)
        chosen = results[labels.index(chosen_label)]
        st.session_state["disease_id"] = chosen.disease_id
        if chosen.n_associated_targets is not None:
            st.caption(f"{chosen.n_associated_targets:,} candidate targets")
        return chosen.disease_id


def get_active_weights() -> dict[str, float]:
    """Current scenario weights (Context.md §38.5), defaulting to
    Milestone 1's weights until a page sets ``st.session_state["weights"]``."""
    from target_prioritization.config import load_model_config

    return st.session_state.get("weights") or dict(load_model_config().milestone_1_weights)
