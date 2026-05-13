---
name: ci-script-batch
description: "Mehrere Skript-Varianten zum gleichen Thema generieren (A/B-Testing-ready). UNBEDINGT nutzen bei 'ci-script-batch', 'gib mir 3 Skript-Varianten', 'A/B Skripte', 'mehrere Hook-Optionen', 'verschiedene Skript-Versionen'. NICHT fuer einzelnes Skript (/ci-script)."
argument-hint: "--client \"Name\" --thema \"<topic>\" --count 3"
allowed-tools: Bash, Read
effort: high
user-invocable: true
---

# /ci-script-batch — Mehrere Skript-Varianten

Generiert N (2-5) Skript-Varianten zum gleichen Thema, jeweils mit unterschiedlichen Hook-Types. Sortiert nach Score-Prediction.

## Wie ausfuehren

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/python/cmd_script.py" batch \
  --client "<Name>" \
  --thema "<Topic>" \
  --count 3 \
  [--dry-run]
```

Default: 3 Varianten. Maximum: 5.

## Hook-Type Rotation

Varianten 1-5 nutzen jeweils:
1. pattern_interrupt
2. question
3. problem
4. shock
5. demonstration

Pro Variante steigt die Temperature leicht (0.5 → 0.9) fuer mehr Diversitaet.

## Output

```
# 3 Skript-Varianten fuer 'Asbest-Sanierung' — CS Abbruch

## Score-Ranking
1. **pattern_interrupt** — Score 82/100 (ID: abc...)
2. **problem**          — Score 76/100 (ID: def...)
3. **question**         — Score 71/100 (ID: ghi...)

---

[Variante 1 full markdown]

---

[Variante 2 full markdown]

---

[Variante 3 full markdown]
```

## Workflow-Tipp

Nutze das wenn:
- Klient nicht weiss welche Richtung er einschlagen soll
- A/B-Test geplant ist (2 Versionen drehen, beide posten, sehen welche performt)
- Du Optionen brauchst um zu praesentieren

Alle Varianten werden in der DB als separate `scripts` Eintraege gespeichert mit Status `draft`. Der User kann spaeter den Winner mit `--status approved` markieren.
