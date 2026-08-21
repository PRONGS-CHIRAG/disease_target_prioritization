import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { TooltipProvider } from "@/components/ui/tooltip";
import type { EvidenceDetailResponse } from "@/hooks/use-evidence-detail";

const detail = vi.hoisted(() => ({ current: {} as EvidenceDetailResponse }));

vi.mock("@/hooks/use-evidence-detail", () => ({
  useEvidenceDetail: () => ({ data: detail.current, isLoading: false, error: null }),
}));

const { EvidenceDetailPanels } = await import("@/components/evidence/evidence-detail-panels");

function base(): EvidenceDetailResponse {
  return {
    disease_id: "MONDO_1",
    disease_name: "Test disease",
    target_id: "ENSG_A",
    gene_symbol: "AAA",
    pathway_groups: [
      {
        root_pathway_id: "R-1",
        root_pathway_name: "Immune System",
        pathways: [{ pathway_id: "R-11", name: "Alpha signalling", url: "https://reactome.org/R-11" }],
      },
    ],
    n_root_categories: 1,
    tissues: [
      { tissue: "Brain_Cortex", median_tpm: 50, is_relevant: true },
      { tissue: "Liver", median_tpm: 5, is_relevant: false },
    ],
    relevant_tissues_matched: { brain: ["Brain_Cortex"] },
    relevant_tissues_unmatched: [],
    partners: [
      { target_id: "ENSG_B", gene_symbol: "BBB", score: 999, is_candidate: true },
      { target_id: "ENSG_C", gene_symbol: "CCC", score: 800, is_candidate: false },
    ],
    partner_min_score: 700,
    literature: { europepmc_score: 0.9, europepmc_evidence_count: 120, search_url: "https://europepmc.org/x" },
    not_buildable: {},
    dataset_version: "26.06",
    limitations: [],
  };
}

function renderPanels(overrides: Partial<EvidenceDetailResponse> = {}) {
  detail.current = { ...base(), ...overrides };
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <TooltipProvider>
        <EvidenceDetailPanels diseaseId="MONDO_1" targetId="ENSG_A" />
      </TooltipProvider>
    </QueryClientProvider>,
  );
}

describe("EvidenceDetailPanels", () => {
  it("names pathways and links them to Reactome", () => {
    renderPanels();
    expect(screen.getByText("Immune System")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Alpha signalling/ })).toHaveAttribute(
      "href",
      "https://reactome.org/R-11",
    );
  });

  it("shows the root-category count, the unit path__n_pathways measures", () => {
    renderPanels({ n_root_categories: 8 });
    expect(screen.getByText("8 categories")).toBeInTheDocument();
  });

  it("links a partner that is a candidate for this disease", () => {
    renderPanels();
    expect(screen.getByRole("link", { name: /BBB/ })).toHaveAttribute(
      "href",
      "/evidence?disease=MONDO_1&target=ENSG_B",
    );
  });

  it("does NOT link a partner outside this disease — its page would 404", () => {
    renderPanels();
    expect(screen.getByText("CCC")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /CCC/ })).not.toBeInTheDocument();
  });

  it("states an unmatched relevant tissue instead of showing nothing", () => {
    renderPanels({ relevant_tissues_unmatched: ["synovium"] });
    expect(screen.getByText(/synovium/)).toBeInTheDocument();
    expect(screen.getByText(/no value/i)).toBeInTheDocument();
  });

  it("says so when a gene has no pathway annotation", () => {
    renderPanels({ pathway_groups: [], n_root_categories: 0 });
    expect(screen.getByText(/No Reactome pathway annotation/)).toBeInTheDocument();
    expect(screen.queryByText(/categories$/)).not.toBeInTheDocument();
  });

  it("renders a dash, never a zero, for an absent co-mention score", () => {
    renderPanels({
      literature: { europepmc_score: null, europepmc_evidence_count: null, search_url: "https://europepmc.org/x" },
    });
    expect(screen.queryByText("0.000")).not.toBeInTheDocument();
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });
});
