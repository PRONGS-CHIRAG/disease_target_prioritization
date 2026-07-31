"""Target evidence page (Context.md §21 detail view, §37, Project_info.md §38.4).

Combines the weighted baseline's exact contribution breakdown and the
held-out XGBoost model's live SHAP explanation (services.evidence_summary),
plus everything Context.md §21/§37/§38.4 ask for that this milestone can
actually build. Pathway membership, tissue expression and a
protein-interaction summary were the ones this page rendered as placeholders
through Milestone 3; Milestone 4 wired in Reactome/GTEx/STRING
(milestone4_plan.md), so those three now render real evidence. Direction of
effect and a calibrated confidence level remain unbuilt — unrelated to
Reactome/GTEx/STRING — and still render as explicit placeholders naming what
would be needed, never as a blank or a zero.
"""

from __future__ import annotations

import polars as pl
import streamlit as st
from common import get_active_weights, get_app_data, get_features

from target_prioritization.models.baseline import WeightedBaseline
from target_prioritization.services.evidence_summary import build_evidence_card
from target_prioritization.services.target_ranking import (
    UNAVAILABLE_EVIDENCE_CATEGORIES,
    rank_for_disease,
)
from target_prioritization.viz import build_evidence_breakdown_figure, build_evidence_radar_figure

_NOT_BUILDABLE = {
    "Direction of effect": "nothing in the pipeline computes this yet (Context.md §37.6)",
    "Confidence level": "no calibrated uncertainty estimate exists yet (Context.md §30.13, §37.1)",
}


def render() -> None:
    st.title("Target evidence")

    disease_id = st.session_state.get("disease_id")
    target_id = st.session_state.get("selected_target_id")
    if not disease_id:
        st.info("Select a disease in the sidebar to begin.")
        return
    if not target_id:
        st.info("Select a target from the Target ranking page first.")
        return

    weights = get_active_weights()

    try:
        features = get_features()
        card = build_evidence_card(disease_id, target_id, features=features, weights=weights)
    except FileNotFoundError as exc:
        st.error(str(exc))
        return
    except KeyError:
        st.error(f"({disease_id}, {target_id}) is not in the feature table.")
        return

    row_frame = features.filter((pl.col("disease_id") == disease_id) & (pl.col("target_id") == target_id))
    row = row_frame.row(0, named=True)

    st.header(f"{card.gene_symbol or target_id}")
    st.caption(f"{target_id} — {row.get('gene_name') or ''}")

    col1, col2, col3 = st.columns(3)
    col1.metric("Weighted-baseline score", f"{card.score:.3f}")

    try:
        app_row = get_app_data().filter(
            (pl.col("disease_id") == disease_id) & (pl.col("target_id") == target_id)
        )
        if not app_row.is_empty():
            app_row_dict = app_row.row(0, named=True)
            xgb_score = app_row_dict.get("xgboost_score_held_out")
            col2.metric("XGBoost score (held-out)", f"{xgb_score:.3f}" if xgb_score is not None else "—")
            col3.metric(
                "Positive in N other diseases", app_row_dict.get("n_other_diseases_positive")
            )
    except FileNotFoundError:
        col2.metric("XGBoost score (held-out)", "—")

    try:
        ranking = rank_for_disease(disease_id, top_n=None, weights=weights, features=features)
        rank = next((r.rank for r in ranking if r.target_id == target_id), None)
        if rank is not None:
            st.caption(f"Overall rank: {rank} of {len(ranking)} candidates for this disease")
    except FileNotFoundError:
        pass

    st.subheader("Evidence breakdown")
    baseline = WeightedBaseline(weights)
    scored = baseline.score(row_frame)
    ranked_single = baseline.rank(scored, top_n=1)
    fig = build_evidence_breakdown_figure(
        ranked_single,
        top_n=1,
        weights=weights,
        title=f"{card.gene_symbol or target_id} evidence breakdown",
        subtitle="Weighted-baseline score decomposed into its evidence dimensions",
    )
    st.pyplot(fig)

    st.subheader("Evidence radar")
    dimension_values = {dim: row.get(f"dim__{dim}") for dim in weights}
    radar_fig = build_evidence_radar_figure(dimension_values, title=card.gene_symbol or target_id)
    col_radar, col_caption = st.columns([1, 1])
    with col_radar:
        st.pyplot(radar_fig)
    with col_caption:
        st.caption(
            "A dimension at or near zero can mean either weak evidence or NO evidence "
            "(Context.md §32.3) — check the missing-evidence panel below before reading a low "
            "spike as a negative finding."
        )

    col_support, col_contra = st.columns(2)
    with col_support:
        st.subheader("Strongest supporting evidence")
        for item in card.supporting[:8]:
            value = f"{item.value:.3f}" if isinstance(item.value, float) else item.value
            st.markdown(f"- **{item.category}** ({item.source}): {value}")
        if not card.supporting:
            st.caption("No supporting factors identified.")
    with col_contra:
        st.subheader("Strongest negative evidence")
        for item in card.contradicting[:8]:
            value = f"{item.value:.3f}" if isinstance(item.value, float) else item.value
            st.markdown(f"- **{item.category}** ({item.source}): {value}")
        if not card.contradicting:
            st.caption("None identified.")

    st.subheader("Missing evidence")
    for category in card.missing:
        reason = UNAVAILABLE_EVIDENCE_CATEGORIES.get(category, "no evidence recorded for this target")
        st.markdown(f"- **{category.capitalize()}**: {reason}")

    st.subheader("Existing drug information")
    st.caption(
        "This is the clinical-development evidence the training label is built from "
        "(Context.md §15) — shown for context, not as ranking evidence (milestone3_plan.md §3)."
    )
    try:
        app_row = get_app_data().filter(
            (pl.col("disease_id") == disease_id) & (pl.col("target_id") == target_id)
        )
        if not app_row.is_empty():
            r = app_row.row(0, named=True)
            n_drugs = r.get("label__n_drugs") or 0
            st.write(f"**{n_drugs}** drug(s) recorded for this disease family.")
            if r.get("label__drug_names"):
                st.write(r["label__drug_names"])
            if r.get("label__max_clinical_stage") is not None:
                st.write(f"Maximum clinical stage reached: {r['label__max_clinical_stage']}")
    except FileNotFoundError:
        st.caption("Not available — run scripts/build_app_data.py.")

    st.subheader("Not yet available for any target")
    for label, reason in _NOT_BUILDABLE.items():
        st.markdown(f"- **{label}**: not yet integrated — {reason}")

    st.subheader("Source references")
    for name, url in card.source_links.items():
        st.markdown(f"- [{name}]({url})")

    st.subheader("Limitations")
    for limitation in card.limitations:
        st.markdown(f"- {limitation}")


if __name__ == "__main__":
    render()
