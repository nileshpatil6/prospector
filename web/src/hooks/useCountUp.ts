"use client";

import { useEffect, useRef, useState } from "react";
import { useReducedMotion } from "./useReducedMotion";

/** Animates a displayed number toward `value` over `durationMs`. Used for
 * every "counter" in the UI (leads found, plan steps, learn metric tiles).
 * Jumps straight to the value when the viewer prefers reduced motion. */
export function useCountUp(value: number, durationMs = 600): number {
  const [display, setDisplay] = useState(value);
  const reduced = useReducedMotion();
  const fromRef = useRef(value);
  const frameRef = useRef<number | null>(null);

  useEffect(() => {
    if (reduced) {
      // Jumping straight to the target value is a deliberate sync from the
      // reduced-motion external signal, not a derived-state anti-pattern.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setDisplay(value);
      fromRef.current = value;
      return;
    }
    const from = fromRef.current;
    if (from === value) return;
    const start = performance.now();

    function tick(now: number) {
      const t = Math.min(1, (now - start) / durationMs);
      const eased = 1 - Math.pow(1 - t, 3); // ease-out cubic
      setDisplay(from + (value - from) * eased);
      if (t < 1) {
        frameRef.current = requestAnimationFrame(tick);
      } else {
        fromRef.current = value;
      }
    }
    frameRef.current = requestAnimationFrame(tick);
    return () => {
      if (frameRef.current) cancelAnimationFrame(frameRef.current);
    };
  }, [value, durationMs, reduced]);

  return Math.round(display);
}
