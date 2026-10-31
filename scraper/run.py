"""Hauptprogramm: sammelt, filtert, bewertet und schreibt docs/data/jobs.json.

Aufruf:  python -m scraper.run [--debug] [--only Infineon Krones] [--no-claude]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from datetime import date, datetime, timezone

from playwright.sync_api import sync_playwright

from . import classify
from .common import (DEBUG_DIR, KA, OUTPUT_FILE, STATE_FILE, clean, load_companies,
                     load_settings, region_match, slug, title_is_student_job)
from .detail import fetch_detail
from .harvest import harvest

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")
MAX_DETAILS_PER_COMPANY = 300
STATE_VERSION = 1


def load_state() -> dict:
    if STATE_FILE.exists():
        s = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        if s.get("version") == STATE_VERSION:
            return s
    return {"version": STATE_VERSION, "jobs": {}, "rejected": {}}


def write_debug(company: dict, dbg: dict) -> None:
    d = DEBUG_DIR / slug(company["name"])
    d.mkdir(parents=True, exist_ok=True)
    if "list_html" in dbg:
        (d / "list.html").write_text(dbg["list_html"][:3_000_000], encoding="utf-8")
    if "list_text" in dbg:
        (d / "list.txt").write_text(dbg["list_text"], encoding="utf-8")
    if "screenshot" in dbg:
        (d / "screenshot.png").write_bytes(dbg["screenshot"])
    (d / "network.json").write_text(json.dumps(dbg.get("network", [])[:80], ensure_ascii=False, indent=1), encoding="utf-8")
    (d / "links.json").write_text(json.dumps(dbg.get("links", []), ensure_ascii=False, indent=1), encoding="utf-8")
    if "details" in dbg:
        (d / "details.json").write_text(json.dumps(dbg["details"], ensure_ascii=False, indent=1), encoding="utf-8")
    if "error" in dbg:
        (d / "error.txt").write_text(dbg["error"], encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--debug", action="store_true", help="Rohdaten nach debug/ schreiben")
    ap.add_argument("--only", nargs="*", help="Nur diese Firmen")
    ap.add_argument("--no-claude", action="store_true")
    ap.add_argument("--reclassify", action="store_true", help="Bereits bewertete Stellen neu bewerten")
    args = ap.parse_args()

    settings = load_settings()
    companies = load_companies(args.only)
    state = load_state()
    today = date.today().isoformat()
    use_claude = classify.claude_available() and not args.no_claude
    model = os.environ.get("CLAUDE_MODEL", "haiku")
    print(f"Firmen: {', '.join(c['name'] for c in companies)}")
    print(f"Bewertung: {'Claude (' + model + ')' if use_claude else 'Stichwort-Regeln'}")

    company_status = []
    active_urls: set[str] = set()
    to_classify: list[dict] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, executable_path=os.environ.get("CHROME_PATH") or None)
        ctx = browser.new_context(user_agent=UA, locale="de-DE", viewport={"width": 1366, "height": 900})
        page = ctx.new_page()

        for comp in companies:
            name = comp["name"]
            dbg = {} if args.debug else None
            status = {"name": name, "career_url": comp["career_url"], "ok": True, "found": 0, "note": ""}
            t0 = time.time()
            print(f"\n== {name} ==")
            try:
                raw = harvest(page, comp, dbg)
                status["found"] = len(raw)
                print(f"  {len(raw)} Stellen-Links gefunden")
                cands = [r for r in raw if title_is_student_job(r["title"] + " " + r.get("card", "")[:160], settings)]
                print(f"  {len(cands)} davon Praktikum/Werkstudent/Junior/Trainee (Titel)")

                # Ortsfilter auf Listenebene, falls Ort bekannt
                filtered = []
                for c in cands:
                    loc_text = " ".join([c.get("location", ""), c.get("card", "")])
                    hint = region_match(loc_text, settings)
                    if c.get("location") and not hint:
                        continue  # Ort bekannt und nicht Regensburg
                    c["location_hint"] = hint or ""
                    filtered.append(c)
                print(f"  {len(filtered)} nach Ortsfilter (Liste)")

                details_dbg = []
                n_detail = 0
                for c in filtered:
                    url = c["url"]
                    known = state["jobs"].get(url)
                    if known and not args.reclassify:
                        active_urls.add(url)
                        known["last_seen"] = today
                        continue
                    if url in state["rejected"] and not args.reclassify:
                        state["rejected"][url] = today
                        continue
                    if n_detail >= MAX_DETAILS_PER_COMPANY:
                        status["note"] = "Limit für Detailseiten erreicht"
                        break
                    n_detail += 1
                    try:
                        det = fetch_detail(page, url)
                    except Exception as e:  # noqa: BLE001
                        print(f"  ! Detailseite fehlgeschlagen: {url} ({e.__class__.__name__})")
                        continue
                    loc_hint = c.get("location_hint") or region_match(det["location"], settings) \
                        or region_match(url.replace("-", " "), settings) \
                        or region_match(det["text"][:6000], settings)
                    if not loc_hint:
                        state["rejected"][url] = today
                        continue
                    job = {
                        "url": url,
                        "company": name,
                        "title": det["title"] if len(det["title"]) > len(c["title"]) - 5 and det["title"] else c["title"],
                        "list_title": c["title"],
                        "location_hint": loc_hint,
                        "posted_source": c.get("posted") or det.get("posted"),
                        "text": det["text"],
                    }
                    if not job["title"] or len(job["title"]) > 200:
                        job["title"] = c["title"]
                    to_classify.append(job)
                    if dbg is not None:
                        details_dbg.append({k: v for k, v in job.items() if k != "text"} | {"text_start": det["text"][:1500]})
                if dbg is not None:
                    dbg["details"] = details_dbg
                if status["found"] == 0:
                    status["ok"] = False
                    status["note"] = "Keine Stellen gefunden (Seite evtl. geändert)"
            except Exception as e:  # noqa: BLE001
                status["ok"] = False
                status["note"] = f"Fehler: {e.__class__.__name__}"
                print(f"  ! Fehler bei {name}: {e}")
                if dbg is not None:
                    dbg["error"] = traceback.format_exc()
            status["seconds"] = round(time.time() - t0)
            company_status.append(status)
            if dbg is not None:
                write_debug(comp, dbg)

        browser.close()

    # ---- Bewertung neuer Stellen ----
    print(f"\n{len(to_classify)} neue Stellen werden bewertet …")
    claude_results = {}
    if use_claude and to_classify:
        claude_results = classify.classify_with_claude(to_classify, settings["fachbereiche"], model=model)
    for job in to_classify:
        raw = claude_results.get(job["url"]) or classify.heuristic(job)
        c = classify.normalize(raw, settings["fachbereiche"])
        c["bewertet_von"] = "claude" if job["url"] in claude_results else "regeln"
        # Ort muss Region Regensburg sein
        if c["standort"] == KA:
            c["standort"] = job["location_hint"]
        if not region_match(c["standort"], settings) and not job["location_hint"]:
            c["relevant"] = False
        if not c["relevant"]:
            state["rejected"][job["url"]] = today
            print(f"  – {job['company']}: {job['title']} ({c['grund']})")
            continue
        state["jobs"][job["url"]] = {
            "url": job["url"],
            "company": job["company"],
            "title": clean(job["title"]),
            "first_seen": today,
            "last_seen": today,
            "posted": job["posted_source"] or c.pop("veroeffentlicht", None),
            **{k: v for k, v in c.items() if k not in ("veroeffentlicht", "relevant")},
        }
        active_urls.add(job["url"])
        print(f"  + {job['company']}: {job['title']} [{c['art']}, {c['fachbereich']}]")

    # ---- Firmen, deren Abruf fehlschlug: alte Stellen einmalig behalten ----
    failed = {s["name"] for s in company_status if not s["ok"]}
    for url, j in state["jobs"].items():
        if j["company"] in failed and url not in active_urls and j.get("kept_runs", 0) < 1:
            j["kept_runs"] = j.get("kept_runs", 0) + 1
            active_urls.add(url)
    # Inaktive Stellen entfernen
    state["jobs"] = {u: j for u, j in state["jobs"].items() if u in active_urls}
    for j in state["jobs"].values():
        if j["company"] not in failed:
            j.pop("kept_runs", None)
    # Abgelehnte Stellen nach 60 Tagen vergessen
    cutoff = (date.today().toordinal() - 60)
    state["rejected"] = {u: d for u, d in state["rejected"].items() if date.fromisoformat(d).toordinal() >= cutoff}

    # ---- Ausgabe ----
    jobs_out = []
    for j in state["jobs"].values():
        jobs_out.append({
            "titel": j["title"],
            "firma": j["company"],
            "art": j["art"],
            "standort": j["standort"],
            "arbeitsmodell": j["arbeitsmodell"],
            "fachbereich": j["fachbereich"],
            "start": j["start"],
            "umfang": j["umfang"],
            "veroeffentlicht": j.get("posted") or j["first_seen"],
            "datum_geschaetzt": not j.get("posted"),
            "link": j["url"],
        })
    jobs_out.sort(key=lambda x: x["veroeffentlicht"], reverse=True)
    out = {
        "aktualisiert": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "bewertung": "claude" if use_claude else "regeln",
        "firmen": [{k: s[k] for k in ("name", "career_url", "ok", "note")} |
                   {"stellen": sum(1 for j in jobs_out if j["firma"] == s["name"])} for s in company_status],
        "stellen": jobs_out,
    }
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")

    print(f"\nFertig: {len(jobs_out)} Stellen online.")
    for s in company_status:
        print(f"  {'OK ' if s['ok'] else 'ERR'} {s['name']}: {s['found']} Links, {s['seconds']}s {s['note']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
