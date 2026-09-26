import path from "node:path";
import type { APIRequestContext } from "@playwright/test";

/** The scripted backend from tests/e2e_server.py -- see playwright.config.ts. */
export const API_BASE = "http://localhost:8010";

export const SCREENSHOT_DIR = path.join(__dirname, "..", "..", "docs", "screenshots");

export function screenshotPath(name: string): string {
  return path.join(SCREENSHOT_DIR, `${name}.png`);
}

export interface RunJson {
  run_id: string;
  status: string;
  leads: Record<string, { id: string; score: number }>;
  [key: string]: unknown;
}

/** Starts a run directly against the API (skipping the UI) for specs that
 * need a completed run as setup rather than as the thing under test. */
export async function createRunViaApi(request: APIRequestContext, goal: string): Promise<string> {
  const res = await request.post(`${API_BASE}/api/runs`, { data: { goal } });
  if (!res.ok()) throw new Error(`createRunViaApi failed: ${res.status()} ${await res.text()}`);
  const body = (await res.json()) as { run_id: string };
  return body.run_id;
}

export async function waitForRunDoneViaApi(
  request: APIRequestContext,
  runId: string,
  timeoutMs = 20_000
): Promise<RunJson> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const res = await request.get(`${API_BASE}/api/runs/${runId}`);
    if (res.ok()) {
      const data = (await res.json()) as RunJson;
      if (data.status !== "running") return data;
    }
    await new Promise((r) => setTimeout(r, 200));
  }
  throw new Error(`run ${runId} did not finish within ${timeoutMs}ms`);
}

export async function labelViaApi(
  request: APIRequestContext,
  runId: string,
  leadId: string,
  label: "good" | "bad"
): Promise<void> {
  const res = await request.post(`${API_BASE}/api/labels`, {
    data: { run_id: runId, lead_id: leadId, label },
  });
  if (!res.ok()) throw new Error(`labelViaApi failed: ${res.status()} ${await res.text()}`);
}
