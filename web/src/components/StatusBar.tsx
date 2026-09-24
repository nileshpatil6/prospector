import type { RunStatus } from "@/lib/types";

const COPY: Record<RunStatus, string> = {
  running: "Running",
  done: "Done",
  failed: "Failed",
  max_steps: "Stopped at max steps",
};

const DOT_CLASS: Record<RunStatus, string> = {
  running: "bg-running pulse-dot",
  done: "bg-ok",
  failed: "bg-fail",
  max_steps: "bg-running",
};

const TEXT_CLASS: Record<RunStatus, string> = {
  running: "text-running",
  done: "text-ok",
  failed: "text-fail",
  max_steps: "text-running",
};

export function StatusBar({
  status,
  detail,
}: {
  status: RunStatus;
  detail?: string;
}) {
  return (
    <div className="flex items-center gap-2.5 border border-rule bg-paper-raised px-4 py-2.5 rounded-sm">
      <span className={`h-2 w-2 rounded-full shrink-0 ${DOT_CLASS[status]}`} />
      <span className={`text-sm font-medium ${TEXT_CLASS[status]}`}>
        {COPY[status]}
      </span>
      {detail && (
        <span className="text-sm text-ink-muted truncate">{detail}</span>
      )}
    </div>
  );
}
