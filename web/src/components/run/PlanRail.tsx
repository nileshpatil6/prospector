"use client";

import { motion } from "motion/react";
import { CheckCircle2, Circle, Loader2 } from "lucide-react";
import type { RunState } from "@/lib/types";
import type { LoopPhase } from "@/lib/format";
import { phaseForAction } from "@/lib/format";
import { useCountUp } from "@/hooks/useCountUp";
import { useElapsedTime } from "@/hooks/useElapsedTime";
import { formatElapsed } from "@/lib/format";

// -- Plan checklist: a step's action doesn't map 1:1 onto a free-text plan
// item, so a plan item is considered "done" once a tool from its matching
// category has completed ok at least once; items with no keyword match
// fall back to ticking in step order. --------------------------------

const CATEGORIES: { keywords: string[]; actions: string[] }[] = [
  { keywords: ["search", "find", "identify", "locate", "discover"], actions: ["geocode", "search_businesses", "widen_area"] },
  { keywords: ["extract", "detail", "contact", "website", "enrich", "phone", "hour"], actions: ["enrich"] },
  { keywords: ["assess", "evaluat", "score", "research", "gap", "need"], actions: ["score", "deep_research"] },
  { keywords: ["compil", "verify", "final", "hook", "pitch", "summar", "report"], actions: ["write_hooks", "finish"] },
];

function categoryFor(text: string) {
  const lower = text.toLowerCase();
  return CATEGORIES.find((c) => c.keywords.some((k) => lower.includes(k)));
}

function planItemDone(item: string, index: number, okActions: Set<string>, okStepCount: number): boolean {
  const cat = categoryFor(item);
  if (cat) return cat.actions.some((a) => okActions.has(a));
  return okStepCount > index;
}

function PlanChecklist({ run }: { run: RunState }) {
  const okActions = new Set(run.step_log.filter((s) => s.ok).map((s) => s.action));
  const okStepCount = run.step_log.filter((s) => s.ok).length;
  const doneFlags = run.plan.map((item, i) => planItemDone(item, i, okActions, okStepCount));
  const currentIndex = doneFlags.findIndex((d) => !d);

  return (
    <div>
      <h2 className="text-[11px] uppercase tracking-wider text-muted font-medium mb-2.5">
        Plan
      </h2>
      <ol className="space-y-2" data-testid="plan-checklist">
        {run.plan.map((item, i) => {
          const done = doneFlags[i];
          const active = run.status === "running" && i === currentIndex;
          return (
            <li key={i} className="flex items-start gap-2 text-sm">
              <motion.span
                key={done ? "done" : "pending"}
                initial={{ scale: 0.5, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                transition={{ type: "spring", stiffness: 400, damping: 20 }}
                className="mt-0.5 shrink-0"
              >
                {done ? (
                  <CheckCircle2 size={15} className="text-lime" />
                ) : active ? (
                  <Loader2 size={15} className="text-amber animate-spin" />
                ) : (
                  <Circle size={15} className="text-hairline" />
                )}
              </motion.span>
              <span className={done ? "text-muted line-through decoration-hairline" : active ? "text-text" : "text-muted"}>
                {item}
              </span>
            </li>
          );
        })}
        {run.plan.length === 0 && (
          <li className="text-sm text-muted italic">Planning...</li>
        )}
      </ol>
    </div>
  );
}

// -- Agent loop indicator ----------------------------------------------

const PHASES: LoopPhase[] = ["plan", "act", "observe", "decide"];
const PHASE_LABEL: Record<LoopPhase, string> = {
  plan: "PLAN",
  act: "ACT",
  observe: "OBSERVE",
  decide: "DECIDE",
};

function LoopIndicator({ run }: { run: RunState }) {
  const last = run.step_log[run.step_log.length - 1];
  const current: LoopPhase = run.step_log.length === 0 ? "plan" : phaseForAction(last.action);

  return (
    <div>
      <h2 className="text-[11px] uppercase tracking-wider text-muted font-medium mb-2.5">
        Agent loop
      </h2>
      <div className="flex items-center gap-1" data-testid="loop-indicator" data-phase={current}>
        {PHASES.map((phase, i) => {
          const active = run.status === "running" && phase === current;
          return (
            <div key={phase} className="flex items-center gap-1 flex-1">
              <div
                className={`flex-1 text-center text-[10px] font-mono py-1.5 rounded-md border transition-colors ${
                  active
                    ? "border-lime/40 bg-lime-soft text-lime"
                    : "border-hairline text-muted"
                }`}
              >
                {PHASE_LABEL[phase]}
              </div>
              {i < PHASES.length - 1 && <span className="text-hairline text-xs">&rsaquo;</span>}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// -- Live counters -------------------------------------------------------

function Counter({ label, value }: { label: string; value: number }) {
  const display = useCountUp(value);
  return (
    <div className="border border-hairline rounded-lg px-3 py-2.5 bg-surface">
      <div className="font-mono tabular-nums text-lg text-text">{display}</div>
      <div className="text-[10px] uppercase tracking-wider text-muted mt-0.5">{label}</div>
    </div>
  );
}

function Counters({ run }: { run: RunState }) {
  const leads = Object.values(run.leads);
  const enriched = leads.filter((l) => l.site_ok !== null || l.fetch_error !== "").length;
  const scored = leads.filter((l) => l.reasons.length > 0).length;
  const elapsedMs = useElapsedTime(run.run_id, run.status === "running");
  const llmCalls = run.step_log.length + 1; // +1 for the initial PLAN call

  return (
    <div>
      <h2 className="text-[11px] uppercase tracking-wider text-muted font-medium mb-2.5">
        Live counters
      </h2>
      <div className="grid grid-cols-2 gap-2" data-testid="counters">
        <Counter label="found" value={leads.length} />
        <Counter label="enriched" value={enriched} />
        <Counter label="scored" value={scored} />
        <Counter label="steps" value={run.step_log.length} />
        <div className="border border-hairline rounded-lg px-3 py-2.5 bg-surface">
          <div className="font-mono tabular-nums text-lg text-text">{formatElapsed(elapsedMs)}</div>
          <div className="text-[10px] uppercase tracking-wider text-muted mt-0.5">elapsed</div>
        </div>
        <div className="border border-hairline rounded-lg px-3 py-2.5 bg-surface">
          <div className="font-mono tabular-nums text-lg text-text">{llmCalls}</div>
          <div className="text-[10px] uppercase tracking-wider text-muted mt-0.5">llm calls</div>
        </div>
      </div>
    </div>
  );
}

export function PlanRail({ run }: { run: RunState }) {
  return (
    <div className="space-y-7">
      <PlanChecklist run={run} />
      <LoopIndicator run={run} />
      <Counters run={run} />
    </div>
  );
}
