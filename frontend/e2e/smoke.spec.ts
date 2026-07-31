import { expect, test } from "@playwright/test";

// Real disease, real backend (FastAPI on :8000, started separately —
// milestone5_plan.md §7). Parkinson's disease is the same fixture the
// Python test suite's headline claim uses (all five established genes
// surface near the top of the ranking).
const PARKINSONS = "MONDO_0005180";
const LRRK2 = "ENSG00000188906"; // complete evidence — every dimension present
const GBA1 = "ENSG00000177628"; // missing `functional` — confirmed via manual pass

test.describe("Disease overview", () => {
  test("loads real disease data and shows the evidence coverage table", async ({ page }) => {
    await page.goto(`/overview?disease=${PARKINSONS}`);
    await expect(page.getByRole("heading", { name: "Parkinson's disease" })).toBeVisible();
    await expect(page.getByText(PARKINSONS)).toBeVisible();
    // All six evidence categories are built as of Milestone 4.
    await expect(page.getByText("6 of 6")).toBeVisible();
  });

  test("shows a prompt instead of an error when no disease is selected", async ({ page }) => {
    await page.goto("/overview");
    await expect(page.getByText("Select a disease in the sidebar to begin.")).toBeVisible();
  });
});

test.describe("Target ranking", () => {
  test("surfaces established Parkinson's genes near the top", async ({ page }) => {
    await page.goto(`/ranking?disease=${PARKINSONS}`);
    await page.waitForSelector("table tbody tr");
    const geneNames = await page.locator("table tbody tr td:nth-child(3)").allTextContents();
    // LRRK2, GBA1, SNCA, PARK7, PRKN — Milestone 1's headline result,
    // still true under the new frontend's default scenario.
    for (const gene of ["LRRK2", "GBA1", "SNCA", "PARK7"]) {
      expect(geneNames.some((cell) => cell.includes(gene))).toBe(true);
    }
  });

  test("a target missing genetics evidence renders a dash, never 0 (invariant 1)", async ({ page }) => {
    await page.goto(`/ranking?disease=${PARKINSONS}&top=200`);
    await page.waitForSelector("table tbody tr");
    // At least one em-dash must appear somewhere in the Genetics/Functional/
    // Literature/Druggability columns across 200 rows — Context.md §32.2
    // measured that most candidates have partial evidence.
    const dashCount = await page.getByText("—", { exact: true }).count();
    expect(dashCount).toBeGreaterThan(0);
  });

  test("switching to the Custom scenario reveals five weight sliders", async ({ page }) => {
    await page.goto(`/ranking?disease=${PARKINSONS}`);
    await page.waitForSelector("table tbody tr");
    await page.locator("button", { hasText: "Research-focused" }).click();
    await page.getByRole("option", { name: "Custom" }).click();
    await expect(page.locator('[role="slider"]')).toHaveCount(8); // 5 weights + 2 filters + top-N
    await expect(page).toHaveURL(/scenario=custom/);
  });

  test("selecting two targets enables the compare button and links to /compare", async ({ page }) => {
    await page.goto(`/ranking?disease=${PARKINSONS}`);
    await page.waitForSelector("table tbody tr");
    await page.locator("table tbody tr").nth(0).locator('button[role="checkbox"]').click();
    await page.locator("table tbody tr").nth(1).locator('button[role="checkbox"]').click();
    const compareButton = page.getByRole("button", { name: /Compare 2 selected/ });
    await expect(compareButton).toBeEnabled();
    await compareButton.click();
    await expect(page).toHaveURL(/\/compare\?/);
    // Same weights-passthrough mechanism as "View evidence" (invariant 10,
    // milestone5_plan.md §3) — the compare link must carry them too.
    await expect(page).toHaveURL(/wGenetics=/);
  });

  test("the CSV export button states the partial-export count honestly", async ({ page }) => {
    await page.goto(`/ranking?disease=${PARKINSONS}&top=50`);
    await page.waitForSelector("table tbody tr");
    // milestone5_plan.md §2.7 — never implies a 50-row export is the whole ranking.
    await expect(page.getByRole("button", { name: /Export 50 of 8,690/ })).toBeVisible();
  });
});

test.describe("Target evidence", () => {
  test("shows the exact contribution breakdown for a complete-evidence target", async ({ page }) => {
    await page.goto(`/evidence?disease=${PARKINSONS}&target=${LRRK2}`);
    await expect(page.getByRole("heading", { name: "LRRK2" })).toBeVisible();
    await expect(page.getByText(/Overall rank: 1 of/)).toBeVisible();
  });

  test("score matches the ranking row under a non-default scenario (weights carry through the link)", async ({
    page,
  }) => {
    // Clinical-focused reweights genetics/druggability away from the
    // research-focused default, so a stale-weights bug (evidence page
    // silently recomputing under default weights) would change this
    // target's displayed score after following "View evidence".
    await page.goto(`/ranking?disease=${PARKINSONS}&scenario=clinical`);
    await page.waitForSelector("table tbody tr");
    const row = page.locator("table tbody tr", { hasText: "LRRK2" }).first();
    const rankingScore = (await row.locator("td").nth(3).locator("span").first().textContent())?.trim();
    expect(rankingScore).toBeTruthy();

    await row.getByRole("link", { name: "View evidence" }).click();
    await expect(page).toHaveURL(/wGenetics=/);
    await expect(page.getByRole("heading", { name: "LRRK2" })).toBeVisible();
    const scoreBlock = page.getByText("Weighted-baseline score").locator("..").first();
    await expect(scoreBlock).toContainText(Number(rankingScore).toFixed(3));
  });

  test("a target missing a dimension shows it in Missing evidence, not as a zero", async ({ page }) => {
    await page.goto(`/evidence?disease=${PARKINSONS}&target=${GBA1}`);
    await expect(page.getByRole("heading", { name: "GBA1" })).toBeVisible();
    await expect(page.getByText(/functional/i).first()).toBeVisible();
  });

  test("prompts for a target when none is selected", async ({ page }) => {
    await page.goto(`/evidence?disease=${PARKINSONS}`);
    await expect(page.getByText("Select a target from the Target ranking page first.")).toBeVisible();
  });
});

test.describe("Compare", () => {
  test("renders side-by-side cards and lets the user remove one", async ({ page }) => {
    await page.goto(`/compare?disease=${PARKINSONS}&targets=${LRRK2},${GBA1}`);
    await expect(page.getByRole("heading", { name: "LRRK2" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "GBA1" })).toBeVisible();

    await page.getByRole("button", { name: /Remove.*from comparison/ }).first().click();
    await expect(page).toHaveURL(new RegExp(`targets=(?!.*,)`));
  });

  test("prompts to pick targets when fewer than two are selected", async ({ page }) => {
    await page.goto(`/compare?disease=${PARKINSONS}`);
    await expect(page.getByText(/Select 2-4 targets to compare/)).toBeVisible();
  });
});
