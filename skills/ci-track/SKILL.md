---
name: ci-track
description: "Account-Tracking fuer kontinuierliche Reel-Analyse. UNBEDINGT nutzen bei 'ci-track', 'track diesen Account', 'beobachte @competitor', 'Account dauerhaft tracken', 'Auto-Scrape Setup', 'kontinuierlich beobachten'. NICHT fuer einmalige Batch-Analyse (das ist /ci-batch)."
argument-hint: "<add|list|run|remove> [@handle] [--client Name] [--interval 24]"
allowed-tools: Bash, Read
effort: medium
user-invocable: true
---

# /ci-track — Account-Monitoring

Markiert IG/TikTok-Accounts fuer kontinuierliches Tracking. Beim manuellen `run` werden alle "due" Accounts re-scrapt + neue Reels analysiert.

**Automatisches Background-Cron:** Phase 6+ via n8n-Workflow oder Windows-Task-Scheduler. Aktuell: `/ci-track run` manuell aufrufen.

## Sub-Commands

### add — Account zum Tracking hinzufuegen
```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/python/cmd_track.py" add @username \
  --client "<Name>" [--source ig|tiktok] [--is-own] [--interval 24]
```

### list — Tracked Accounts anzeigen
```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/python/cmd_track.py" list [--client "Name"]
```

### run — Manueller Scrape-Lauf
```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/python/cmd_track.py" run [--client "Name"] [--last 10] [--force]
```
- Default: scrapet nur Accounts deren `last_scraped + interval_hours < now`
- `--force`: ignoriert Interval, scrapet alle
- `--last 10`: scrapet top 10 Reels pro Account (neue werden analysiert, alte ignoriert)

### remove — Tracking entfernen
```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/python/cmd_track.py" remove @username
```

## Use-Cases

**Setup fuer einen neuen Klienten:**
```
/ci-track add @csabbruch --client "CS Abbruch" --is-own --interval 24
/ci-track add @abbruch_berlin --client "CS Abbruch" --interval 24
/ci-track add @rueckbau_pro --client "CS Abbruch" --interval 24
```

**Manueller Lauf am Montagmorgen:**
```
/ci-track run
```
Scrapet alle Accounts die >24h nicht gescraped wurden, analysiert neue Reels.

## Cost-Awareness

Wenn du 10 Accounts trackst à 10 neue Reels/Woche = 100 Reels/Woche = ~30 ct Apify + ~10 ct Gemini = ~40 ct/Woche. Wenn du auf 100+ Accounts gehst, plane Pro-Tier.
