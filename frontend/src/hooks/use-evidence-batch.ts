"use client";

import { useQueries } from "@tanstack/react-query";

import { api } from "@/lib/api-client";
import type { EvidenceRequestBody } from "@/hooks/use-evidence";

/**
 * N evidence requests in parallel — `useQueries` (not N calls to
 * `useEvidence`) because the target count is dynamic (2-4), and hooks
 * cannot be called in a variable-length loop. Backs the comparison view
 * (milestone5_plan.md Phase 6), which §4.2 named as the worst case for
 * the evidence endpoint's ~120ms full-population sort — measured, not yet
 * mitigated (see §4.2's note); four parallel requests are still the
 * realistic ceiling here since MAX_COMPARE caps it.
 */
export function useEvidenceBatch(requests: (EvidenceRequestBody | null)[]) {
  return useQueries({
    queries: requests.map((request) => ({
      queryKey: ["evidence", request],
      queryFn: async () => {
        if (!request) throw new Error("useEvidenceBatch: null request");
        const { data, error } = await api.POST("/api/evidence", { body: request });
        if (error) throw error;
        return data;
      },
      enabled: request !== null,
    })),
  });
}
