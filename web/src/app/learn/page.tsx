"use client";

import { useCallback, useEffect, useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  errorMessage,
  getLabelsSummary,
  getMemory,
  runLearn,
} from "@/lib/api";
import type { LabelsSummary, LearnReport, MemoryResponse } from "@/lib/types";

function RuleRow({
  rule,
  extra,
}: {
  rule: { feature: string; op: string; value: unknown; weight: number; rationale: string };
  extra?: string;
}) {
  return (
    <tr className="border-b border-rule">
      <td className="py-2 pr-3 font-mono text-xs whitespace-nowrap">
        {rule.feature} {rule.op} {JSON.stringify(rule.value)}
      </td>
      <td className="py-2 pr-3 font-mono text-xs">
        {rule.weight > 0 ? "+" : ""}
        {rule.weight}
      </td>
      <td className="py-2 pr-3 text-ink-muted">{rule.rationale}</td>
      {extra !== undefined && (
        <td className="py-2 pl-3 font-mono text-xs text-ok text-right">{extra}</td>
      )}
    </tr>
  );
}

export default function LearnPage() {
  const [summary, setSummary] = useState<LabelsSummary | null>(null);
  const [memory, setMemory] = useState<MemoryResponse | null>(null);
  const [report, setReport] = useState<LearnReport | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [learning, setLearning] = useState(false);
  const [learnError, setLearnError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [s, m] = await Promise.all([getLabelsSummary(), getMemory()]);
      setSummary(s);
      setMemory(m);
      setLoadError(null);
    } catch (err) {
      setLoadError(errorMessage(err));
    }
  }, []);

  useEffect(() => {
    // Fetch on mount; `load` only calls setState after an awaited response.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
  }, [load]);

  async function handleLearn() {
    setLearning(true);
    setLearnError(null);
    try {
      const result = await runLearn();
      setReport(result);
      await load();
    } catch (err) {
      setLearnError(errorMessage(err));
    } finally {
      setLearning(false);
    }
  }

  const chartData =
    memory?.history.map((h, i) => ({
      run: i + 1,
      acc_after: Math.round(h.acc_after * 10) / 10,
      p_at_10_after: h.p_at_10_after === null ? null : Math.round(h.p_at_10_after * 10) / 10,
      optimistic: !!h.note,
    })) ?? [];

  return (
    <div className="space-y-10">
      <div className="space-y-2">
        <h1 className="font-display text-3xl text-ink">Learn</h1>
        <p className="text-ink-muted text-sm max-w-2xl">
          Turn your good/bad labels into new scoring rules, each validated on
          labels the rule-selection step never saw.
        </p>
      </div>

      {loadError && <p className="text-sm text-fail">{loadError}</p>}

      {summary && (
        <div className="border border-rule rounded-sm px-4 py-3 flex flex-wrap items-center justify-between gap-3">
          <span className="text-sm text-ink">
            <span className="font-mono">{summary.total}</span> labelled (
            <span className="text-ok font-mono">{summary.good} good</span>,{" "}
            <span className="text-fail font-mono">{summary.bad} bad</span>)
          </span>
          <div className="flex items-center gap-3">
            {!summary.ready && (
              <span className="text-sm text-ink-muted">
                need {summary.need}
              </span>
            )}
            <button
              type="button"
              disabled={!summary.ready || learning}
              onClick={handleLearn}
              className="bg-ink text-paper text-sm font-medium px-5 py-2 rounded-sm hover:opacity-90 transition-opacity disabled:opacity-40"
            >
              {learning ? "Learning..." : "Learn"}
            </button>
          </div>
        </div>
      )}
      {learnError && <p className="text-sm text-fail">{learnError}</p>}

      {report && (
        <section className="space-y-5 border border-rule rounded-sm px-4 py-4">
          <p className="text-sm text-ink">{report.message}</p>
          {report.ok && (
            <div className="flex flex-wrap gap-6 text-sm">
              <span>
                Test accuracy{" "}
                <span className="font-mono text-ink-muted">
                  {report.acc_before.toFixed(1)}%
                </span>{" "}
                <span aria-hidden>&rarr;</span>{" "}
                <span className="font-mono text-ok">
                  {report.acc_after.toFixed(1)}%
                </span>
              </span>
              <span>
                p@k{" "}
                <span className="font-mono text-ink-muted">
                  {report.p_at_10_before === null ? "n/a" : `${report.p_at_10_before.toFixed(1)}%`}
                </span>{" "}
                <span aria-hidden>&rarr;</span>{" "}
                <span className="font-mono text-ok">
                  {report.p_at_10_after === null ? "n/a" : `${report.p_at_10_after.toFixed(1)}%`}
                </span>
              </span>
            </div>
          )}

          {report.added.length > 0 && (
            <div>
              <h3 className="text-xs uppercase tracking-wide text-ink-muted mb-1.5">
                Added
              </h3>
              <table className="w-full text-sm border-collapse">
                <tbody>
                  {report.added.map((r) => (
                    <RuleRow
                      key={r.id}
                      rule={r}
                      extra={`+${r.holdout_gain.toFixed(1)}`}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {report.removed.length > 0 && (
            <div>
              <h3 className="text-xs uppercase tracking-wide text-ink-muted mb-1.5">
                Removed
              </h3>
              <table className="w-full text-sm border-collapse">
                <tbody>
                  {report.removed.map((r) => (
                    <RuleRow key={r.id} rule={r} />
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {report.rejected.length > 0 && (
            <div>
              <h3 className="text-xs uppercase tracking-wide text-ink-muted mb-1.5">
                Rejected
              </h3>
              <ul className="text-sm space-y-1">
                {report.rejected.map((rej, i) => (
                  <li key={i} className="text-ink-muted">
                    <span className="font-mono text-xs">
                      {String(rej.rule?.feature ?? "?")} {String(rej.rule?.op ?? "")}{" "}
                      {JSON.stringify(rej.rule?.value)}
                    </span>{" "}
                    -- {rej.reason}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>
      )}

      <section className="space-y-3">
        <h2 className="font-display text-xl text-ink">Current rules</h2>
        {memory && memory.rules.length === 0 && (
          <p className="text-sm text-ink-muted italic">
            No learned rules yet -- scoring uses the fixed base heuristic only.
          </p>
        )}
        {memory && memory.rules.length > 0 && (
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="border-b border-rule text-left text-ink-muted text-xs uppercase tracking-wide">
                <th className="py-2 pr-3 font-medium">Rule</th>
                <th className="py-2 pr-3 font-medium">Weight</th>
                <th className="py-2 pr-3 font-medium">Rationale</th>
              </tr>
            </thead>
            <tbody>
              {memory.rules.map((r) => (
                <RuleRow key={r.id} rule={r} />
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="space-y-3">
        <h2 className="font-display text-xl text-ink">Accuracy over time</h2>
        {chartData.length === 0 ? (
          <p className="text-sm text-ink-muted italic">
            No learning runs yet.
          </p>
        ) : (
          <>
            <div className="border border-rule rounded-sm px-2 py-4">
              <ResponsiveContainer width="100%" height={280}>
                <LineChart data={chartData} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
                  <CartesianGrid vertical={false} stroke="var(--rule)" />
                  <XAxis
                    dataKey="run"
                    tickLine={false}
                    axisLine={{ stroke: "var(--rule)" }}
                    tick={{ fill: "var(--ink-muted)", fontSize: 12, fontFamily: "var(--font-mono)" }}
                    label={{ value: "learn run", position: "insideBottom", offset: -2, fill: "var(--ink-muted)", fontSize: 11 }}
                  />
                  <YAxis
                    domain={[0, 100]}
                    unit="%"
                    tickLine={false}
                    axisLine={false}
                    tick={{ fill: "var(--ink-muted)", fontSize: 12, fontFamily: "var(--font-mono)" }}
                  />
                  <Tooltip
                    contentStyle={{
                      background: "var(--paper)",
                      border: "1px solid var(--rule)",
                      borderRadius: 2,
                      fontSize: 12,
                    }}
                    labelFormatter={(v) => `run ${v}`}
                  />
                  <Legend wrapperStyle={{ fontSize: 12, color: "var(--ink-muted)" }} />
                  <Line
                    type="monotone"
                    dataKey="acc_after"
                    name="Test accuracy"
                    stroke="var(--ok)"
                    strokeWidth={2}
                    dot={{ r: 3 }}
                    connectNulls
                  />
                  <Line
                    type="monotone"
                    dataKey="p_at_10_after"
                    name="p@k"
                    stroke="var(--running)"
                    strokeWidth={2}
                    dot={{ r: 3 }}
                    connectNulls
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>

            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="border-b border-rule text-left text-ink-muted text-xs uppercase tracking-wide">
                  <th className="py-2 pr-3 font-medium">Run</th>
                  <th className="py-2 pr-3 font-medium">Labels</th>
                  <th className="py-2 pr-3 font-medium">Test acc</th>
                  <th className="py-2 pr-3 font-medium">p@k</th>
                  <th className="py-2 pr-3 font-medium">Notes</th>
                </tr>
              </thead>
              <tbody>
                {memory!.history.map((h, i) => (
                  <tr key={h.run_id} className="border-b border-rule">
                    <td className="py-2 pr-3 font-mono text-xs">{i + 1}</td>
                    <td className="py-2 pr-3 font-mono text-xs">{h.n_labels}</td>
                    <td className="py-2 pr-3 font-mono text-xs">
                      {h.acc_before.toFixed(1)}% &rarr; {h.acc_after.toFixed(1)}%
                    </td>
                    <td className="py-2 pr-3 font-mono text-xs">
                      {h.p_at_10_before === null ? "n/a" : `${h.p_at_10_before.toFixed(1)}%`} &rarr;{" "}
                      {h.p_at_10_after === null ? "n/a" : `${h.p_at_10_after.toFixed(1)}%`}
                    </td>
                    <td className="py-2 pr-3">
                      {h.note && (
                        <span className="text-[11px] font-mono px-1.5 py-0.5 rounded-sm border border-running/40 bg-running-soft text-running">
                          {h.note}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </section>
    </div>
  );
}
