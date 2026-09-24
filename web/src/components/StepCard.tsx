import type { Step } from "@/lib/types";

function formatArgs(args: Record<string, unknown>): string {
  const entries = Object.entries(args);
  if (entries.length === 0) return "{}";
  return `{ ${entries.map(([k, v]) => `${k}: ${JSON.stringify(v)}`).join(", ")} }`;
}

export function StepCard({ step }: { step: Step }) {
  return (
    <div
      className={`step-enter border px-4 py-3 rounded-sm ${
        step.ok
          ? "border-rule bg-paper"
          : "border-fail/40 bg-fail-soft"
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-baseline gap-2.5 min-w-0">
          <span className="font-mono text-xs text-ink-muted shrink-0">
            {String(step.n).padStart(2, "0")}
          </span>
          {step.action ? (
            <code className="font-mono text-xs bg-paper-raised border border-rule px-1.5 py-0.5 rounded-sm truncate">
              {step.action}
              {Object.keys(step.args ?? {}).length > 0
                ? formatArgs(step.args)
                : "()"}
            </code>
          ) : (
            <span className="font-mono text-xs text-ink-muted italic">
              (no action)
            </span>
          )}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span className="font-mono text-[11px] text-ink-muted">
            {step.ms}ms
          </span>
          <span
            className={`text-[11px] font-medium font-mono px-1.5 py-0.5 rounded-sm ${
              step.ok
                ? "text-ok bg-ok-soft"
                : "text-fail bg-fail-soft border border-fail/30"
            }`}
          >
            {step.ok ? "ok" : "fail"}
          </span>
        </div>
      </div>

      {step.thought && (
        <p className="mt-2 text-sm italic text-ink-muted">{step.thought}</p>
      )}

      {step.observation && (
        <p className="mt-1.5 text-sm text-ink leading-relaxed break-words">
          {step.observation}
        </p>
      )}
    </div>
  );
}
