"use client";

import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { api } from "@/lib/api-client";

/** Debounces *value* by *delayMs* — used so the disease search box doesn't
 * fire a request on every keystroke. */
function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(timer);
  }, [value, delayMs]);
  return debounced;
}

/**
 * Server-side disease search (`GET /api/diseases/search?q=`) rather than a
 * client-side filter over all ten — `services.disease_search` normalizes
 * apostrophes/punctuation ("parkinsons" still matches "Parkinson's
 * disease"), which a naive client-side substring match would not
 * replicate.
 */
export function useDiseaseSearch(query: string) {
  const debounced = useDebouncedValue(query, 250);
  return useQuery({
    queryKey: ["disease-search", debounced],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/diseases/search", {
        params: { query: { q: debounced } },
      });
      if (error) throw error;
      return data;
    },
    placeholderData: (previous) => previous,
  });
}
