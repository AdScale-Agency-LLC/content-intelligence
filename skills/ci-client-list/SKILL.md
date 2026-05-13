---
name: ci-client-list
description: "Alle Klienten auflisten mit Reel-Count und letzter Aktivitaet. UNBEDINGT nutzen bei 'ci-client-list', 'zeig mir alle Klienten', 'Klienten-Uebersicht', 'welche Clients haben wir', 'liste Klienten'. NICHT fuer Detail-Audit eines einzelnen Klienten (das ist /ci-audit)."
argument-hint: ""
allowed-tools: Bash, Read
effort: low
user-invocable: true
---

# /ci-client-list — Klienten-Uebersicht

Zeigt alle Klienten in der lokalen DB mit:
- Name
- Branche
- IG-Handle
- Anzahl analysierter Reels
- Letzte Analyse-Aktivitaet

## Wie ausfuehren

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/python/cmd_client.py" list
```

Optional: `--json` fuer maschinen-lesbaren Output.

## Output

```
Clients (4):

  Name                          Branche           IG-Handle              Reels
  ----------------------------- ----------------- ---------------------- ------
  CS Abbruch                    abbruch           @csabbruch                 35
  Trautmann                     catering          @trautmann_grills          22
  Immoverse                     immobilien        @immoverse                 18
  Mansulting                    consulting        -                           5
```

## Wenn leer

```
No clients yet. Create one with: /ci-client-add <name>
```

Dann schlag dem User vor einen ersten Klienten anzulegen.
