"use client";

import { useEffect, useState } from "react";
import { errorMessage, getRun, listRuns } from "@/lib/api";
import type { RunSummary } from "@/lib/types";
import { RunCard, type RunCardData } from "@/components/runs/RunCard";
import { ApiDownState } from "@/components/ErrorState";

async function enrich(summary: RunSummary): Promise<RunCardData> {
  try {
    const full = await getRun(summary.run_id);
    return {
      run_id: summary.run_id,
      goal: summary.goal,
      place: full.place,
      status: summary.status,
      n_leads: summary.n_leads,
      started_at: summary.started_at,
      scores: Object.values(full.leads).map((l) => l.score),
    };
  } catch {
    // A run whose state.json can't be read for some reason still shows up
    // with the list-endpoint fields, just without a place/histogram.
    return {
      run_id: summary.run_id,
      goal: summary.goal,
      place: "",
      status: summary.status,
      n_leads: summary.n_leads,
      started_at: summary.started_at,
      scores: [],
    };
  }
}

export default function RunsPage() {
  const [runs, setRuns] = useState<RunCardData[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listRuns()
      .then(async (summaries) => {
        const detailed = await Promise.all(summaries.map(enrich));
        if (!cancelled) setRuns(detailed);
      })
      .catch((err) => {
        if (!cancelled) setError(errorMessage(err));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) return <ApiDownState />;

  return (
    <div className="max-w-[1200px] mx-auto px-4 sm:px-6 py-8 space-y-6">
      <h1 className="font-display text-3xl text-text">Runs</h1>

      {!runs && <p className="text-sm text-muted italic">Loading...</p>}

      {runs && runs.length === 0 && (
        <p className="text-sm text-muted italic">
          No runs yet. Start one from the Run page.
        </p>
      )}

      {runs && runs.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3" data-testid="run-list">
          {runs.map((run) => (
            <RunCard key={run.run_id} run={run} />
          ))}
        </div>
      )}
    </div>
  );
}
