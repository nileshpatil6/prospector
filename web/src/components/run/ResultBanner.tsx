"use client";

import { motion } from "motion/react";
import { FileText, Download, ListChecks } from "lucide-react";
import type { RunState } from "@/lib/types";
import { getCsvUrl, getReportUrl } from "@/lib/api";

export function ResultBanner({ run }: { run: RunState }) {
  const leadCount = Object.keys(run.leads).length;
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="rounded-xl border border-lime/25 bg-lime-soft px-5 py-5"
      data-testid="result-banner"
    >
      <p className="text-[11px] uppercase tracking-wider text-lime font-medium mb-1.5">
        {run.status === "done" ? "Run complete" : run.status.replace("_", " ")}
      </p>
      <p className="text-base text-text max-w-2xl">
        {run.final_answer || `Found ${leadCount} leads.`}
      </p>
      <div className="mt-4 flex flex-wrap gap-2">
        <a
          href={`/runs/${run.run_id}`}
          data-testid="review-link"
          className="flex items-center gap-1.5 text-sm font-medium px-3.5 py-2 rounded-lg bg-lime text-bg hover:brightness-110 transition"
        >
          <ListChecks size={14} />
          Review &amp; label
        </a>
        <a
          href={getReportUrl(run.run_id)}
          target="_blank"
          rel="noreferrer"
          className="flex items-center gap-1.5 text-sm px-3.5 py-2 rounded-lg border border-hairline text-text hover:border-lime/40 transition"
        >
          <FileText size={14} />
          Report
        </a>
        <a
          href={getCsvUrl(run.run_id)}
          className="flex items-center gap-1.5 text-sm px-3.5 py-2 rounded-lg border border-hairline text-text hover:border-lime/40 transition"
        >
          <Download size={14} />
          CSV
        </a>
      </div>
    </motion.div>
  );
}
