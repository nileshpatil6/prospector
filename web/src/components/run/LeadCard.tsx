"use client";

import { motion } from "motion/react";
import type { Lead } from "@/lib/types";
import { ScoreRing } from "@/components/ScoreRing";
import { websiteHost } from "@/lib/format";
import { CallReceptionistButton } from "@/components/call/CallReceptionistButton";

export function LeadCardGrid({ leads, runId }: { leads: Lead[]; runId: string }) {
  const top = [...leads].sort((a, b) => b.score - a.score).slice(0, 5);
  if (top.length === 0) return null;

  return (
    <div>
      <h2 className="text-[11px] uppercase tracking-wider text-muted font-medium mb-2.5">
        Top leads
      </h2>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3" data-testid="top-leads">
        {top.map((lead, i) => (
          <motion.div
            key={lead.id}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.25, delay: i * 0.05 }}
            className="border border-hairline rounded-xl p-3.5 bg-surface flex flex-col gap-2.5"
            data-testid="lead-card"
          >
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="text-sm font-medium text-text truncate">{lead.name}</p>
                <p className="text-[11px] text-muted truncate">
                  {lead.niche || "--"}
                  {lead.website ? ` · ${websiteHost(lead.website)}` : ""}
                </p>
              </div>
              <ScoreRing score={lead.score} size={34} />
            </div>

            {lead.reasons.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {lead.reasons.slice(0, 3).map((r, ri) => (
                  <span
                    key={ri}
                    className="font-mono text-[10px] px-1.5 py-0.5 rounded border border-hairline text-muted"
                  >
                    {r}
                  </span>
                ))}
              </div>
            )}

            {lead.hook && (
              <blockquote className="text-xs italic text-text/90 font-serif border-l-2 border-lime/40 pl-2.5 mt-auto">
                &ldquo;{lead.hook}&rdquo;
              </blockquote>
            )}

            <CallReceptionistButton runId={runId} lead={lead} className="mt-1 self-start" />
          </motion.div>
        ))}
      </div>
    </div>
  );
}
