---
name: ci-script
description: "Reel-Skript generieren fuer einen Klienten basierend auf bewiesenen Top-Performer-Patterns. UNBEDINGT nutzen bei 'ci-script', 'schreib ein Skript', 'Reel-Skript erstellen', 'Content-Idee fuer Klient X', 'generiere ein Skript zum Thema Y'. NICHT fuer einzelne Reel-Analyse (/ci-analyze) oder reine Hook-Liste (/ci-hooks)."
argument-hint: "--client \"Name\" --thema \"<topic>\" [--hook-type X] [--angle Y]"
allowed-tools: Bash, Read
effort: high
user-invocable: true
---

# /ci-script — KI-generiertes Reel-Skript

Generiert ein produktionsreifes Reel-Skript fuer einen Klienten. Basiert nicht auf "was Claude sich ausdenkt", sondern auf **bewiesenen Top-Performer-Patterns** aus deiner DB.

## Pipeline

1. Klienten-Profil laden (Branche, Zielgruppe, Tonalitaet, Do's/Don'ts)
2. Top-Performer aus DB ziehen (eigene + Competitor mix)
3. Patterns extrahieren (Hook-Types, Angles, Schnittfrequenz)
4. Gemini 2.5 Flash mit JSON-Schema fuer strukturiertes Skript
5. Markdown-Rendering mit Hook + Szenen + CTA + Score-Prediction + Rationale

## Wie ausfuehren

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/python/cmd_script.py" generate \
  --client "<Klienten-Name>" \
  --thema "<Was soll das Reel ueber>" \
  [--hook-type <type>] [--angle <angle>] \
  [--temperature 0.4] [--dry-run]
```

## Output

```
# Reel-Skript: Asbest-Sanierung — CS Abbruch

**Score-Prediction:** 78/100
**Hook-Type:** problem  |  **Angle:** problem_solution  |  **Laenge:** ~28s

**Score-Reasoning:** Pattern-Match zu @csabbruch's best-performing problem-Hooks (DEF456 mit 84/100)

## Hook
> "Wenn dein Vermieter Asbest verdaechtigt, mach NIEMALS das hier"

## Szenen-Breakdown
### Szene 1 (0-3s) — hook
- **Visual:** Close-Up Hand zeigt auf bröckelnde Wand
- **Audio:** "Wenn dein Vermieter Asbest verdaechtigt, mach NIEMALS das hier"
- **Text-Overlay:** STOP ⚠️

### Szene 2 (3-12s) — setup
...

## CTA (explicit)
> "Kommentier INFO und ich schick dir den Asbest-Check-Plan"

## Referenz-Reels
- DEF456 (Score 84/100, problem-Hook, 245k views)
- XYZ789 (Score 78/100, demonstration)

## Rationale
[konkrete Begruendung warum dieses Schema basierend auf den Daten funktioniert]
```

## Voraussetzungen

**Du brauchst Daten in der DB.** Wenn der Klient noch keine analysierten Reels hat, schlag dem User vor erst zu batch-analysieren:

```
/ci-batch @<own-handle> --last 20 --client "X" --is-own
/ci-batch @<competitor> --last 20 --client "X"
```

Mindestens 10 analysierte Reels (eigene + Competitor) fuer gute Skript-Qualitaet.

## Constraints

Wenn der User einen bestimmten Hook-Type oder Angle vorgibt, das mit `--hook-type` oder `--angle` weiterreichen:
- "Mach mir ein Frage-Hook Skript" → `--hook-type question`
- "Aber als Story-Format" → `--angle story`

## Self-Audit (Pflicht)

- [ ] Skript hat mind. 3 Szenen mit klar getrennten Visual/Audio/Text
- [ ] Hook ist konkret zitiert, nicht generisch beschrieben
- [ ] CTA ist actionable ("Kommentier X") nicht passiv ("Folge fuer mehr")
- [ ] referenz_shortcodes enthaelt mind. 2 konkrete Reels
- [ ] score_prediction zwischen 55-85 (nicht 100, nicht <40)
- [ ] Tonalitaet matched Klienten-Profil (du vs. Sie)
