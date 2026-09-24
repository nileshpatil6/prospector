"""Report generation: a leads CSV and a markdown run report."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import TYPE_CHECKING

from prospector.memory import Memory

if TYPE_CHECKING:  # avoid a circular import at module load time
    from prospector.agent import RunState

CSV_FIELDS = [
    "id", "name", "niche", "score", "phone", "emails", "website",
    "has_booking", "chat_widget", "hook", "address", "opening_hours", "source_url",
]


def write_leads_csv(state: "RunState", path: Path) -> None:
    path = Path(path)
    leads = sorted(state.leads.values(), key=lambda ld: ld.score, reverse=True)
    # utf-8-sig so Excel on Windows doesn't mangle non-ASCII business names.
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for lead in leads:
            writer.writerow({
                "id": lead.id,
                "name": lead.name,
                "niche": lead.niche,
                "score": lead.score,
                "phone": lead.phone,
                "emails": "; ".join(lead.emails),
                "website": lead.website,
                "has_booking": lead.has_booking,
                "chat_widget": lead.chat_widget,
                "hook": lead.hook,
                "address": lead.address,
                "opening_hours": lead.opening_hours,
                "source_url": lead.source_url,
            })


def write_report(state: "RunState", memory: Memory, path: Path) -> None:
    path = Path(path)
    leads = sorted(state.leads.values(), key=lambda ld: ld.score, reverse=True)
    top_leads = leads[:20]

    lines: list[str] = []
    lines.append(f"# Prospector run report: {state.run_id}")
    lines.append("")
    lines.append(f"**Goal:** {state.goal}")
    lines.append(f"**Status:** {state.status}")
    if state.final_answer:
        lines.append(f"**Final answer:** {state.final_answer}")
    lines.append("")

    lines.append("## Plan")
    if state.plan:
        for item in state.plan:
            lines.append(f"1. {item}")
    else:
        lines.append("(no plan recorded)")
    lines.append("")

    lines.append("## Steps")
    lines.append("| # | action | ok | observation |")
    lines.append("|---|--------|----|-------------|")
    for step in state.step_log:
        obs = step.observation.replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {step.n} | {step.action} | {'yes' if step.ok else 'no'} | {obs} |")
    lines.append("")

    lines.append(f"## Top leads ({len(top_leads)} of {len(state.leads)})")
    if top_leads:
        lines.append("| score | name | niche | phone | reasons |")
        lines.append("|-------|------|-------|-------|---------|")
        for lead in top_leads:
            reasons = "; ".join(lead.reasons) or "(not scored)"
            lines.append(f"| {lead.score:.0f} | {lead.name} | {lead.niche} | {lead.phone or '-'} | {reasons} |")
    else:
        lines.append("(no leads found)")
    lines.append("")

    lines.append("## What was learned from memory")
    rules = memory.load_rules()
    if rules:
        for rule in rules:
            lines.append(f"- `{rule.id}`: {rule.feature} {rule.op} {rule.value!r} (weight {rule.weight:+g}) -- {rule.rationale}")
    else:
        lines.append("(no learned rules yet)")
    history = memory.get_history()
    if history:
        last = history[-1]
        lines.append(
            f"\nLast learning run: holdout accuracy {last.get('acc_before', 0):.1f}% -> "
            f"{last.get('acc_after', 0):.1f}%, p@10 {last.get('p_at_10_before', 0):.1f}% -> "
            f"{last.get('p_at_10_after', 0):.1f}%."
        )
    lines.append("")

    lines.append("## What was NOT found")
    if state.notes:
        for note in state.notes:
            lines.append(f"- {note}")
    else:
        lines.append("(no issues noted)")
    if state.target_count and len(state.leads) < state.target_count:
        lines.append(f"- fell short of target_count: found {len(state.leads)} of {state.target_count}")
    lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
