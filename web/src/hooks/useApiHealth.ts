"use client";

import { useEffect, useState } from "react";
import { listRuns } from "@/lib/api";

export type ApiHealth = "checking" | "up" | "down";

/** Polls GET /api/runs every 5s as a liveness check for the top bar dot and
 * the friendly "backend is down" empty states. */
export function useApiHealth(intervalMs = 5000): ApiHealth {
  const [health, setHealth] = useState<ApiHealth>("checking");

  useEffect(() => {
    let cancelled = false;

    async function check() {
      try {
        await listRuns();
        if (!cancelled) setHealth("up");
      } catch {
        if (!cancelled) setHealth("down");
      }
    }

    check();
    const id = setInterval(check, intervalMs);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [intervalMs]);

  return health;
}
