"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import {
  deleteLabel,
  errorMessage,
  getCsvUrl,
  getLabelsSummary,
  getReportUrl,
  getRun,
  postLabel,
} from "@/lib/api";
import type { Label, Lead, LabelsSummary, RunState } from "@/lib/types";
import { StatusBar } from "@/components/StatusBar";
import { LeadsTable } from "@/components/LeadsTable";

type Filter = "all" | "unlabelled";

export default function ReviewPage() {
  const params = useParams<{ id: string }>();
  const runId = params.id;

  const [run, setRun] = useState<RunState | null>(null);
  const [labels, setLabels] = useState<Record<string, Label>>({});
  const [summary, setSummary] = useState<LabelsSummary | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [toggleError, setToggleError] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>("all");

  const load = useCallback(async () => {
    try {
      const [runData, summaryData] = await Promise.all([
        getRun(runId),
        getLabelsSummary(),
      ]);
      setRun(runData);
      setLabels(runData.labels);
      setSummary(summaryData);
      setLoadError(null);
    } catch (err) {
      setLoadError(errorMessage(err));
    }
  }, [runId]);

  useEffect(() => {
    // Fetch on mount; `load` only calls setState after an awaited response.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
  }, [load]);

  async function handleToggle(lead: Lead, next: Label | null) {
    const previous = labels[lead.id] ?? null;
    setToggleError(null);
    setLabels((old) => {
      const copy = { ...old };
      if (next === null) delete copy[lead.id];
      else copy[lead.id] = next;
      return copy;
    });
    try {
      if (next === null) {
        await deleteLabel(lead.id);
      } else {
        await postLabel(runId, lead.id, next);
      }
      const s = await getLabelsSummary();
      setSummary(s);
    } catch (err) {
      // revert the optimistic update
      setLabels((old) => {
        const copy = { ...old };
        if (previous === null) delete copy[lead.id];
        else copy[lead.id] = previous;
        return copy;
      });
      setToggleError(errorMessage(err));
    }
  }

  if (loadError) {
    return <p className="text-sm text-fail">{loadError}</p>;
  }
  if (!run) {
    return <p className="text-sm text-ink-muted italic">Loading...</p>;
  }

  const allLeads = Object.values(run.leads);
  const visibleLeads =
    filter === "unlabelled"
      ? allLeads.filter((lead) => !labels[lead.id])
      : allLeads;

  return (
    <div className="space-y-6">
      <div className="space-y-3">
        <h1 className="font-display text-3xl text-ink">{run.goal}</h1>
        <div className="flex flex-wrap items-center gap-3">
          <StatusBar
            status={run.status}
            detail={`${allLeads.length} lead${allLeads.length === 1 ? "" : "s"}`}
          />
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
        </div>
      </div>

      {summary && (
        <div className="sticky top-14 z-10 -mx-4 sm:-mx-6 px-4 sm:px-6 py-2.5 bg-paper/95 backdrop-blur border-y border-rule text-sm flex flex-wrap items-center justify-between gap-2">
          <span className="text-ink">
            <span className="font-mono">{summary.total}</span> labelled (
            <span className="text-ok font-mono">{summary.good} good</span>,{" "}
            <span className="text-fail font-mono">{summary.bad} bad</span>)
            {!summary.ready && summary.need && (
              <span className="text-ink-muted"> -- need {summary.need}</span>
            )}
            {summary.ready && (
              <span className="text-ok"> -- ready to learn</span>
            )}
          </span>
          <div className="flex gap-1">
            {(["all", "unlabelled"] as Filter[]).map((f) => (
              <button
                key={f}
                type="button"
                onClick={() => setFilter(f)}
                className={`text-xs px-2.5 py-1 rounded-sm border transition-colors ${
                  filter === f
                    ? "border-ink text-ink"
                    : "border-rule text-ink-muted hover:text-ink"
                }`}
              >
                {f === "all" ? "All" : "Unlabelled"}
              </button>
            ))}
          </div>
        </div>
      )}

      {toggleError && <p className="text-sm text-fail">{toggleError}</p>}

      <LeadsTable
        leads={visibleLeads}
        labels={labels}
        onToggleLabel={handleToggle}
      />
    </div>
  );
}
