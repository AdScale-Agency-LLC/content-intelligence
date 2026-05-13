---
name: ci-report
description: "Weekly/Monthly Klienten-Report generieren mit Performance, Competitor-Moves, Skript-Empfehlungen. UNBEDINGT nutzen bei 'ci-report', 'Weekly Report', 'Klienten-Report', 'monatlicher Bericht', 'Performance-Report', 'Reporting fuer Klient'. NICHT fuer Audit (das ist /ci-audit) oder Trend ohne Klient (/ci-trends)."
argument-hint: "--client \"Name\" [--period weekly|monthly|quarterly] [--save path]"
allowed-tools: Bash, Read
effort: medium
user-invocable: true
---

# /ci-report — Klienten-Performance-Report

Generiert einen Markdown-Report fuer einen Klienten ueber die letzte Woche/Monat/Quartal. Eignet sich als Klienten-Deliverable.

## Wie ausfuehren

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/python/cmd_report.py" report \
  --client "<Name>" \
  --period weekly|monthly|quarterly \
  [--save /path/to/report.md]
```

## Inhalt

- **Eigene Performance** (Period): Anzahl Reels, Avg Hook-Score, Avg Views, Top Hook-Types
- **Competitor Activity**: Was haben sie neues gepostet, Avg Score
- **Top Competitor Reels**: Die staerksten Reels der Periode
- **Generated Scripts**: Drafts die noch nicht gepostet wurden
- **Action Items**: Automatisch generierte Empfehlungen basierend auf Daten

## Output

```
# Weekly Report: CS Abbruch
_Generated: 2026-05-12T..._

## Our Performance (weekly)
  Reels analyzed:  3
  Avg Hook-Score:  64.0/100
  Avg Views:       12,400
  Top Hook-Types:  problem, demonstration

## Competitor Activity (weekly)
  Competitor reels: 18
  Avg Hook-Score:  76.2/100
  Top Hook-Types:  pattern_interrupt, shock

## Top Competitor Reels (this weekly)
  - [ 92/100] @abbruch_berlin       views: 245,000
           'STOP! Asbest selbst entfernen war mein groesster Fehler'
  ...

## Action Items
  - Competitors out-hooking us by 12.2 pts. Run /ci-script to generate stronger hooks.
  - Untested hook-types vs competitors: pattern_interrupt, shock. Run A/B with /ci-script-batch.
```

## Workflow als Klienten-Deliverable

```bash
python cmd_report.py report --client "CS Abbruch" --period weekly --save weekly-2026-05-12.md
```

Dann kann das Markdown weiterverarbeitet werden (PDF-Export, monday.com Update, etc.).
