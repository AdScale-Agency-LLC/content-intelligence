---
name: ci-trends
description: "Trend-Report ueber analysierte Reels (Hook-Verteilung, Angles, Score-Trends, Themes). UNBEDINGT nutzen bei 'ci-trends', 'was trendet', 'Trend-Report', 'was funktioniert gerade in', 'Branche-Analyse', 'Hook-Verteilung'. NICHT fuer Viral-Outliers (das ist /ci-viral) oder einzelnen Klienten-Audit (/ci-audit)."
argument-hint: "[--period 30] [--branche X] [--client \"Name\"]"
allowed-tools: Bash, Read
effort: medium
user-invocable: true
---

# /ci-trends — Trend-Report

Aggregiert die Reels in der DB ueber einen Zeitraum + Filter und zeigt Patterns:
- Hook-Type-Verteilung (welche dominieren?)
- Angle-Verteilung
- Avg Hook-Score, Cut-Frequenz, Retention
- Score-Verteilung (Bins)
- Top-10 Hooks der Periode
- Top-Themes (Content-Tags)
- Color-Mood-Verteilung

## Wie ausfuehren

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/python/cmd_trends.py" trends \
  [--period 30] [--branche <branche>] [--client "<Name>"]
```

## Filter-Modi

| Mode | Beispiel | Was zeigt es |
|---|---|---|
| Alle Daten | `--period 30` | Trends ueber alle analysierten Reels |
| Branche | `--period 30 --branche abbruch` | Nur Reels von Klienten in dieser Branche |
| Klient-spezifisch | `--client "CS Abbruch"` | Nur Reels eines Klienten (eigene + Competitor) |

## Output Auszug

```
# Trend-Report (Branche: abbruch)
**Period:** 30 days  |  Reels: 87  |  Accounts: 6
**Avg Hook-Score:** 71.2/100
**Avg Cut-Frequency:** 3.4 / 10s
**Avg Retention-Prediction:** 64.8%

## Hook-Type Distribution
  pattern_interrupt       28  (32.2%)
  problem                 19  (21.8%)
  demonstration           14  (16.1%)
  question                12  (13.8%)
  story                    8  (9.2%)
  ...

## Top 10 Hooks (by score)
  - [ 92/100] @viralcreator       pattern_interrupt   'Stop! Niemals das hier machen'
  ...
```

## Voraussetzung

Mindestens ~30 Reels in der DB fuer aussagekraefte Trends. Bei <10 Reels schreibe dem User: "DB zu klein fuer Trend-Analyse, sammle erst mehr Daten mit /ci-batch."
