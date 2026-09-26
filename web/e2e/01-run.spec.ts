import { test, expect } from "@playwright/test";
import { screenshotPath } from "./helpers";

test("run flow: goal -> plan -> steps -> failure+recovery -> done -> map -> top leads", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByTestId("goal-input")).toBeVisible();
  await page.getByTestId("goal-input").fill(
    "Find 12 dental clinics in Pune that would benefit from an AI phone receptionist"
  );
  await page.getByTestId("run-button").click();

  // The plan should render once the PLAN call comes back.
  await expect(page.getByTestId("plan-checklist")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId("plan-checklist").locator("li")).toHaveCount(4);

  // Step cards stream into the thought stream as the loop runs.
  await expect(page.getByTestId("step-card").first()).toBeVisible({ timeout: 15_000 });

  // The scripted plan fails one search_businesses call, then recovers on
  // the very next step -- both must be visible in the thought stream.
  await expect(page.locator('[data-testid="step-card"][data-ok="false"]')).toBeVisible({
    timeout: 15_000,
  });
  await expect(page.getByText(/recovered from step/i)).toBeVisible({ timeout: 15_000 });

  // Agent loop indicator reflects a real phase while running.
  await expect(page.getByTestId("loop-indicator")).toBeVisible();

  await page.screenshot({ path: screenshotPath("run"), fullPage: true });

  // Wait for the run to finish and the result banner to appear.
  await expect(page.getByTestId("result-banner")).toBeVisible({ timeout: 20_000 });

  // Map shows a pin per lead (12 fixture leads).
  await expect(page.getByTestId("prospector-map")).toBeVisible();
  await expect(page.locator(".prospector-pin")).toHaveCount(12, { timeout: 10_000 });

  // Top lead cards (at most 5, ranked by score).
  await expect(page.getByTestId("lead-card").first()).toBeVisible();
  const cardCount = await page.getByTestId("lead-card").count();
  expect(cardCount).toBeGreaterThan(0);
  expect(cardCount).toBeLessThanOrEqual(5);

  // Counters reflect the finished run.
  await expect(page.getByTestId("counters")).toContainText("12");

  await page.screenshot({ path: screenshotPath("run-done"), fullPage: true });

  // "Review & label" hands off to the review page for this run.
  await page.getByTestId("review-link").click();
  await expect(page).toHaveURL(/\/runs\/run_/);
});
