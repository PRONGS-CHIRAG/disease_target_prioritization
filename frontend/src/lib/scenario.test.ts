import { describe, expect, it } from "vitest";

import { resolveScenarioWeights } from "@/lib/scenario";
import type { components } from "@/lib/api-types";

type MetaResponse = components["schemas"]["MetaResponse"];

const meta: MetaResponse = {
  scenario_presets: [
    { slug: "research", label: "Research-focused", weights: { genetics: 0.45, literature: 0.1 } },
  ],
  safety_first: { slug: "safety_first", label: "Safety-first", weights: { genetics: 0.4, literature: 0.15 } },
  custom_slug: "custom",
  custom_label: "Custom",
  dimension_keys: ["genetics", "literature"],
  dimension_labels: { genetics: "Genetics", literature: "Literature" },
  evidence_categories: ["genetics", "functional", "pathways", "expression", "network", "druggability"],
  unavailable_evidence_categories: {},
  not_buildable: {},
  default_weights: { genetics: 0.4, literature: 0.15 },
};

describe("resolveScenarioWeights", () => {
  it("returns null while meta hasn't loaded", () => {
    expect(resolveScenarioWeights("research", {}, undefined)).toBeNull();
  });

  it("resolves a preset slug to its fixed weights", () => {
    expect(resolveScenarioWeights("research", {}, meta)).toEqual({ genetics: 0.45, literature: 0.1 });
  });

  it("resolves the safety-first slug to the DEFAULT weights, not a distinct safety weight", () => {
    // Invariant 4 (milestone5_plan.md §3): Safety-first changes a filter,
    // never the weights — it must return the same weights as the
    // meta.safety_first payload, which the backend already sets to
    // default_weights (models/config's milestone_1_weights).
    expect(resolveScenarioWeights(meta.safety_first.slug, {}, meta)).toEqual(meta.safety_first.weights);
    expect(meta.safety_first.weights).toEqual(meta.default_weights);
  });

  it("resolves the custom slug to the caller-supplied weights, unmodified", () => {
    const custom = { genetics: 0.9, literature: 0.1 };
    expect(resolveScenarioWeights(meta.custom_slug, custom, meta)).toBe(custom);
  });

  it("falls back to default weights for an unrecognized scenario", () => {
    expect(resolveScenarioWeights("not-a-real-scenario", {}, meta)).toEqual(meta.default_weights);
  });
});
