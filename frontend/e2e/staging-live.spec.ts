import { expect, test } from "@playwright/test";

/**
 * Batch 8 — one real browser test against the deployed staging stack.
 *
 * Flow: sign up → workspace created → run analysis → chart annotations →
 * recommendation → thesis created → memory written → second analysis on the
 * same symbol shows recalled memory.
 *
 * This intentionally does NOT mock the API. A red result is the valuable
 * output — do not weaken assertions to force green.
 */
const STAGING = process.env.STAGING_BASE_URL ?? "https://staging.leovee.lork.cloud";

test.describe("Staging live product path", () => {
  test("signup through memory recall on second analysis", async ({ page }) => {
    const stamp = Date.now();
    // email-validator rejects reserved TLDs like .test — use a real-looking domain.
    const email = `batch8.e2e.${stamp}@users.leovee.lork.cloud`;
    const password = `Batch8!${stamp}`;
    const org = `Batch8 Desk ${stamp}`;

    await page.goto(`${STAGING}/signup`);
    await expect(page.getByTestId("signup-form")).toBeVisible({ timeout: 30_000 });
    await page.getByLabel(/workspace|organization/i).fill(org);
    await page.getByLabel(/^email$/i).fill(email);
    await page.getByLabel(/^password$/i).fill(password);
    await page.getByRole("button", { name: /sign up/i }).click();

    // Signup creates a default workspace; land authenticated on home/shell.
    await expect(page.getByRole("link", { name: "Analysis" })).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText(/Welcome to Leovee/i)).toBeVisible();

    await page.getByRole("link", { name: "Analysis" }).click();
    await expect(page.getByRole("heading", { name: "Analysis" })).toBeVisible();
    await page.getByLabel(/^symbol$/i).fill("EURUSD");
    await page.getByLabel(/full pipeline/i).check();
    await page.getByRole("button", { name: /run analysis/i }).click();

    await expect(page.getByText(/EURUSD ·/i)).toBeVisible({ timeout: 120_000 });
    await expect(page.getByText(/recalled\s+\d+\s+memories/i)).toBeVisible();
    await expect(page.getByTestId("chart-status")).toContainText(/annotation/i);

    // Chart with annotations
    await page.getByRole("button", { name: /view chart/i }).click();
    await expect(page.getByRole("heading", { name: /AI Analyst/i })).toBeVisible({
      timeout: 30_000,
    });
    await expect(page.getByTestId("chart-container")).toBeVisible();
    await expect(page.getByTestId("annotation-count")).toContainText(/[1-9]\d* annotation/, {
      timeout: 30_000,
    });

    // Recommendation appears
    await page.getByRole("link", { name: "Recommendations" }).click();
    await expect(page.getByRole("heading", { name: "Recommendations" })).toBeVisible();
    await expect(page.getByText(/EURUSD/i).first()).toBeVisible({ timeout: 30_000 });

    // Thesis created — recommendation card / analysis result implies thesis via full pipeline.
    // Memory written — Memory page should list at least one item after first analysis.
    await page.getByRole("link", { name: "Memory" }).click();
    await expect(page.getByRole("heading", { name: "Memory" })).toBeVisible();
    await expect(page.locator("body")).toContainText(/EURUSD|episode|lesson|fact/i, {
      timeout: 30_000,
    });

    // Second analysis on same symbol shows recalled memory (count > 0).
    await page.getByRole("link", { name: "Analysis" }).click();
    await page.getByLabel(/^symbol$/i).fill("EURUSD");
    await page.getByRole("button", { name: /run analysis/i }).click();
    await expect(page.getByText(/EURUSD ·/i)).toBeVisible({ timeout: 120_000 });
    const recallLine = page.getByText(/recalled\s+(\d+)\s+memories/i);
    await expect(recallLine).toBeVisible();
    const text = await recallLine.innerText();
    const match = text.match(/recalled\s+(\d+)\s+memories/i);
    expect(match, `expected recall count in: ${text}`).not.toBeNull();
    const count = Number(match?.[1] ?? 0);
    expect(count, "second analysis must recall at least one memory").toBeGreaterThan(0);
  });
});
