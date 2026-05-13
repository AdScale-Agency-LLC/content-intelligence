---
name: ci-viral
description: "Viral-Outliers identifizieren (Reels mit ueberdurchschnittlicher Performance relativ zu Account-Groesse). UNBEDINGT nutzen bei 'ci-viral', 'was ist viral gegangen', 'Viral-Analyse', 'Ausreisser finden', 'ueber-performende Reels', 'was hat geknallt'. NICHT fuer normale Top-Listen (das ist /ci-hooks)."
argument-hint: "[--period 30] [--branche X] [--client \"Name\"] [--threshold 2.0]"
allowed-tools: Bash, Read
effort: medium
user-invocable: true
---

# /ci-viral — Viral-Outlier Detector

Findet Reels die viel besser performen als sie eigentlich sollten — basiert auf der **views/follower-Ratio**. Reels mit Ratio ≥ 2x dem Median werden als viral markiert.

Beispiel:
- Account hat 5.000 Followers
- Median-Views in der Nische: 2.000 (Ratio 0.4)
- Ein Reel hat 50.000 Views → Ratio 10.0 → **25x Median** → VIRAL

## Wie ausfuehren

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/python/cmd_trends.py" viral \
  [--period 30] [--branche X] [--client "Name"] [--threshold 2.0]
```

## Threshold

- `2.0` (default): 2x Median — moderate Outliers
- `3.0`: Klare Outliers
- `5.0+`: Hard-Virals nur

## Output

```
# Viral Outliers (>2.0x median views/follower ratio)
  Period: 30d  |  Found: 4

@brand_xyz  [pattern_interrupt/85/100]
  Views: 450,000  Followers: 12,000  Ratio: 37.5 (47.8x median)
  Hook: 'STOP! Bevor du das machst, hoer mir 5 Sekunden zu'
  Why:  Imperativ + Loss-Aversion + Audio-Spike, bricht Scroll-Pattern
  ABC123

@competitor_a  [shock/91/100]
  Views: 280,000  Followers: 8,500  Ratio: 32.9 (41.9x median)
  ...
```

## Warum das wichtig ist

Viral-Outliers sind die **wertvollsten Daten-Punkte** weil sie zeigen was bricht-durch-funktioniert. Ein Reel mit 1M Views von einem 5M-Account ist nicht viral (Ratio 0.2). Ein Reel mit 50k Views von einem 1k-Account ist krass viral (Ratio 50).

## Workflow

Wenn du Virals findest:
1. Lass User mit `/ci-script-from-ref --reference <viral-shortcode>` direkt adaptieren
2. Pattern-Match ueber alle Virals: gleicher Hook-Type? Gleicher Angle? → Strategy-Insight
