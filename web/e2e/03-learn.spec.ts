import { test, expect } from "@playwright/test";
import { createRunViaApi, labelViaApi, screenshotPath, waitForRunDoneViaApi } from "./helpers";

test("learn flow: seed labels via API, Learn, verdict cards, rules and chart render", async ({
  page,
  request,
}) => {
  const runId = await createRunViaApi(
    request,
    "Find 12 dental clinics in Pune that would benefit from an AI phone receptionist"
  );
  const run = await waitForRunDoneViaApi(request, runId);
  const leadIds = Object.keys(run.leads);

  // MIN_LABELS is 12; alternate good/bad so both classes are present.
  for (let i = 0; i < leadIds.length; i++) {
    await labelViaApi(request, runId, leadIds[i], i % 2 === 0 ? "good" : "bad");
  }

  await page.goto("/learn");
  await expect(page.getByTestId("metric-tiles")).toBeVisible();
  await expect(page.getByTestId("learn-button")).toBeEnabled({ timeout: 10_000 });

  await page.getByTestId("learn-button").click();
  await expect(page.getByTestId("verdict-list")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId("verdict-card").first()).toBeVisible();

  // The scripted candidates are both deterministically rejected on this
  // small fixture set: one for an out-of-range weight, one for a measured
  // holdout accuracy gain of exactly 0 (not > 0) on these 12 leads.
  await expect(page.locator('[data-testid="verdict-card"][data-kind="rejected"]')).toHaveCount(2);

  await expect(page.getByTestId("rule-list")).toBeVisible();
  await expect(page.getByTestId("accuracy-chart")).toBeVisible();

  await page.screenshot({ path: screenshotPath("learn"), fullPage: true });
});
