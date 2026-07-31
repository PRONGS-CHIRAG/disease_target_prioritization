import type { components } from "@/lib/api-types";

type MetaResponse = components["schemas"]["MetaResponse"];

/**
 * Resolves the raw (not yet server-normalized) weights for the active
 * scenario. Mirrors Streamlit's `_render_scenario_controls`
 * (app/pages/target_ranking.py, removed in Phase 7) — a preset slug or
 * "safety_first" maps to a fixed weight set; "custom" uses the slider
 * values as-is. The server is always the one that normalizes (§4.1) and
 * its echoed `weights_used` is what gets displayed once a response
 * arrives — this function only decides what to SEND.
 */
export function resolveScenarioWeights(
  scenario: string,
  customWeights: Record<string, number>,
  meta: MetaResponse | undefined,
): Record<string, number> | null {
  if (!meta) return null;
  const preset = meta.scenario_presets.find((p) => p.slug === scenario);
  if (preset) return preset.weights;
  if (scenario === meta.safety_first.slug) return meta.safety_first.weights;
  if (scenario === meta.custom_slug) return customWeights;
  return meta.default_weights;
}
