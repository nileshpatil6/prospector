import { defineConfig, devices } from "@playwright/test";

// The scripted backend (tests/e2e_server.py, repo root) and a dedicated
// Next dev server, both on non-default ports so they never collide with a
// real `uvicorn server:app --port 8000` / `npm run dev` the owner might
// already have running. NEVER used for the demo -- see README.
const API_PORT = 8010;
const WEB_PORT = 3010;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  timeout: 45_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL: `http://localhost:${WEB_PORT}`,
    viewport: { width: 1440, height: 900 },
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  // Chromium only, per the redesign contract. The fake-device flags let the
  // live-call spec's getUserMedia() call succeed with a synthetic mic
  // instead of hanging on a real permission prompt or failing headless.
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1440, height: 900 },
        permissions: ["microphone"],
        launchOptions: {
          args: ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"],
        },
      },
    },
  ],
  webServer: [
    {
      command: `uvicorn tests.e2e_server:app --port ${API_PORT}`,
      cwd: "..",
      url: `http://localhost:${API_PORT}/api/runs`,
      reuseExistingServer: false,
      timeout: 30_000,
      stdout: "pipe",
      stderr: "pipe",
    },
    {
      command: `npx next dev -p ${WEB_PORT}`,
      cwd: ".",
      url: `http://localhost:${WEB_PORT}`,
      reuseExistingServer: false,
      timeout: 60_000,
      stdout: "pipe",
      stderr: "pipe",
      env: { NEXT_PUBLIC_API_URL: `http://localhost:${API_PORT}` },
    },
  ],
});
