"use client";

import { useQueryState } from "nuqs";

/** The target selected for the evidence page, carried in `?target=`
 * (milestone5_plan.md §2.2) — never a path segment, since there are 8,690
 * candidates for Parkinson's alone. */
export function useTargetId() {
  return useQueryState("target", { defaultValue: "", clearOnDefault: true });
}
