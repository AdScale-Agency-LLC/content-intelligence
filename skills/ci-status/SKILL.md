---
name: ci-status
description: "Content-Intelligence Plugin Dashboard. UNBEDINGT nutzen bei 'ci-status', 'CI Status', 'wie viele Reels', 'wie viele Klienten', 'Plugin Dashboard', 'Content-Intelligence Uebersicht'. Zeigt Klienten-Liste, Reel-Count, API-Usage, Queue-Health, Config-Status. NICHT fuer einzelne Reel-Analyse."
argument-hint: "[--json]"
allowed-tools: Bash, Read
effort: low
user-invocable: true
---

# /ci-status — Plugin Dashboard

Schneller Overview des Content-Intelligence Plugin-Zustands.

## Was es zeigt

1. **Config-Status**: Gemini/Apify/Supabase/TikTok/R2 konfiguriert?
2. **Supabase-Stats**: Reels total + last 7d, Clients total, Queue (queued/failed), Tracked Accounts
3. **Top-10 Klienten** nach kuerzlicher Aktivitaet, mit Reel-Count
4. **Local Cache**: Invocations, recent clients (fuer Tab-Completion)
5. **User Identity**: Welcher User-Name wird als `created_by` gespeichert

## Wie aufrufen

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/python/cmd_status.py"
```

Optionen:
- `--json` — Maschinen-lesbare JSON-Ausgabe (fuer Weiterverarbeitung)
- `--preflight` — Silent check, exit 0/1 (wird von SessionStart-Hook genutzt)

## Output-Beispiel

```
Content Intelligence Plugin — Status
  User: nayl

Configuration:
  Gemini + Apify:  READY
  Supabase:        READY
  TikTok actor:    NOT YET (Phase 1)
  R2 storage:      NOT YET (Phase 5)

Supabase DB:
  Reels total:       147
  Reels last 7 days: 23
  Clients total:     8
  Jobs queued:       0
  Jobs failed:       2
  Tracked accounts:  3

Clients (top 10 by recent activity):
  - CS Abbruch                    [abbruch        ] reels: 35
  - Trautmann                     [catering       ] reels: 22
  - Immoverse                     [immobilien     ] reels: 18
  ...

Local cache:
  Invocations total:  142
  Invocations failed: 3
  Recent clients:     8
```

## Wenn Probleme

Wenn Config nicht ready:
- "Gemini + Apify: NOT CONFIGURED" → User soll `/ci-setup` ausfuehren
- "Supabase: ERROR" → Supabase-DB schlaeft (Free-Tier) oder DB-URL falsch
- "Jobs failed: >0" → User soll `/ci-job-retry` aufrufen (Phase 5) oder Logs pruefen

## Workflow-Ende

Wenn alles OK, einfach das Dashboard zeigen und fragen ob der User einen Skill ausfuehren will (z.B. `/ci-analyze <url>` fuer ein einzelnes Reel).

Wenn Dinge fehlen, klare Action-Items: "X fehlt, fix mit Y".
