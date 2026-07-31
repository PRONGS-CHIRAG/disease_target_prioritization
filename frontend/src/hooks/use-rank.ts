"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api-client";
import type { components } from "@/lib/api-types";

export type RankingRequestBody = components["schemas"]["RankingRequest"];
export type RankedTarget = components["schemas"]["RankedTargetResponse"];
export type RankingResponse = components["schemas"]["RankingResponse"];

/**
 * `POST /api/rank` modeled as a query, not a mutation — the request body
 * is a filter/sort/weights specification, not a state change, so it
 * belongs in the query key (TanStack Query's documented pattern for
 * "POST as a read"). Disabled until a disease is selected.
 */
export function useRanking(request: RankingRequestBody | null) {
  return useQuery({
    queryKey: ["rank", request],
    queryFn: async () => {
      if (!request) throw new Error("useRanking called with no request");
      const { data, error } = await api.POST("/api/rank", { body: request });
      if (error) throw error;
      return data;
    },
    enabled: request !== null && request.disease_id.length > 0,
  });
}
