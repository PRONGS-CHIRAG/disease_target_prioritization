import { describe, expect, it } from "vitest";

import { linkedWeightsQueryString } from "@/hooks/use-linked-weights";

describe("linkedWeightsQueryString", () => {
  it("round-trips into the exact param names useLinkedWeights parses", () => {
    const weights = {
      genetics: 0.45,
      evidence_diversity: 0.25,
      functional: 0.15,
      literature: 0.1,
      druggability: 0.05,
    };
    const params = new URLSearchParams(linkedWeightsQueryString(weights));
    expect(params.get("wGenetics")).toBe("0.45");
    expect(params.get("wEvidenceDiversity")).toBe("0.25");
    expect(params.get("wFunctional")).toBe("0.15");
    expect(params.get("wLiterature")).toBe("0.1");
    expect(params.get("wDruggability")).toBe("0.05");
  });
});
