---
name: ci-script-review
description: "Bestehendes Skript (vom User geliefert) gegen DB-Benchmarks bewerten. UNBEDINGT nutzen bei 'ci-script-review', 'bewerte dieses Skript', 'ist der Hook gut genug', 'reviewe mein Skript', 'Skript-Audit'. NICHT fuer Skript-Generation (/ci-script)."
argument-hint: "[--client \"Name\"] --text \"<Skript-Text>\" ODER --file <path>"
allowed-tools: Bash, Read
effort: medium
user-invocable: true
---

# /ci-script-review — Skript bewerten gegen DB-Benchmarks

Der User hat ein Skript geschrieben (oder von woanders) und will wissen ob es gut ist. Plugin bewertet Hook/Angle/CTA gegen die Top-Performer in der DB und gibt konkrete Verbesserungen.

## Wie ausfuehren

**Inline:**
```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/python/cmd_script.py" review \
  --client "CS Abbruch" \
  --text "Hook: ...\n\nSzene 1: ..."
```

**Aus Datei:**
```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/python/cmd_script.py" review \
  --client "CS Abbruch" \
  --file path/to/script.md
```

`--client` ist optional aber empfohlen — gibt klienten-spezifische Benchmarks.

## Output

```
# Skript-Review (CS Abbruch)

**Overall Score:** 64/100
  Hook: 58/100  |  Angle: 72/100  |  CTA: 50/100

## Staerken
- Angle (problem_solution) matched die Top-Performer der Nische
- Visual-Beschreibung in Szene 2 ist konkret

## Schwaechen
- Hook ("Wusstest du dass...") generisch, top-Reels nutzen pattern-interrupt
- CTA "Folge fuer mehr" ist passiv — Klient's top-Reels haben konkrete CTAs
- Szene 3 hat keinen klaren Visual-Anker

## Verbesserungen
- Hook ersetzen: "STOP! Bevor du Asbest siehst, wisse das" (pattern_interrupt, +15-20 Score)
- CTA aktiv machen: "Kommentier INFO fuer den Asbest-Check-Plan"
- Szene 3: Vorher/Nachher-Vergleich einbauen (wie DEF456 Score 84)

## Benchmark-Vergleich
Im Vergleich zu den Top-3 CS-Abbruch-Reels (Score-Avg 79/100) liegt das Skript ~15 Punkte unter
Branchen-Top. Mit den Hook+CTA Fixes erwartbar +12 Punkte → ~76/100.
```

## Voraussetzung

DB sollte mind. 5 Reels enthalten (idealerweise klienten-spezifisch) fuer aussagekraefte Benchmarks. Bei leerer DB nutzt das System allgemeine Best-Practice statt klienten-spezifisch — funktioniert aber weniger praezise.

## Self-Audit

- [ ] Score nicht ueber 100 oder unter 0
- [ ] Verbesserungen sind actionable mit konkreten Vorschlaegen
- [ ] Bei niedrigem Score: Top-3 Benchmark-Reels zitiert
- [ ] Sprache: deutsch, klar, kein Mealy-Mouth
