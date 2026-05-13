---
name: ci-search
description: "Semantische Suche ueber analysierte Reels per Embedding-Vergleich. UNBEDINGT nutzen bei 'ci-search', 'finde Reels die ueber X reden', 'suche aehnliche Reels', 'semantische Suche', 'Reels zum Thema Y'. NICHT fuer reine Filter ohne Bedeutung (das ist /ci-hooks)."
argument-hint: "<query> [--column hook_emb|transcript_emb|summary_emb] [--client X] [--min-hook-score 70]"
allowed-tools: Bash, Read
effort: medium
user-invocable: true
---

# /ci-search — Semantische Reel-Suche

Embedded die User-Query mit Gemini und macht Cosine-Similarity-Search gegen die 3 Embeddings (hook / transcript / summary) der gespeicherten Reels.

## Use-Cases

- "Finde Reels die ueber Preiserhoehung reden"
- "Aehnliche Hooks wie 'Du wirst nicht glauben was passiert'"
- "Welche Reels haben Vorher/Nachher-Transformation"
- "Suche nach urgency-Content"

## Wie ausfuehren

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/python/cmd_search.py" search "<query>" \
  [--column summary_emb|hook_emb|transcript_emb] \
  [--top-k 10] [--min-score 0.5] \
  [--client "Name"] [--hook-type pattern_interrupt] \
  [--angle problem_solution] [--min-hook-score 70] [--min-views 10000]
```

## Column-Auswahl

| Column | Wann |
|---|---|
| `summary_emb` (default) | "Reels die ueber X reden" — allgemeine Aehnlichkeit |
| `hook_emb` | "Aehnliche Hooks wie..." — Hook-Engineering |
| `transcript_emb` | Exakte gesprochene Phrasen finden |

## Output

```
Query: 'Preiserhoehung kommunizieren'  (column=summary_emb)
Top 5 results:

  Sim    Account              Shortcode      Hook                          Score  Summary
  -----  -------------------- -------------- ----------------------------- -----  -------
  0.82  @csabbruch            ABC123         "So sagst du Kunden Preise"   78    Verkaeufer erklaert wie...
  0.79  @bmw_dealer           XYZ789         "Wenn dein Kunde fragt..."    82    Showcase Preisanker...
```

## Wenn 0 Results

Pruefe ob DB ueberhaupt Reels enthaelt: `/ci-status`. Wenn ja, vorschlagen:
- Andere `--column` versuchen
- `--min-score 0.3` (lockerer)
- Query reformulieren

## Cost

Eine Query: ~0,01 ct (1 Embedding via Gemini). Quasi gratis.
