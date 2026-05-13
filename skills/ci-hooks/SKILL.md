---
name: ci-hooks
description: "Hook-Library durchsuchen mit Filtern (Type, Score, Klient). UNBEDINGT nutzen bei 'ci-hooks', 'Hook-Library', 'zeig mir die besten Hooks', 'pattern interrupt Hooks', 'beste Frage-Hooks', 'Hook-Inspiration'. NICHT fuer semantische Suche nach Thema (das ist /ci-search)."
argument-hint: "[--hook-type X] [--min-score 70] [--client \"Name\"] [--limit 20]"
allowed-tools: Bash, Read
effort: low
user-invocable: true
---

# /ci-hooks — Hook-Library Browser

Filtert die analysierten Reels nach Hook-Eigenschaften. Im Gegensatz zu `/ci-search` (semantisch) macht das hier strukturierte Filter-Queries.

## Filter-Optionen

| Filter | Werte | Beispiel |
|---|---|---|
| `--hook-type` | question, shock, pattern_interrupt, social_proof, problem, listicle, story, demonstration, transformation, other | `--hook-type pattern_interrupt` |
| `--min-score` | 0-100 | `--min-score 80` |
| `--client` | Klienten-Name | `--client "CS Abbruch"` |
| `--limit` | int | `--limit 50` |

## Wie ausfuehren

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/python/cmd_search.py" hooks \
  [--hook-type X] [--min-score N] [--client "Name"] [--limit 20]
```

## Use-Cases

**"Zeig mir die staerksten Pattern-Interrupt Hooks":**
```bash
python cmd_search.py hooks --hook-type pattern_interrupt --min-score 80
```

**"Beste Frage-Hooks der CS-Abbruch-Nische":**
```bash
python cmd_search.py hooks --hook-type question --min-score 70 --client "CS Abbruch"
```

**"Alle hochskorenden Hooks ueberhaupt":**
```bash
python cmd_search.py hooks --min-score 85 --limit 30
```

## Output

```
Hook Library — 12 matches
  Type:     pattern_interrupt
  Min Score: 80

  [ 92/100] @viralcreator              [pattern_interrupt]
           "Stop! Bevor du das machst, hoer mir 5 Sekunden zu"
           Why: Imperativ + Loss-Aversion-Frame, bricht Scroll-Pattern...
           ABC123 (views: 2400000)

  [ 88/100] @brand_xyz                 [pattern_interrupt]
           "Was wenn ich dir sage..."
           Why: Mystery + Direct-Address, baut Curiosity-Gap...
           DEF456 (views: 850000)
```

## Workflow-Tipp

Bevor du `/ci-script` aufrufst, lass User oft mit `/ci-hooks` die Top-Performer der Nische anschauen — gibt ihm Gefuehl was funktioniert.
