"""Gemeinsame Hilfsfunktionen: Konfiguration, Textnormalisierung, Filter."""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
STATE_FILE = ROOT / "data" / "state.json"
OUTPUT_FILE = ROOT / "docs" / "data" / "jobs.json"
DEBUG_DIR = ROOT / "debug"

KA = "k. A."


def load_yaml(name: str):
    with open(CONFIG_DIR / name, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_settings() -> dict:
    s = load_yaml("settings.yaml")
    s["_include"] = [re.compile(r"\b" + p, re.I) for p in s["include_title"]]
    s["_exclude"] = [re.compile(r"\b" + p, re.I) for p in s["exclude_title"]]
    s["_region"] = [re.compile(r"\b" + re.escape(p) + r"\b", re.I) for p in s["region"]]
    return s


def load_companies(only: list[str] | None = None) -> list[dict]:
    import os
    fname = os.environ.get("STUDIJOBS_COMPANIES", "companies.yaml")  # für Tests
    comps = [c for c in load_yaml(fname) if c.get("enabled")]
    if only:
        wanted = {o.lower() for o in only}
        comps = [c for c in comps if c["name"].lower() in wanted or slug(c["name"]) in wanted]
    return comps


def slug(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def clean(text: str | None) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", str(text)).strip()


def title_is_student_job(title: str, settings: dict) -> bool:
    t = clean(title)
    if any(p.search(t) for p in settings["_exclude"]):
        return False
    return any(p.search(t) for p in settings["_include"])


def region_match(text: str, settings: dict) -> str | None:
    """Gibt den im Text zuerst genannten Regions-Ort zurück, sonst None."""
    best = None
    for name, pat in zip(settings["region"], settings["_region"]):
        m = pat.search(text or "")
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), name)
    return best[1] if best else None


_MONTHS = {
    "jan": 1, "januar": 1, "feb": 2, "februar": 2, "mär": 3, "maerz": 3, "märz": 3, "mar": 3,
    "march": 3, "apr": 4, "april": 4, "mai": 5, "may": 5, "jun": 6, "juni": 6, "june": 6,
    "jul": 7, "juli": 7, "july": 7, "aug": 8, "august": 8, "sep": 9, "sept": 9,
    "september": 9, "okt": 10, "oktober": 10, "oct": 10, "october": 10, "nov": 11,
    "november": 11, "dez": 12, "dezember": 12, "dec": 12, "december": 12,
}


def parse_date(value) -> str | None:
    """Versucht, ein Datum in ISO (YYYY-MM-DD) umzuwandeln."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        ts = value / 1000 if value > 1e11 else value
        try:
            return datetime.utcfromtimestamp(ts).date().isoformat()
        except (OverflowError, OSError, ValueError):
            return None
    s = clean(str(value))
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return _safe(int(m[1]), int(m[2]), int(m[3]))
    m = re.search(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b", s)
    if m:
        return _safe(int(m[3]), int(m[2]), int(m[1]))
    m = re.search(r"\b(\d{1,2})[.\s-]+([A-Za-zäÄ]{3,9})\.?[\s-]+(\d{4})\b", s)
    if m and m[2].lower() in _MONTHS:
        return _safe(int(m[3]), _MONTHS[m[2].lower()], int(m[1]))
    m = re.search(r"\b([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s+(\d{4})\b", s)
    if m and m[1].lower() in _MONTHS:
        return _safe(int(m[3]), _MONTHS[m[1].lower()], int(m[2]))
    return None


def _safe(y: int, m: int, d: int) -> str | None:
    try:
        return date(y, m, d).isoformat()
    except ValueError:
        return None
