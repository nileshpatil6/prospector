"use client";

import type { Label, Lead } from "@/lib/types";
import { ScoreRing } from "@/components/ScoreRing";
import { Favicon } from "./Favicon";
import { websiteHost } from "@/lib/format";

interface LedgerProps {
  leads: Lead[];
  labels: Record<string, Label>;
  selectedId: string | null;
  onSelect: (id: string) => void;
}

const LABEL_DOT: Record<Label, string> = {
  good: "bg-lime",
  bad: "bg-coral",
};

export function Ledger({ leads, labels, selectedId, onSelect }: LedgerProps) {
  const sorted = [...leads].sort((a, b) => b.score - a.score);

  if (sorted.length === 0) {
    return <p className="text-sm text-muted italic py-8 text-center">No leads match this filter.</p>;
  }

  return (
    <table className="w-full text-sm border-collapse" data-testid="ledger">
      <thead>
        <tr className="border-b border-hairline text-left text-muted text-[11px] uppercase tracking-wider sticky top-0 bg-bg">
          <th className="py-2 pr-3 font-medium w-16">Score</th>
          <th className="py-2 pr-3 font-medium">Name</th>
          <th className="py-2 pr-3 font-medium hidden sm:table-cell">Niche</th>
          <th className="py-2 pr-3 font-medium hidden md:table-cell">Phone</th>
          <th className="py-2 pr-3 font-medium hidden md:table-cell">Website</th>
          <th className="py-2 pr-3 font-medium hidden lg:table-cell">Reasons</th>
          <th className="py-2 pl-3 font-medium w-8" />
        </tr>
      </thead>
      <tbody>
        {sorted.map((lead) => {
          const selected = lead.id === selectedId;
          const label = labels[lead.id];
          return (
            <tr
              key={lead.id}
              onClick={() => onSelect(lead.id)}
              data-testid="ledger-row"
              data-lead-id={lead.id}
              data-selected={selected}
              className={`border-b border-hairline align-middle cursor-pointer transition-colors ${
                selected ? "bg-lime-soft" : "hover:bg-raised"
              }`}
            >
              <td className="py-2 pr-3">
                <ScoreRing score={lead.score} size={30} />
              </td>
              <td className="py-2 pr-3 font-medium text-text max-w-[14rem] truncate">
                {lead.name}
              </td>
              <td className="py-2 pr-3 text-muted hidden sm:table-cell whitespace-nowrap">
                {lead.niche || "--"}
              </td>
              <td className="py-2 pr-3 font-mono text-xs hidden md:table-cell whitespace-nowrap">
                {lead.phone || "--"}
              </td>
              <td className="py-2 pr-3 hidden md:table-cell whitespace-nowrap">
                {lead.website ? (
                  <span className="flex items-center gap-1.5">
                    <Favicon website={lead.website} />
                    <span className="text-muted">{websiteHost(lead.website)}</span>
                  </span>
                ) : (
                  <span className="text-muted">--</span>
                )}
              </td>
              <td className="py-2 pr-3 max-w-[16rem] hidden lg:table-cell">
                <div className="flex flex-wrap gap-1">
                  {lead.reasons.slice(0, 2).map((r, i) => (
                    <span
                      key={i}
                      className="font-mono text-[10px] px-1.5 py-0.5 rounded border border-hairline text-muted whitespace-nowrap"
                    >
                      {r.split(":")[0]}
                    </span>
                  ))}
                </div>
              </td>
              <td className="py-2 pl-3">
                {label && (
                  <span
                    className={`inline-block h-2 w-2 rounded-full ${LABEL_DOT[label]}`}
                    title={label}
                  />
                )}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
