"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { NuqsAdapter } from "nuqs/adapters/next/app";
import { useState } from "react";

import { TooltipProvider } from "@/components/ui/tooltip";

export function Providers({ children }: { children: React.ReactNode }) {
  // Constructed inside the component (not module scope) so each browser
  // session gets its own cache — the standard TanStack Query + Next.js
  // App Router pattern, since this app has no server-rendered data to
  // hydrate into (milestone5_plan.md §2.2: everything fetches client-side).
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 60_000,
            retry: 1,
          },
        },
      }),
  );

  return (
    <QueryClientProvider client={queryClient}>
      <NuqsAdapter>
        <TooltipProvider delayDuration={150}>{children}</TooltipProvider>
      </NuqsAdapter>
    </QueryClientProvider>
  );
}
