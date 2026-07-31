import { defineConfig } from "@playwright/test";

// milestone5_plan.md §7 — a smoke pass over the three migrated pages plus
// the comparison view, asserting a known-null dimension renders an
// em-dash rather than "0" (invariant 1). Expects the FastAPI backend
// already running on :8000 (`make api` or `make dev`) with the real
// processed artifacts — no mocking, same standard the Python acceptance
// checks hold themselves to.
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"]],
  use: {
    baseURL: "http://localhost:3000",
    trace: "retain-on-failure",
  },
  webServer: {
    command: "npm run dev",
    url: "http://localhost:3000",
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
});
