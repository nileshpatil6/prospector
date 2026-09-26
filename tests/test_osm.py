import json
from pathlib import Path

import pytest

from prospector import osm

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "overpass_response.json").read_text())


class _FakeResp:
    def __init__(self, status_code):
        self.status_code = status_code

    def json(self):
        return FIXTURE


def test_build_query_includes_niche_filters():
    bbox = osm.BBox(south=18.4, west=73.7, north=18.6, east=73.9)
    query = osm._build_query(bbox, ["dentist"])
    assert 'nwr["amenity"="dentist"]' in query
    assert 'nwr["healthcare"="dentist"]' in query
    assert "18.4,73.7,18.6,73.9" in query
    assert "out center tags;" in query


def test_build_query_dedupes_shared_tags_across_niches():
    bbox = osm.BBox(south=0, west=0, north=1, east=1)
    query = osm._build_query(bbox, ["med_spa", "salon"])
    # "shop"="beauty" is shared by both niches; must appear only once.
    assert query.count('nwr["shop"="beauty"]') == 1


def test_search_parses_and_dedupes_fixture(monkeypatch):
    monkeypatch.setattr(osm, "_query_overpass", lambda query: FIXTURE)
    bbox = osm.BBox(south=18.4, west=73.7, north=18.6, east=73.9)

    leads = osm.search(bbox, ["dentist"], limit=10)

    # 4 raw elements: one no-name (dropped), one duplicate id (deduped) -> 2 leads.
    assert len(leads) == 2
    ids = {lead.id for lead in leads}
    assert ids == {"osm:node/111", "osm:way/222"}

    smile = next(lead for lead in leads if lead.id == "osm:node/111")
    assert smile.name == "Smile Dental Clinic"
    assert smile.phone == "+91 20 1234 5678"
    assert smile.website == "https://smiledental.example"
    assert smile.niche == "dentist"

    way_lead = next(lead for lead in leads if lead.id == "osm:way/222")
    assert way_lead.lat == 18.53 and way_lead.lon == 73.86
    assert way_lead.address == "FC Road, Pune"


def test_search_respects_limit(monkeypatch):
    monkeypatch.setattr(osm, "_query_overpass", lambda query: FIXTURE)
    bbox = osm.BBox(south=18.4, west=73.7, north=18.6, east=73.9)
    leads = osm.search(bbox, ["dentist"], limit=1)
    assert len(leads) == 1


def test_search_empty_niches_returns_empty():
    bbox = osm.BBox(south=0, west=0, north=1, east=1)
    assert osm.search(bbox, [], limit=10) == []


def test_bbox_widened_grows_around_center():
    bbox = osm.BBox(south=10.0, west=10.0, north=20.0, east=20.0)
    wide = bbox.widened(2.0)
    assert wide.south == 5.0 and wide.north == 25.0
    assert wide.west == 5.0 and wide.east == 25.0


def test_lead_from_dict_loads_old_state_missing_receptionist_fields():
    # A state.json written before receptionist_prompt/messages existed must
    # still load, defaulting the new fields instead of raising a TypeError.
    old_dict = {
        "id": "osm:node/1", "name": "Old Clinic", "niche": "dentist",
        "lat": 18.5, "lon": 73.8, "address": "", "phone": "", "website": "",
        "opening_hours": "", "source_url": "", "emails": [], "has_booking": None,
        "chat_widget": "", "has_contact_form": None, "site_ok": None,
        "fetch_error": "", "research": {}, "score": 0.0, "reasons": [], "hook": "",
    }
    lead = osm.Lead.from_dict(old_dict)
    assert lead.receptionist_prompt == ""
    assert lead.messages == []
    assert lead.to_dict()["receptionist_prompt"] == ""
    assert lead.to_dict()["messages"] == []


# --- MED: Overpass 429/504 moves to the next mirror immediately (no sleep) -

def test_query_overpass_fast_fails_on_429_without_sleeping(monkeypatch):
    calls = []

    def fake_post(url, data=None, headers=None, timeout=None):
        calls.append(url)
        if url == osm.OVERPASS_ENDPOINTS[0]:
            return _FakeResp(429)
        return _FakeResp(200)

    sleeps = []
    monkeypatch.setattr(osm.requests, "post", fake_post)
    monkeypatch.setattr(osm.time, "sleep", lambda s: sleeps.append(s))

    result = osm._query_overpass("fake query")

    assert result == FIXTURE
    # First endpoint hit exactly once (429 -> immediate move-on), never slept.
    assert calls.count(osm.OVERPASS_ENDPOINTS[0]) == 1
    assert sleeps == []


def test_query_overpass_skips_sleep_after_final_attempt(monkeypatch):
    # Every mirror returns a plain 500 (not fast-failed): retried up to
    # max_retries times per mirror, but the very last attempt overall must
    # not sleep afterward since there's nothing left to wait for.
    monkeypatch.setattr(osm.requests, "post", lambda *a, **k: _FakeResp(500))
    sleeps = []
    monkeypatch.setattr(osm.time, "sleep", lambda s: sleeps.append(s))

    with pytest.raises(osm.OSMError):
        osm._query_overpass("fake query", max_retries=2)

    total_calls = len(osm.OVERPASS_ENDPOINTS) * 2
    # One sleep between each pair of attempts within a mirror, none after
    # the last attempt of the last mirror.
    assert len(sleeps) == total_calls - len(osm.OVERPASS_ENDPOINTS)


def test_query_overpass_respects_total_time_budget(monkeypatch):
    # Simulate a clock that has already blown the budget on the very first
    # check: must raise promptly instead of grinding through every mirror.
    monkeypatch.setattr(osm.requests, "post", lambda *a, **k: _FakeResp(500))
    monkeypatch.setattr(osm.time, "sleep", lambda s: None)

    clock = {"t": 0.0}
    def fake_monotonic():
        clock["t"] += 100.0  # first budget check already exceeds any budget
        return clock["t"]
    monkeypatch.setattr(osm.time, "monotonic", fake_monotonic)

    with pytest.raises(osm.OSMError, match="budget"):
        osm._query_overpass("fake query", total_budget=90.0)
