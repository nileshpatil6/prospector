import { test, expect, type Page } from "@playwright/test";
import { createRunViaApi, waitForRunDoneViaApi } from "./helpers";

test.use({ viewport: { width: 390, height: 844 } });

async function expectNoHorizontalScroll(page: Page) {
  const overflow = await page.evaluate(() => {
    const doc = document.documentElement;
    return doc.scrollWidth - doc.clientWidth;
  });
  // A 1px tolerance for sub-pixel rounding across browsers.
  expect(overflow).toBeLessThanOrEqual(1);
}

test("mobile viewport (390x844): every page renders with no horizontal scroll", async ({
  page,
  request,
}) => {
  const runId = await createRunViaApi(
    request,
    "Find 12 dental clinics in Pune that would benefit from an AI phone receptionist"
  );
  await waitForRunDoneViaApi(request, runId);

  await page.goto("/");
  await expect(page.getByTestId("goal-input")).toBeVisible();
  await expectNoHorizontalScroll(page);

  await page.goto("/runs");
  await expect(page.getByTestId("run-list")).toBeVisible({ timeout: 15_000 });
  await expectNoHorizontalScroll(page);

  await page.goto(`/runs/${runId}`);
  await expect(page.getByTestId("ledger")).toBeVisible({ timeout: 15_000 });
  await expectNoHorizontalScroll(page);

  await page.goto("/learn");
  await expect(page.getByTestId("metric-tiles")).toBeVisible();
  await expectNoHorizontalScroll(page);
});
