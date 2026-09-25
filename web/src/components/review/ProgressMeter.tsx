"use client";

import Link from "next/link";
import { ArrowRight } from "lucide-react";
import type { LabelsSummary } from "@/lib/types";

const MIN_LABELS = 12; // mirrors learner.MIN_LABELS -- see labels_summary()'s `need` text

export function ProgressMeter({ summary }: { summary: LabelsSummary }) {
  const pct = Math.min(100, Math.round((summary.total / MIN_LABELS) * 100));

  return (
    <div className="flex items-center gap-3 flex-wrap" data-testid="progress-meter">
      <div className="flex items-center gap-2 text-sm">
        <span className="font-mono tabular-nums text-text">{summary.total}</span>
        <span className="text-muted">labelled</span>
        <span className="font-mono text-lime">{summary.good} good</span>
        <span className="font-mono text-coral">{summary.bad} bad</span>
      </div>

      <div className="w-28 h-1.5 rounded-full bg-hairline overflow-hidden">
        <div
          className={`h-full transition-[width] duration-300 ${summary.ready ? "bg-lime" : "bg-amber"}`}
          style={{ width: `${pct}%` }}
        />
      </div>

      {summary.ready ? (
        <Link
          href="/learn"
          data-testid="ready-to-learn"
          className="flex items-center gap-1 text-sm text-lime font-medium hover:underline"
        >
          Ready to learn <ArrowRight size={13} />
        </Link>
      ) : (
        summary.need && (
          <span className="text-xs text-muted">need {summary.need} to learn</span>
        )
      )}
    </div>
  );
}
