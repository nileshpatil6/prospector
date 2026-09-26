"use client";

import { useState } from "react";
import dynamic from "next/dynamic";
import { errorMessage, startRun } from "@/lib/api";
import { useRunPolling } from "@/hooks/useRunPolling";
import { useApiHealth } from "@/hooks/useApiHealth";
import { CommandBar } from "@/components/run/CommandBar";
import { PlanRail } from "@/components/run/PlanRail";
import { ThoughtStream } from "@/components/run/ThoughtStream";
import { ResultBanner } from "@/components/run/ResultBanner";
import { LeadCardGrid } from "@/components/run/LeadCard";
import { ApiDownState } from "@/components/ErrorState";
import { MapSkeleton } from "@/components/map/MapSkeleton";

const ProspectorMap = dynamic(() => import("@/components/map/ProspectorMap"), {
  ssr: false,
  loading: () => <MapSkeleton />,
});

const SEARCH_ACTIONS = new Set(["geocode", "search_businesses", "widen_area"]);

const STATUS_LABEL: Record<string, string> = {
  running: "Running",
  done: "Done",
  failed: "Failed",
  max_steps: "Stopped at max steps",
};

export default function RunPage() {
  const [goal, setGoal] = useState("");
  const [runId, setRunId] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);
  const [selectedLeadId, setSelectedLeadId] = useState<string | null>(null);

  const { run, error: pollError } = useRunPolling(runId);
  const health = useApiHealth();

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

  if (health === "down" && !run) {
    return <ApiDownState />;
  }

  if (!run) {
    return (
      <CommandBar
        value={goal}
        onChange={setGoal}
        onSubmit={handleRun}
        busy={busy}
        error={startError}
      />
    );
  }

  const leads = Object.values(run.leads);
  const lastStep = run.step_log[run.step_log.length - 1];
  const sweeping = run.status === "running" && !!lastStep && SEARCH_ACTIONS.has(lastStep.action);

  return (
    <div className="flex flex-col">
      <div className="border-b border-hairline px-4 sm:px-6 py-3.5 flex items-center gap-3 flex-wrap">
        <span
          className={`h-2 w-2 rounded-full shrink-0 ${
            run.status === "running"
              ? "bg-amber pulse-dot"
              : run.status === "done"
                ? "bg-lime"
                : "bg-coral"
          }`}
        />
        <span className="text-sm font-medium text-text">{STATUS_LABEL[run.status]}</span>
        <span className="text-sm text-muted truncate">{run.goal}</span>
        {pollError && <span className="text-sm text-coral ml-auto">{pollError}</span>}
      </div>

      {/* >=1280px: three-panel. Below that: stacked (counters, map, stream). */}
      <div className="xl:hidden flex flex-col">
        <div className="p-4 sm:p-6">
          <PlanRail run={run} />
        </div>
        <div className="h-[360px] border-y border-hairline">
          <ProspectorMap
            leads={leads}
            labels={run.labels}
            bbox={run.bbox}
            selectedId={selectedLeadId}
            onSelect={setSelectedLeadId}
            sweeping={sweeping}
          />
        </div>
        <div className="p-4 sm:p-6">
          <ThoughtStream steps={run.step_log} running={run.status === "running"} />
        </div>
      </div>

      <div className="hidden xl:grid xl:grid-cols-[280px_1fr_400px] xl:h-[calc(100vh-7.75rem)]">
        <div className="border-r border-hairline overflow-y-auto p-5">
          <PlanRail run={run} />
        </div>
        <div className="relative">
          <ProspectorMap
            leads={leads}
            labels={run.labels}
            bbox={run.bbox}
            selectedId={selectedLeadId}
            onSelect={setSelectedLeadId}
            sweeping={sweeping}
          />
        </div>
        <div className="border-l border-hairline overflow-y-auto p-5">
          <ThoughtStream steps={run.step_log} running={run.status === "running"} />
        </div>
      </div>

      {run.status !== "running" && (
        <div className="p-4 sm:p-6 space-y-6 border-t border-hairline">
          <ResultBanner run={run} />
          {run.notes.length > 0 && (
            <ul className="text-sm text-muted space-y-1 list-disc list-inside">
              {run.notes.map((note, i) => (
                <li key={i}>{note}</li>
              ))}
            </ul>
          )}
          <LeadCardGrid leads={leads} runId={run.run_id} />
        </div>
      )}
    </div>
  );
}
