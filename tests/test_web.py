from pathlib import Path

import requests

from prospector import web
from prospector.osm import Lead

SAMPLE_HTML = (Path(__file__).parent / "fixtures" / "sample_site.html").read_text()


class FakeResponse:
    def __init__(self, status_code: int, url: str, text: str = ""):
        self.status_code = status_code
        self.url = url
        self.text = text


def _lead(website: str = "https://smiledental.example") -> Lead:
    return Lead(id="osm:node/1", name="Smile Dental Clinic", niche="dentist", lat=0.0, lon=0.0, website=website)


def test_enrich_extracts_signals_from_fixture(monkeypatch):
    def fake_fetch(url, timeout):
        if url.rstrip("/") == "https://smiledental.example":
            return FakeResponse(200, "https://smiledental.example/", SAMPLE_HTML)
        return FakeResponse(404, url, "")

    monkeypatch.setattr(web, "_fetch", fake_fetch)
    result = web.enrich(_lead())

    assert result.fetch_error == ""
    assert result.site_ok is True
    assert "hello@smiledental.example" in result.emails
    assert result.has_booking is True
    assert result.chat_widget == "intercom"
    assert result.has_contact_form is True


def test_enrich_rejects_junk_emails(monkeypatch):
    def fake_fetch(url, timeout):
        return FakeResponse(200, "https://smiledental.example/", SAMPLE_HTML)

    monkeypatch.setattr(web, "_fetch", fake_fetch)
    result = web.enrich(_lead())

    assert all("2x.png" not in e and not e.startswith("sales@2x") for e in result.emails)
    # the image-filename-looking address must never appear at all
    assert "sales@2x.png" not in result.emails


def test_enrich_no_website_sets_fetch_error():
    result = web.enrich(_lead(website=""))
    assert result.fetch_error == "no_website"
    assert result.site_ok is None
    assert result.emails == []


def test_enrich_timeout_never_raises(monkeypatch):
    def raising_fetch(url, timeout):
        raise requests.exceptions.Timeout("simulated timeout")

    monkeypatch.setattr(web, "_fetch", raising_fetch)
    result = web.enrich(_lead())

    assert result.site_ok is False
    assert "Timeout" in result.fetch_error


def test_enrich_all_never_raises_and_returns_all(monkeypatch):
    def fake_fetch(url, timeout):
        return FakeResponse(200, "https://smiledental.example/", SAMPLE_HTML)

    monkeypatch.setattr(web, "_fetch", fake_fetch)
    leads = [_lead(), _lead(website="")]
    results = web.enrich_all(leads, workers=2)
    assert len(results) == 2


def test_detect_booking_ignores_prose_appointments():
    from bs4 import BeautifulSoup

    html = "<html><body><p>Call us to schedule an appointment at your convenience.</p></body></html>"
    soup = BeautifulSoup(html, "html.parser")
    assert web._detect_booking(soup) is False
