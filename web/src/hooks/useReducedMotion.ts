"use client";

import { useEffect, useState } from "react";

/** Tracks prefers-reduced-motion so decorative-only effects (radar sweep,
 * pin bounce, typewriter caret) can be switched off. The `motion` library's
 * <MotionConfig reduceMotion="user"> handles its own animations; this hook
 * is for the plain CSS keyframes gated behind the `.motion-ok` class. */
export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(
    () => typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );

  useEffect(() => {
    const mql = window.matchMedia("(prefers-reduced-motion: reduce)");
    const onChange = () => setReduced(mql.matches);
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, []);

  return reduced;
}
