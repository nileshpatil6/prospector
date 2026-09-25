"use client";

import { useEffect, useState } from "react";
import { motion } from "motion/react";
import { RefreshCcw } from "lucide-react";
import type { Step } from "@/lib/types";
import { useReducedMotion } from "@/hooks/useReducedMotion";

function formatArgs(args: Record<string, unknown>): string {
  const entries = Object.entries(args ?? {});
  if (entries.length === 0) return "()";
  return `(${entries.map(([k, v]) => `${k}: ${JSON.stringify(v)}`).join(", ")})`;
}

/** Reveals `text` character-by-character once, on mount. Used only for the
 * newest thought-stream card so the reader's eye is drawn there. */
function TypewriterText({ text }: { text: string }) {
  const reduced = useReducedMotion();
  const [shown, setShown] = useState(reduced ? text : "");

  useEffect(() => {
    if (reduced) return;
    let i = 0;
    const stepMs = Math.max(6, Math.min(18, 900 / Math.max(text.length, 1)));
    const id = setInterval(() => {
      i += 1;
      setShown(text.slice(0, i));
      if (i >= text.length) clearInterval(id);
    }, stepMs);
    return () => clearInterval(id);
    // Runs once on mount only -- this card's `key` is the step number, so a
    // fresh instance is created exactly once per step.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <p className="mt-2 text-sm italic text-muted font-serif">
      {shown}
      {shown.length < text.length && (
        <span className="type-caret inline-block w-[6px] h-[13px] bg-muted/70 ml-0.5 align-middle" />
      )}
    </p>
  );
}

function StepCard({
  step,
  isNewest,
  recoveredFrom,
}: {
  step: Step;
  isNewest: boolean;
  recoveredFrom: number | null;
}) {
  return (
    <div className="relative">
      {recoveredFrom !== null && (
        <div className="flex items-center gap-1.5 pl-1 pb-1.5 -mt-1">
          <span className="h-3 w-px bg-lime/40" />
          <RefreshCcw size={11} className="text-lime" />
          <span className="text-[11px] font-mono text-lime">
            recovered from step {String(recoveredFrom).padStart(2, "0")}
          </span>
        </div>
      )}
      <motion.div
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.18 }}
        data-testid="step-card"
        data-ok={step.ok}
        data-action={step.action}
        className={`border rounded-lg px-4 py-3 ${
          step.ok ? "border-hairline bg-surface" : "border-coral/40 bg-coral-soft"
        }`}
      >
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-baseline gap-2 min-w-0">
            <span className="font-mono text-[11px] text-muted shrink-0">
              {String(step.n).padStart(2, "0")}
            </span>
            {step.action ? (
              <code className="font-mono text-[11px] bg-raised border border-hairline px-1.5 py-0.5 rounded truncate text-text">
                {step.action}
                {formatArgs(step.args)}
              </code>
            ) : (
              <span className="font-mono text-[11px] text-muted italic">(llm error)</span>
            )}
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <span className="font-mono text-[10px] text-muted tabular-nums">{step.ms}ms</span>
            <span
              className={`text-[10px] font-medium font-mono px-1.5 py-0.5 rounded ${
                step.ok ? "text-lime bg-lime-soft" : "text-coral bg-coral-soft border border-coral/30"
              }`}
            >
              {step.ok ? "ok" : "fail"}
            </span>
          </div>
        </div>

        {step.thought && isNewest ? (
          <TypewriterText text={step.thought} />
        ) : step.thought ? (
          <p className="mt-2 text-sm italic text-muted font-serif">{step.thought}</p>
        ) : null}

        {step.observation && (
          <p className="mt-1.5 text-sm text-text/90 leading-relaxed break-words">
            {step.observation}
          </p>
        )}
      </motion.div>
    </div>
  );
}

export function ThoughtStream({ steps, running }: { steps: Step[]; running: boolean }) {
  const newestN = steps.length > 0 ? steps[steps.length - 1].n : -1;

  // A step "recovers" the previous one when it repeats the same action right
  // after a failure of that action and itself succeeds.
  const recoveredFrom = new Map<number, number>();
  for (let i = 1; i < steps.length; i++) {
    const prev = steps[i - 1];
    const cur = steps[i];
    if (!prev.ok && cur.ok && cur.action && cur.action === prev.action) {
      recoveredFrom.set(cur.n, prev.n);
    }
  }

  return (
    <div>
      <h2 className="text-[11px] uppercase tracking-wider text-muted font-medium mb-2.5">
        Thought stream
      </h2>
      <div className="space-y-2.5" data-testid="thought-stream">
        {steps.map((step) => (
          <StepCard
            key={step.n}
            step={step}
            isNewest={step.n === newestN}
            recoveredFrom={recoveredFrom.get(step.n) ?? null}
          />
        ))}
        {steps.length === 0 && running && (
          <p className="text-sm text-muted italic">Planning...</p>
        )}
      </div>
    </div>
  );
}
