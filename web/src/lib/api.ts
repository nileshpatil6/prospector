import type {
  Label,
  LabelsSummary,
  LearnReport,
  MemoryResponse,
  RunState,
  RunSummary,
} from "./types";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** Build a full URL against the API, for direct links (report/CSV downloads). */
export function apiUrl(path: string): string {
  return `${API_BASE}${path}`;
}

class ApiError extends Error {}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(apiUrl(path), {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
      cache: "no-store",
    });
  } catch {
    throw new ApiError(
      `Could not reach the Prospector API at ${API_BASE}. Is the backend running?`
    );
  }
  if (!res.ok) {
    let message = res.statusText || `HTTP ${res.status}`;
    try {
      const body = await res.json();
      if (body && typeof body.error === "string") message = body.error;
    } catch {
      // body wasn't JSON; keep the status text
    }
    throw new ApiError(message);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export function startRun(
  goal: string,
  maxSteps?: number
): Promise<{ run_id: string }> {
  return request("/api/runs", {
    method: "POST",
    body: JSON.stringify({ goal, max_steps: maxSteps }),
  });
}

export function listRuns(): Promise<RunSummary[]> {
  return request("/api/runs");
}

export function getRun(runId: string): Promise<RunState> {
  return request(`/api/runs/${encodeURIComponent(runId)}`);
}

export function getReportUrl(runId: string): string {
  return apiUrl(`/api/runs/${encodeURIComponent(runId)}/report`);
}

export function getCsvUrl(runId: string): string {
  return apiUrl(`/api/runs/${encodeURIComponent(runId)}/csv`);
}

export function postLabel(
  runId: string,
  leadId: string,
  label: Label
): Promise<{ ok: boolean }> {
  return request("/api/labels", {
    method: "POST",
    body: JSON.stringify({ run_id: runId, lead_id: leadId, label }),
  });
}

/** lead_id contains a literal "/" (e.g. "osm:way/12345"); the API route
 * uses a path-converter param, so the id is interpolated raw, not
 * percent-encoded. */
export function deleteLabel(
  leadId: string
): Promise<{ ok: boolean; removed: boolean }> {
  return request(`/api/labels/${leadId}`, { method: "DELETE" });
}

export function getLabelsSummary(): Promise<LabelsSummary> {
  return request("/api/labels/summary");
}

export function runLearn(): Promise<LearnReport> {
  return request("/api/learn", { method: "POST" });
}

export function getMemory(): Promise<MemoryResponse> {
  return request("/api/memory");
}

export function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}
