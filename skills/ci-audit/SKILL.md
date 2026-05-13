---
name: ci-audit
description: "Content-Audit fuer einen Klienten: eigene Reels vs. Competitor-Benchmark, Luecken-Analyse, Empfehlungen. UNBEDINGT nutzen bei 'ci-audit', 'Content-Audit fuer', 'wie steht Client X da', 'Competitor-Vergleich', 'wo stehen wir vs', 'Performance-Analyse Klient'. NICHT fuer Trend ueber alle Klienten (/ci-trends)."
argument-hint: "--client \"Name\""
allowed-tools: Bash, Read
effort: medium
user-invocable: true
---

# /ci-audit — Klienten-Content-Audit

Analysiert eigene Reels eines Klienten gegen Competitor-Reels in der DB. Zeigt:
- Benchmark-Vergleich (Hook/Retention/CTA/Visual als Tabelle)
- Top-Hook-Types: Uns vs. Competitors
- Top-Angles: Uns vs. Competitors
- Posting-Frequenz
- Konkrete Empfehlungen (Gap-Analyse)

## Voraussetzung

In der DB sollten sein:
- Eigene Reels (`--is-own` markiert), mindestens 5
- Competitor-Reels, mindestens 10

Wenn weniger: User soll erst `/ci-batch` ausfuehren.

## Wie ausfuehren

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/python/cmd_audit.py" --client "<Name>"
```

## Output

```
# Content-Playbook: CS Abbruch
Branche: abbruch

## Datenbasis
  Eigene Reels:       18
  Competitor Reels:   62

## Performance Benchmark
  Metric                        Uns    Competitors    Gap
  ----------------------     ------    -----------   -----
  Hook-Score                   62.4           74.8   -12.4
  Retention                    58.0           67.2    -9.2
  CTA                          51.0           68.5   -17.5
  Visual-Quality               71.0           69.2    +1.8

## Unsere Top Hook-Types
  - problem                  avg 68.2/100  (6 reels)
  - story                    avg 65.0/100  (4 reels)

## Competitor Top Hook-Types
  - pattern_interrupt        avg 79.4/100  (18 reels)
  - shock                    avg 76.5/100  (11 reels)

## Empfehlungen
1. Hook-Staerke schwach: 62.4 vs 74.8. Top-Competitor-Hook-Types nutzen: ['pattern_interrupt', 'shock']
2. CTA-Klarheit schwach: 51 vs 68.5. Konkrete CTAs einbauen.
3. Hook-Types die Competitors nutzen aber wir nicht: pattern_interrupt, shock
4. Posting-Frequenz "sporadic" ist niedrig. 3-5x/Woche anstreben.
```

## Workflow

Nach Audit: Schlag User direkt 2 Next-Steps vor:
1. `/ci-playbook --client X` zum Speichern als Strategie-Dokument
2. `/ci-script --client X --thema "..."` um konkrete Skripte zu generieren basierend auf den Empfehlungen
