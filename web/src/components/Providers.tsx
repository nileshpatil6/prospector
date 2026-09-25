"use client";

import { useEffect } from "react";
import { MotionConfig } from "motion/react";
import { ToastProvider } from "./Toast";
import { useReducedMotion } from "@/hooks/useReducedMotion";

/** Applies/removes the `motion-ok` class (gates plain-CSS keyframes: radar
 * sweep, pin bounce, tick pop, typewriter caret) and wraps the app so every
 * `motion` component also respects prefers-reduced-motion automatically. */
export function Providers({ children }: { children: React.ReactNode }) {
  const reduced = useReducedMotion();

  useEffect(() => {
    document.documentElement.classList.toggle("motion-ok", !reduced);
  }, [reduced]);

  return (
    <MotionConfig reducedMotion="user">
      <ToastProvider>{children}</ToastProvider>
    </MotionConfig>
  );
}
