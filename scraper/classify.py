"""Bewertet Stellen: Ist es eine BWL-Stelle? Welche Keyfacts hat sie?

Zwei Wege:
  * Claude (wenn CLAUDE_CODE_OAUTH_TOKEN oder ANTHROPIC_API_KEY gesetzt ist):
    liest jede Anzeige und füllt die Keyfacts zuverlässig aus.
  * Stichwort-Regeln (Fallback ohne Schlüssel): grober, aber kostenlos.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess

from .common import KA, clean

ARTEN = ["Praktikum", "Werkstudent", "Trainee", "Junior / Berufseinstieg"]
MODELLE = ["Präsenz", "Hybrid", "Remote", KA]

# ---------------------------------------------------------------------------
# Stichwort-Regeln
# ---------------------------------------------------------------------------
FACH_RULES = [
    ("Vertrieb & Kundenmanagement", r"vertrieb|sales|key account|account manag|kundenbetreuung|customer|innendienst|pricing|order management|auftragsmanagement|auftragsabwicklung|e-?business|e-?commerce"),
    ("Einkauf & Supply Chain", r"einkauf|procurement|purchas|beschaffung|sourcing|supply|logisti|\bscm\b|materialwirtschaft|disposition|lieferanten|zoll|customs|transport|spedition|total cost|\btco\b|scheduling|resource management|travel"),
    ("Personal (HR)", r"\bhr\b|human resources|personal|recruit|talent|people|learning|change management|adoption|health management|gesundheitsmanagement"),
    ("Marketing & Kommunikation", r"marketing|kommunikation|communication|\bpr\b|social media|brand|content|event|employer branding|storytelling|video|redaktion|text"),
    ("Finanzen & Controlling", r"controlling|controller|finance|finanz|accounting|buchhaltung|rechnungswesen|\bsteuer|\btax|treasury|audit|revision|reporting|ifrs|financial|bilanz|konsolidierung|bankfach|bankbetrieb|bankkaufm|kreditwesen|kundenberater|vermögensberat"),
    ("Business Development & Strategie", r"business development|strateg|m&a|corporate development|innovation|geschäftsentwicklung|portfolio|entrepreneur"),
    ("Projektmanagement", r"projekt|project|\bpmo\b|program management|koordination|coordination"),
    ("Digitalisierung, Daten & KI", r"digital|data|daten|analytics|\bbi\b|power ?bi|business intelligence|\bsap\b|\bcrm\b|\bki\b|\bai\b|künstliche intelligenz|prozessmanagement|prozessoptimierung|process management|process transformation|it-?consult|business analyst|servicenow|microsoft 365|master data|stammdaten"),
    ("Recht & Compliance", r"legal|recht|compliance|contract|vertragsmanagement|export control|exportkontrolle|governance|datenschutz"),
]
TECH = re.compile(
    r"engineer|ingenieur|entwickl|software|firmware|hardware|embedded|elektro|"
    r"electric|mechani|mechatron|konstrukt|physik|physics|chemi|verfahrenstechn|process engineering|"
    r"prozesstechn|equipment|metrolog|mems|halbleiter|semiconductor|verification|"
    r"simulation|layout|frontend|backend|full.?stack|devops|cyber|robot|automatisier|"
    r"automation|fertigung|produktion|production|montage|wartung|maintenance|labor\b|\blab\b|chip|wafer|"
    r"r&d|research|forschung|programmier|informatik|sensor|messtechn|material|kunststoff|"
    r"versuchstechn|servicetechn|ansteuerung|motor|cad\b|bim\b|unreal|unity|animation|qualitäts|quality|technolog",
    re.I,
)


def heuristic(job: dict) -> dict:
    title = job.get("title", "")
    text = job.get("text", "")
    t = title.lower()
    fach = [name for name, pat in FACH_RULES if re.search(pat, t, re.I)]
    tech_hits = {m.group(0).lower() for m in TECH.finditer(title)}
    relevant = len(fach) > len(tech_hits)
    return {
        "relevant": relevant,
        "grund": "Stichwort-Regel",
        "art": guess_art(title),
        "arbeitsmodell": guess_modell(text),
        "fachbereich": fach[0] if fach else "Sonstiges BWL",
        "start": guess_start(text),
        "umfang": guess_umfang(text, guess_art(title)),
        "standort": job.get("location_hint") or KA,
    }


def guess_art(title: str) -> str:
    t = title.lower()
    if re.search(r"werks?stud|working student|studentische|student assistant", t):
        return "Werkstudent"
    if re.search(r"praktik|intern(ship)?\b", t):
        return "Praktikum"
    if "trainee" in t:
        return "Trainee"
    return "Junior / Berufseinstieg"


def guess_modell(text: str) -> str:
    t = text.lower()
    if re.search(r"\bhybrid|mobiles arbeiten|mobile work|teilweise remote|home ?office", t):
        return "Hybrid"
    if re.search(r"100\s?% remote|fully remote|vollständig remote", t):
        return "Remote"
    return KA


def guess_start(text: str) -> str:
    t = text.lower()
    m = re.search(r"(ab|zum|start(datum)?|beginn|starting|start date)[:\s]+(\d{1,2}\.\d{1,2}\.\d{2,4})", t)
    if m:
        return m.group(3)
    m = re.search(r"(ab|zum|beginn)\s+(januar|februar|märz|april|mai|juni|juli|august|september|oktober|november|dezember)\s*(\d{4})?", t)
    if m:
        return clean(f"{m.group(2).capitalize()} {m.group(3) or ''}")
    if re.search(r"ab sofort|asap|as soon as possible|nächstmöglich", t):
        return "ab sofort"
    return KA


def guess_umfang(text: str, art: str) -> str:
    t = text.lower()
    m = re.search(r"(\d{1,2})\s*(?:-|–|bis)\s*(\d{1,2})\s*(?:stunden|std\.?|h)\b", t)
    if m and int(m.group(2)) <= 40:
        return f"{m.group(1)}–{m.group(2)} Std./Woche"
    m = re.search(r"(\d{1,2})\s*(?:stunden|std\.?|h)\s*(?:pro|/|je|in der|per)\s*(?:woche|week)", t)
    if m:
        return f"{m.group(1)} Std./Woche"
    m = re.search(r"(?:für|dauer(?: von)?|for|duration of)?\s*(\d{1,2})\s*(?:-|–|bis)?\s*(\d{1,2})?\s*monat", t)
    if m and art in ("Praktikum", "Werkstudent", "Trainee"):
        return f"{m.group(1)}{'–' + m.group(2) if m.group(2) else ''} Monate"
    if re.search(r"teilzeit|part.?time", t) and not re.search(r"vollzeit|full.?time", t):
        return "Teilzeit"
    if re.search(r"vollzeit|full.?time", t):
        return "Vollzeit"
    return KA


# ---------------------------------------------------------------------------
# Claude
# ---------------------------------------------------------------------------
PROMPT = """Du bewertest Stellenanzeigen für eine Jobbörse für BWL-Studierende in Regensburg.
Für JEDE Stelle unten gibst du ein JSON-Objekt zurück. Antworte NUR mit einem JSON-Array, ohne Text davor oder danach.

Felder pro Objekt:
- "id": wie angegeben
- "relevant": true, wenn es eine Stelle für BWL-Studierende ist (kaufmännisch, auch mit leichtem IT-Bezug wie Datenanalyse, CRM, SAP, KI-Projekte, Digitalisierung, Prozessmanagement). false bei Ingenieurs-, Entwicklungs-, Software-, Labor-, Produktions- oder rein technischen Stellen, sowie bei Ausbildung, dualem Studium und Abschlussarbeiten.
- "grund": max. 10 Wörter, warum relevant oder nicht
- "art": eines von {arten}
- "standort": Arbeitsort(e) laut Anzeige, kurz (z. B. "Regensburg" oder "Neutraubling"); mehrere mit " / "
- "arbeitsmodell": eines von {modelle}
- "fachbereich": eines von {fachbereiche}
- "start": Startdatum kurz, z. B. "ab sofort", "01.03.2027", "März 2027" oder "k. A."
- "umfang": Werkstudent: Wochenstunden (z. B. "16–20 Std./Woche"); Praktikum: Dauer (z. B. "6 Monate"); Trainee: Dauer; Junior: "Vollzeit"/"Teilzeit". Wenn nicht genannt: "k. A."
- "veroeffentlicht": Veröffentlichungsdatum als YYYY-MM-DD, falls im Text genannt, sonst null

Erfinde nichts. Fehlende Angaben sind "k. A.".

STELLEN:
{jobs}
"""


def claude_available() -> bool:
    return bool(shutil.which("claude")) and bool(
        os.environ.get("CLAUDE_CODE_OAUTH_TOKEN") or os.environ.get("ANTHROPIC_API_KEY")
    )


def _call_claude(prompt: str, model: str) -> str:
    proc = subprocess.run(
        ["claude", "-p", "--model", model, "--output-format", "json", "--max-turns", "1"],
        input=prompt, capture_output=True, text=True, timeout=600,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"claude exit {proc.returncode}: {proc.stderr[-500:]}")
    out = json.loads(proc.stdout)
    return out.get("result", "") if isinstance(out, dict) else str(out)


def _parse_array(text: str) -> list[dict]:
    m = re.search(r"\[.*\]", text, re.S)
    if not m:
        raise ValueError("Keine JSON-Liste in der Antwort")
    return json.loads(m.group(0))


def classify_with_claude(jobs: list[dict], fachbereiche: list[str], model: str = "haiku",
                         batch_size: int = 6) -> dict[str, dict]:
    results: dict[str, dict] = {}
    for i in range(0, len(jobs), batch_size):
        batch = jobs[i:i + batch_size]
        payload = []
        for n, j in enumerate(batch):
            payload.append({
                "id": str(n),
                "firma": j["company"],
                "titel": j["title"],
                "ort_hinweis": j.get("location_hint", ""),
                "anzeige": j.get("text", "")[:6000],
            })
        prompt = PROMPT.format(
            arten=json.dumps(ARTEN, ensure_ascii=False),
            modelle=json.dumps(MODELLE, ensure_ascii=False),
            fachbereiche=json.dumps(fachbereiche, ensure_ascii=False),
            jobs=json.dumps(payload, ensure_ascii=False, indent=1),
        )
        try:
            arr = _parse_array(_call_claude(prompt, model))
        except Exception as e:  # noqa: BLE001
            print(f"  ! Claude-Bewertung fehlgeschlagen ({e}); nutze Stichwort-Regeln für {len(batch)} Stellen")
            continue
        for obj in arr:
            try:
                j = batch[int(obj.get("id"))]
            except (TypeError, ValueError, IndexError):
                continue
            obj["grund"] = clean(obj.get("grund")) or "Claude"
            results[j["url"]] = obj
    return results


def normalize(c: dict, fachbereiche: list[str]) -> dict:
    """Sorgt dafür, dass alle Felder vorhanden und einheitlich sind."""
    out = {
        "relevant": bool(c.get("relevant")),
        "grund": clean(c.get("grund")),
        "art": c.get("art") if c.get("art") in ARTEN else KA,
        "standort": clean(c.get("standort")) or KA,
        "arbeitsmodell": c.get("arbeitsmodell") if c.get("arbeitsmodell") in MODELLE else KA,
        "fachbereich": c.get("fachbereich") if c.get("fachbereich") in fachbereiche else "Sonstiges BWL",
        "start": clean(c.get("start")) or KA,
        "umfang": clean(c.get("umfang")) or KA,
        "veroeffentlicht": c.get("veroeffentlicht") if isinstance(c.get("veroeffentlicht"), str) else None,
    }
    for k in ("start", "umfang", "standort"):
        if out[k].lower() in ("k.a.", "ka", "unbekannt", "n/a", "none", "null", "-"):
            out[k] = KA
    return out
