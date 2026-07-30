"""Streamlit MVP interface (Context.md §21, §29 Phase 7).

Required sections per Context.md §21: disease search, ranked target table,
target detail view, filters — and, on every page, an explicit statement of
limitations. Context.md §31.12 is unambiguous that this tool is not for
medical decisions, and that has to be visible in the product, not only in
the README.

Entry point for ``st.navigation`` (Streamlit >=1.36, pinned in
pyproject.toml). The disease search/picker lives in the sidebar here, not
on its own page, so the selected disease (``st.session_state["disease_id"]``)
is available and visible on every page rather than only one of them.
"""

from __future__ import annotations

import streamlit as st
from common import render_disease_picker, render_limitations_sidebar
from pages import disease_overview, target_evidence, target_ranking


def main() -> None:
    st.set_page_config(page_title="Disease-Target Prioritization", layout="wide")

    render_limitations_sidebar()
    render_disease_picker()

    pages = {
        "disease_overview": st.Page(
            disease_overview.render,
            title="Disease overview",
            icon="🧬",
            url_path="disease-overview",
            default=True,
        ),
        "target_ranking": st.Page(
            target_ranking.render, title="Target ranking", icon="📊", url_path="target-ranking"
        ),
        "target_evidence": st.Page(
            target_evidence.render, title="Target evidence", icon="🔎", url_path="target-evidence"
        ),
    }
    # Callable-defined pages can only be switch_page'd via their StreamlitPage
    # object (st.switch_page's own docstring), not a file path — stashed here
    # so target_ranking.render can navigate to target_evidence after a user
    # picks a target (Context.md §21's ranked-table -> detail-view flow).
    st.session_state["_pages"] = pages

    st.navigation(list(pages.values())).run()


if __name__ == "__main__":
    main()
