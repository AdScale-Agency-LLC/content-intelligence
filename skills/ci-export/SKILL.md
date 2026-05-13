---
name: ci-export
description: "Reel-Daten exportieren als CSV oder JSON. UNBEDINGT nutzen bei 'ci-export', 'exportier die Daten', 'CSV Export', 'JSON Export', 'daten herunterladen'. NICHT fuer formatierte Reports (das ist /ci-report)."
argument-hint: "[--client \"Name\"] [--format csv|json] [--out file]"
allowed-tools: Bash, Read
effort: low
user-invocable: true
---

# /ci-export — Datenexport

Exportiert die analysierten Reels als CSV (default) oder JSON. Fuer externe Weiterverarbeitung (Spreadsheets, BI-Tools, Klienten-Reports).

## Wie ausfuehren

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/python/cmd_report.py" export \
  [--client "<Name>"] \
  [--format csv|json] \
  [--limit 1000] \
  [--out /path/to/export.csv]
```

## CSV-Spalten

shortcode, source, account, client_id, is_own, views, likes, comments, engagement_rate, language, summary, angle, hook_type, hook_text, hook_score, score_retention, score_visual, score_cta, posted_at, analyzed_at

## Beispiele

```bash
# Alle Reels eines Klienten als CSV
python cmd_report.py export --client "CS Abbruch" --format csv --out csabbruch.csv

# Alle Reels JSON ohne Filter
python cmd_report.py export --format json --out all.json

# Ohne --out: stdout (zum Pipen)
python cmd_report.py export --format csv | grep "viral"
```

## Workflow

Use Cases:
- Daten an externe Datenanalysten weitergeben
- In Google Sheets fuer Klienten-Pivot importieren
- Backup vor groesseren Operationen
