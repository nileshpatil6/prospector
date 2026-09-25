"use client";

import { ArrowRight, Sparkles } from "lucide-react";
import { motion } from "motion/react";

const EXAMPLES: { chip: string; goal: string }[] = [
  {
    chip: "20 dental clinics, Pune",
    goal: "Find 20 dental clinics in Pune that would benefit from an AI phone receptionist",
  },
  {
    chip: "salons, Mumbai",
    goal: "Find 15 salons in Mumbai that would benefit from an AI phone receptionist",
  },
  {
    chip: "physio clinics, Nashik",
    goal: "Find 15 physiotherapy clinics in Nashik that would benefit from an AI phone receptionist",
  },
];

interface CommandBarProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  busy: boolean;
  error?: string | null;
}

export function CommandBar({ value, onChange, onSubmit, busy, error }: CommandBarProps) {
  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onSubmit();
    }
  }

  return (
    <div className="relative overflow-hidden">
      <div
        aria-hidden
        className="absolute inset-0 bg-radar-rings opacity-60 pointer-events-none"
        style={{ maskImage: "radial-gradient(circle at 50% 40%, black, transparent 75%)" }}
      />
      <div className="relative max-w-3xl mx-auto px-4 sm:px-6 pt-20 pb-16 text-center">
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          className="inline-flex items-center gap-1.5 text-xs font-mono text-lime bg-lime-soft border border-lime/25 rounded-full px-3 py-1 mb-6"
        >
          <Sparkles size={12} />
          radar for your next customers
        </motion.div>

        <motion.h1
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.45, delay: 0.05 }}
          className="font-display text-4xl sm:text-5xl font-semibold tracking-tight text-text leading-[1.08]"
        >
          Tell it who you want to{" "}
          <span className="font-serif italic font-normal text-lime">sell</span> to.
        </motion.h1>

        <motion.p
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.45, delay: 0.1 }}
          className="mt-4 text-sm text-muted max-w-lg mx-auto"
        >
          The agent plans a search, acts through OpenStreetMap and live
          websites, observes what it finds, and learns from every good or
          bad label you give it.
        </motion.p>

        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.45, delay: 0.15 }}
          className="mt-8 text-left"
        >
          <div className="relative rounded-xl border border-hairline bg-surface shadow-2xl shadow-black/40 focus-within:border-lime/50 transition-colors">
            <textarea
              value={value}
              onChange={(e) => onChange(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Find 30 dental clinics in Pune that would benefit from an AI phone receptionist"
              rows={2}
              disabled={busy}
              data-testid="goal-input"
              className="w-full resize-none bg-transparent px-5 pt-4 pb-3 text-base text-text placeholder:text-muted/70 focus:outline-none disabled:opacity-60"
            />
            <div className="flex items-center justify-between px-4 pb-3">
              <span className="text-[11px] font-mono text-muted">
                Enter to run &middot; Shift+Enter for a new line
              </span>
              <button
                type="button"
                onClick={onSubmit}
                disabled={busy || !value.trim()}
                data-testid="run-button"
                className="flex items-center gap-1.5 bg-lime text-bg text-sm font-semibold px-4 py-1.5 rounded-lg hover:brightness-110 active:brightness-95 transition disabled:opacity-30 disabled:cursor-not-allowed"
              >
                {busy ? "Starting..." : "Run"}
                {!busy && <ArrowRight size={14} />}
              </button>
            </div>
          </div>

          {error && (
            <p className="mt-2.5 text-sm text-coral" data-testid="start-error">
              {error}
            </p>
          )}

          <div className="mt-4 flex flex-wrap gap-2 justify-center">
            {EXAMPLES.map((ex) => (
              <button
                key={ex.chip}
                type="button"
                disabled={busy}
                onClick={() => onChange(ex.goal)}
                className="text-xs font-mono px-3 py-1.5 rounded-full border border-hairline text-muted hover:text-text hover:border-lime/40 transition-colors disabled:opacity-50"
              >
                {ex.chip}
              </button>
            ))}
          </div>
        </motion.div>

        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.4, delay: 0.25 }}
          className="mt-10 text-xs font-mono text-muted tracking-wide"
        >
          PLAN <span className="text-hairline mx-1">&rarr;</span> ACT{" "}
          <span className="text-hairline mx-1">&rarr;</span> OBSERVE{" "}
          <span className="text-hairline mx-1">&rarr;</span> LEARN
        </motion.p>
      </div>
    </div>
  );
}
