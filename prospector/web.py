"""Website enrichment: fetch a lead's website (and a couple of common
subpages) and extract signals useful for scoring and outreach.

Never raises: every network/parse failure degrades to `fetch_error` being
set on the returned Lead, and the run keeps going.
"""

from __future__ import annotations

import copy
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from prospector.osm import Lead

BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 prospector-agent/1.0 "
    "(contact: ganeshpatil643613@gmail.com)"
)

EXTRA_PATHS = ["/contact", "/about", "/book"]

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
JUNK_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".css", ".js")
JUNK_DOMAINS = ("example.com", "sentry.io", "wixpress.com", "godaddy.com")

BOOKING_KEYWORDS = [
    "calendly", "acuityscheduling", "squareup.com/appointments", "setmore",
    "booksy", "zocdoc", "vagaro", "mindbody", "schedulicity", "housecallpro",
    "servicetitan", "jobber", "opentable", "resy", "tock", "patientviewer",
    "nexhealth", "localmed", "solutionreach", "getweave", "simplifeye",
    "patientpop", "doctible", "flexbooker", "appointlet", "youcanbook",
    "timetap", "simplybook", "bookeo", "zenoti", "boulevard", "phorest",
    "fresha", "squarespace-scheduling",
]
BOOKING_TEXT_RE = re.compile(
    r"book\s+now|book\s+online|schedule\s+now|schedule\s+online|"
    r"request\s+(?:an\s+)?appointment|book\s+(?:an\s+)?appointment|"
    r"schedule\s+(?:an\s+)?appointment|make\s+(?:an\s+)?appointment|"
    r"online\s+scheduling",
    re.IGNORECASE,
)

# Vendor name -> script/iframe src domain substrings that actually indicate
# the widget is embedded. Matched only against src attributes and inline
# script bodies, never visible page text -- prose like "crisp dosas" or
# "video intercom" must never be mistaken for the chat vendor.
CHAT_VENDOR_DOMAINS: dict[str, list[str]] = {
    "podium": ["connect.podium.com", "podium.com/widget"],
    "birdeye": ["birdeye.com/js", "bl-1.com"],
    "intercom": ["widget.intercom.io", "js.intercomcdn.com"],
    "tidio": ["code.tidio.co"],
    "drift": ["js.driftt.com", "widget.drift.com"],
    "tawk.to": ["embed.tawk.to"],
    "livechat": ["cdn.livechatinc.com"],
    "hubspot": ["js.hs-scripts.com", "js.usemessages.com", "js.hubspot.com", "js.hs-banner.com"],
    "crisp": ["client.crisp.chat"],
    "olark": ["static.olark.com"],
    "gorgias": ["config.gorgias.chat"],
}


def _is_junk_email(email: str) -> bool:
    local, _, domain = email.partition("@")
    lowered = email.lower()
    if any(ext in lowered for ext in JUNK_EXTENSIONS):
        return True
    if any(junk in domain.lower() for junk in JUNK_DOMAINS):
        return True
    if re.fullmatch(r"[0-9a-f]{16,}", local.lower()):
        return True
    return False


def _extract_emails(soup: BeautifulSoup, page_text: str, site_domain: str) -> list[str]:
    found: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.lower().startswith("mailto:"):
            addr = href[7:].split("?")[0].strip()
            if addr:
                found.append(addr)
    found.extend(EMAIL_RE.findall(page_text))

    cleaned = []
    for email in found:
        email = email.strip().strip(".,;:").lower()
        if email and not _is_junk_email(email):
            cleaned.append(email)

    seen: set[str] = set()
    same_domain: list[str] = []
    other_domain: list[str] = []
    for email in cleaned:
        if email in seen:
            continue
        seen.add(email)
        domain = email.partition("@")[2]
        (same_domain if site_domain and domain == site_domain else other_domain).append(email)

    return (same_domain + other_domain)[:5]


def _detect_booking(soup: BeautifulSoup) -> bool:
    """Vendor names are matched only against hrefs/script srcs, never against
    prose (words like "appointments" appear constantly in ordinary text)."""
    urls: list[str] = [a["href"].lower() for a in soup.find_all("a", href=True)]
    urls += [t["src"].lower() for t in soup.find_all("script", src=True)]
    urls += [t["src"].lower() for t in soup.find_all("iframe", src=True)]
    if any(k in url for url in urls for k in BOOKING_KEYWORDS):
        return True

    for a in soup.find_all(["a", "button"]):
        text = a.get_text(strip=True)
        if not text or not BOOKING_TEXT_RE.search(text):
            continue
        href = (a.get("href") or "").lower().strip()
        if href.startswith(("mailto:", "tel:", "#", "javascript:")):
            continue
        if any(seg in href for seg in ("/contact", "contact-us", "contact.html")):
            continue
        return True
    return False


def _detect_chat_widget(soup: BeautifulSoup) -> str:
    """Match only script/iframe src attributes and inline script bodies
    against known vendor domains. Never scans visible page text: ordinary
    prose ("crisp dosas", "video intercom") would false-positive constantly."""
    sources = [t["src"].lower() for t in soup.find_all("script", src=True)]
    sources += [t["src"].lower() for t in soup.find_all("iframe", src=True)]
    inline_bodies = [t.get_text().lower() for t in soup.find_all("script", src=False)]

    for vendor, domains in CHAT_VENDOR_DOMAINS.items():
        if any(domain in src for src in sources for domain in domains):
            return vendor
        if any(domain in body for body in inline_bodies for domain in domains):
            return vendor
    return ""


def _detect_contact_form(soup: BeautifulSoup) -> bool:
    for form in soup.find_all("form"):
        for inp in form.find_all(["input", "textarea"]):
            combined = f"{(inp.get('type') or '').lower()} {(inp.get('name') or '').lower()} {(inp.get('placeholder') or '').lower()}"
            if "email" in combined or "message" in combined or inp.name == "textarea":
                return True
    return False


def _fetch(url: str, timeout: int) -> requests.Response:
    resp = requests.get(
        url, headers={"User-Agent": BROWSER_USER_AGENT}, timeout=timeout, allow_redirects=True
    )
    # Strip scripts before any text scan so JS source code never pollutes
    # the phone/email regex sweep run over page_text.
    return resp


def enrich(lead: Lead, timeout: int = 10) -> Lead:
    """Fetch a lead's website (+ up to 3 extra pages) and return a NEW Lead
    with enrichment fields filled in. Never raises."""
    result = copy.deepcopy(lead)

    website = (lead.website or "").strip()
    if not website:
        result.fetch_error = "no_website"
        result.site_ok = None
        return result

    if not website.lower().startswith(("http://", "https://")):
        website = "https://" + website

    try:
        resp = _fetch(website, timeout)
        result.site_ok = resp.status_code == 200
        site_domain = urlparse(resp.url).netloc.lower()
        if site_domain.startswith("www."):
            site_domain = site_domain[4:]

        all_emails: list[str] = []
        # None means "not observed" (honesty invariant): only a page we
        # actually parsed at HTTP 200 may turn these into a real True/False.
        booking: bool | None = None
        chat = ""
        contact_form: bool | None = None
        processed_any = False
        base_url = resp.url

        def process(page_resp: requests.Response) -> None:
            nonlocal booking, chat, contact_form, processed_any
            try:
                soup = BeautifulSoup(page_resp.text, "html.parser")
            except Exception:  # noqa: BLE001
                return
            processed_any = True
            # Booking/chat vendor detection reads <script src>/<a href>, so it
            # must run before scripts are stripped for the plain-text scan below.
            if _detect_booking(soup):
                booking = True
            found_chat = _detect_chat_widget(soup)
            if found_chat and not chat:
                chat = found_chat
            if _detect_contact_form(soup):
                contact_form = True

            for tag in soup(["script", "style"]):
                tag.decompose()
            page_text = soup.get_text(separator=" ", strip=True)
            for email in _extract_emails(soup, page_text, site_domain):
                if email not in all_emails:
                    all_emails.append(email)

        # Only parse pages that actually loaded. A 403/404 error page must
        # never be scanned -- it would silently record "no booking found"
        # etc. for a site we never really saw.
        if resp.status_code == 200:
            process(resp)
        extra_fetches = 0
        for path in EXTRA_PATHS:
            if extra_fetches >= 3:
                break
            try:
                extra_resp = _fetch(urljoin(base_url, path), timeout)
            except Exception:  # noqa: BLE001 - degrade gracefully, keep going
                continue
            extra_fetches += 1
            if extra_resp.status_code == 200:
                process(extra_resp)

        # A page was successfully checked and the signal simply wasn't
        # there: that's a confirmed False, not "unknown".
        if processed_any:
            if booking is None:
                booking = False
            if contact_form is None:
                contact_form = False

        result.emails = all_emails
        result.has_booking = booking
        result.chat_widget = chat
        result.has_contact_form = contact_form

    except Exception as exc:  # noqa: BLE001 - never crash the run
        result.fetch_error = f"{type(exc).__name__}: {exc}"
        result.site_ok = False

    return result


def enrich_all(leads: list[Lead], workers: int = 8) -> list[Lead]:
    """Enrich many leads concurrently (bounded worker pool)."""
    workers = max(1, min(workers, 16))
    results: list[Lead | None] = [None] * len(leads)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_index = {executor.submit(enrich, lead): i for i, lead in enumerate(leads)}
        for future in as_completed(future_to_index):
            index = future_to_index[future]
            try:
                results[index] = future.result()
            except Exception as exc:  # noqa: BLE001 - never crash the run
                fallback = copy.deepcopy(leads[index])
                fallback.fetch_error = f"enrich_crash: {exc}"
                results[index] = fallback
    return [r for r in results if r is not None]


def deep_research(lead: Lead, timeout: int = 10) -> dict:
    """Gather a slightly deeper text snapshot of a lead's site for the LLM
    to reason over when writing hooks. Never raises; returns {} on failure.
    Only observed text goes in -- no inference happens here."""
    website = (lead.website or "").strip()
    if not website:
        return {}
    if not website.lower().startswith(("http://", "https://")):
        website = "https://" + website
    try:
        resp = _fetch(website, timeout)
        if resp.status_code != 200:
            return {"http_status": resp.status_code}
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()
        title = soup.title.string.strip()[:150] if soup.title and soup.title.string else ""
        text = soup.get_text(separator=" ", strip=True)
        return {
            "http_status": resp.status_code,
            "title": title,
            "text_excerpt": text[:1500],
        }
    except Exception as exc:  # noqa: BLE001 - never crash the run
        return {"error": f"{type(exc).__name__}: {exc}"}
