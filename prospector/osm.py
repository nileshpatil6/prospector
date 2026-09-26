"""OpenStreetMap data source: geocoding via Nominatim and business search via
the Overpass API.

No API keys required. Nominatim is rate-limited to 1 request/second and
requires a real User-Agent or it returns HTTP 403. Overpass area[name=...]
lookups routinely time out with HTTP 504, so bbox queries are used instead,
against a list of mirrors tried in order with retries.
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field

import requests

USER_AGENT = "prospector-agent/1.0 (contact: ganeshpatil643613@gmail.com)"

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]

# Friendly niche name -> list of (osm_key, osm_value) tag filters.
NICHES: dict[str, list[tuple[str, str]]] = {
    "dentist": [("amenity", "dentist"), ("healthcare", "dentist")],
    "lawyer": [("office", "lawyer")],
    "vet": [("amenity", "veterinary")],
    "med_spa": [("shop", "beauty"), ("leisure", "spa"), ("shop", "massage")],
    "salon": [("shop", "hairdresser"), ("shop", "nail_salon"), ("shop", "beauty")],
    "plumber": [("craft", "plumber")],
    "hvac": [("craft", "hvac")],
    "electrician": [("craft", "electrician")],
    "roofer": [("craft", "roofer")],
    "restaurant": [("amenity", "restaurant")],
    "chiropractor": [("healthcare", "chiropractor")],
    "optometrist": [("shop", "optician")],
    "physio": [("healthcare", "physiotherapist")],
    "real_estate": [("office", "estate_agent")],
    "accountant": [("office", "accountant")],
    "insurance": [("office", "insurance")],
}

_last_nominatim_call = 0.0


class OSMError(Exception):
    """Raised when OSM lookups fail after exhausting retries/mirrors."""


@dataclass
class BBox:
    south: float
    west: float
    north: float
    east: float

    def widened(self, factor: float) -> "BBox":
        """Grow the box around its center by `factor` (e.g. 1.5 = 50% bigger)."""
        lat_c = (self.south + self.north) / 2
        lon_c = (self.west + self.east) / 2
        lat_half = (self.north - self.south) / 2 * factor
        lon_half = (self.east - self.west) / 2 * factor
        return BBox(
            south=lat_c - lat_half,
            west=lon_c - lon_half,
            north=lat_c + lat_half,
            east=lon_c + lon_half,
        )


@dataclass
class Lead:
    """A prospected business, and everything observed about it so far.

    HONESTY INVARIANT: a field that has not been observed stays at its empty
    default (None / "" / [] / {}). Nothing here is ever guessed or filled in
    from an LLM's imagination -- LLM output only lands in `research`,
    `reasons`, and `hook`, and even those must be traceable to observed text.
    """

    id: str
    name: str
    niche: str
    lat: float
    lon: float
    address: str = ""
    phone: str = ""
    website: str = ""
    opening_hours: str = ""
    source_url: str = ""

    # Enrichment (web.py)
    emails: list[str] = field(default_factory=list)
    has_booking: bool | None = None
    chat_widget: str = ""
    has_contact_form: bool | None = None
    site_ok: bool | None = None
    fetch_error: str = ""
    research: dict = field(default_factory=dict)

    # Scoring/learning (rules.py)
    score: float = 0.0
    reasons: list[str] = field(default_factory=list)
    hook: str = ""

    # AI receptionist demo (live.py)
    receptionist_prompt: str = ""
    messages: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "niche": self.niche,
            "lat": self.lat,
            "lon": self.lon,
            "address": self.address,
            "phone": self.phone,
            "website": self.website,
            "opening_hours": self.opening_hours,
            "source_url": self.source_url,
            "emails": list(self.emails),
            "has_booking": self.has_booking,
            "chat_widget": self.chat_widget,
            "has_contact_form": self.has_contact_form,
            "site_ok": self.site_ok,
            "fetch_error": self.fetch_error,
            "research": dict(self.research),
            "score": self.score,
            "reasons": list(self.reasons),
            "hook": self.hook,
            "receptionist_prompt": self.receptionist_prompt,
            "messages": [dict(m) for m in self.messages],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Lead":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})


def geocode(place: str) -> BBox:
    """Resolve a place name to a bounding box using Nominatim.

    Nominatim returns boundingbox as [south, north, west, east] strings; we
    reorder to (south, west, north, east) to match BBox / Overpass order.
    """
    global _last_nominatim_call

    # Rate-limit to 1 request/sec as required by Nominatim's usage policy.
    elapsed = time.time() - _last_nominatim_call
    if elapsed < 1.0:
        time.sleep(1.0 - elapsed)

    try:
        resp = requests.get(
            NOMINATIM_URL,
            params={"q": place, "format": "json", "limit": 1},
            headers={"User-Agent": USER_AGENT},
            timeout=15,
        )
        _last_nominatim_call = time.time()
        resp.raise_for_status()
        results = resp.json()
    except requests.RequestException as exc:
        raise OSMError(f"Nominatim request failed for {place!r}: {exc}") from exc

    if not results:
        raise OSMError(f"Nominatim found no results for place: {place!r}")

    south, north, west, east = (float(x) for x in results[0]["boundingbox"])
    return BBox(south=south, west=west, north=north, east=east)


def _build_query(bbox: BBox, niches: list[str]) -> str:
    """Build a single Overpass QL query covering all requested niches."""
    bbox_str = f"{bbox.south},{bbox.west},{bbox.north},{bbox.east}"

    filters: list[str] = []
    seen: set[tuple[str, str]] = set()
    for niche in niches:
        for key, value in NICHES.get(niche, []):
            if (key, value) in seen:
                continue
            seen.add((key, value))
            filters.append(f'  nwr["{key}"="{value}"]({bbox_str});')

    body = "\n".join(filters)
    return f"[out:json][timeout:60];\n(\n{body}\n);\nout center tags;\n"


OVERPASS_TOTAL_BUDGET_S = 90.0


def _query_overpass(query: str, max_retries: int = 3, total_budget: float = OVERPASS_TOTAL_BUDGET_S) -> dict:
    """Run the query against each mirror in order, retrying with backoff
    before falling through to the next mirror.

    Overpass can block a caller for a long time on a busy mirror, so the
    whole function is capped at `total_budget` seconds wall-clock. A 429
    (rate limited) or 504 (gateway timeout) response is not worth retrying
    on the same mirror -- move to the next one immediately. The sleep after
    the very last attempt (nothing left to retry) is skipped entirely.
    """
    start = time.monotonic()
    last_error: Exception | None = None
    for endpoint in OVERPASS_ENDPOINTS:
        for attempt in range(max_retries):
            if time.monotonic() - start >= total_budget:
                raise OSMError(
                    f"Overpass query exceeded its {total_budget:.0f}s budget. Last error: {last_error}"
                )
            fast_fail = False
            try:
                resp = requests.post(
                    endpoint,
                    data={"data": query},
                    headers={"User-Agent": USER_AGENT},
                    timeout=60,
                )
                if resp.status_code == 200:
                    return resp.json()
                last_error = RuntimeError(f"{endpoint} returned HTTP {resp.status_code}")
                fast_fail = resp.status_code in (429, 504)
            except Exception as exc:  # noqa: BLE001 - retry/fallback by design
                last_error = exc

            is_last_attempt = attempt == max_retries - 1
            if fast_fail or is_last_attempt:
                # Either this mirror told us to back off (429/504) or we're
                # out of retries for it -- move to the next mirror right away.
                break

            remaining = total_budget - (time.monotonic() - start)
            backoff = min(2**attempt, remaining)
            if backoff > 0:
                print(
                    f"  [overpass] {endpoint} attempt {attempt + 1} failed "
                    f"({last_error}); retrying in {backoff:.0f}s",
                    file=sys.stderr,
                )
                time.sleep(backoff)
    raise OSMError(f"All Overpass endpoints failed. Last error: {last_error}")


def _first_tag(tags: dict, *keys: str) -> str:
    for key in keys:
        value = tags.get(key)
        if value:
            return value
    return ""


def _parse_elements(elements: list[dict], niches: list[str]) -> list[Lead]:
    """Normalize raw Overpass elements into deduped Leads."""
    tag_to_niche: dict[tuple[str, str], str] = {}
    for niche in niches:
        for key, value in NICHES.get(niche, []):
            tag_to_niche.setdefault((key, value), niche)

    seen_ids: set[str] = set()
    leads: list[Lead] = []

    for el in elements:
        osm_type = el.get("type", "")
        osm_id = el.get("id")
        tags = el.get("tags", {}) or {}

        name = tags.get("name", "").strip()
        if not name or osm_type is None or osm_id is None:
            continue

        lead_id = f"osm:{osm_type}/{osm_id}"
        if lead_id in seen_ids:
            continue

        niche = ""
        for key, value in tag_to_niche:
            if tags.get(key) == value:
                niche = tag_to_niche[(key, value)]
                break

        if "center" in el:
            lat, lon = el["center"].get("lat"), el["center"].get("lon")
        else:
            lat, lon = el.get("lat"), el.get("lon")
        if lat is None or lon is None:
            continue

        seen_ids.add(lead_id)

        street = tags.get("addr:street", "")
        city = tags.get("addr:city", "")
        address = ", ".join(p for p in (street, city) if p)

        leads.append(
            Lead(
                id=lead_id,
                name=name,
                niche=niche,
                lat=float(lat),
                lon=float(lon),
                address=address,
                phone=_first_tag(tags, "phone", "contact:phone"),
                website=_first_tag(tags, "website", "contact:website"),
                opening_hours=tags.get("opening_hours", ""),
                source_url=f"https://www.openstreetmap.org/{osm_type}/{osm_id}",
            )
        )

    return leads


def search(bbox: BBox, niches: list[str], limit: int) -> list[Lead]:
    """Search for businesses of the given niches within bbox. Deduped by
    OSM (type, id). Returns at most `limit` leads."""
    if not niches:
        return []
    query = _build_query(bbox, niches)
    data = _query_overpass(query)
    elements = data.get("elements", [])
    leads = _parse_elements(elements, niches)
    return leads[:limit]
