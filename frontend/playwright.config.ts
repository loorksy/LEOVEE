import { defineConfig } from "@playwright/test";

/**
 * Live staging E2E — hits the deployed stack, not local mocks.
 * Base URL can be overridden: STAGING_BASE_URL=https://staging.leovee.lork.cloud
 */
const baseURL = process.env.STAGING_BASE_URL ?? "https://staging.leovee.lork.cloud";

export default defineConfig({
  testDir: "./e2e",
  timeout: 180_000,
  expect: { timeout: 60_000 },
  fullyParallel: false,
  retries: 0,
  workers: 1,
  reporter: [["list"], ["html", { open: "never", outputFolder: "playwright-report" }]],
  use: {
    baseURL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
});
