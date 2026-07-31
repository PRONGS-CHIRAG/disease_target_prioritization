import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { EvidenceValue } from "@/components/evidence-value";
import { TooltipProvider } from "@/components/ui/tooltip";

function renderValue(value: number | null | undefined, digits?: number) {
  return render(
    <TooltipProvider>
      <EvidenceValue value={value} digits={digits} />
    </TooltipProvider>,
  );
}

describe("EvidenceValue — invariant 1 (null is not zero)", () => {
  it("renders null as a dash, never as 0", () => {
    renderValue(null);
    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.queryByText("0")).not.toBeInTheDocument();
    expect(screen.queryByText("0.000")).not.toBeInTheDocument();
  });

  it("renders undefined the same way as null", () => {
    renderValue(undefined);
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("marks a missing value with an accessible label distinguishing it from a real zero", () => {
    renderValue(null);
    expect(screen.getByLabelText("No evidence recorded")).toBeInTheDocument();
  });

  it("renders an actual zero as the literal formatted number, not a dash", () => {
    renderValue(0);
    expect(screen.getByText("0.000")).toBeInTheDocument();
    expect(screen.queryByText("—")).not.toBeInTheDocument();
  });

  it("formats a real value to the requested precision", () => {
    renderValue(0.86543, 3);
    expect(screen.getByText("0.865")).toBeInTheDocument();
  });

  it("respects a zero-digit format for integer-like fields", () => {
    renderValue(3, 0);
    expect(screen.getByText("3")).toBeInTheDocument();
  });
});
