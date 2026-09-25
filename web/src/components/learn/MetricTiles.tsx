"use client";

import { useCountUp } from "@/hooks/useCountUp";
import type { HistoryRecord, LabelsSummary } from "@/lib/types";

function Tile({
  label,
  before,
  after,
  suffix = "",
}: {
  label: string;
  before: number | null;
  after: number | null;
  suffix?: string;
}) {
  const afterDisplay = useCountUp(after === null ? 0 : Math.round(after * 10));

  return (
    <div className="border border-hairline rounded-xl px-4 py-3.5 bg-surface">
      <div className="text-[10px] uppercase tracking-wider text-muted font-medium mb-1.5">
        {label}
      </div>
      {after === null ? (
        <div className="font-mono text-xl text-muted">n/a</div>
      ) : (
        <div className="flex items-baseline gap-1.5 font-mono tabular-nums">
          {before !== null && (
            <>
              <span className="text-sm text-muted">{before.toFixed(1)}{suffix}</span>
              <span className="text-muted text-sm">&rarr;</span>
            </>
          )}
          <span className="text-xl text-lime">
            {(afterDisplay / 10).toFixed(1)}
            {suffix}
          </span>
        </div>
      )}
    </div>
  );
}

function CountTile({ label, value, sub }: { label: string; value: number; sub?: string }) {
  const display = useCountUp(value);
  return (
    <div className="border border-hairline rounded-xl px-4 py-3.5 bg-surface">
      <div className="text-[10px] uppercase tracking-wider text-muted font-medium mb-1.5">
        {label}
      </div>
      <div className="font-mono tabular-nums text-xl text-text">{display}</div>
      {sub && <div className="text-[11px] text-muted mt-0.5">{sub}</div>}
    </div>
  );
}

export function MetricTiles({
  latest,
  summary,
  ruleCount,
}: {
  latest: HistoryRecord | null;
  summary: LabelsSummary | null;
  ruleCount: number;
}) {
  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3" data-testid="metric-tiles">
      <Tile
        label="Test accuracy"
        before={latest?.acc_before ?? null}
        after={latest?.acc_after ?? null}
        suffix="%"
      />
      <Tile
        label="p@k"
        before={latest?.p_at_10_before ?? null}
        after={latest?.p_at_10_after ?? null}
        suffix="%"
      />
      <CountTile
        label="Labels"
        value={summary?.total ?? 0}
        sub={summary ? `${summary.good} good · ${summary.bad} bad` : undefined}
      />
      <CountTile label="Rules in memory" value={ruleCount} />
    </div>
  );
}
