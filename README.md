# StudiJobs Regensburg

Praktika, Werkstudentenstellen, Trainee- und Einstiegsjobs für BWL-Studierende in Regensburg und direkter Umgebung, gesammelt von ausgewählten Unternehmen. Die Seite aktualisiert sich jeden Montag automatisch.

## So funktioniert es

1. Ein GitHub-Workflow (`.github/workflows/update.yml`) startet jeden Montag früh.
2. Das Skript in `scraper/` öffnet die Karriereseite jeder Firma in einem echten Browser, sammelt die Stellenlinks und behält nur Praktikum, Werkstudent, Trainee und Junior/Berufseinstieg (Ausbildung, duales Studium und Abschlussarbeiten fliegen raus).
3. Für neue Stellen wird die Anzeige geöffnet. Liegt der Arbeitsort nicht in der Region Regensburg, fliegt sie raus.
4. Jede neue Stelle wird bewertet: BWL-Bezug ja/nein und die Keyfacts (Art, Standort, Arbeitsmodell, Fachbereich, Start, Umfang, Veröffentlichungsdatum).
   - Mit hinterlegtem Claude-Zugang macht das Claude (genauer).
   - Ohne Zugang greifen einfache Stichwort-Regeln.
5. Ergebnis landet in `docs/data/jobs.json`, die Website in `docs/` zeigt es an (GitHub Pages).

Bereits bekannte Stellen werden nicht erneut bewertet. Stellen, die auf der Karriereseite verschwinden, verschwinden auch hier.

## Häufige Aufgaben

**Firma hinzufügen oder deaktivieren:** `config/companies.yaml` auf GitHub öffnen, Stift-Symbol, Eintrag ändern, „Commit changes“. Neue Firmen brauchen zusätzlich `list_url` und `job_link` (siehe Kommentare in der Datei).

**Orte oder Stichwörter ändern:** `config/settings.yaml`.

**Update sofort starten:** Reiter *Actions* → *Stellen aktualisieren* → *Run workflow*.

**Fehlersuche:** Beim manuellen Start „debug“ anhaken. Dann landen Rohdaten jeder Karriereseite (Screenshot, Text, gefundene Links) im Ordner `debug/`.

## Claude-Bewertung einschalten

Einmalig auf deinem Rechner (Node.js nötig):

```bash
npm install -g @anthropic-ai/claude-code
claude setup-token
```

Den ausgegebenen Token unter *Settings → Secrets and variables → Actions → New repository secret* als `CLAUDE_CODE_OAUTH_TOKEN` speichern. Die Bewertung läuft dann über dein Claude-Abo. Alternativ funktioniert ein API-Schlüssel als Secret `ANTHROPIC_API_KEY`.

## Lokal ausprobieren

```bash
pip install -r requirements.txt
python -m playwright install chromium
python -m scraper.run --debug --only infineon
```
