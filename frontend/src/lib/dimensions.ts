/**
 * Client-side presentation for the five weighted-baseline dimensions
 * (`presentation.DIMENSION_KEYS` on the backend — labels come from
 * `GET /api/meta`, never hardcoded here; only the CHART COLOR is a
 * frontend-only concern, since the API has no reason to know about CSS).
 * Colors reference the CSS custom properties in globals.css, which mirror
 * `viz.py`'s validated DIMENSION_COLORS exactly (light) or a lightened
 * dark-mode variant — see that file's comment for why the palette wasn't
 * re-derived from scratch.
 */
export const DIMENSION_ORDER = [
  "genetics",
  "evidence_diversity",
  "functional",
  "literature",
  "druggability",
] as const;

export type DimensionKey = (typeof DIMENSION_ORDER)[number];

export const DIMENSION_COLOR_VAR: Record<DimensionKey, string> = {
  genetics: "var(--dimension-genetics)",
  evidence_diversity: "var(--dimension-evidence-diversity)",
  functional: "var(--dimension-functional)",
  literature: "var(--dimension-literature)",
  druggability: "var(--dimension-druggability)",
};
