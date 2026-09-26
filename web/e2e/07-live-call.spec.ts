import { test, expect } from "@playwright/test";
import { createRunViaApi, screenshotPath, waitForRunDoneViaApi } from "./helpers";

test("live call: fake session drives the panel, transcript, and a take_message POST", async ({
  page,
  request,
}) => {
  // Only Playwright sets this -- it makes useLiveCall skip the real
  // /live-session + Gemini Live connection and drive a scripted fake
  // session instead (see web/src/lib/live/fakeSession.ts).
  await page.addInitScript(() => {
    (window as unknown as { __PROSPECTOR_LIVE_FAKE__: boolean }).__PROSPECTOR_LIVE_FAKE__ = true;
  });

  const runId = await createRunViaApi(
    request,
    "Find 12 dental clinics in Pune that would benefit from an AI phone receptionist"
  );
  await waitForRunDoneViaApi(request, runId);

  await page.goto(`/runs/${runId}`);
  await expect(page.getByTestId("detail-panel")).toBeVisible();

  const messagePostPromise = page.waitForResponse(
    (res) => res.url().includes("/messages") && res.request().method() === "POST"
  );

  await page.getByTestId("call-receptionist-button").click();
  await expect(page.getByTestId("call-panel")).toBeVisible();

  // Fake session emits one transcript line from each side.
  await expect(page.getByTestId("call-transcript-line")).toHaveCount(2, { timeout: 10_000 });
  await expect(page.locator('[data-testid="call-transcript-line"][data-speaker="caller"]')).toBeVisible();
  await expect(
    page.locator('[data-testid="call-transcript-line"][data-speaker="receptionist"]')
  ).toBeVisible();

  // Fake session fires a take_message toolCall -- the panel must POST it to
  // the real backend and show a message card.
  const messageResponse = await messagePostPromise;
  expect(messageResponse.ok()).toBe(true);
  await expect(page.getByTestId("call-message-card")).toBeVisible({ timeout: 10_000 });

  await page.screenshot({ path: screenshotPath("call"), fullPage: true });

  await page.getByTestId("call-hangup-button").click();
  await expect(page.getByTestId("call-panel")).toBeHidden();
});
