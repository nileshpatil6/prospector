import { test, expect } from "@playwright/test";
import { createRunViaApi, screenshotPath, waitForRunDoneViaApi } from "./helpers";

test("review flow: select, label via click and keyboard, counters, persistence, filter", async ({
  page,
  request,
}) => {
  const runId = await createRunViaApi(
    request,
    "Find 12 dental clinics in Pune that would benefit from an AI phone receptionist"
  );
  const run = await waitForRunDoneViaApi(request, runId);
  const leadIds = Object.keys(run.leads);
  expect(leadIds.length).toBe(12);

  await page.goto(`/runs/${runId}`);
  await expect(page.getByTestId("ledger")).toBeVisible();
  await expect(page.getByTestId("ledger-row")).toHaveCount(12);
  await expect(page.getByTestId("detail-panel")).toBeVisible();

  // Click-select the second row, then label it good via the detail panel.
  const secondRow = page.getByTestId("ledger-row").nth(1);
  await secondRow.click();
  await expect(secondRow).toHaveAttribute("data-selected", "true");
  await page.getByTestId("good-button").click();
  await expect(page.getByTestId("toast")).toBeVisible();
  await expect(page.getByTestId("progress-meter")).toContainText("1");

  // Keyboard nav: J moves selection down, then G labels the new lead good.
  await page.keyboard.press("j");
  await page.keyboard.press("g");
  await expect(page.getByTestId("progress-meter")).toContainText("2");

  // K moves back up; B labels bad.
  await page.keyboard.press("k");
  await page.keyboard.press("k");
  await page.keyboard.press("b");
  await expect(page.getByTestId("progress-meter")).toContainText("3");

  await page.screenshot({ path: screenshotPath("review"), fullPage: true });

  // Reload: labels must have persisted server-side.
  await page.reload();
  await expect(page.getByTestId("progress-meter")).toContainText("3");
  const labelledDots = page.locator('[data-testid="ledger-row"] span[title="good"], [data-testid="ledger-row"] span[title="bad"]');
  await expect(labelledDots).toHaveCount(3);

  // Filter to unlabelled -- 9 of the 12 leads remain.
  await page.getByTestId("filter-unlabelled").click();
  await expect(page.getByTestId("ledger-row")).toHaveCount(9);

  await page.getByTestId("filter-all").click();
  await expect(page.getByTestId("ledger-row")).toHaveCount(12);
});
