import { AlertCircle, Info } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";

export function SelectDiseasePrompt() {
  return (
    <div className="flex items-center gap-2 rounded-md border border-dashed border-border bg-card px-4 py-3 text-sm text-muted-foreground">
      <Info className="size-4 shrink-0" aria-hidden />
      Select a disease in the sidebar to begin.
    </div>
  );
}

export function ApiErrorNotice({ message }: { message: string }) {
  return (
    <div className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
      <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden />
      <span>{message}</span>
    </div>
  );
}

export function LoadingBlock({ rows = 4 }: { rows?: number }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-8 w-full" />
      ))}
    </div>
  );
}
