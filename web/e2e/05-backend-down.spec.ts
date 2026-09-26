import { test, expect } from "@playwright/test";
import { API_BASE } from "./helpers";

test("backend-down: friendly error state with the exact start command", async ({ page }) => {
  // Abort every call to the API for this test only -- the real scripted
  // backend keeps running for every other spec.
  await page.route(`${API_BASE}/**`, (route) => route.abort());

  await page.goto("/");
  await expect(page.getByTestId("api-down")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText("uvicorn server:app --port 8000")).toBeVisible();

  await expect(page.getByTestId("api-health")).toHaveAttribute("data-health", "down", {
    timeout: 15_000,
  });

  await page.goto("/runs");
  await expect(page.getByTestId("api-down")).toBeVisible({ timeout: 15_000 });
});
