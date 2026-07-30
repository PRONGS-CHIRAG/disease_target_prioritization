"""Target ranking page (Context.md §21, Project_info.md §38.2, §38.3, §38.5).

The ranked table, the buildable filters, and the scenario weight controls.
Existing-drug / clinical-stage information deliberately does NOT appear as
a column or a filter here — those are exactly the evidence the training
label is built from (milestone3_plan.md §3), and a sortable "existing drug
status" column on the ranking table would let a user sort by the answer
key without realising it. That information is shown on the Target evidence
page instead, explicitly labelled as the training label.
"""

from __future__ import annotations

import polars as pl
import streamlit as st
from common import (
    CUSTOM_LABEL,
    SAFETY_FIRST_LABEL,
    SCENARIO_PRESETS,
)

from target_prioritization.config import load_model_config
from target_prioritization.services.target_ranking import (
    APP_EVIDENCE_CATEGORIES,
    RankingFilters,
    normalize_weights,
    rank_for_disease,
)

_DIMENSION_LABELS = {
    "genetics": "Genetics",
    "evidence_diversity": "Evidence diversity",
    "functional": "Functional / biology",
    "literature": "Literature",
    "druggability": "Druggability",
}


def _render_scenario_controls() -> tuple[dict[str, float], bool]:
    st.subheader("Scenario weights")
    st.caption(
        "Context.md §38.5 — change what the weighted-baseline score rewards. The held-out "
        "XGBoost score does not change: its weights cannot be adjusted at inference."
    )
    default_weights = dict(load_model_config().milestone_1_weights)
    scenario_names = [*SCENARIO_PRESETS, SAFETY_FIRST_LABEL, CUSTOM_LABEL]
    choice = st.selectbox("Scenario", scenario_names, index=0)

    force_exclude_safety = choice == SAFETY_FIRST_LABEL

    if choice in SCENARIO_PRESETS:
        weights = SCENARIO_PRESETS[choice]
    elif choice == SAFETY_FIRST_LABEL:
        weights = default_weights
    else:
        st.caption("Sliders need not sum to 1.0 — they are normalized automatically; the normalized "
                   "values used are shown below.")
        raw = {
            dim: st.slider(_DIMENSION_LABELS[dim], 0.0, 1.0, default_weights.get(dim, 0.2), 0.05)
            for dim in _DIMENSION_LABELS
        }
        weights = normalize_weights(raw)
        st.write({_DIMENSION_LABELS[d]: round(w, 3) for d, w in weights.items()})

    st.session_state["weights"] = weights
    return weights, force_exclude_safety


def _render_filters(force_exclude_safety: bool) -> RankingFilters:
    st.subheader("Filters")
    st.caption(
        "Relevant-tissue and target-family filters are not available in this release "
        "(need GTEx / target.targetClass — Context.md §28 Step 9)."
    )
    col1, col2 = st.columns(2)
    with col1:
        min_genetics = st.slider("Minimum genetics evidence", 0.0, 1.0, 0.0, 0.05)
        require_druggable = st.checkbox("Require small-molecule druggability", value=False)
    with col2:
        min_completeness = st.slider(
            f"Minimum evidence completeness (of {len(APP_EVIDENCE_CATEGORIES)} categories)", 0.0, 1.0, 0.0, 1 / 6
        )
        exclude_safety = st.checkbox(
            "Hide targets with a recorded safety concern", value=force_exclude_safety, disabled=force_exclude_safety
        )

    return RankingFilters(
        min_genetics_evidence=min_genetics or None,
        require_druggable=require_druggable,
        min_evidence_completeness=min_completeness or None,
        exclude_safety_concerns=exclude_safety,
    )


def render() -> None:
    st.title("Target ranking")

    disease_id = st.session_state.get("disease_id")
    if not disease_id:
        st.info("Select a disease in the sidebar to begin.")
        return

    weights, force_exclude_safety = _render_scenario_controls()
    filters = _render_filters(force_exclude_safety)

    sort_label = st.radio(
        "Sort by",
        ["Weighted baseline (default, exact contributions)", "XGBoost held-out (see caveat below)"],
        horizontal=True,
    )
    sort_by = "weighted_baseline" if sort_label.startswith("Weighted") else "xgboost_held_out"
    if sort_by == "xgboost_held_out":
        st.warning(
            "milestone2.md §1: cross-disease target popularity accounts for most of the XGBoost "
            "score for most targets (novel-only NDCG@10 0.009 vs. 0.696 primary). A high score "
            "here is a weaker disease-specific claim than the weighted-baseline score."
        )

    top_n = st.slider("Show top N", 10, 200, 50, 10)

    try:
        results = rank_for_disease(disease_id, filters=filters, top_n=top_n, weights=weights, sort_by=sort_by)
    except FileNotFoundError as exc:
        st.error(str(exc))
        return

    if not results:
        st.warning("No targets survive the current filters.")
        return

    rows = [
        {
            "Rank": r.rank,
            "Gene": r.gene_symbol,
            "Gene name": r.gene_name,
            "Score (active sort)": round(r.score, 4),
            "Weighted baseline": round(r.weighted_baseline_score, 4),
            "XGBoost (held-out)": round(r.xgboost_score_held_out, 4) if r.xgboost_score_held_out is not None else None,
            "Genetics": r.evidence.get("genetics"),
            "Functional": r.evidence.get("functional"),
            "Literature": r.evidence.get("literature"),
            "Druggability": r.evidence.get("druggability"),
            "Evidence completeness": (
                f"{round((r.app_evidence_completeness or 0) * len(APP_EVIDENCE_CATEGORIES))} of "
                f"{len(APP_EVIDENCE_CATEGORIES)}"
            ),
            "Positive in N other diseases": r.n_other_diseases_positive,
        }
        for r in results
    ]
    # A native polars DataFrame, not a list of dicts — Streamlit's own
    # object-column dtype inference for list-of-dict input (via pandas'
    # maybe_convert_objects -> pyarrow.array) segfaults in this environment's
    # pandas/pyarrow pairing (pandas 3.0.5 / pyarrow 25.0.0); polars serializes
    # straight to Arrow with no pandas object-array inference in the path.
    st.dataframe(pl.DataFrame(rows), hide_index=True, width="stretch")
    st.caption(
        "Evidence completeness counts genetics/functional/druggability (built) plus pathway/"
        "expression/network (not yet integrated for any disease — Context.md §28 Step 9), out "
        "of 6 total categories."
    )

    st.subheader("View target detail")
    options = {f"{r.gene_symbol} ({r.target_id})": r.target_id for r in results}
    chosen_label = st.selectbox("Target", list(options))
    if st.button("View evidence"):
        st.session_state["selected_target_id"] = options[chosen_label]
        st.switch_page(st.session_state["_pages"]["target_evidence"])


if __name__ == "__main__":
    render()
