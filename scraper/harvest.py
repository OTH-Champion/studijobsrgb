"""Sammelt Stellen-Links von einer Karriereseite.

Funktioniert generisch für die meisten Karriere-Systeme:
  1. Seite im echten Browser (Chromium) öffnen, damit auch JavaScript-Seiten laden.
  2. Cookie-Banner ablehnen.
  3. "Mehr laden" klicken bzw. weiterblättern.
  4. Alle Links einsammeln, die wie eine Stellenanzeige aussehen (Regex aus der Konfiguration).
  5. Zusätzlich alle JSON-Antworten der Seite mitlesen und darin nach Stellenlisten suchen
     (hilft bei Seiten, die Stellen ohne echte Links anzeigen).
"""
from __future__ import annotations

import json
import re
from urllib.parse import urljoin

from playwright.sync_api import Page, TimeoutError as PWTimeout

from .common import clean, parse_date

REJECT_COOKIES = re.compile(
    r"^(alle ablehnen|ablehnen|nur notwendige|nur erforderliche|nur essenzielle|"
    r"notwendige cookies|reject all|reject|decline|decline all|necessary only|"
    r"only necessary|continue without accepting|ohne zustimmung fortfahren)",
    re.I,
)
LOAD_MORE = re.compile(
    r"(mehr laden|weitere (elemente|jobs|stellen|ergebnisse|anzeigen|laden)|mehr anzeigen|"
    r"mehr ergebnisse|load more|show more|more jobs|view more|alle anzeigen)",
    re.I,
)

TITLE_KEYS = ("name", "title", "jobTitle", "job_title", "positionTitle", "postingTitle", "displayName")
ID_KEYS = ("id", "jobId", "job_id", "jobReqId", "reqId", "requisitionId", "displayJobId", "ats_job_id")
URL_KEYS = ("canonicalPositionUrl", "positionUrl", "jobUrl", "url", "applyUrl", "externalUrl", "link", "href")
LOC_KEYS = ("location", "locations", "full_location", "short_location", "cityLabel", "city", "primaryLocation", "jobLocation", "locationName",
            "standardizedLocations", "cityState", "workLocation")
DATE_KEYS = ("posted_date", "publicationDate", "postingDate", "t_create", "postedTs", "postedDate", "datePosted", "createdDate", "publishedDate",
             "postingDate", "creationDate", "posted_on", "startDate_posted", "releasedDate")


def dismiss_cookies(page: Page) -> None:
    for sel in ("#onetrust-reject-all-handler", "button#CybotCookiebotDialogBodyButtonDecline",
                "[data-testid='uc-deny-all-button']", "button.cc-deny"):
        try:
            if page.locator(sel).first.is_visible(timeout=500):
                page.locator(sel).first.click(timeout=1500)
                page.wait_for_timeout(500)
                return
        except Exception:
            pass
    try:
        btn = page.get_by_role("button", name=REJECT_COOKIES).first
        if btn.is_visible(timeout=800):
            btn.click(timeout=1500)
            page.wait_for_timeout(500)
    except Exception:
        pass


def _collect_links(page: Page, link_re: str) -> list[dict]:
    """Liest alle passenden Links samt Text der umgebenden 'Karte' aus."""
    return page.evaluate(
        """(pattern) => {
            const re = new RegExp(pattern);
            const out = [];
            for (const a of document.querySelectorAll('a[href]')) {
                const href = a.href;
                if (!re.test(href)) continue;
                // Karte = nächster Vorfahre, der deutlich mehr Text als der Link enthält
                const linkLen = (a.innerText || '').trim().length;
                let card = a.closest('li, article, tr');
                if (!card) {
                    let el = a.parentElement;
                    for (let i = 0; el && i < 6; i++, el = el.parentElement) {
                        if ((el.innerText || '').trim().length > linkLen + 15) { card = el; break; }
                    }
                }
                const textOf = (el) => {
                    const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
                    const parts = [];
                    while (w.nextNode()) { const t = w.currentNode.textContent.trim(); if (t) parts.push(t); }
                    return parts.join(' ');
                };
                let cardText = card ? textOf(card) : '';
                if (cardText.length > 800) cardText = cardText.slice(0, 800);
                out.push({href, text: (a.innerText || a.getAttribute('title') || a.getAttribute('aria-label') || '').trim(), card: cardText});
            }
            // Tabellenzeilen/Karten ohne <a>, die per data-href verlinken
            for (const el of document.querySelectorAll('[data-href]')) {
                const href = new URL(el.getAttribute('data-href'), location.href).href;
                if (!re.test(href)) continue;
                const first = el.querySelector('td, h2, h3, h4, [data-title]') || el;
                const t = (first.innerText || '').trim();
                const parts = [...el.querySelectorAll('td')].map(td => td.innerText.trim()).filter(Boolean);
                out.push({href, text: t, card: (parts.length ? parts.join(' | ') : el.innerText).slice(0, 800)});
            }
            return out;
        }""",
        link_re,
    )


def _click_load_more(page: Page) -> bool:
    for role in ("button", "link"):
        try:
            loc = page.get_by_role(role, name=LOAD_MORE).first
            if loc.is_visible(timeout=600):
                loc.scroll_into_view_if_needed(timeout=1500)
                loc.click(timeout=3000)
                return True
        except Exception:
            continue
    return False


NEXT_PAGE = re.compile(r"(nächste( seite)?|next( page)?|weiter|^›$|^»$|^>$)", re.I)


def _click_next(page: Page) -> bool:
    for role in ("button", "link"):
        try:
            loc = page.get_by_role(role, name=NEXT_PAGE)
            for i in range(min(loc.count(), 4)):
                el = loc.nth(i)
                if el.is_visible(timeout=400) and el.is_enabled(timeout=400) \
                        and el.get_attribute("aria-disabled") != "true":
                    el.scroll_into_view_if_needed(timeout=1500)
                    el.click(timeout=3000)
                    return True
        except Exception:
            continue
    return False


def _settle(page: Page, ms: int = 2500) -> None:
    try:
        page.wait_for_load_state("networkidle", timeout=ms * 4)
    except PWTimeout:
        pass
    page.wait_for_timeout(ms)


def _unwrap(d: dict) -> dict:
    """Manche APIs packen jede Stelle ein, z. B. {"data": {...}} oder {"node": {...}}."""
    if any(k in d for k in TITLE_KEYS):
        return d
    for v in d.values():
        if isinstance(v, dict) and any(k in v for k in TITLE_KEYS):
            return v
    return d


def _walk_json(obj, found: list[dict], depth: int = 0) -> None:
    if depth > 8:
        return
    if isinstance(obj, list):
        dicts = [_unwrap(o) for o in obj if isinstance(o, dict)]
        if dicts and sum(1 for d in dicts if any(k in d for k in TITLE_KEYS)) >= max(1, len(dicts) // 2):
            for d in dicts:
                found.append(d)
        for o in obj[:500]:
            _walk_json(o, found, depth + 1)
    elif isinstance(obj, dict):
        for v in obj.values():
            if isinstance(v, (list, dict)):
                _walk_json(v, found, depth + 1)


def _first(d: dict, keys) -> object:
    for k in keys:
        if k in d and d[k] not in (None, "", []):
            return d[k]
    return None


def _loc_to_text(loc) -> str:
    if isinstance(loc, list):
        return "; ".join(_loc_to_text(x) for x in loc[:10])
    if isinstance(loc, dict):
        parts = [loc.get(k) for k in ("name", "city", "addressLocality", "locality", "state", "country") if loc.get(k)]
        return ", ".join(str(p) for p in parts)
    return clean(str(loc)) if loc else ""


def jobs_from_json(payloads: list, company: dict, base_url: str) -> list[dict]:
    found: list[dict] = []
    for p in payloads:
        _walk_json(p, found)
    jobs = []
    for d in found:
        title = _first(d, TITLE_KEYS)
        if not isinstance(title, str) or len(title) < 4:
            continue
        url = _first(d, URL_KEYS)
        jid = _first(d, ID_KEYS)
        if company.get("job_url"):
            fields = {k: v for k, v in d.items() if isinstance(v, (str, int))}
            fields.setdefault("id", jid)
            try:
                url = company["job_url"].format(**fields)
            except (KeyError, IndexError, ValueError):
                if not (isinstance(url, str) and url):
                    continue
                url = urljoin(base_url, url)
        elif isinstance(url, str) and url:
            url = urljoin(base_url, url)
        else:
            continue
        jobs.append({
            "url": url.rstrip("/"),
            "title": clean(title),
            "location": _loc_to_text(_first(d, LOC_KEYS)),
            "posted": parse_date(_first(d, DATE_KEYS)),
            "department": clean(str(_first(d, ("department", "category", "jobFamily", "business_unit")) or "")),
            "source": "json",
        })
    return jobs


def harvest(page: Page, company: dict, debug: dict | None = None) -> list[dict]:
    """Gibt eine Liste roher Stellen zurück: url, title, location, posted, card."""
    payloads: list = []

    def on_response(resp):
        try:
            ct = resp.headers.get("content-type", "")
            if "json" in ct and resp.request.resource_type in ("xhr", "fetch"):
                body = resp.text()
                if len(body) < 5_000_000:
                    payloads.append(json.loads(body))
                    if debug is not None:
                        debug.setdefault("network", []).append({"url": resp.url, "size": len(body), "sample": body[:8000]})
        except Exception:
            pass

    page.on("response", on_response)
    link_re = company["job_link"]
    urls = [company["list_url"]]
    pages_cfg = company.get("pages")
    raw_links: list[dict] = []
    seen: set[str] = set()

    def grab() -> int:
        new = 0
        for l in _collect_links(page, link_re):
            if l["href"] not in seen:
                seen.add(l["href"])
                raw_links.append(l)
                new += 1
        return new

    page.goto(urls[0], wait_until="domcontentloaded", timeout=60_000)
    _settle(page)
    dismiss_cookies(page)
    _settle(page, 1500)
    grab()
    if debug is not None:
        debug["list_html"] = page.content()
        debug["list_text"] = page.evaluate("document.body.innerText")
        debug["screenshot"] = page.screenshot(full_page=False)

    # "Mehr laden"-Buttons
    for _ in range(company.get("max_load_more", 30)):
        if not _click_load_more(page):
            break
        _settle(page, 1500)
        if grab() == 0:
            # Manche Seiten laden langsam: einmal nachschauen, dann aufhören
            page.wait_for_timeout(2000)
            if grab() == 0:
                break

    # Blättern per "Nächste Seite"-Knopf
    if company.get("next_click"):
        stale = 0
        for _ in range(company["next_click"]):
            before = len(payloads)
            if not _click_next(page):
                break
            _settle(page, 1500)
            if grab() == 0 and len(payloads) == before:
                stale += 1
                if stale >= 2:
                    break
            else:
                stale = 0

    # Weitere Start-Seiten (z. B. andere Sprache)
    for extra in company.get("extra_urls", []):
        try:
            page.goto(extra, wait_until="domcontentloaded", timeout=60_000)
            _settle(page, 1500)
            grab()
        except Exception:
            pass

    # Blättern über URL-Vorlage
    if pages_cfg:
        step = pages_cfg.get("step", 10)
        for i in range(1, pages_cfg.get("max_pages", 10)):
            url = pages_cfg["template"].format(offset=i * step, page=i + 1)
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60_000)
                _settle(page, 1500)
            except Exception:
                break
            if grab() == 0:
                break

    page.remove_listener("response", on_response)

    jobs: dict[str, dict] = {}
    for l in raw_links:
        url = l["href"].split("#")[0].rstrip("/")
        title = clean(l["text"]).split(" · ")[0]
        card = clean(l["card"])
        if len(title) < 4 or len(title) > 250:
            title = card[:200]
        jobs.setdefault(url, {"url": url, "title": title, "location": "", "posted": parse_date(card),
                              "card": card, "source": "link"})
    for j in jobs_from_json(payloads, company, company["list_url"]):
        if j["url"] in jobs:
            if j["title"] and j["title"].lower() in jobs[j["url"]]["title"].lower():
                jobs[j["url"]]["title"] = j["title"]
            for k in ("location", "posted", "department"):
                if j.get(k) and not jobs[j["url"]].get(k):
                    jobs[j["url"]][k] = j[k]
        else:
            j["card"] = ""
            jobs[j["url"]] = j

    if debug is not None:
        debug["links"] = list(jobs.values())
    return list(jobs.values())
