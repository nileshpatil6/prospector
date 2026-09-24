"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { errorMessage, listRuns } from "@/lib/api";
import type { RunSummary } from "@/lib/types";

const STATUS_TEXT_CLASS: Record<RunSummary["status"], string> = {
  running: "text-running",
  done: "text-ok",
  failed: "text-fail",
  max_steps: "text-running",
};

function formatDate(startedAt: number): string {
  if (!startedAt) return "--";
  return new Date(startedAt * 1000).toLocaleString();
}

export default function RunsPage() {
  const [runs, setRuns] = useState<RunSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listRuns()
      .then((data) => {
        if (!cancelled) setRuns(data);
      })
      .catch((err) => {
        if (!cancelled) setError(errorMessage(err));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="space-y-6">
      <h1 className="font-display text-3xl text-ink">Runs</h1>

      {error && <p className="text-sm text-fail">{error}</p>}

      {!runs && !error && (
        <p className="text-sm text-ink-muted italic">Loading...</p>
      )}

      {runs && runs.length === 0 && (
        <p className="text-sm text-ink-muted italic">
          No runs yet. Start one from the Run page.
        </p>
      )}

      {runs && runs.length > 0 && (
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="border-b border-rule text-left text-ink-muted text-xs uppercase tracking-wide">
              <th className="py-2 pr-3 font-medium">Started</th>
              <th className="py-2 pr-3 font-medium">Goal</th>
              <th className="py-2 pr-3 font-medium">Status</th>
              <th className="py-2 pr-3 font-medium">Leads</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((run) => (
              <tr
                key={run.run_id}
                className="border-b border-rule hover:bg-paper-raised/60 transition-colors"
              >
                <td className="py-2.5 pr-3 font-mono text-xs text-ink-muted whitespace-nowrap">
                  {formatDate(run.started_at)}
                </td>
                <td className="py-2.5 pr-3 max-w-md">
                  <Link
                    href={`/runs/${run.run_id}`}
                    className="text-ink underline decoration-rule underline-offset-2 hover:decoration-ink"
                  >
                    {run.goal}
                  </Link>
                </td>
                <td
                  className={`py-2.5 pr-3 font-medium ${STATUS_TEXT_CLASS[run.status]}`}
                >
                  {run.status}
                </td>
                <td className="py-2.5 pr-3 font-mono">{run.n_leads}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
