"""Scripted FastAPI app for Playwright end-to-end tests ONLY.

Wires server.create_app() to a deterministic, offline stand-in LLM and to
monkeypatched OSM/website functions, so the full run -> review -> learn
flow exercises the real agent loop and the real FastAPI routes with zero
network access and zero real Gemini calls. This module is never imported by
the demo app or by `python -m pytest`; it exists only so `web/e2e/*.spec.ts`
have something real to drive.

Run standalone with: uvicorn tests.e2e_server:app --port 8010
(web/playwright.config.ts's `webServer` does exactly this.)
"""

from __future__ import annotations

import copy
import tempfile
from pathlib import Path

import prospector.agent as agent_mod
import prospector.web as web_mod
import server as server_mod
from prospector.llm import LLM, LLMError
from prospector.osm import BBox, Lead, OSMError

# -- Fixture data: ~12 dental clinics scattered around Pune -------------

_PUNE_BBOX = BBox(south=18.44, west=73.75, north=18.61, east=73.95)

# (name, lat, lon, address, phone, website, opening_hours)
_FIXTURE_ROWS: list[tuple[str, float, float, str, str, str, str]] = [
    ("Sunrise Dental Care", 18.5204, 73.8567, "FC Road, Shivajinagar, Pune", "+91 98220 11111", "https://sunrisedental.example.com", "Mo-Sa 09:00-19:00"),
    ("Smile Bright Clinic", 18.5314, 73.8446, "JM Road, Deccan, Pune", "+91 98220 22222", "", "Mo-Sa 10:00-18:00"),
    ("Pune City Dentist", 18.5089, 73.8258, "Karve Road, Pune", "+91 98220 33333", "https://punecitydentist.example.com", "Mo-Su 09:00-21:00"),
    ("Family Dental Studio", 18.5679, 73.9143, "Viman Nagar, Pune", "", "https://familydentalstudio.example.com", ""),
    ("Koregaon Dental", 18.5362, 73.8938, "North Main Road, Koregaon Park, Pune", "+91 98220 44444", "https://koregaondental.example.com", "Mo-Sa 09:30-19:30"),
    ("Baner Smile Center", 18.5590, 73.7868, "Baner Road, Pune", "+91 98220 55555", "", "Mo-Sa 09:00-18:00"),
    ("Aundh Dental Care", 18.5620, 73.8077, "Aundh, Pune", "+91 98220 66666", "https://aundhdentalcare.example.com", "Mo-Sa 09:00-20:00"),
    ("Kothrud Dentistry", 18.5074, 73.8077, "Kothrud, Pune", "", "", ""),
    ("Viman Nagar Dental", 18.5679, 73.9151, "Viman Nagar Main Road, Pune", "+91 98220 77777", "https://vimannagardental.example.com", "Mo-Su 08:00-20:00"),
    ("Wakad Family Dentist", 18.5975, 73.7645, "Wakad, Pune", "+91 98220 88888", "", "Mo-Sa 09:00-19:00"),
    ("Hinjewadi Dental Hub", 18.5912, 73.7389, "Hinjewadi Phase 1, Pune", "+91 98220 99999", "https://hinjewadidentalhub.example.com", "Mo-Sa 09:00-19:00"),
    ("Shivaji Nagar Dental", 18.5304, 73.8478, "Shivaji Nagar, Pune", "+91 98220 10101", "https://shivajinagardental.example.com", "Mo-Sa 09:00-18:30"),
]


def _build_fixture_leads() -> list[Lead]:
    """Fresh Lead objects on every call -- each run/search gets its own
    unenriched, unscored instances instead of sharing (and mutating) state
    across separate test runs."""
    leads = []
    for i, (name, lat, lon, address, phone, website, hours) in enumerate(_FIXTURE_ROWS):
        leads.append(
            Lead(
                id=f"osm:node/{9000000 + i}",
                name=name,
                niche="dentist",
                lat=lat,
                lon=lon,
                address=address,
                phone=phone,
                website=website,
                opening_hours=hours,
                source_url=f"https://www.openstreetmap.org/node/{9000000 + i}",
            )
        )
    return leads


# -- Monkeypatched OSM/web functions -------------------------------------
#
# agent.py did `from prospector.osm import geocode, search` and
# `from prospector import web`, so geocode/search must be patched as
# attributes of the agent module itself (where the names are bound),
# while enrich_all/deep_research are patched on the `web` module object
# (agent.py calls them as `web.enrich_all(...)`, an attribute lookup at
# call time, so patching prospector.web's attributes is enough).

_failed_once_bbox_ids: set[int] = set()


def _fake_geocode(place: str) -> BBox:
    # A fresh BBox instance every call (dataclasses aren't interned), which
    # is exactly what the fail-once-per-bbox tracking below relies on: each
    # new agent run gets its own bbox identity, so every run independently
    # sees one search failure followed by a recovery.
    return BBox(south=_PUNE_BBOX.south, west=_PUNE_BBOX.west, north=_PUNE_BBOX.north, east=_PUNE_BBOX.east)


def _fake_search(bbox: BBox, niches: list[str], limit: int) -> list[Lead]:
    key = id(bbox)
    if key not in _failed_once_bbox_ids:
        _failed_once_bbox_ids.add(key)
        raise OSMError("overpass mirror timed out (scripted e2e failure)")
    return _build_fixture_leads()[: limit or 50]


def _domain(website: str) -> str:
    return website.replace("https://", "").replace("http://", "").rstrip("/")


def _fake_enrich_all(leads: list[Lead], workers: int = 8) -> list[Lead]:
    results = []
    for i, lead in enumerate(leads):
        result = copy.deepcopy(lead)
        if not result.website:
            result.fetch_error = "no_website"
            result.site_ok = None
            results.append(result)
            continue
        result.site_ok = True
        result.emails = [f"info@{_domain(result.website)}"]
        result.has_booking = i % 3 == 0  # a mix, so "no_online_booking" fires for most
        result.chat_widget = "Tawk.to" if i % 4 == 0 else ""
        result.has_contact_form = i % 2 == 0
        result.fetch_error = ""
        results.append(result)
    return results


def _fake_deep_research(lead: Lead, timeout: int = 10) -> dict:
    if not lead.website:
        return {}
    return {
        "http_status": 200,
        "title": f"{lead.name} - Home",
        "text_excerpt": (
            f"Welcome to {lead.name}. We are a trusted dental clinic in Pune. "
            f"Call us to book an appointment -- walk-ins welcome. "
            f"Opening hours: {lead.opening_hours or 'contact us for hours'}."
        ),
    }


agent_mod.geocode = _fake_geocode
agent_mod.search = _fake_search
web_mod.enrich_all = _fake_enrich_all
web_mod.deep_research = _fake_deep_research


# -- Routing scripted LLM --------------------------------------------------
#
# server.py calls `app.state.llm_factory()` fresh for EVERY /api/runs and
# EVERY /api/learn request (a new Agent per run, a new one-off call per
# learn), so a single call-order queue would leak positions across
# unrelated calls. Instead, each fresh instance routes on the distinctive
# system-prompt text of each call site (plan / loop-decision / write_hooks
# / learner) and pops an independent per-category queue -- robust to
# interleaving and to however many runs/learns a test session makes.

_PLAN_TEMPLATE: list[dict] = [
    {
        "place": "Pune, Maharashtra, India",
        "niches": ["dentist"],
        "target_count": 12,
        "plan": [
            "Search for dental clinics in Pune using OpenStreetMap listings.",
            "Extract contact details, hours, and website URLs for each clinic.",
            "Assess phone answering setups and online booking or chat gaps.",
            "Compile the top candidates with a pitch hook for each.",
        ],
    }
]

_LOOP_TEMPLATE: list[dict] = [
    {
        "thought": "First I need a bounding box for Pune before I can search anything.",
        "action": "geocode",
        "args": {},
    },
    {
        "thought": "Searching OpenStreetMap for dental clinics inside the Pune bounding box.",
        "action": "search_businesses",
        "args": {"niches": ["dentist"], "limit": 50},
    },
    {
        "thought": "That Overpass mirror timed out -- retrying the same search once more.",
        "action": "search_businesses",
        "args": {"niches": ["dentist"], "limit": 50},
    },
    {
        "thought": "Now fetching each clinic's website to check for phone, booking, and chat signals.",
        "action": "enrich",
        "args": {"max_leads": 20},
    },
    {
        "thought": "Scoring every lead against the base heuristic and any learned rules.",
        "action": "score",
        "args": {},
    },
    {
        "thought": "Pulling a deeper page snapshot of the top-scoring clinics to ground the pitch hooks.",
        "action": "deep_research",
        "args": {},
    },
    {
        "thought": "Writing a one-line pitch hook for each top clinic from observed facts only.",
        "action": "write_hooks",
        "args": {},
    },
    {
        "thought": "12 dental clinics found, enriched, scored, and pitched -- goal satisfied.",
        "action": "finish",
        "args": {
            "summary": (
                "Found and ranked 12 dental clinics in Pune. The top candidates take phone "
                "calls but have no online booking and no chat widget, making them strong "
                "fits for an AI phone receptionist."
            )
        },
    },
]


def _hooks_template() -> list[dict]:
    hooks = {
        f"osm:node/{9000000 + i}": f"{name} answers every call by phone -- an AI receptionist could pick up the ones they miss after hours."
        for i, (name, *_rest) in enumerate(_FIXTURE_ROWS)
    }
    return [{"hooks": hooks}]


_LEARN_TEMPLATE: list[dict] = [
    {
        "rules": [
            {
                "feature": "has_contact_form",
                "op": "is_true",
                "value": True,
                "weight": 8,
                "rationale": "a contact form but no live chat still means missed after-hours enquiries",
            },
            {
                "feature": "research_has_text",
                "op": "is_true",
                "value": True,
                "weight": -50,
                "rationale": "scripted-invalid candidate (weight out of range) to exercise the rejected state",
            },
        ]
    }
]


class RoutingScriptedLLM:
    """See module docstring section above. Duck-types `prospector.llm.LLM`."""

    def __init__(self) -> None:
        self._plan_queue = list(_PLAN_TEMPLATE)
        self._loop_queue = list(_LOOP_TEMPLATE)
        self._hooks_queue = _hooks_template()
        self._learn_queue = list(_LEARN_TEMPLATE)
        self.calls: list[tuple[str, str, str]] = []

    def _pop(self, queue: list[dict], category: str) -> dict:
        if not queue:
            raise LLMError(f"RoutingScriptedLLM: {category} queue exhausted")
        return queue.pop(0)

    def json(self, system: str, user: str, schema_hint: str) -> dict:
        self.calls.append(("json", system, user))
        if "planning module" in system:
            return self._pop(self._plan_queue, "plan")
        if "acting module" in system:
            return self._pop(self._loop_queue, "loop")
        if "write a single-sentence" in system:
            return self._pop(self._hooks_queue, "hooks")
        if "tuning a lead-scoring rule set" in system:
            return self._pop(self._learn_queue, "learn")
        raise LLMError(f"RoutingScriptedLLM: no canned response for system prompt {system[:80]!r}")

    def text(self, system: str, user: str) -> str:
        self.calls.append(("text", system, user))
        raise LLMError("RoutingScriptedLLM: .text() is not used by any e2e-tested code path")


def _llm_factory() -> LLM:
    return RoutingScriptedLLM()


def make_app(runs_dir: Path, data_dir: Path):
    """Build the scripted FastAPI app. Exposed for anything that wants a
    fresh instance (e.g. re-running with a clean data dir); the module-level
    `app` below is what uvicorn/Playwright actually serve."""
    return server_mod.create_app(runs_dir=runs_dir, data_dir=data_dir, llm_factory=_llm_factory)


_tmp_root = Path(tempfile.mkdtemp(prefix="prospector_e2e_"))
app = make_app(_tmp_root / "runs", _tmp_root / "data")
