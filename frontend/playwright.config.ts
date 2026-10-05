import { defineConfig } from "@playwright/test";

// The golden path runs against a running app (the offline Docker stack in CI, `make up` locally):
//   E2E_BASE_URL=http://localhost:8080 E2E_DATASET=sample_roll pnpm e2e
// Google Chrome (channel "chrome") plays the simulator's H.264 video; Playwright's own Chromium cannot.
export default defineConfig({
  testDir: "e2e",
  timeout: 240_000,
  expect: { timeout: 15_000 },
  retries: 0,
  reporter: [["list"], ["html", { open: "never", outputFolder: "playwright-report" }]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:8080",
    channel: process.env.E2E_CHANNEL ?? "chrome",
    viewport: { width: 1440, height: 900 },
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
});
