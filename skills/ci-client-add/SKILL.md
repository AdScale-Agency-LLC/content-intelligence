---
name: ci-client-add
description: "Neuen Klienten anlegen fuer Content-Intelligence. UNBEDINGT nutzen bei 'ci-client-add', 'neuen Klienten anlegen', 'Client erstellen', 'Klient hinzufuegen', oder wenn User explizit ein Klienten-Profil mit Branche/Zielgruppe/IG-Handle/Competitors anlegen will. Auto-Create wenn aehnlicher Name nicht existiert — sonst Warnung mit Vorschlag."
argument-hint: "<name> [--branche X] [--ig-handle @user] [--competitor @comp1]"
allowed-tools: Bash, Read
effort: low
user-invocable: true
---

# /ci-client-add — Klient anlegen

Erstellt ein neues Klienten-Profil mit Name, Branche, Zielgruppe, Tonalitaet, IG-Handle, Competitor-Liste.

## Felder

| Feld | Pflicht? | Beispiel |
|---|---|---|
| `name` | Ja | "CS Abbruch" |
| `--branche` | optional | "abbruch", "catering", "immobilien" |
| `--zielgruppe` | optional | "30-55, regional, B2B" |
| `--tonalitaet` | optional | "du/locker", "Sie/formal" |
| `--ig-handle` | optional | "@csabbruch" (ohne @ auch ok) |
| `--competitor` | optional, mehrfach | "@abbruch_berlin" |
| `--notes` | optional | freie Notiz |

## Wie ausfuehren

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/python/cmd_client.py" add "<NAME>" \
  [--branche "..."] [--zielgruppe "..."] [--tonalitaet "..."] \
  [--ig-handle "@..."] [--competitor "@..."] [--competitor "@..."] \
  [--notes "..."]
```

Beispiel:
```bash
python cmd_client.py add "CS Abbruch" \
  --branche abbruch \
  --zielgruppe "30-55, regional, B2B + B2C" \
  --ig-handle csabbruch \
  --competitor abbruch_berlin \
  --competitor rueckbau_pro \
  --tonalitaet "du/locker, direkt"
```

## Fuzzy-Duplicate Detection

Wenn der Skill einen aehnlichen existierenden Klienten findet (Jaccard-Token-Similarity ≥ 0.6), zeigt er eine Warnung:

```
Warning: similar clients found:
  - CS-Abbruch (similarity: 0.85)

If you meant one of those, use that name instead.
To create anyway, re-run with --yes or --force.
```

Exit-Code 2 wenn aehnliche da sind. **Du sollst den User fragen** ob er den existierenden meinte oder wirklich einen neuen will:

```
[zeige Liste der aehnlichen Klienten]
Meintest du einen davon, oder soll ich "<NEUER NAME>" wirklich neu anlegen?
```

Wenn User "neu anlegen" sagt: rerun mit `--yes` Flag.

## Auto-Create Verhalten

Wenn User nur `/ci-analyze <url> --client "Neuer Name"` macht und der Klient noch nicht existiert: das Plugin legt ihn **silent automatisch an** ohne Branche/Zielgruppe. Der User kann ihn spaeter mit `/ci-client-update` vervollstaendigen.

## Workflow-Tipp

Wenn User einen neuen Klienten anlegt, frage anschliessend ob du gleich:
- Sein eigenes IG-Profil (top 20 Reels) analysieren sollst: `/ci-batch @<own-handle> --client "<Name>" --is-own`
- Competitor-Profile analysieren: `/ci-batch @<comp> --client "<Name>"`

Das gibt dir sofort Daten fuer Audits + Skript-Generierung.

## Output

```
[ci-client-add] Created client: CS Abbruch
  Slug: cs-abbruch
  Branche: abbruch
  IG: @csabbruch
  Competitors: @abbruch_berlin, @rueckbau_pro

Next: /ci-analyze <url> --client "CS Abbruch"
```
