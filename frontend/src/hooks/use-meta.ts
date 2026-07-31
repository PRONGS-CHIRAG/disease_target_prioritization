"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api-client";

/** Scenario presets, dimension labels, limitations — fetched once and
 * cached indefinitely for the session (milestone5_plan.md §2.6): this is
 * config, not per-request data, so it never goes stale within a session. */
export function useMeta() {
  return useQuery({
    queryKey: ["meta"],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/meta");
      if (error) throw error;
      return data;
    },
    staleTime: Infinity,
  });
}
