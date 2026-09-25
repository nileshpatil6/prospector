"use client";

export type ReviewFilter = "all" | "unlabelled" | "good" | "bad";

const TABS: { key: ReviewFilter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "unlabelled", label: "Unlabelled" },
  { key: "good", label: "Good" },
  { key: "bad", label: "Bad" },
];

export function FilterTabs({
  value,
  onChange,
}: {
  value: ReviewFilter;
  onChange: (f: ReviewFilter) => void;
}) {
  return (
    <div className="flex gap-1" data-testid="filter-tabs">
      {TABS.map((tab) => (
        <button
          key={tab.key}
          type="button"
          onClick={() => onChange(tab.key)}
          data-testid={`filter-${tab.key}`}
          className={`text-xs px-2.5 py-1 rounded-md border transition-colors ${
            value === tab.key
              ? "border-lime/40 bg-lime-soft text-lime"
              : "border-hairline text-muted hover:text-text"
          }`}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
