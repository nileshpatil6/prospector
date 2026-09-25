function band(score: number): "lime" | "amber" | "coral" {
  if (score >= 65) return "lime";
  if (score >= 35) return "amber";
  return "coral";
}

const STROKE: Record<string, string> = {
  lime: "var(--lime)",
  amber: "var(--amber)",
  coral: "var(--coral)",
};

/** A compact SVG ring gauge for a 0-100 lead score. Used on lead cards and
 * the review ledger/detail panel. */
export function ScoreRing({
  score,
  size = 40,
}: {
  score: number;
  size?: number;
}) {
  const clamped = Math.max(0, Math.min(100, score));
  const b = band(clamped);
  const stroke = 3.5;
  const r = size / 2 - stroke;
  const c = 2 * Math.PI * r;
  const offset = c * (1 - clamped / 100);

  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="var(--hairline)"
          strokeWidth={stroke}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={STROKE[b]}
          strokeWidth={stroke}
          strokeDasharray={c}
          strokeDashoffset={offset}
          strokeLinecap="round"
          style={{ transition: "stroke-dashoffset 480ms ease-out" }}
        />
      </svg>
      <span
        className="absolute inset-0 flex items-center justify-center font-mono tabular-nums text-text"
        style={{ fontSize: size * 0.32 }}
      >
        {Math.round(clamped)}
      </span>
    </div>
  );
}
