"use client";

import { useEffect, useState } from "react";

const RUN_ID_TS_RE = /(\d+)$/;

/** run_id is `run_<unix epoch>` (see server.py _started_at) -- reuse that to
 * derive a wall-clock elapsed time without needing a dedicated field. Ticks
 * once a second while running, freezes once the run leaves "running". */
export function useElapsedTime(runId: string | null, running: boolean): number {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!running) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [running]);

  if (!runId) return 0;
  const match = RUN_ID_TS_RE.exec(runId);
  if (!match) return 0;
  const startedMs = Number(match[1]) * 1000;
  return Math.max(0, now - startedMs);
}
