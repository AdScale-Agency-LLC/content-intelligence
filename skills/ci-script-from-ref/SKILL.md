---
name: ci-script-from-ref
description: "Reel-Skript basierend auf konkretem Referenz-Reel (Reverse-Engineering). UNBEDINGT nutzen bei 'ci-script-from-ref', 'mach ein Skript wie dieses Reel', 'adaptier das fuer Klient X', 'gleicher Stil wie <URL>', 'inspiriert von <Reel>'. NICHT ohne explizite Referenz (das ist /ci-script)."
argument-hint: "--client \"Name\" --thema \"<topic>\" --reference <url-or-shortcode>"
allowed-tools: Bash, Read
effort: high
user-invocable: true
---

# /ci-script-from-ref — Reverse-Engineering eines Referenz-Reels

Nimmt ein konkretes Reel als Vorbild und generiert ein Skript das die selbe Struktur fuer einen anderen Klienten/Thema adaptiert.

## Use-Cases

- "Mach mir ein Skript wie dieses virale Reel von @competitor"
- "Adaptier @brand's Top-Hook fuer unseren Klienten"
- "Reverse-engineer das Format und nutze es fuer Klient X"

## Voraussetzung

Das Referenz-Reel muss **vorher analysiert sein** (`/ci-analyze <ref-url>`). Wenn es noch nicht in der DB ist, biete an es zuerst zu analysieren.

## Wie ausfuehren

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/python/cmd_script.py" from-ref \
  --client "<Klienten-Name>" \
  --thema "<Was soll das neue Reel ueber>" \
  --reference "<URL oder shortcode>"
```

Beispiel:
```bash
python cmd_script.py from-ref \
  --client "CS Abbruch" \
  --thema "Schimmel-Sanierung" \
  --reference "https://instagram.com/reel/ABC123/"
```

## Workflow

1. Lade Referenz-Reel aus DB (Hook-Text, Score, Reasoning, Angle)
2. Constraint-Generation: Hook-Type + Angle vom Referenz uebernehmen
3. Injection in den Generation-Prompt: "Adaptiere die Struktur"
4. Output enthaelt `referenz_shortcodes[0] = <ref>` als Pflicht-Eintrag

## Output

Gleich wie `/ci-script`, aber:
- Score-Reasoning verweist explizit auf die Referenz
- Rationale erklaert wie die Struktur uebernommen wurde
- referenz_shortcodes hat das Referenz-Reel als ersten Eintrag

## Self-Audit

- [ ] Hook-Struktur matched die Referenz (Type + Pattern)
- [ ] Klienten-Tonalitaet bleibt erhalten (nicht blind kopieren wenn Tonalitaet anders)
- [ ] Rationale erklaert was uebernommen wurde und was adaptiert
