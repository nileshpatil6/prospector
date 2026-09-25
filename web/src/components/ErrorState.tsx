import { ServerOff } from "lucide-react";

/** Friendly full-area error state for when the backend can't be reached, per
 * the contract: "Friendly error state if the backend is down, with the
 * exact command to start it." */
export function ApiDownState() {
  return (
    <div
      data-testid="api-down"
      className="flex flex-col items-center justify-center gap-4 py-24 text-center px-4"
    >
      <div className="h-14 w-14 rounded-full border border-hairline bg-raised flex items-center justify-center">
        <ServerOff size={22} className="text-coral" />
      </div>
      <div className="space-y-1.5">
        <h2 className="font-display text-xl text-text">
          Can&apos;t reach the Prospector API
        </h2>
        <p className="text-sm text-muted max-w-md">
          The frontend is up, but nothing answered at{" "}
          <span className="font-mono text-text">
            {process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}
          </span>
          . Start the backend, then this page will pick it up automatically.
        </p>
      </div>
      <code className="font-mono text-xs bg-surface border border-hairline rounded-md px-3 py-2 text-text">
        uvicorn server:app --port 8000
      </code>
    </div>
  );
}
