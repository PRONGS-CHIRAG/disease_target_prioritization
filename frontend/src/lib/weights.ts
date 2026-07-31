/**
 * Client-side mirror of `services.target_ranking.normalize_weights`, used
 * ONLY to preview the normalized values next to the custom sliders before
 * a request round-trips. The server is the actual authority — its
 * `weights_used` in the response is what gets displayed as "Applied"
 * (ScenarioControls) — this never substitutes for that.
 */
export function normalizeWeights(weights: Record<string, number>): Record<string, number> {
  const total = Object.values(weights).reduce((sum, v) => sum + Math.max(v, 0), 0);
  if (total <= 0) return weights;
  return Object.fromEntries(Object.entries(weights).map(([k, v]) => [k, Math.max(v, 0) / total]));
}
