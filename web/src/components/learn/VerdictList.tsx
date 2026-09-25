"use client";

import { motion } from "motion/react";
import type { LearnReport, Rule } from "@/lib/types";

type Verdict =
  | { kind: "kept"; rule: Rule }
  | { kind: "rejected"; rule: Record<string, unknown>; reason: string }
  | { kind: "removed"; rule: Rule };

const STAMP: Record<Verdict["kind"], { label: string; cls: string }> = {
  kept: { label: "KEPT", cls: "text-lime bg-lime-soft border-lime/30" },
  rejected: { label: "REJECTED", cls: "text-coral bg-coral-soft border-coral/30" },
  removed: { label: "REMOVED", cls: "text-muted bg-raised border-hairline" },
};

function ruleLine(rule: { feature?: unknown; op?: unknown; value?: unknown }): string {
  return `${rule.feature ?? "?"} ${rule.op ?? ""} ${JSON.stringify(rule.value)}`;
}

export function VerdictList({ report }: { report: LearnReport }) {
  const verdicts: Verdict[] = [
    ...report.added.map((rule): Verdict => ({ kind: "kept", rule })),
    ...report.rejected.map(
      (r): Verdict => ({ kind: "rejected", rule: r.rule, reason: r.reason })
    ),
    ...report.removed.map((rule): Verdict => ({ kind: "removed", rule })),
  ];

  const isOptimistic = report.message.toLowerCase().includes("optimistic");

  return (
    <div className="space-y-3" data-testid="verdict-list">
      <p className="text-sm text-text">{report.message}</p>
      {isOptimistic && (
        <p className="text-xs font-mono text-amber bg-amber-soft border border-amber/30 rounded-md px-2.5 py-1.5 inline-block">
          optimistic: selection and test share data
        </p>
      )}

      {verdicts.length === 0 ? (
        <p className="text-sm text-muted italic">No candidate rules this round.</p>
      ) : (
        <div className="space-y-2">
          {verdicts.map((v, i) => {
            const stamp = STAMP[v.kind];
            return (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.22, delay: i * 0.18 }}
                data-testid="verdict-card"
                data-kind={v.kind}
                className="flex items-center gap-3 border border-hairline rounded-lg px-3.5 py-2.5 bg-surface"
              >
                <span className={`shrink-0 text-[10px] font-mono font-semibold px-2 py-1 rounded border ${stamp.cls}`}>
                  {stamp.label}
                </span>
                <span className="font-mono text-xs text-text truncate flex-1">
                  {ruleLine(v.rule)}
                </span>
                {v.kind === "kept" && (
                  <span className="text-xs font-mono text-lime shrink-0">
                    +{v.rule.holdout_gain.toFixed(1)}
                  </span>
                )}
                {v.kind === "rejected" && (
                  <span className="text-xs text-muted shrink-0 max-w-[40%] truncate" title={v.reason}>
                    {v.reason}
                  </span>
                )}
              </motion.div>
            );
          })}
        </div>
      )}
    </div>
  );
}
