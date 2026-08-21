"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api-client";
import type { components } from "@/lib/api-types";

export type EvidenceDetailResponse = components["schemas"]["EvidenceDetailResponse"];

/**
 * The browsable half of the target-detail view (Context.md §21): named
 * Reactome pathways, per-tissue GTEx expression, high-confidence STRING
 * partners.
 *
 * A separate query from `useEvidence` on purpose. This response does not
 * depend on the scenario weights — it is the same evidence whatever the user
 * has the sliders set to — so it is keyed on (disease, target) alone and
 * cached for the session, and moving the weights never refetches it.
 */
export function useEvidenceDetail(diseaseId: string, targetId: string) {
  return useQuery({
    queryKey: ["evidence-detail", diseaseId, targetId],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/evidence/detail", {
        params: { query: { disease_id: diseaseId, target_id: targetId } },
      });
      if (error) throw error;
      return data;
    },
    enabled: diseaseId.length > 0 && targetId.length > 0,
    staleTime: Infinity,
  });
}
