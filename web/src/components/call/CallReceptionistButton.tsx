"use client";

import { useState } from "react";
import { Phone } from "lucide-react";
import type { Lead } from "@/lib/types";
import { CallPanel } from "./CallPanel";

interface CallReceptionistButtonProps {
  runId: string;
  lead: Lead;
  className?: string;
}

/** "Call its AI receptionist" -- opens a call panel wired to the Gemini Live
 * demo for this lead. Lives on the run page's top lead cards and in the
 * review detail panel. */
export function CallReceptionistButton({ runId, lead, className = "" }: CallReceptionistButtonProps) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        type="button"
        data-testid="call-receptionist-button"
        onClick={(e) => {
          e.stopPropagation();
          setOpen(true);
        }}
        className={`flex items-center justify-center gap-1.5 text-xs font-medium px-2.5 py-1.5 rounded-md border border-lime/40 text-lime hover:bg-lime-soft transition-colors ${className}`}
      >
        <Phone size={12} /> Call its AI receptionist
      </button>
      {open && <CallPanel runId={runId} lead={lead} onClose={() => setOpen(false)} />}
    </>
  );
}
