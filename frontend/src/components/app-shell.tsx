"use client";

import { FlaskConical } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { DiseasePicker } from "@/components/disease-picker";
import { LimitationsPanel } from "@/components/limitations-panel";
import { useDiseaseId } from "@/hooks/use-disease-id";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { href: "/overview", label: "Overview" },
  { href: "/ranking", label: "Target ranking" },
  { href: "/evidence", label: "Target evidence" },
  { href: "/compare", label: "Compare" },
] as const;

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [diseaseId] = useDiseaseId();

  return (
    <div className="flex min-h-screen flex-col lg:h-full lg:flex-row">
      <aside className="flex w-full shrink-0 flex-col border-b border-sidebar-border bg-sidebar lg:w-72 lg:border-b-0 lg:border-r">
        <div className="flex items-center gap-2 border-b border-sidebar-border px-4 py-4">
          <FlaskConical className="size-4 text-primary" aria-hidden />
          <div className="min-w-0">
            <div className="truncate font-heading text-sm font-semibold">
              Disease–Target Prioritization
            </div>
            <div className="text-[11px] text-muted-foreground">Research-support prototype</div>
          </div>
        </div>

        <div className="space-y-2 border-b border-sidebar-border px-4 py-4">
          <div className="text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">
            Disease
          </div>
          <DiseasePicker />
        </div>

        <nav className="flex flex-row flex-wrap gap-0.5 px-2 py-3 lg:flex-col">
          {NAV_ITEMS.map((item) => {
            const href = diseaseId ? `${item.href}?disease=${encodeURIComponent(diseaseId)}` : item.href;
            const active = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "rounded-sm px-2.5 py-1.5 text-sm transition-colors",
                  active
                    ? "bg-sidebar-accent font-medium text-sidebar-accent-foreground"
                    : "text-muted-foreground hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground",
                )}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>

        <div className="mt-auto">
          <LimitationsPanel />
        </div>
      </aside>

      <main className="min-w-0 flex-1 bg-background">
        <div className="mx-auto max-w-6xl px-4 py-6 sm:px-6 lg:px-8 lg:py-8">{children}</div>
      </main>
    </div>
  );
}
