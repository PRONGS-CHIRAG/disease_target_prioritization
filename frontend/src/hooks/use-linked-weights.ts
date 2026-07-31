"use client";

import { parseAsFloat, useQueryStates } from "nuqs";

import type { DimensionKey } from "@/lib/dimensions";

/**
 * Optional weight params a link FROM the ranking page attaches so a
 * target's score stays identical on the page it links to — carries the
 * server-normalized `weights_used` behind the ranking response that
 * produced the link, not the raw (possibly un-normalized) slider values.
 * Present only when every dimension is set in the URL; a page visited
 * directly (no upstream link, e.g. a bookmark) falls back to
 * `meta.default_weights`, same as before this existed.
 *
 * The `w<Dimension>` param names are shared with `useRankingState`
 * (`use-ranking-state.ts`) but mean something different there — raw,
 * possibly-un-normalized custom-slider values, only live when
 * `scenario=custom`. Safe today because every cross-page link here builds a
 * fresh query string rather than forwarding the ranking page's own params,
 * but a future link that preserves the incoming query string wholesale
 * would silently reinterpret one hook's values as the other's.
 */
const linkedWeightParsers = {
  wGenetics: parseAsFloat,
  wEvidenceDiversity: parseAsFloat,
  wFunctional: parseAsFloat,
  wLiterature: parseAsFloat,
  wDruggability: parseAsFloat,
};

export function useLinkedWeights(): Record<DimensionKey, number> | null {
  const [params] = useQueryStates(linkedWeightParsers);
  const { wGenetics, wEvidenceDiversity, wFunctional, wLiterature, wDruggability } = params;
  if (
    wGenetics === null ||
    wEvidenceDiversity === null ||
    wFunctional === null ||
    wLiterature === null ||
    wDruggability === null
  ) {
    return null;
  }
  return {
    genetics: wGenetics,
    evidence_diversity: wEvidenceDiversity,
    functional: wFunctional,
    literature: wLiterature,
    druggability: wDruggability,
  };
}

/** Builds the query string a link consumed by {@link useLinkedWeights} needs. */
export function linkedWeightsQueryString(weights: Record<string, number>): string {
  return new URLSearchParams({
    wGenetics: String(weights.genetics),
    wEvidenceDiversity: String(weights.evidence_diversity),
    wFunctional: String(weights.functional),
    wLiterature: String(weights.literature),
    wDruggability: String(weights.druggability),
  }).toString();
}
