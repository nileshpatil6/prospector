"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, Brain } from "lucide-react";
import {
  errorMessage,
  getLabelsSummary,
  getMemory,
  listRuns,
  runLearn,
} from "@/lib/api";
import type { LabelsSummary, LearnReport, MemoryResponse, RunSummary } from "@/lib/types";
import { MetricTiles } from "@/components/learn/MetricTiles";
import { VerdictList } from "@/components/learn/VerdictList";
import { RuleList } from "@/components/learn/RuleList";
import { AccuracyChart } from "@/components/learn/AccuracyChart";
import { useToast } from "@/components/Toast";

export default function LearnPage() {
  const [summary, setSummary] = useState<LabelsSummary | null>(null);
  const [memory, setMemory] = useState<MemoryResponse | null>(null);
  const [report, setReport] = useState<LearnReport | null>(null);
  const [latestRun, setLatestRun] = useState<RunSummary | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [learning, setLearning] = useState(false);
  const toast = useToast();

  const load = useCallback(async () => {
    try {
      const [s, m, runs] = await Promise.all([getLabelsSummary(), getMemory(), listRuns()]);
      setSummary(s);
      setMemory(m);
      setLatestRun(runs[0] ?? null);
      setLoadError(null);
    } catch (err) {
      setLoadError(errorMessage(err));
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
  }, [load]);

  async function handleLearn() {
    setLearning(true);
    try {
      const result = await runLearn();
      setReport(result);
      await load();
    } catch (err) {
      toast.push(errorMessage(err), "fail");
    } finally {
      setLearning(false);
    }
  }

  if (loadError) {
    return <p className="text-sm text-coral p-6">{loadError}</p>;
  }

  const latestHistory = memory && memory.history.length > 0 ? memory.history[memory.history.length - 1] : null;

  return (
    <div className="max-w-[1100px] mx-auto px-4 sm:px-6 py-8 space-y-10">
      <div className="space-y-2">
        <h1 className="font-display text-3xl text-text">Memory</h1>
        <p className="text-muted text-sm max-w-xl">
          Turn your good/bad labels into new scoring rules, each validated on
          labels the selection step never saw.
        </p>
      </div>

      <MetricTiles latest={latestHistory} summary={summary} ruleCount={memory?.rules.length ?? 0} />

      {summary && (
        <div className="flex flex-wrap items-center justify-between gap-3 border border-hairline rounded-xl px-4 py-3.5 bg-surface">
          <span className="text-sm text-text">
            <span className="font-mono">{summary.total}</span> labelled (
            <span className="font-mono text-lime">{summary.good} good</span>,{" "}
            <span className="font-mono text-coral">{summary.bad} bad</span>)
          </span>
          <div className="flex items-center gap-3">
            {!summary.ready && summary.need && (
              <span className="text-sm text-muted">need {summary.need}</span>
            )}
            <button
              type="button"
              disabled={!summary.ready || learning}
              onClick={handleLearn}
              data-testid="learn-button"
              className="flex items-center gap-1.5 bg-lime text-bg text-sm font-semibold px-4 py-2 rounded-lg hover:brightness-110 transition disabled:opacity-30 disabled:cursor-not-allowed"
            >
              <Brain size={14} />
              {learning ? "Learning..." : "Learn"}
            </button>
          </div>
        </div>
      )}

      {summary && !summary.ready && (
        <div className="border border-hairline rounded-xl px-5 py-6 text-center space-y-2" data-testid="not-ready">
          <p className="text-sm text-text">
            Not enough labels yet -- need {summary.need} before a learning run can validate anything.
          </p>
          {latestRun && (
            <Link
              href={`/runs/${latestRun.run_id}`}
              className="inline-flex items-center gap-1 text-sm text-lime hover:underline"
            >
              Review &amp; label leads from &ldquo;{latestRun.goal}&rdquo; <ArrowRight size={13} />
            </Link>
          )}
        </div>
      )}

      {report && (
        <section className="space-y-4 border border-hairline rounded-xl px-5 py-5 bg-surface">
          <h2 className="font-display text-xl text-text">Latest learning run</h2>
          <VerdictList report={report} />
        </section>
      )}

      <section className="space-y-3">
        <h2 className="font-display text-xl text-text">Rules in memory</h2>
        {memory && <RuleList rules={memory.rules} />}
      </section>

      <section className="space-y-3">
        <h2 className="font-display text-xl text-text">Accuracy over time</h2>
        {memory && <AccuracyChart history={memory.history} />}
      </section>
    </div>
  );
}
