"use client";

import { parseAsArrayOf, parseAsString, useQueryState } from "nuqs";

const MAX_COMPARE = 4;

/** The 2-4 targets selected for `/compare`, carried as `?targets=id1,id2`
 * (milestone5_plan.md §2.2). Clamped to MAX_COMPARE on write so a
 * hand-edited URL can't force an unbounded comparison. */
export function useTargetIds() {
  const [ids, setIds] = useQueryState(
    "targets",
    parseAsArrayOf(parseAsString).withDefault([]),
  );
  const setClamped = (next: string[]) => setIds(next.slice(0, MAX_COMPARE));
  return [ids.slice(0, MAX_COMPARE), setClamped] as const;
}

export { MAX_COMPARE };
