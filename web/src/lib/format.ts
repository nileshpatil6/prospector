/** Formatting helpers shared by run/review/runs pages. Kept framework-free
 * so they're trivial to unit-reason-about and reuse in tests. */

export function formatElapsed(ms: number): string {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000));
  const m = Math.floor(totalSeconds / 60);
  const s = totalSeconds % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

export function formatDate(startedAt: number): string {
  if (!startedAt) return "--";
  return new Date(startedAt * 1000).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function websiteHost(url: string): string {
  try {
    return new URL(url).host.replace(/^www\./, "");
  } catch {
    return url;
  }
}

export function faviconUrl(url: string): string | null {
  const host = websiteHost(url);
  if (!host || host === url) return null;
  return `https://www.google.com/s2/favicons?sz=32&domain=${host}`;
}

/** Which phase of the agent loop a step's action belongs to, for the
 * PLAN/ACT/OBSERVE/DECIDE indicator. The loop is really act-then-decide in
 * agent.py, but visually splitting "search-shaped" tools into ACT and
 * everything else into DECIDE/OBSERVE reads better and still tracks what
 * the agent is actually doing. */
export type LoopPhase = "plan" | "act" | "observe" | "decide";

const ACT_ACTIONS = new Set([
  "geocode",
  "search_businesses",
  "widen_area",
  "enrich",
]);
const OBSERVE_ACTIONS = new Set(["score", "deep_research"]);

const REASON_RE = /^(.*):\s*([+-]?\d+(?:\.\d+)?)$/;

/** rules.py score() produces reasons like "has_phone: +30" or
 * "rule:r1 (...): -15". Split into a label + signed point value for the
 * score-breakdown bars; falls back to points=null for anything that
 * doesn't match (defensive -- should never happen against real data). */
export function parseReason(reason: string): { label: string; points: number | null } {
  const match = REASON_RE.exec(reason);
  if (!match) return { label: reason, points: null };
  return { label: match[1].trim(), points: Number(match[2]) };
}

export function phaseForAction(action: string): LoopPhase {
  if (ACT_ACTIONS.has(action)) return "act";
  if (OBSERVE_ACTIONS.has(action)) return "observe";
  return "decide"; // write_hooks, finish, unknown/failed/empty actions
}
