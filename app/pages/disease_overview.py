"""Disease overview page (Context.md §21, Project_info.md §38.1).

Displays: disease name, description, relevant tissues, candidate-target
count, evidence-source coverage, and data-release information.
"""

from __future__ import annotations

import polars as pl
import streamlit as st
from common import get_app_data, get_features, get_search_results

from target_prioritization.services.target_ranking import (
    APP_EVIDENCE_CATEGORIES,
    UNAVAILABLE_EVIDENCE_CATEGORIES,
)


def render() -> None:
    st.title("Disease overview")

    disease_id = st.session_state.get("disease_id")
    if not disease_id:
        st.info("Select a disease in the sidebar to begin.")
        return

    results = get_search_results("")
    match = next((r for r in results if r.disease_id == disease_id), None)
    if match is None:
        st.error(f"{disease_id} is not in the precomputed set of ten configured diseases.")
        return

    st.header(match.name)
    st.caption(disease_id)
    st.write(match.description or "_No description available for this release._")

    col1, col2, col3 = st.columns(3)
    col1.metric("Candidate targets", f"{match.n_associated_targets:,}" if match.n_associated_targets else "—")

    try:
        get_features()  # confirms the artifact exists before claiming a coverage count
        built = [c for c in APP_EVIDENCE_CATEGORIES if c not in UNAVAILABLE_EVIDENCE_CATEGORIES]
        col2.metric("Evidence categories built", f"{len(built)} of {len(APP_EVIDENCE_CATEGORIES)}")
    except FileNotFoundError:
        col2.metric("Evidence categories built", "—")

    try:
        app_data = get_app_data()
        release = app_data.get_column("dataset_version").drop_nulls().to_list()
        extraction_date = app_data.get_column("extraction_date").drop_nulls().to_list()
        col3.metric("Data release", release[0] if release else "—")
        if extraction_date:
            st.caption(f"Extracted {extraction_date[0]}")
    except FileNotFoundError:
        col3.metric("Data release", "—")

    st.subheader("Therapeutic area")
    st.write(", ".join(match.therapeutic_areas) or "—")

    st.subheader("Evidence-source coverage")
    st.caption(
        "This milestone builds three of the six evidence categories Context.md §21/§38.2 "
        "specify. The other three are not a gap in this disease's data — they are not built "
        "for ANY disease yet (Context.md §28 Step 9)."
    )
    coverage_rows = [
        {
            "Category": category.capitalize(),
            "Status": "Built" if category not in UNAVAILABLE_EVIDENCE_CATEGORIES else "Not yet integrated",
            "Note": UNAVAILABLE_EVIDENCE_CATEGORIES.get(category, ""),
        }
        for category in APP_EVIDENCE_CATEGORIES
    ]
    # Native polars DataFrame — see target_ranking.py's identical comment for
    # why a list of dicts crashes Streamlit's own rendering in this environment.
    st.dataframe(pl.DataFrame(coverage_rows), hide_index=True, width="stretch")

    st.info(
        "Scores are prioritization hypotheses from public evidence, not validated scientific "
        "conclusions. See the Limitations panel in the sidebar."
    )


if __name__ == "__main__":
    render()
