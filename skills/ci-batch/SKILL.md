---
name: ci-batch
description: "Bulk-Analyse mehrerer Reels von einem Account ODER URL-Liste. UNBEDINGT nutzen bei 'ci-batch', 'analysier die letzten X Reels', 'bulk Reel-Analyse', 'analysier alle von @account', 'batch-analyze'. NICHT fuer einzelnes Reel (das ist /ci-analyze)."
argument-hint: "@username [--last 20] [--client \"Name\"] [--is-own]  ODER  --urls url1,url2"
allowed-tools: Bash, Read
effort: high
user-invocable: true
---

# /ci-batch — Bulk Reel-Analyse

Scrapt entweder die letzten N Reels eines IG-Accounts ODER eine Liste von URLs, analysiert sie parallel mit Gemini, speichert alles in der DB.

## Modes

**Mode A — Account-Scrape:** Erste N Reels eines Accounts holen + analysieren
```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/python/cmd_batch.py" @username --last 20 --client "Name" [--is-own]
```

**Mode B — URL-Liste:** Liste von URLs (kommagetrennt)
```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/python/cmd_batch.py" --urls "url1,url2,url3" --client "Name"
```

## Performance + Limits

- **Default-Concurrency: 3 parallel** (Gemini Rate-Limit: 15 RPM Free-Tier)
- **Max-Concurrency: 5** (`--concurrency 5`)
- **20 Reels = ~5-10 min** je nach Reel-Laenge
- **Idempotent:** Reels die schon in DB sind werden uebersprungen (`--skip-existing` default an)

## Workflow-Tipps

Wenn der User einen neuen Klienten angelegt hat, ist `/ci-batch` der **erste Schritt** um Daten zu sammeln:

```
/ci-batch @csabbruch --last 30 --client "CS Abbruch" --is-own
/ci-batch @abbruch_berlin --last 30 --client "CS Abbruch"     # Competitor
/ci-batch @rueckbau_pro --last 30 --client "CS Abbruch"       # Competitor
```

Nach diesen 3 Batches (~30 min) hast du ~90 Reels in der DB, von denen 30 dein eigene + 60 Competitor. Damit kannst du dann `/ci-audit --client "CS Abbruch"` und `/ci-trends` ausfuehren.

## Output

```
[ci-batch] Scraping @csabbruch (last 20 reels)...
[ci-batch] Found 18 reels from @csabbruch
[ci-batch] Processing 18 reels with concurrency=3
[ci-batch] >>> https://www.instagram.com/reel/ABC/
[ci-batch] >>> https://www.instagram.com/reel/DEF/
...

[ci-batch] Completed in 312.4s — 17 ok, 1 failed

Successful analyses:
  Account             Shortcode    Hook                  Score Angle
  @csabbruch          ABC123        problem               72   problem_solution
  @csabbruch          DEF456        demonstration         84   demonstration
  ...
```

## Failure-Modes

- **Apify Account-Scrape failed:** IG hat Bot-Detection getriggered → Apify-Run loggen, evtl. Residential-Proxies aktivieren (kostet extra)
- **Einzelnes Reel failed:** Liste zeigt am Ende welche, andere werden trotzdem gespeichert
- **Gemini-Quota:** Wenn 15 RPM ueberschritten — Skript wartet automatisch (tenacity exponential backoff)

## Self-Audit (Pflicht)

- [ ] Anzahl erfolgreich vs. fehlgeschlagen genannt
- [ ] Bei <50% Erfolg: Fehler-Liste mit User durchgehen, root cause kommunizieren
- [ ] Hook-Scores plausibel (Verteilung sollte nicht alle 50 oder alle 95 sein)
- [ ] User-Info: "diese Reels sind jetzt in der DB, du kannst /ci-search oder /ci-hooks nutzen"
