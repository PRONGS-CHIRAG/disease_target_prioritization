"""Streamlit MVP interface (Context.md §21, §29 Phase 7).

Required sections per Context.md §21: disease search, ranked target table,
target detail view, filters — and, on every page, an explicit statement of
limitations. Context.md §31.12 is unambiguous that this tool is not for medical
decisions, and that has to be visible in the product, not only in the README.
"""

from __future__ import annotations

import streamlit as st

LIMITATIONS = [
    "A high score does not prove a target will produce an effective drug.",
    "Database evidence is incomplete and biased toward well-studied genes.",
    "Association does not prove causation.",
    "Absence of evidence is not evidence of absence — check evidence completeness.",
    "Predictions change when the underlying databases are updated.",
    "Not for medical diagnosis or treatment decisions.",
]


def main() -> None:
    st.set_page_config(page_title="Disease-Target Prioritization", layout="wide")
    st.title("Disease–Target Prioritization")
    st.caption(
        "Research-support prototype. Scores are prioritization hypotheses from public "
        "evidence, not validated scientific conclusions."
    )

    with st.sidebar:
        st.header("Limitations")
        for item in LIMITATIONS:
            st.markdown(f"- {item}")

    st.info("Milestone 3 — see Context.md §21 for the interface specification.")


if __name__ == "__main__":
    main()
