"use client";

import { useState } from "react";
import type { Label, Lead } from "@/lib/types";
import { ScorePill } from "./ScorePill";

interface LeadsTableProps {
  leads: Lead[];
  labels?: Record<string, Label>;
  /** Present + interactive only on the Review page. Clicking the already-
   * active button un-labels (toggle); clicking the other one relabels. */
  onToggleLabel?: (lead: Lead, next: Label | null) => Promise<void>;
}

function websiteHost(url: string): string {
  try {
    return new URL(url).host.replace(/^www\./, "");
  } catch {
    return url;
  }
}

export function LeadsTable({ leads, labels, onToggleLabel }: LeadsTableProps) {
  const [pending, setPending] = useState<Record<string, boolean>>({});

  const sorted = [...leads].sort((a, b) => b.score - a.score);

  async function handleClick(lead: Lead, clicked: Label) {
    if (!onToggleLabel || pending[lead.id]) return;
    const current = labels?.[lead.id] ?? null;
    const next = current === clicked ? null : clicked;
    setPending((p) => ({ ...p, [lead.id]: true }));
    try {
      await onToggleLabel(lead, next);
    } finally {
      setPending((p) => ({ ...p, [lead.id]: false }));
    }
  }

  if (sorted.length === 0) {
    return (
      <p className="text-sm text-ink-muted italic py-6">
        No leads to show.
      </p>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="border-b border-rule text-left text-ink-muted text-xs uppercase tracking-wide">
            <th className="py-2 pr-3 font-medium">Score</th>
            <th className="py-2 pr-3 font-medium">Name</th>
            <th className="py-2 pr-3 font-medium">Niche</th>
            <th className="py-2 pr-3 font-medium">Phone</th>
            <th className="py-2 pr-3 font-medium">Website</th>
            <th className="py-2 pr-3 font-medium">Reasons</th>
            <th className="py-2 pr-3 font-medium">Hook</th>
            {onToggleLabel && (
              <th className="py-2 pl-3 font-medium text-right">Label</th>
            )}
          </tr>
        </thead>
        <tbody>
          {sorted.map((lead) => {
            const current = labels?.[lead.id] ?? null;
            const isPending = !!pending[lead.id];
            return (
              <tr
                key={lead.id}
                className="border-b border-rule align-top hover:bg-paper-raised/60 transition-colors"
              >
                <td className="py-2.5 pr-3">
                  <ScorePill score={lead.score} />
                </td>
                <td className="py-2.5 pr-3 font-medium text-ink max-w-[16rem]">
                  {lead.name}
                </td>
                <td className="py-2.5 pr-3 text-ink-muted whitespace-nowrap">
                  {lead.niche || "--"}
                </td>
                <td className="py-2.5 pr-3 font-mono text-xs whitespace-nowrap">
                  {lead.phone || "--"}
                </td>
                <td className="py-2.5 pr-3 whitespace-nowrap">
                  {lead.website ? (
                    <a
                      href={lead.website}
                      target="_blank"
                      rel="noreferrer"
                      className="text-ink underline decoration-rule underline-offset-2 hover:decoration-ink"
                    >
                      {websiteHost(lead.website)}
                    </a>
                  ) : (
                    <span className="text-ink-muted">--</span>
                  )}
                </td>
                <td className="py-2.5 pr-3 max-w-[18rem]">
                  <div className="flex flex-wrap gap-1">
                    {lead.reasons.length === 0 && (
                      <span className="text-ink-muted">--</span>
                    )}
                    {lead.reasons.slice(0, 4).map((r, i) => (
                      <span
                        key={i}
                        className="font-mono text-[11px] px-1.5 py-0.5 rounded-sm border border-rule text-ink-muted whitespace-nowrap"
                      >
                        {r}
                      </span>
                    ))}
                  </div>
                </td>
                <td className="py-2.5 pr-3 max-w-[20rem] text-ink-muted italic">
                  {lead.hook || "--"}
                </td>
                {onToggleLabel && (
                  <td className="py-2.5 pl-3">
                    <div className="flex justify-end gap-1.5">
                      <button
                        type="button"
                        disabled={isPending}
                        onClick={() => handleClick(lead, "good")}
                        className={`text-xs px-2 py-1 rounded-sm border transition-colors disabled:opacity-50 ${
                          current === "good"
                            ? "border-ok bg-ok-soft text-ok"
                            : "border-rule text-ink-muted hover:text-ok hover:border-ok"
                        }`}
                      >
                        Good
                      </button>
                      <button
                        type="button"
                        disabled={isPending}
                        onClick={() => handleClick(lead, "bad")}
                        className={`text-xs px-2 py-1 rounded-sm border transition-colors disabled:opacity-50 ${
                          current === "bad"
                            ? "border-fail bg-fail-soft text-fail"
                            : "border-rule text-ink-muted hover:text-fail hover:border-fail"
                        }`}
                      >
                        Bad
                      </button>
                    </div>
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
