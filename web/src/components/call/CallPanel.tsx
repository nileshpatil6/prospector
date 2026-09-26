"use client";

import { useEffect, useRef } from "react";
import { motion, AnimatePresence } from "motion/react";
import { AlertTriangle, Loader2, Mic, MicOff, Phone, PhoneOff, X } from "lucide-react";
import type { Lead } from "@/lib/types";
import { useLiveCall } from "@/lib/live/useLiveCall";

const ERROR_COPY: Record<string, string> = {
  mic_denied: "Microphone access was denied. Allow mic access in your browser and try again.",
  token_error: "Could not start the demo call. The backend rejected the session request.",
  socket_error: "The call connection dropped unexpectedly.",
};

function elapsedLabel(ms: number): string {
  const totalSeconds = Math.floor(ms / 1000);
  const m = Math.floor(totalSeconds / 60);
  const s = totalSeconds % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

interface CallPanelProps {
  runId: string;
  lead: Lead;
  onClose: () => void;
}

export function CallPanel({ runId, lead, onClose }: CallPanelProps) {
  // useLiveCall starts the call itself on mount (and tears it down on
  // unmount) -- see the paired effect at the bottom of the hook.
  const call = useLiveCall(runId, lead);
  const transcriptEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ block: "nearest" });
  }, [call.transcript]);

  function handleClose() {
    call.hangUp();
    onClose();
  }

  const orbScale = 1 + Math.max(call.micLevel, call.outputLevel) * 0.35;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4"
      data-testid="call-panel"
    >
      <motion.div
        initial={{ opacity: 0, y: 12, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        className="w-full max-w-md rounded-2xl border border-hairline bg-surface p-5 space-y-4"
      >
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-[11px] uppercase tracking-wider text-muted font-medium">
              Live AI receptionist demo
            </p>
            <h2 className="font-display text-lg text-text leading-tight">{lead.name}</h2>
          </div>
          <button
            type="button"
            aria-label="Close"
            onClick={handleClose}
            className="text-muted hover:text-text transition-colors"
          >
            <X size={18} />
          </button>
        </div>

        <div className="flex flex-col items-center gap-2 py-2">
          <div className="relative flex items-center justify-center h-28 w-28">
            <motion.div
              animate={{ scale: orbScale }}
              transition={{ duration: 0.12 }}
              className="absolute h-full w-full rounded-full"
              style={{
                background:
                  "radial-gradient(circle, rgba(212,255,58,0.28) 0%, rgba(212,255,58,0.05) 60%, transparent 75%)",
              }}
            />
            <div className="relative h-16 w-16 rounded-full border border-lime/40 bg-raised flex items-center justify-center">
              {call.status === "connecting" ? (
                <Loader2 size={22} className="text-lime animate-spin" data-testid="call-connecting" />
              ) : call.status === "error" ? (
                <AlertTriangle size={22} className="text-coral" />
              ) : (
                <Phone size={20} className="text-lime" />
              )}
            </div>
          </div>
          <span className="text-xs font-mono text-muted tabular-nums" data-testid="call-timer">
            {call.status === "active" ? elapsedLabel(call.elapsedMs) : call.status}
          </span>
        </div>

        {call.status === "error" && (
          <div
            className="flex items-start gap-2 rounded-lg border border-coral/30 bg-coral-soft p-3 text-xs text-coral"
            data-testid="call-error"
            data-error-kind={call.errorKind ?? ""}
          >
            <AlertTriangle size={14} className="shrink-0 mt-0.5" />
            <span>{call.errorText || (call.errorKind ? ERROR_COPY[call.errorKind] : "Something went wrong.")}</span>
          </div>
        )}

        <div
          className="h-40 overflow-y-auto rounded-lg border border-hairline bg-bg/40 p-3 space-y-2"
          data-testid="call-transcript"
        >
          {call.transcript.length === 0 && call.status !== "error" && (
            <p className="text-xs text-muted italic">
              {call.status === "connecting" ? "Connecting..." : "Say hello to start the conversation."}
            </p>
          )}
          <AnimatePresence initial={false}>
            {call.transcript.map((line) => (
              <motion.div
                key={line.id}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                data-testid="call-transcript-line"
                data-speaker={line.speaker}
                className={`text-xs max-w-[85%] rounded-lg px-2.5 py-1.5 ${
                  line.speaker === "caller"
                    ? "ml-auto bg-hairline text-text"
                    : "bg-lime-soft text-lime"
                }`}
              >
                {line.text}
              </motion.div>
            ))}
          </AnimatePresence>
          <div ref={transcriptEndRef} />
        </div>

        {call.takenMessages.length > 0 && (
          <div className="space-y-1.5">
            <h3 className="text-[11px] uppercase tracking-wider text-muted font-medium">Messages taken</h3>
            {call.takenMessages.map((m, i) => (
              <div
                key={i}
                data-testid="call-message-card"
                className="rounded-lg border border-amber/30 bg-amber-soft p-2.5 text-xs text-text space-y-0.5"
              >
                <p className="font-medium">{m.caller_name || "Unknown caller"}</p>
                <p className="text-muted">{m.callback_number || "no callback number given"}</p>
                <p>{m.reason}</p>
              </div>
            ))}
          </div>
        )}

        <div className="flex gap-2">
          <button
            type="button"
            data-testid="call-mute-button"
            disabled={call.status !== "active"}
            onClick={call.toggleMute}
            className="flex-1 flex items-center justify-center gap-1.5 text-sm font-medium py-2 rounded-lg border border-hairline text-text hover:border-lime/40 transition-colors disabled:opacity-40"
          >
            {call.muted ? <MicOff size={14} /> : <Mic size={14} />}
            {call.muted ? "Unmute" : "Mute"}
          </button>
          <button
            type="button"
            data-testid="call-hangup-button"
            onClick={handleClose}
            className="flex-1 flex items-center justify-center gap-1.5 text-sm font-medium py-2 rounded-lg border border-coral/40 bg-coral-soft text-coral hover:bg-coral/20 transition-colors"
          >
            <PhoneOff size={14} /> Hang up
          </button>
        </div>
      </motion.div>
    </div>
  );
}
