"""Shared persona template for the AI receptionist demo.

The agent's `prepare_receptionists` tool asks the LLM to write a persona per
lead from observed facts; `default_receptionist_prompt` below is the
deterministic fallback used both when that LLM call fails/never ran for a
lead and when /live-session is asked for a lead the agent never touched.
Both paths must obey the same HONESTY INVARIANT as the rest of the agent:
never invent a name, price, service, or phone number that wasn't observed.
"""

from __future__ import annotations

from prospector.osm import Lead

MAX_RECEPTIONISTS = 3

PERSONA_RULES = (
    "Use ONLY the facts listed above. Never invent doctor/staff names, prices, "
    "services, or phone numbers that aren't given. If the caller asks something "
    "you don't have a fact for, say a staff member will call them back and offer "
    "to take a message. Open the call with a warm greeting that says you are a "
    "demo AI receptionist for the business. Speak in Indian English with short, "
    "natural replies. If the caller speaks Hindi or Marathi, reply in that "
    "language instead."
)


def _facts_block(lead: Lead) -> str:
    facts = [f"Business name: {lead.name}", f"Niche: {lead.niche or 'unknown'}"]
    if lead.address:
        facts.append(f"Address: {lead.address}")
    if lead.opening_hours:
        facts.append(f"Observed opening hours: {lead.opening_hours}")
    return "\n".join(f"- {f}" for f in facts)


def default_receptionist_prompt(lead: Lead) -> str:
    """Build a system-instruction persona from a lead's observed facts alone,
    with no LLM call -- the fallback used whenever an LLM-authored persona
    isn't available."""
    return (
        f"You are the AI receptionist of {lead.name}.\n\n"
        f"Observed facts:\n{_facts_block(lead)}\n\n"
        f"{PERSONA_RULES}"
    )
