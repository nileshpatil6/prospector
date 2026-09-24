"""Pure, deterministic feature extraction from a Lead.

This is the ONLY input scoring rules may reference (see rules.py). Every
feature is a straight, side-effect-free read of fields already observed on
the Lead -- nothing here makes a network call or invents data.
"""

from __future__ import annotations

from prospector.osm import Lead

# Declared type for every feature, used by rules.py to validate that a rule's
# operator is legal for the feature it targets (e.g. ">=" only makes sense
# for a float feature, "contains" only for a string feature).
FEATURE_TYPES: dict[str, type] = {
    "has_website": bool,
    "site_ok": bool,
    "fetch_ok": bool,
    "has_email": bool,
    "email_count": float,
    "has_phone": bool,
    "has_booking": bool,
    "booking_known": bool,
    "has_chat_widget": bool,
    "chat_vendor": str,
    "chat_incumbent": bool,
    "has_contact_form": bool,
    "hours_known": bool,
    "open_24_7": bool,
    "open_weekends": bool,
    "address_known": bool,
    "niche": str,
    "high_ticket_niche": bool,
    "research_has_text": bool,
    "research_mentions_phone_only": bool,
}

HIGH_TICKET_NICHES = {"dentist", "lawyer", "plumber", "hvac", "roofer", "med_spa", "chiropractor", "vet"}
CHAT_INCUMBENTS = {"podium", "birdeye"}

_WEEKEND_TOKENS = ("sa", "su")  # "Sa", "Su" day codes in opening_hours syntax


def _looks_24_7(opening_hours: str) -> bool:
    return opening_hours.strip().replace(" ", "").lower() in ("24/7", "mo-su00:00-24:00")


def _looks_open_weekends(opening_hours: str) -> bool:
    hours = opening_hours.lower()
    return any(tok in hours for tok in _WEEKEND_TOKENS) or _looks_24_7(opening_hours)


def features(lead: Lead) -> dict[str, bool | float | str]:
    """Compute the feature vector for a lead. Pure and deterministic: same
    Lead in, same features out, always."""
    emails = lead.emails or []
    research_text = str(lead.research.get("text_excerpt", "")) if lead.research else ""
    research_lower = research_text.lower()

    return {
        "has_website": bool(lead.website),
        "site_ok": bool(lead.site_ok),
        "fetch_ok": lead.fetch_error == "",
        "has_email": bool(emails),
        "email_count": float(len(emails)),
        "has_phone": bool(lead.phone),
        "has_booking": bool(lead.has_booking),
        "booking_known": lead.has_booking is not None,
        "has_chat_widget": bool(lead.chat_widget),
        "chat_vendor": lead.chat_widget or "",
        "chat_incumbent": (lead.chat_widget or "").lower() in CHAT_INCUMBENTS,
        "has_contact_form": bool(lead.has_contact_form),
        "hours_known": bool(lead.opening_hours),
        "open_24_7": _looks_24_7(lead.opening_hours or ""),
        "open_weekends": _looks_open_weekends(lead.opening_hours or ""),
        "address_known": bool(lead.address),
        "niche": lead.niche or "",
        "high_ticket_niche": (lead.niche or "") in HIGH_TICKET_NICHES,
        "research_has_text": bool(research_text),
        "research_mentions_phone_only": (
            ("call" in research_lower or "phone" in research_lower)
            and "book" not in research_lower
        ),
    }
