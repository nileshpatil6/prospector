"use client";

import { useState } from "react";
import { errorMessage, getCsvUrl, getReportUrl, startRun } from "@/lib/api";
import { useRunPolling } from "@/hooks/useRunPolling";
import { StatusBar } from "@/components/StatusBar";
import { StepCard } from "@/components/StepCard";
import { LeadsTable } from "@/components/LeadsTable";

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

export default function RunPage() {
  const [goal, setGoal] = useState("");
  const [runId, setRunId] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);

  const { run, error: pollError } = useRunPolling(runId);

  const busy = starting || run?.status === "running";

  async function handleRun() {
    const trimmed = goal.trim();
    if (!trimmed || busy) return;
    setStarting(true);
    setStartError(null);
    try {
      const { run_id } = await startRun(trimmed);
      setRunId(run_id);
    } catch (err) {
      setStartError(errorMessage(err));
    } finally {
      setStarting(false);
    }
  }

  const leads = run ? Object.values(run.leads) : [];

  return (
    <div className="space-y-10">
      <section className="space-y-4">
        <h1 className="font-display text-3xl text-ink">New run</h1>
        <p className="text-ink-muted text-sm max-w-2xl">
          Describe who you&apos;re looking for. The agent plans, searches
          OpenStreetMap, enriches each business&apos;s website, scores every
          lead, and writes a one-line pitch hook for the best ones.
        </p>

        <textarea
          value={goal}
          onChange={(e) => setGoal(e.target.value)}
          placeholder="Find 30 dental clinics in Pune that would benefit from an AI phone receptionist"
          rows={3}
          disabled={busy}
          className="w-full resize-none border border-rule bg-paper px-4 py-3 text-base font-display placeholder:text-ink-muted/70 focus:outline-none focus:border-ink rounded-sm disabled:opacity-60"
        />

        <div className="flex flex-wrap gap-2">
          {EXAMPLES.map((ex) => (
            <button
              key={ex.chip}
              type="button"
              disabled={busy}
              onClick={() => setGoal(ex.goal)}
              className="text-xs font-mono px-2.5 py-1 rounded-full border border-rule text-ink-muted hover:text-ink hover:border-ink transition-colors disabled:opacity-50"
            >
              {ex.chip}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={handleRun}
            disabled={busy || !goal.trim()}
            className="bg-ink text-paper text-sm font-medium px-5 py-2.5 rounded-sm hover:opacity-90 transition-opacity disabled:opacity-40"
          >
            {starting ? "Starting..." : run?.status === "running" ? "Running..." : "Run"}
          </button>
          {startError && (
            <span className="text-sm text-fail">{startError}</span>
          )}
        </div>
      </section>

      {run && (
        <section className="space-y-5 border-t border-rule pt-8">
          <StatusBar
            status={run.status}
            detail={
              run.status === "running"
                ? `step ${run.step_log.length}${run.plan.length ? ` of plan (${run.plan.length} items)` : ""}`
                : `${leads.length} lead${leads.length === 1 ? "" : "s"} found`
            }
          />
          {pollError && (
            <p className="text-sm text-fail">{pollError}</p>
          )}

          {run.plan.length > 0 && (
            <div className="border border-rule rounded-sm px-4 py-3">
              <h2 className="text-xs uppercase tracking-wide text-ink-muted mb-2">
                Plan
              </h2>
              <ol className="list-decimal list-inside space-y-1 text-sm text-ink">
                {run.plan.map((item, i) => (
                  <li key={i}>{item}</li>
                ))}
              </ol>
            </div>
          )}

          <div className="space-y-2.5">
            {run.step_log.map((step) => (
              <StepCard key={step.n} step={step} />
            ))}
            {run.step_log.length === 0 && run.status === "running" && (
              <p className="text-sm text-ink-muted italic">
                Planning...
              </p>
            )}
          </div>

          {run.status !== "running" && (
            <div className="space-y-6 border-t border-rule pt-6">
              {run.final_answer && (
                <p className="text-base font-display text-ink">
                  {run.final_answer}
                </p>
              )}

              {run.notes.length > 0 && (
                <ul className="text-sm text-ink-muted space-y-1 list-disc list-inside">
                  {run.notes.map((note, i) => (
                    <li key={i}>{note}</li>
                  ))}
                </ul>
              )}

              <div className="flex items-center gap-3">
                <a
                  href={getReportUrl(run.run_id)}
                  target="_blank"
                  rel="noreferrer"
                  className="text-sm px-3 py-1.5 border border-rule rounded-sm text-ink hover:border-ink transition-colors"
                >
                  View report
                </a>
                <a
                  href={getCsvUrl(run.run_id)}
                  className="text-sm px-3 py-1.5 border border-rule rounded-sm text-ink hover:border-ink transition-colors"
                >
                  Download CSV
                </a>
                <a
                  href={`/runs/${run.run_id}`}
                  className="text-sm px-3 py-1.5 border border-rule rounded-sm text-ink hover:border-ink transition-colors"
                >
                  Review &amp; label
                </a>
              </div>

              <LeadsTable leads={leads} />
            </div>
          )}
        </section>
      )}
    </div>
  );
}
