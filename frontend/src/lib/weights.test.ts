import { describe, expect, it } from "vitest";

import { normalizeWeights } from "@/lib/weights";

describe("normalizeWeights", () => {
  it("rescales to sum to 1.0", () => {
    const result = normalizeWeights({ a: 2, b: 2, c: 2, d: 2, e: 2 });
    const total = Object.values(result).reduce((s, v) => s + v, 0);
    expect(total).toBeCloseTo(1.0, 9);
    expect(result.a).toBeCloseTo(0.2, 9);
  });

  it("preserves relative proportions", () => {
    const result = normalizeWeights({ a: 4, b: 1 });
    expect(result.a).toBeCloseTo(0.8, 9);
    expect(result.b).toBeCloseTo(0.2, 9);
  });

  it("treats negative values as zero, mirroring the backend's rejection intent", () => {
    // The backend (normalize_weights) raises on negatives; the client-side
    // mirror is preview-only (never submitted directly), so it clamps
    // instead of throwing — matches lib/weights.ts's documented contract.
    const result = normalizeWeights({ a: 1, b: -1 });
    expect(result.a).toBe(1);
  });

  it("returns the input unchanged when everything is zero or negative", () => {
    const input = { a: 0, b: 0 };
    expect(normalizeWeights(input)).toEqual(input);
  });
});
