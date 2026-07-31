"use client";

import { Check, ChevronsUpDown, Search } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useDiseaseId } from "@/hooks/use-disease-id";
import { useDiseaseSearch } from "@/hooks/use-disease-search";
import { cn } from "@/lib/utils";

/**
 * The disease search/picker (Context.md §21) — the search space is only
 * the ten configured diseases (services.disease_search's module
 * docstring); an unmatched query shows the honest "not in the precomputed
 * set" message rather than an empty list with no explanation.
 */
export function DiseasePicker() {
  const [diseaseId, setDiseaseId] = useDiseaseId();
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const { data: results, isFetching } = useDiseaseSearch(query);

  const selected = results?.find((r) => r.disease_id === diseaseId);
  const label = selected?.name ?? (diseaseId ? diseaseId : "Select a disease…");

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          role="combobox"
          aria-expanded={open}
          className="w-full justify-between border-sidebar-border bg-sidebar font-sans text-sm font-normal"
        >
          <span className="flex min-w-0 items-center gap-2">
            <Search className="size-3.5 shrink-0 text-muted-foreground" aria-hidden />
            <span className="truncate">{label}</span>
          </span>
          <ChevronsUpDown className="size-3.5 shrink-0 text-muted-foreground" aria-hidden />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[--radix-popover-trigger-width] p-0" align="start">
        <Command shouldFilter={false}>
          <CommandInput
            placeholder="e.g. Parkinson's disease"
            value={query}
            onValueChange={setQuery}
          />
          <CommandList>
            {!isFetching && (results?.length ?? 0) === 0 && (
              <CommandEmpty>No disease found in the precomputed set of ten.</CommandEmpty>
            )}
            <CommandGroup>
              {results?.map((r) => (
                <CommandItem
                  key={r.disease_id}
                  value={r.disease_id}
                  onSelect={() => {
                    void setDiseaseId(r.disease_id);
                    setOpen(false);
                  }}
                  className="flex items-start justify-between gap-2"
                >
                  <span className="flex min-w-0 flex-col">
                    <span className="truncate">{r.name}</span>
                    {r.n_associated_targets != null && (
                      <span className="font-mono text-xs text-muted-foreground">
                        {r.n_associated_targets.toLocaleString()} candidate targets
                      </span>
                    )}
                  </span>
                  <Check
                    className={cn(
                      "mt-0.5 size-4 shrink-0",
                      r.disease_id === diseaseId ? "opacity-100" : "opacity-0",
                    )}
                    aria-hidden
                  />
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
