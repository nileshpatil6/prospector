"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
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
import type { Label, LabelsSummary, RunState } from "@/lib/types";
import { Ledger } from "@/components/review/Ledger";
import { DetailPanel } from "@/components/review/DetailPanel";
import { FilterTabs, type ReviewFilter } from "@/components/review/FilterTabs";
import { ProgressMeter } from "@/components/review/ProgressMeter";
import { ShortcutLegend } from "@/components/review/ShortcutLegend";
import { useToast } from "@/components/Toast";
import { FileText, Download } from "lucide-react";

export default function ReviewPage() {
  const params = useParams<{ id: string }>();
  const runId = params.id;
  const toast = useToast();

  const [run, setRun] = useState<RunState | null>(null);
  const [labels, setLabels] = useState<Record<string, Label>>({});
  const [summary, setSummary] = useState<LabelsSummary | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [filter, setFilter] = useState<ReviewFilter>("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [pendingId, setPendingId] = useState<string | null>(null);

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
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
  }, [load]);

  const allLeads = useMemo(() => (run ? Object.values(run.leads) : []), [run]);
  const visibleLeads = useMemo(() => {
    const sorted = [...allLeads].sort((a, b) => b.score - a.score);
    if (filter === "unlabelled") return sorted.filter((l) => !labels[l.id]);
    if (filter === "good") return sorted.filter((l) => labels[l.id] === "good");
    if (filter === "bad") return sorted.filter((l) => labels[l.id] === "bad");
    return sorted;
  }, [allLeads, labels, filter]);

  useEffect(() => {
    // Keeps selection valid as the filter changes the visible set -- a
    // deliberate sync of derived state, not an avoidable effect.
    if (visibleLeads.length === 0) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setSelectedId(null);
      return;
    }
    if (!selectedId || !visibleLeads.some((l) => l.id === selectedId)) {
      setSelectedId(visibleLeads[0].id);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visibleLeads]);

  const handleToggle = useCallback(
    async (leadId: string, next: Label | null) => {
      const previous = labels[leadId] ?? null;
      if (previous === next) return;
      setPendingId(leadId);
      setLabels((old) => {
        const copy = { ...old };
        if (next === null) delete copy[leadId];
        else copy[leadId] = next;
        return copy;
      });
      try {
        if (next === null) {
          await deleteLabel(leadId);
        } else {
          await postLabel(runId, leadId, next);
        }
        const s = await getLabelsSummary();
        setSummary(s);
        toast.push(next ? `Marked ${next}` : "Label cleared", "ok");
      } catch (err) {
        setLabels((old) => {
          const copy = { ...old };
          if (previous === null) delete copy[leadId];
          else copy[leadId] = previous;
          return copy;
        });
        toast.push(errorMessage(err), "fail");
      } finally {
        setPendingId(null);
      }
    },
    [labels, runId, toast]
  );

  // Keyboard shortcuts: J/K or arrows move selection, G/B label, U clears.
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      const target = e.target as HTMLElement | null;
      if (target && ["INPUT", "TEXTAREA"].includes(target.tagName)) return;
      if (visibleLeads.length === 0) return;

      const idx = visibleLeads.findIndex((l) => l.id === selectedId);

      if (e.key === "j" || e.key === "ArrowDown") {
        e.preventDefault();
        const next = visibleLeads[Math.min(visibleLeads.length - 1, idx + 1)];
        if (next) setSelectedId(next.id);
      } else if (e.key === "k" || e.key === "ArrowUp") {
        e.preventDefault();
        const prev = visibleLeads[Math.max(0, idx - 1)];
        if (prev) setSelectedId(prev.id);
      } else if ((e.key === "g" || e.key === "G") && selectedId) {
        handleToggle(selectedId, labels[selectedId] === "good" ? null : "good");
      } else if ((e.key === "b" || e.key === "B") && selectedId) {
        handleToggle(selectedId, labels[selectedId] === "bad" ? null : "bad");
      } else if ((e.key === "u" || e.key === "U") && selectedId) {
        handleToggle(selectedId, null);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [visibleLeads, selectedId, labels, handleToggle]);

  if (loadError) {
    return <p className="text-sm text-coral p-6">{loadError}</p>;
  }
  if (!run) {
    return <p className="text-sm text-muted italic p-6">Loading...</p>;
  }

  const selectedLead = allLeads.find((l) => l.id === selectedId) ?? null;

  return (
    <div className="flex flex-col">
      <div className="border-b border-hairline px-4 sm:px-6 py-4 space-y-3">
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div>
            <h1 className="font-display text-2xl text-text leading-tight">{run.goal}</h1>
            <p className="text-xs text-muted mt-1">
              {allLeads.length} lead{allLeads.length === 1 ? "" : "s"}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <a
              href={getReportUrl(run.run_id)}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-md border border-hairline text-text hover:border-lime/40 transition"
            >
              <FileText size={12} /> Report
            </a>
            <a
              href={getCsvUrl(run.run_id)}
              className="flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-md border border-hairline text-text hover:border-lime/40 transition"
            >
              <Download size={12} /> CSV
            </a>
          </div>
        </div>

        <div className="flex items-center justify-between gap-3 flex-wrap">
          {summary && <ProgressMeter summary={summary} />}
          <FilterTabs value={filter} onChange={setFilter} />
        </div>
        <ShortcutLegend />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_360px]">
        <div className="overflow-x-auto p-4 sm:p-6">
          <Ledger
            leads={visibleLeads}
            labels={labels}
            selectedId={selectedId}
            onSelect={setSelectedId}
          />
        </div>
        <div className="border-l border-hairline p-4 sm:p-6 lg:sticky lg:top-14 lg:self-start lg:max-h-[calc(100vh-3.5rem)] lg:overflow-y-auto">
          {selectedLead ? (
            <DetailPanel
              lead={selectedLead}
              label={labels[selectedLead.id]}
              pending={pendingId === selectedLead.id}
              onLabel={(next) => handleToggle(selectedLead.id, next)}
            />
          ) : (
            <p className="text-sm text-muted italic">No lead selected.</p>
          )}
        </div>
      </div>
    </div>
  );
}
