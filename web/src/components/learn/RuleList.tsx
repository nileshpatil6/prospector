"use client";

import type { Rule } from "@/lib/types";

const MAX_WEIGHT = 30; // rules.py MIN_WEIGHT/MAX_WEIGHT

export function RuleList({ rules }: { rules: Rule[] }) {
  if (rules.length === 0) {
    return (
      <p className="text-sm text-muted italic" data-testid="rule-list">
        No learned rules yet -- scoring uses the fixed base heuristic only.
      </p>
    );
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3" data-testid="rule-list">
      {rules.map((r) => {
        const positive = r.weight >= 0;
        const width = (Math.abs(r.weight) / MAX_WEIGHT) * 100;
        return (
          <div key={r.id} className="border border-hairline rounded-lg px-3.5 py-3 bg-surface space-y-2">
            <div className="flex items-start justify-between gap-2">
              <code className="font-mono text-xs text-text">
                {r.feature} {r.op} {JSON.stringify(r.value)}
              </code>
              <span className={`font-mono text-xs shrink-0 ${positive ? "text-lime" : "text-coral"}`}>
                {positive ? "+" : ""}
                {r.weight}
              </span>
            </div>
            <div className="h-1.5 rounded-full bg-hairline overflow-hidden">
              <div
                className={`h-full ${positive ? "bg-lime" : "bg-coral"}`}
                style={{ width: `${width}%` }}
              />
            </div>
            {r.rationale && <p className="text-xs text-muted">{r.rationale}</p>}
            <div className="flex items-center justify-between text-[10px] font-mono text-muted">
              <span>gain +{r.holdout_gain.toFixed(1)}</span>
              <span>{r.created_run}</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}
