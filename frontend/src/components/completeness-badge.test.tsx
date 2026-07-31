import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CompletenessBadge } from "@/components/completeness-badge";
import { TooltipProvider } from "@/components/ui/tooltip";

function renderBadge(count: number, total: number) {
  return render(
    <TooltipProvider>
      <CompletenessBadge count={count} total={total} />
    </TooltipProvider>,
  );
}

describe("CompletenessBadge — invariant 2 (never a bare fraction)", () => {
  it("renders as 'N of TOTAL', not a decimal", () => {
    renderBadge(4, 6);
    expect(screen.getByText("4 of 6")).toBeInTheDocument();
    expect(screen.queryByText("0.67")).not.toBeInTheDocument();
    expect(screen.queryByText(/^0\./)).not.toBeInTheDocument();
  });

  it("carries the denominator even at full completeness", () => {
    renderBadge(6, 6);
    expect(screen.getByText("6 of 6")).toBeInTheDocument();
  });

  it("carries the denominator even at zero completeness", () => {
    renderBadge(0, 6);
    expect(screen.getByText("0 of 6")).toBeInTheDocument();
  });
});
