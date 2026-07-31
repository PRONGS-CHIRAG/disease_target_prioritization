"use client";

import { AlertTriangle } from "lucide-react";

import { useMeta } from "@/hooks/use-meta";

/**
 * Standing limitations, visible on every page (Context.md §21, §31.12;
 * invariant 8, milestone5_plan.md §3) — a persistent panel, never a
 * dismissible toast, so it cannot be closed away and forgotten mid-session.
 */
export function LimitationsPanel() {
  const { data: meta } = useMeta();

  return (
    <div className="border-t border-sidebar-border px-4 py-3">
      <div className="mb-2 flex items-center gap-1.5 text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">
        <AlertTriangle className="size-3" aria-hidden />
        Limitations
      </div>
      <ul className="space-y-1.5 text-[11px] leading-snug text-muted-foreground">
        {(meta?.limitations ?? []).map((item) => (
          <li key={item} className="flex gap-1.5">
            <span aria-hidden>·</span>
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
