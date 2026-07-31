"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

// No dynamic route segments in this app (milestone5_plan.md §2.2) — disease
// and target both travel as search params, so the root route has nothing
// of its own to show. Redirects client-side (this is a fully
// client-rendered SPA under `output: "export"` — no SSR) to the overview
// page, which owns the "select a disease" empty state.
export default function Home() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/overview");
  }, [router]);
  return null;
}
