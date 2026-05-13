---
name: ci-client-update
description: "Bestehenden Klienten updaten (Branche, IG-Handle, Competitors, Tonalitaet etc.). UNBEDINGT nutzen bei 'ci-client-update', 'update Client X', 'aendere Klienten', 'neue Competitors fuer', 'Klient bearbeiten'. NICHT fuer neue Klienten (das ist /ci-client-add)."
argument-hint: "<name> [--branche X] [--ig-handle @user] [--competitor @comp1]"
allowed-tools: Bash, Read
effort: low
user-invocable: true
---

# /ci-client-update — Klienten updaten

Updated einen existierenden Klienten. Nur die Felder werden geaendert die du explizit angibst — der Rest bleibt wie er ist.

## Wie ausfuehren

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/python/cmd_client.py" update "<NAME>" \
  [--branche "..."] [--zielgruppe "..."] [--tonalitaet "..."] \
  [--ig-handle "@..."] [--competitor "@..."] [--competitor "@..."] \
  [--notes "..."]
```

Beispiele:

```bash
# Branche und Tonalitaet aendern
python cmd_client.py update "CS Abbruch" --branche "abbruch-rueckbau" --tonalitaet "Sie/formal"

# Competitor-Liste ueberschreiben
python cmd_client.py update "Trautmann" --competitor "@grill_meister" --competitor "@bbq_pro"
```

**Wichtig:** Wenn du `--competitor` angibst, **ersetzt** das die alte Liste vollstaendig — nicht "addiert". Wenn du nur einen hinzufuegen willst, gib alle alten + neuen mit.

## Fuzzy-Find bei Tippfehler

Wenn der Klient nicht gefunden wird, zeigt das Skript aehnliche Namen vor:
```
Client not found: 'CS-Abbruch'
Did you mean:
  - CS Abbruch
```

Frag den User dann nach der korrekten Schreibweise.

## Workflow-Tipp

Klassischer Use-Case:
1. Neuer Klient kommt rein → `/ci-client-add "Name"` mit Basis-Info
2. Du analysierst 20 Reels → siehst dass Tonalitaet anders ist als initial gedacht
3. `/ci-client-update "Name" --tonalitaet "..."` korrigieren

Oder:
1. Klient sagt "wir haben einen neuen Hauptcompetitor"
2. `/ci-client-update "Name" --competitor "@neu" --competitor "@alt1" --competitor "@alt2"`
