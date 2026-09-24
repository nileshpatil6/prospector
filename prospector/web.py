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

CHAT_VENDORS = [
    "podium", "birdeye", "intercom", "tidio", "drift", "tawk.to",
    "livechat", "hubspot", "crisp", "olark", "gorgias",
]


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


def _detect_chat_widget(soup: BeautifulSoup, page_text_lower: str) -> str:
    for script in soup.find_all("script", src=True):
        src = script["src"].lower()
        for vendor in CHAT_VENDORS:
            if vendor in src:
                return vendor
    for vendor in CHAT_VENDORS:
        if vendor in page_text_lower:
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
        booking = False
        chat = ""
        contact_form = False
        base_url = resp.url

        def process(page_resp: requests.Response) -> None:
            nonlocal booking, chat, contact_form
            try:
                soup = BeautifulSoup(page_resp.text, "html.parser")
            except Exception:  # noqa: BLE001
                return
            # Booking/chat vendor detection reads <script src>/<a href>, so it
            # must run before scripts are stripped for the plain-text scan below.
            if _detect_booking(soup):
                booking = True
            page_text_lower = soup.get_text(separator=" ", strip=True).lower()
            found_chat = _detect_chat_widget(soup, page_text_lower)
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
