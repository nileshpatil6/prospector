"use client";

import { useEffect, useState, type ReactNode } from "react";
import { API_BASE } from "@/lib/api";
import { Wordmark } from "@/components/Wordmark";

// Free hosting sleeps the API after ~15 min idle; the first request can take a minute.
// Local dev keeps its instant "backend is down" states, so the gate only runs against a remote API.
const IS_REMOTE = !/^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?/.test(API_BASE);
const SHOW_AFTER_MS = 1200;

export function BackendGate({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(!IS_REMOTE);
  const [visible, setVisible] = useState(false);
  const [seconds, setSeconds] = useState(0);

  useEffect(() => {
    if (!IS_REMOTE) return;
    let cancelled = false;
    const started = Date.now();
    const showTimer = setTimeout(() => !cancelled && setVisible(true), SHOW_AFTER_MS);
    const tick = setInterval(() => setSeconds(Math.floor((Date.now() - started) / 1000)), 1000);

    async function wake() {
      while (!cancelled) {
        try {
          const res = await fetch(`${API_BASE}/api/runs`, { cache: "no-store" });
          if (res.ok) {
            if (!cancelled) setReady(true);
            return;
          }
        } catch {
          // Sleeping service: the request fails (no CORS headers) until it is up.
        }
        await new Promise((r) => setTimeout(r, 3000));
      }
    }
    wake();

    return () => {
      cancelled = true;
      clearTimeout(showTimer);
      clearInterval(tick);
    };
  }, []);

  if (ready) return <>{children}</>;
  if (!visible) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-bg px-4">
      <div className="flex flex-col items-center text-center max-w-md">
        <div className="relative h-28 w-28 mb-8">
          <span className="absolute inset-0 rounded-full border border-hairline" />
          <span className="absolute inset-4 rounded-full border border-hairline" />
          <span className="absolute inset-8 rounded-full border border-hairline" />
          <span
            className="absolute inset-0 rounded-full animate-spin"
            style={{
              animationDuration: "2.4s",
              background: "conic-gradient(from 0deg, rgba(212,255,58,0.45), rgba(212,255,58,0) 70deg, transparent 360deg)",
            }}
          />
          <span className="absolute left-1/2 top-1/2 h-2 w-2 -translate-x-1/2 -translate-y-1/2 rounded-full bg-lime" />
        </div>
        <Wordmark />
        <h1 className="mt-6 text-2xl font-semibold tracking-tight">Waking up the backend</h1>
        <p className="mt-3 text-sm text-muted">
          The demo runs on free hosting, which sleeps when nobody is using it. It usually takes
          under a minute to start. This page opens by itself when it is ready.
        </p>
        <p className="mt-6 font-mono text-xs text-muted tabular-nums">{seconds}s</p>
      </div>
    </div>
  );
}
