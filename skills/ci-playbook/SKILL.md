---
name: ci-playbook
description: "Content-Playbook fuer einen Klienten persistieren (Top-Hooks, Posting-Freq, Empfehlungen). UNBEDINGT nutzen bei 'ci-playbook', 'Playbook erstellen', 'Content-Strategie fuer', 'speicher die Strategie', 'mach mir einen Spielplan'. NICHT fuer Audit (das ist /ci-audit, ohne Speichern)."
argument-hint: "--client \"Name\" [--valid-days 30]"
allowed-tools: Bash, Read
effort: medium
user-invocable: true
---

# /ci-playbook — Klienten-Playbook

Aehnlich zu `/ci-audit`, aber **persistiert** das Ergebnis in der DB als wieder-abrufbares Strategy-Dokument. Pro Klient kann es mehrere Playbooks geben (alle 30 Tage neu generieren empfohlen).

## Wie ausfuehren

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/python/cmd_playbook.py" \
  --client "<Name>" [--valid-days 30] [--dry-run]
```

## Was es speichert

In der `playbooks` Tabelle:
- `top_hooks`: Hook-Type-Stats (eigene + Competitor)
- `top_angles`: Angle-Stats
- `posting_freq`: aktuelle Posting-Frequenz-Klassifikation
- `benchmark`: vollstaendige Score-Tabelle
- `empfehlungen`: Liste konkrete Action-Items
- `valid_until`: bis wann das Playbook aktuell ist (default +30d)

## Output

Gleich wie `/ci-audit`, aber mit Playbook-ID am Ende:

```
---
Playbook ID: a3f7b2c1d4e5f6a7  (valid 30d)
```

## Use-Cases

- **Klienten-Onboarding:** Sobald 10+ Reels vom Klienten analysiert sind, einmaliges Playbook erstellen
- **Quarterly Refresh:** Alle 30 Tage neu generieren (Strategie aendert sich mit neuen Daten)
- **Klienten-Deliverable:** Markdown-Output als PDF exportieren und an Klient schicken
