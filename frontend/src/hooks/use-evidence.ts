"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api-client";
import type { components } from "@/lib/api-types";

export type EvidenceRequestBody = components["schemas"]["EvidenceRequest"];
export type EvidenceResponse = components["schemas"]["EvidenceResponse"];

export function useEvidence(request: EvidenceRequestBody | null) {
  return useQuery({
    queryKey: ["evidence", request],
    queryFn: async () => {
      if (!request) throw new Error("useEvidence called with no request");
      const { data, error } = await api.POST("/api/evidence", { body: request });
      if (error) throw error;
      return data;
    },
    enabled: request !== null && request.disease_id.length > 0 && request.target_id.length > 0,
  });
}
