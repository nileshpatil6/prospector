import json
from pathlib import Path

from prospector import osm

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "overpass_response.json").read_text())


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
