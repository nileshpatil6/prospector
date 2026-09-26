"use client";

import { useEffect, useState } from "react";

const QUERY = "(min-width: 1280px)"; // Tailwind's `xl` breakpoint

/** Tracks whether the viewport is at least the `xl` breakpoint, so a page
 * can render ONE layout variant instead of mounting both a mobile and a
 * desktop tree side by side and toggling visibility with responsive CSS
 * classes -- that pattern doubles every data-testid (and every Leaflet map
 * instance) inside the duplicated subtree. */
export function useIsDesktop(): boolean {
  const [isDesktop, setIsDesktop] = useState(
    () => typeof window !== "undefined" && window.matchMedia(QUERY).matches
  );

  useEffect(() => {
    const mql = window.matchMedia(QUERY);
    const onChange = () => setIsDesktop(mql.matches);
    onChange();
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, []);

  return isDesktop;
}
