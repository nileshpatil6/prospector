/** Small radar glyph (sweep-line inside two rings) + wordmark, used in the
 * top bar and as the hero's watermark. Pure inline SVG so it never needs an
 * icon font or an extra network request. */
export function RadarGlyph({ size = 18 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 20 20"
      fill="none"
      aria-hidden="true"
      className="shrink-0"
    >
      <circle cx="10" cy="10" r="8.5" stroke="var(--hairline)" strokeWidth="1" />
      <circle cx="10" cy="10" r="5" stroke="var(--hairline)" strokeWidth="1" />
      <circle cx="10" cy="10" r="1.4" fill="var(--lime)" />
      <path
        d="M10 10 L10 1.5 A8.5 8.5 0 0 1 17.5 6.5 Z"
        fill="var(--lime)"
        opacity="0.35"
      />
    </svg>
  );
}

export function Wordmark({ size = 18 }: { size?: number }) {
  return (
    <span className="inline-flex items-center gap-2">
      <RadarGlyph size={size} />
      <span className="font-display font-semibold tracking-tight text-text">
        Prospector
      </span>
    </span>
  );
}
