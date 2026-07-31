import createClient from "openapi-fetch";

import type { paths } from "@/lib/api-types";

// Same origin in both dev (next.config.ts rewrites /api/* to the backend)
// and production (FastAPI serves the static export and /api/* from one
// process) — milestone5_plan.md §4.5. No base URL needed; a relative path
// resolves against whatever origin served this page.
export const api = createClient<paths>({ baseUrl: "" });

/** Narrows an openapi-fetch error body to a human-readable string — every
 * error response on this API is a FastAPI HTTPException, whose JSON body
 * is `{ detail: string }`. */
export function apiErrorMessage(error: unknown, fallback: string): string {
  if (error && typeof error === "object" && "detail" in error) {
    const detail = (error as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
  }
  return fallback;
}
