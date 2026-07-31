"use client";

import {
  parseAsBoolean,
  parseAsFloat,
  parseAsInteger,
  parseAsStringEnum,
  useQueryStates,
} from "nuqs";

/**
 * Every control on the ranking page, in the URL (milestone5_plan.md §4.4)
 * — a ranking under a specific scenario is a shareable link, something
 * Streamlit's `st.session_state` structurally cannot do. Scenario slugs
 * come from `presentation.py` (stable identifiers — §2.6); custom weights
 * are individual `w_<dimension>` params so a custom-scenario link is fully
 * reproducible too.
 */
const rankingStateParsers = {
  scenario: parseAsStringEnum(["research", "clinical", "novel", "safety_first", "custom"]).withDefault(
    "research",
  ),
  sort: parseAsStringEnum(["weighted_baseline", "xgboost_held_out"]).withDefault("weighted_baseline"),
  top: parseAsInteger.withDefault(50),
  minGenetics: parseAsFloat.withDefault(0),
  druggable: parseAsBoolean.withDefault(false),
  tissue: parseAsBoolean.withDefault(false),
  completeness: parseAsFloat.withDefault(0),
  safety: parseAsBoolean.withDefault(false),
  wGenetics: parseAsFloat.withDefault(0.4),
  wEvidenceDiversity: parseAsFloat.withDefault(0.2),
  wFunctional: parseAsFloat.withDefault(0.15),
  wLiterature: parseAsFloat.withDefault(0.15),
  wDruggability: parseAsFloat.withDefault(0.1),
};

export function useRankingState() {
  return useQueryStates(rankingStateParsers);
}
