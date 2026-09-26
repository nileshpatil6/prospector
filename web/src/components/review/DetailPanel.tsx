"use client";

import dynamic from "next/dynamic";
import { Check, X } from "lucide-react";
import type { Label, Lead } from "@/lib/types";
import { parseReason, websiteHost } from "@/lib/format";
import { MapSkeleton } from "@/components/map/MapSkeleton";
import { CallReceptionistButton } from "@/components/call/CallReceptionistButton";

const ProspectorMap = dynamic(() => import("@/components/map/ProspectorMap"), {
  ssr: false,
  loading: () => <MapSkeleton />,
});

function Fact({ label, value }: { label: string; value: React.ReactNode }) {
  const empty = value === "" || value === null || value === undefined;
  return (
    <div className="flex items-start justify-between gap-3 py-1.5 border-b border-hairline last:border-0">
      <span className="text-xs text-muted shrink-0">{label}</span>
      <span className={`text-xs text-right ${empty ? "text-muted italic" : "text-text"}`}>
        {empty ? "not observed" : value}
      </span>
    </div>
  );
}

function boolFact(v: boolean | null): React.ReactNode {
  if (v === null) return null;
  return v ? (
    <span className="inline-flex items-center gap-1 text-lime">
      <Check size={12} /> yes
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 text-coral">
      <X size={12} /> no
    </span>
  );
}

function ScoreBreakdown({ reasons }: { reasons: string[] }) {
  if (reasons.length === 0) {
    return <p className="text-xs text-muted italic">Not scored yet.</p>;
  }
  const parsed = reasons.map(parseReason);
  const maxAbs = Math.max(1, ...parsed.map((p) => Math.abs(p.points ?? 0)));

  return (
    <div className="space-y-1.5">
      {parsed.map((p, i) => {
        const pts = p.points ?? 0;
        const width = (Math.abs(pts) / maxAbs) * 100;
        const positive = pts >= 0;
        return (
          <div key={i} className="flex items-center gap-2 text-xs">
            <span className="w-32 shrink-0 text-muted truncate font-mono">{p.label}</span>
            <div className="flex-1 h-1.5 rounded-full bg-hairline overflow-hidden">
              <div
                className={`h-full ${positive ? "bg-lime" : "bg-coral"}`}
                style={{ width: `${width}%` }}
              />
            </div>
            <span className={`w-10 text-right font-mono tabular-nums ${positive ? "text-lime" : "text-coral"}`}>
              {positive ? "+" : ""}
              {pts}
            </span>
          </div>
        );
      })}
    </div>
  );
}

interface DetailPanelProps {
  runId: string;
  lead: Lead;
  label: Label | undefined;
  onLabel: (label: Label | null) => void;
  pending: boolean;
}

export function DetailPanel({ runId, lead, label, onLabel, pending }: DetailPanelProps) {
  return (
    <div className="space-y-5" data-testid="detail-panel">
      <div>
        <h2 className="font-display text-lg text-text leading-tight">{lead.name}</h2>
        <p className="text-xs text-muted mt-0.5">{lead.niche || "unknown niche"}</p>
      </div>

      <div className="h-40 rounded-lg overflow-hidden border border-hairline">
        <ProspectorMap leads={[lead]} bbox={null} labels={label ? { [lead.id]: label } : undefined} />
      </div>

      <CallReceptionistButton runId={runId} lead={lead} className="w-full" />

      <div className="flex gap-2">
        <button
          type="button"
          disabled={pending}
          data-testid="good-button"
          onClick={() => onLabel(label === "good" ? null : "good")}
          className={`flex-1 flex items-center justify-center gap-1.5 text-sm font-medium py-2 rounded-lg border transition-colors disabled:opacity-50 ${
            label === "good"
              ? "border-lime bg-lime-soft text-lime"
              : "border-hairline text-muted hover:text-lime hover:border-lime/40"
          }`}
        >
          <Check size={14} /> Good
        </button>
        <button
          type="button"
          disabled={pending}
          data-testid="bad-button"
          onClick={() => onLabel(label === "bad" ? null : "bad")}
          className={`flex-1 flex items-center justify-center gap-1.5 text-sm font-medium py-2 rounded-lg border transition-colors disabled:opacity-50 ${
            label === "bad"
              ? "border-coral bg-coral-soft text-coral"
              : "border-hairline text-muted hover:text-coral hover:border-coral/40"
          }`}
        >
          <X size={14} /> Bad
        </button>
      </div>

      {lead.hook && (
        <blockquote className="text-sm italic text-text font-serif border-l-2 border-lime/40 pl-3">
          &ldquo;{lead.hook}&rdquo;
        </blockquote>
      )}

      <div>
        <h3 className="text-[11px] uppercase tracking-wider text-muted font-medium mb-1.5">
          Score breakdown
        </h3>
        <ScoreBreakdown reasons={lead.reasons} />
      </div>

      <div>
        <h3 className="text-[11px] uppercase tracking-wider text-muted font-medium mb-1">
          Observed facts
        </h3>
        <Fact label="Address" value={lead.address || null} />
        <Fact label="Phone" value={lead.phone || null} />
        <Fact
          label="Website"
          value={lead.website ? websiteHost(lead.website) : null}
        />
        <Fact label="Hours" value={lead.opening_hours || null} />
        <Fact label="Emails" value={lead.emails.length ? lead.emails.join(", ") : null} />
        <Fact label="Online booking" value={boolFact(lead.has_booking)} />
        <Fact label="Chat widget" value={lead.chat_widget || null} />
        <Fact label="Contact form" value={boolFact(lead.has_contact_form)} />
        <Fact label="Site reachable" value={boolFact(lead.site_ok)} />
        {lead.fetch_error && <Fact label="Fetch error" value={lead.fetch_error} />}
      </div>
    </div>
  );
}
