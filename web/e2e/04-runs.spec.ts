import { test, expect } from "@playwright/test";
import { screenshotPath } from "./helpers";

test("runs history: lists prior runs with a histogram, click -> review", async ({ page }) => {
  await page.goto("/runs");

  await expect(page.getByTestId("run-list")).toBeVisible({ timeout: 15_000 });
  const cardCount = await page.getByTestId("run-card").count();
  // Earlier specs (run flow, review flow, learn flow) each created at least
  // one run against the shared scripted backend.
  expect(cardCount).toBeGreaterThanOrEqual(3);

  await expect(page.getByTestId("score-histogram").first()).toBeVisible();

  await page.screenshot({ path: screenshotPath("runs"), fullPage: true });

  await page.getByTestId("run-card").first().click();
  await expect(page).toHaveURL(/\/runs\/run_/);
  await expect(page.getByTestId("ledger")).toBeVisible({ timeout: 10_000 });
});
