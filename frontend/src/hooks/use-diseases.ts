"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api-client";

/** The ten configured diseases (services.disease_search's module docstring
 * names this as the entire search space) — the disease picker's data
 * source. Cached for the session; the set doesn't change at runtime. */
export function useDiseases() {
  return useQuery({
    queryKey: ["diseases"],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/diseases");
      if (error) throw error;
      return data;
    },
    staleTime: Infinity,
  });
}

export function useDiseaseDetail(diseaseId: string) {
  return useQuery({
    queryKey: ["disease", diseaseId],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/diseases/{disease_id}", {
        params: { path: { disease_id: diseaseId } },
      });
      if (error) throw error;
      return data;
    },
    enabled: diseaseId.length > 0,
  });
}
