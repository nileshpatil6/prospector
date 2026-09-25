import Link from "next/link";
import type { RunStatus } from "@/lib/types";
import { formatDate } from "@/lib/format";

const STATUS_DOT: Record<RunStatus, string> = {
  running: "bg-amber pulse-dot",
  done: "bg-lime",
  failed: "bg-coral",
  max_steps: "bg-amber",
};

const STATUS_TEXT: Record<RunStatus, string> = {
  running: "text-amber",
  done: "text-lime",
  failed: "text-coral",
  max_steps: "text-amber",
};

const BUCKETS = 10;

function Histogram({ scores }: { scores: number[] }) {
  if (scores.length === 0) {
    return <div className="h-6 flex items-end text-[10px] text-muted italic">no leads</div>;
  }
  const buckets = new Array(BUCKETS).fill(0);
  for (const s of scores) {
    const idx = Math.min(BUCKETS - 1, Math.max(0, Math.floor(s / 100 * BUCKETS)));
    buckets[idx] += 1;
  }
  const max = Math.max(...buckets, 1);

  return (
    <div className="h-6 flex items-end gap-[2px]" data-testid="score-histogram">
      {buckets.map((count, i) => (
        <div
          key={i}
          className="flex-1 rounded-[1px]"
          style={{
            height: `${Math.max(8, (count / max) * 100)}%`,
            background: i >= 6.5 ? "var(--lime)" : i >= 3.5 ? "var(--amber)" : "var(--coral)",
            opacity: count === 0 ? 0.15 : 1,
          }}
        />
      ))}
    </div>
  );
}

export interface RunCardData {
  run_id: string;
  goal: string;
  place: string;
  status: RunStatus;
  n_leads: number;
  started_at: number;
  scores: number[];
}

export function RunCard({ run }: { run: RunCardData }) {
  return (
    <Link
      href={`/runs/${run.run_id}`}
      data-testid="run-card"
      className="block border border-hairline rounded-xl p-4 bg-surface hover:border-lime/40 transition-colors space-y-3"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-sm font-medium text-text line-clamp-2">{run.goal}</p>
          {run.place && <p className="text-xs text-muted mt-0.5">{run.place}</p>}
        </div>
        <span className={`h-2 w-2 rounded-full shrink-0 mt-1.5 ${STATUS_DOT[run.status]}`} />
      </div>

      <Histogram scores={run.scores} />

      <div className="flex items-center justify-between text-xs font-mono text-muted">
        <span className={STATUS_TEXT[run.status]}>{run.status}</span>
        <span>{run.n_leads} leads</span>
        <span>{formatDate(run.started_at)}</span>
      </div>
    </Link>
  );
}
