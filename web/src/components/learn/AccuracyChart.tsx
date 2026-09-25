"use client";

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
import type { HistoryRecord } from "@/lib/types";

export function AccuracyChart({ history }: { history: HistoryRecord[] }) {
  const data = history.map((h, i) => ({
    run: i + 1,
    acc_after: Math.round(h.acc_after * 10) / 10,
    p_at_10_after: h.p_at_10_after === null ? null : Math.round(h.p_at_10_after * 10) / 10,
  }));

  if (data.length === 0) {
    return (
      <p className="text-sm text-muted italic" data-testid="accuracy-chart">
        No learning runs yet.
      </p>
    );
  }

  return (
    <div className="border border-hairline rounded-xl px-2 py-4 bg-surface" data-testid="accuracy-chart">
      <ResponsiveContainer width="100%" height={260}>
        <LineChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
          <CartesianGrid vertical={false} stroke="var(--hairline)" />
          <XAxis
            dataKey="run"
            tickLine={false}
            axisLine={{ stroke: "var(--hairline)" }}
            tick={{ fill: "var(--muted)", fontSize: 11, fontFamily: "var(--font-geist-mono)" }}
            label={{ value: "learn run", position: "insideBottom", offset: -2, fill: "var(--muted)", fontSize: 10 }}
          />
          <YAxis
            domain={[0, 100]}
            unit="%"
            tickLine={false}
            axisLine={false}
            tick={{ fill: "var(--muted)", fontSize: 11, fontFamily: "var(--font-geist-mono)" }}
          />
          <Tooltip
            contentStyle={{
              background: "var(--surface)",
              border: "1px solid var(--hairline)",
              borderRadius: 8,
              fontSize: 12,
              color: "var(--text)",
            }}
            labelStyle={{ color: "var(--muted)" }}
            labelFormatter={(v) => `run ${v}`}
          />
          <Legend wrapperStyle={{ fontSize: 11, color: "var(--muted)" }} />
          <Line
            type="monotone"
            dataKey="acc_after"
            name="Test accuracy"
            stroke="var(--lime)"
            strokeWidth={2}
            dot={{ r: 3, fill: "var(--lime)" }}
            connectNulls
          />
          <Line
            type="monotone"
            dataKey="p_at_10_after"
            name="p@k"
            stroke="var(--amber)"
            strokeWidth={2}
            dot={{ r: 3, fill: "var(--amber)" }}
            connectNulls
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
