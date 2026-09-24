function band(score: number): "ok" | "running" | "fail" {
  if (score >= 65) return "ok";
  if (score >= 35) return "running";
  return "fail";
}

const FILL_CLASS = {
  ok: "bg-ok",
  running: "bg-running",
  fail: "bg-fail",
};

const TEXT_CLASS = {
  ok: "text-ok",
  running: "text-running",
  fail: "text-fail",
};

export function ScorePill({ score }: { score: number }) {
  const clamped = Math.max(0, Math.min(100, score));
  const b = band(clamped);
  return (
    <div className="flex items-center gap-2 w-28">
      <div className="flex-1 h-1.5 rounded-full bg-rule overflow-hidden">
        <div
          className={`h-full rounded-full ${FILL_CLASS[b]}`}
          style={{ width: `${clamped}%` }}
        />
      </div>
      <span className={`font-mono text-xs w-7 text-right ${TEXT_CLASS[b]}`}>
        {Math.round(clamped)}
      </span>
    </div>
  );
}
