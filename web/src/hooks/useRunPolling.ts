"use client";

import { useEffect, useRef, useState } from "react";
import { getRun } from "@/lib/api";
import type { RunState } from "@/lib/types";

/** Polls GET /api/runs/{id} once a second while status === "running", per
 * the contract (no SSE -- polling is robust enough and simpler). Stops
 * polling as soon as the run leaves "running". */
export function useRunPolling(runId: string | null) {
  const [run, setRun] = useState<RunState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!runId) {
      // Resetting state when the id prop goes away is the canonical effect
      // cleanup case.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setRun(null);
      return;
    }

    let cancelled = false;

    async function poll() {
      try {
        const data = await getRun(runId!);
        if (cancelled) return;
        setRun(data);
        setError(null);
        if (data.status !== "running" && intervalRef.current) {
          clearInterval(intervalRef.current);
          intervalRef.current = null;
        }
      } catch (err) {
        if (cancelled) return;
        const message = err instanceof Error ? err.message : String(err);
        if (message.includes("not found")) {
          if (intervalRef.current) {
            clearInterval(intervalRef.current);
            intervalRef.current = null;
          }
          setError("This run no longer exists. The server restarted, so please start the run again.");
          return;
        }
        setError(message);
      }
    }

    poll();
    intervalRef.current = setInterval(poll, 1000);

    return () => {
      cancelled = true;
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [runId]);

  return { run, error };
}
