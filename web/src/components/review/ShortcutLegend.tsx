function Key({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="font-mono text-[10px] px-1.5 py-0.5 rounded border border-hairline bg-raised text-text">
      {children}
    </kbd>
  );
}

export function ShortcutLegend() {
  return (
    <div className="flex items-center gap-3 text-xs text-muted flex-wrap" data-testid="shortcut-legend">
      <span className="flex items-center gap-1">
        <Key>J</Key>
        <Key>K</Key> move
      </span>
      <span className="flex items-center gap-1">
        <Key>G</Key> good
      </span>
      <span className="flex items-center gap-1">
        <Key>B</Key> bad
      </span>
      <span className="flex items-center gap-1">
        <Key>U</Key> clear
      </span>
    </div>
  );
}
