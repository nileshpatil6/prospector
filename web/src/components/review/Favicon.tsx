"use client";

import { useState } from "react";
import { faviconUrl, websiteHost } from "@/lib/format";

/** Real favicon when it loads; falls back to a plain monogram so a blocked
 * or offline network (e2e runs against a scripted backend, no internet)
 * never leaves a broken image or shifts layout. */
export function Favicon({ website }: { website: string }) {
  const [failed, setFailed] = useState(false);
  const url = website ? faviconUrl(website) : null;
  const host = website ? websiteHost(website) : "";

  if (!url || failed) {
    return (
      <span className="h-4 w-4 rounded-sm bg-raised border border-hairline flex items-center justify-center text-[9px] text-muted shrink-0">
        {host ? host[0].toUpperCase() : "?"}
      </span>
    );
  }

  return (
    // eslint-disable-next-line @next/next/no-img-element -- tiny favicon, not worth next/image's overhead
    <img
      src={url}
      alt=""
      width={16}
      height={16}
      className="h-4 w-4 rounded-sm shrink-0"
      onError={() => setFailed(true)}
    />
  );
}
