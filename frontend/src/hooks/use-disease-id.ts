"use client";

import { useQueryState } from "nuqs";

/**
 * The globally-selected disease, carried in the `?disease=` URL param
 * (milestone5_plan.md §2.2/§4.4) — read and written from anywhere in the
 * tree via nuqs, mirroring Streamlit's `st.session_state["disease_id"]`
 * but shareable as a URL instead of hidden session state.
 */
export function useDiseaseId() {
  return useQueryState("disease", { defaultValue: "", clearOnDefault: true });
}
