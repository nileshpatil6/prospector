"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Wordmark } from "./Wordmark";
import { useApiHealth } from "@/hooks/useApiHealth";

const LINKS = [
  { href: "/", label: "Run" },
  { href: "/runs", label: "Runs" },
  { href: "/learn", label: "Memory" },
];

const HEALTH_DOT: Record<ReturnType<typeof useApiHealth>, string> = {
  checking: "bg-muted",
  up: "bg-lime",
  down: "bg-coral",
};

const HEALTH_LABEL: Record<ReturnType<typeof useApiHealth>, string> = {
  checking: "checking API",
  up: "API online",
  down: "API offline",
};

export function Nav() {
  const pathname = usePathname();
  const health = useApiHealth();

  return (
    <header className="sticky top-0 z-40 border-b border-hairline bg-bg/90 backdrop-blur">
      <div className="max-w-[1440px] mx-auto px-4 sm:px-6 h-14 flex items-center justify-between">
        <Link href="/" className="flex items-center">
          <Wordmark />
        </Link>
        <nav className="flex items-center gap-1">
          {LINKS.map((link) => {
            const active =
              link.href === "/"
                ? pathname === "/"
                : pathname.startsWith(link.href);
            return (
              <Link
                key={link.href}
                href={link.href}
                className={`px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${
                  active
                    ? "text-lime bg-lime-soft"
                    : "text-muted hover:text-text hover:bg-raised"
                }`}
              >
                {link.label}
              </Link>
            );
          })}
        </nav>
        <div
          className="flex items-center gap-2 text-xs text-muted font-mono"
          title={HEALTH_LABEL[health]}
          data-testid="api-health"
          data-health={health}
        >
          <span
            className={`h-1.5 w-1.5 rounded-full ${HEALTH_DOT[health]} ${
              health === "up" ? "pulse-dot" : ""
            }`}
          />
          <span className="hidden sm:inline">{HEALTH_LABEL[health]}</span>
        </div>
      </div>
    </header>
  );
}
