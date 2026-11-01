"""Liest eine einzelne Stellenanzeige: strukturierte Daten (JSON-LD) und Fließtext."""
from __future__ import annotations

import html as htmllib
import json
import re

from playwright.sync_api import Page, TimeoutError as PWTimeout

from .common import clean, parse_date
from .harvest import dismiss_cookies

MAX_TEXT = 9000


def _jsonld_jobposting(page: Page) -> dict | None:
    blocks = page.evaluate(
        "[...document.querySelectorAll('script[type=\"application/ld+json\"]')].map(s => s.textContent)"
    )
    for raw in blocks:
        try:
            data = json.loads(raw)
        except Exception:
            continue
        stack = [data]
        while stack:
            d = stack.pop()
            if isinstance(d, list):
                stack.extend(d)
            elif isinstance(d, dict):
                t = d.get("@type")
                if t == "JobPosting" or (isinstance(t, list) and "JobPosting" in t):
                    return d
                if "@graph" in d:
                    stack.append(d["@graph"])
    return None


def _jsonld_location(jp: dict) -> str:
    locs = jp.get("jobLocation") or []
    if isinstance(locs, dict):
        locs = [locs]
    out = []
    for l in locs:
        addr = (l or {}).get("address") or {}
        if isinstance(addr, str):
            out.append(addr)
        elif isinstance(addr, dict):
            out.append(", ".join(str(addr[k]) for k in ("addressLocality", "addressRegion") if addr.get(k)))
    if jp.get("jobLocationType") == "TELECOMMUTE":
        out.append("Remote")
    return "; ".join(o for o in out if o)


def _fast(page: Page, url: str) -> dict | None:
    """Schneller Abruf ohne Rendern (für serverseitig erzeugte Seiten)."""
    try:
        resp = page.request.get(url, timeout=30_000)
        if not resp.ok:
            return None
        raw = resp.text()
    except Exception:  # noqa: BLE001
        return None
    jp = {}
    for m in re.finditer(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', raw, re.S | re.I):
        try:
            d = json.loads(m.group(1))
        except Exception:  # noqa: BLE001
            continue
        for x in (d if isinstance(d, list) else d.get("@graph", [d]) if isinstance(d, dict) else []):
            if isinstance(x, dict) and x.get("@type") == "JobPosting":
                jp = x
                break
    body = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", raw, flags=re.S | re.I)
    body = re.sub(r"<br\s*/?>|</(p|div|li|h\d|tr)>", "\n", body, flags=re.I)
    text = htmllib.unescape(re.sub(r"<[^>]+>", " ", body))
    text = "\n".join(clean(l) for l in text.splitlines() if clean(l))
    if len(text) < 300:
        return None
    t = re.search(r"<title>(.*?)</title>", raw, re.S | re.I)
    return {
        "title": clean(jp.get("title")) or clean(htmllib.unescape(t.group(1))) if t else clean(jp.get("title")),
        "posted": parse_date(jp.get("datePosted")),
        "location": _jsonld_location(jp) if jp else "",
        "employment_type": jp.get("employmentType"),
        "text": text[:MAX_TEXT],
    }


def fetch_detail(page: Page, url: str, fast: bool = False) -> dict:
    if fast:
        d = _fast(page, url)
        if d:
            return d
    page.goto(url, wait_until="domcontentloaded", timeout=60_000)
    try:
        page.wait_for_load_state("networkidle", timeout=12_000)
    except PWTimeout:
        pass
    page.wait_for_timeout(1200)
    dismiss_cookies(page)
    jp = _jsonld_jobposting(page) or {}
    text = page.evaluate(
        """() => {
            const el = document.querySelector('main, [role=main], article, #content, .content') || document.body;
            let t = el.innerText || '';
            if (t.length < 400) t = document.body.innerText || '';
            return t;
        }"""
    )
    text = "\n".join(line.strip() for line in (text or "").splitlines() if line.strip())
    return {
        "title": clean(jp.get("title")) or clean(page.title()),
        "posted": parse_date(jp.get("datePosted")),
        "location": _jsonld_location(jp),
        "employment_type": jp.get("employmentType"),
        "text": text[:MAX_TEXT],
    }
