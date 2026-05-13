---
name: ci-compare
description: "2-5 Reels side-by-side vergleichen (Hook, Score, ER, etc.). UNBEDINGT nutzen bei 'ci-compare', 'vergleich diese Reels', 'welcher Hook ist staerker', 'A vs B Reel', 'side-by-side analyse'. NICHT fuer einzelnes Reel (/ci-analyze) oder Search (/ci-search)."
argument-hint: "<url-or-shortcode-1> <url-or-shortcode-2> [...]"
allowed-tools: Bash, Read
effort: medium
user-invocable: true
---

# /ci-compare — Side-by-Side Reel-Vergleich

Zeigt 2-5 Reels nebeneinander mit allen Score-Metriken + Winner-Empfehlung. Reels die noch nicht in der DB sind werden on-the-fly analysiert.

## Wie ausfuehren

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/python/cmd_compare.py" \
  <url-or-shortcode-1> <url-or-shortcode-2> [...] \
  [--client "Name"]
```

Eingabe-Formate:
- Volle URL: `https://www.instagram.com/reel/ABC123/`
- Nur Shortcode: `ABC123` (nur wenn bereits in DB)

Bis zu 5 Reels werden parallel geladen/analysiert.

## Output

```
Comparing 3 reels:

  Metric         Reel 1                Reel 2                Reel 3
  -------------  --------------------- --------------------- ---------------------
  Account        @csabbruch            @abbruch_berlin       @rueckbau_pro
  Shortcode      ABC123                XYZ789                DEF456
  Duration       28s                   34s                   22s
  Views          12500                 89000                 245000
  Hook Type      problem               pattern_interrupt     demonstration
  Hook Score     68/100                85/100                78/100
  Angle          problem_solution      story                 demonstration
  Retention      52%                   72%                   68%

HOOKS:
  Reel 1: [68/100] 'Asbestbeseitigung ist teuer, aber...'
           Why: Problem-Frame solide aber kein Stopper, Audio-Spike fehlt
  Reel 2: [85/100] 'STOP! Mach das niemals selbst'
           Why: Imperativ + Audio-Spike + Loss-Aversion — sehr starker Stopper
  Reel 3: [78/100] (visual: Wand wird mit Bagger zerbrochen, Zeitlupe)
           Why: Visuelle Demonstration + Dust-Cloud — viraler Stopper

WINNER (Hook Score): Reel 2 @abbruch_berlin — 85/100
```

## Use-Cases

- **Eigenes vs. Competitor:** `/ci-compare <our-reel> <comp-reel>`
- **A/B-Variant-Check:** Zwei Versionen desselben Reels (verschiedene Hooks) vergleichen
- **Best-of-Nische:** Top 3 Reels einer Nische gegenuebersgen
- **Vorher/Nachher:** Wir haben Reel umgepostet — laeuft die neue Version besser?
