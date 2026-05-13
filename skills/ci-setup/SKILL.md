---
name: ci-setup
description: "Content-Intelligence Plugin einrichten. UNBEDINGT nutzen bei 'ci-setup', 'plugin einrichten', 'API-Keys setzen', 'Supabase verbinden', 'Content-Intelligence konfigurieren', 'Reel-Analyse Setup'. Prueft Python-Dependencies, fragt nach API-Keys (Gemini, Apify, Supabase), wendet DB-Migration an. NICHT fuer einzelne Reels analysieren (das ist /ci-analyze)."
argument-hint: "[--test-supabase | --apply-migration | --print-migration]"
allowed-tools: Bash, Read, Write, AskUserQuestion
effort: medium
user-invocable: true
---

# /ci-setup — Plugin Setup + Key Management + DB Migration

Erstkonfiguration und Health-Check fuer das content-intelligence Plugin. Wird beim ersten Aufruf jedes `/ci-*` Skills implizit ausgefuehrt (Preflight-Check), kann aber auch direkt aufgerufen werden.

## Was es macht

1. Prueft Python-Dependencies (apify-client, google-genai, httpx, pydantic, asyncpg, ...)
2. Scaffoldet `~/.config/content-intel/.env` mit Placeholder-Werten (chmod 600)
3. Initialisiert lokale SQLite-DB unter `~/.config/content-intel/ci.db`
4. Prueft API-Keys: Gemini, Apify, Supabase
5. Testet Supabase-Verbindung
6. Prueft welche DB-Tabellen vorhanden sind, kann Migration anwenden

## Wann ausfuehren

- **Einmalig pro Maschine** beim ersten Plugin-Einsatz
- **Bei jedem neuen Team-Member** der das Plugin installiert
- **Wenn `/ci-status` Probleme meldet**
- Nach Plugin-Updates die Migrations einfuehren

## Default-Flow (kein Argument)

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/python/cmd_setup.py"
```

Gibt Human-Readable-Status aus. Exit-Code:
- `0` — alles ready
- `2` — Python-Deps fehlen
- `3` — Pflicht-Keys fehlen (Gemini/Apify)
- `4` — Supabase nicht erreichbar
- `5` — DB-Schema unvollstaendig

## Workflow bei fehlenden Keys

Wenn das Skript Exit-Code 3 oder Hinweis auf fehlende Keys gibt:

**Step 1 — User nach Keys fragen** via `AskUserQuestion` mit Optionen:
- "Ich habe alle Keys (Gemini + Apify + Supabase)"
- "Nur Gemini + Apify (Supabase spaeter)"
- "Wo bekomme ich die Keys?"

**Step 2 — Bei "Wo bekomme ich":** Erklaere die URLs:
- Gemini: https://aistudio.google.com/apikey (kostenlos, Free-Tier reicht fuer Tests)
- Apify: https://console.apify.com/account/integrations
- Supabase: Bestehende AdScale-Pro-Instanz ODER neue kostenlose Instanz unter https://supabase.com/dashboard/projects → "New Project". Brauchen 3 Werte aus Project Settings:
  - URL: Settings > API > Project URL
  - Service Role Key: Settings > API > service_role secret
  - DB URL: Settings > Database > Connection String (URI Format)

**Step 3 — Keys einzeln setzen:**

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/python/cmd_setup.py" --set-key GEMINI_API_KEY "AIzaSy..."
python "${CLAUDE_PLUGIN_ROOT}/scripts/python/cmd_setup.py" --set-key APIFY_API_TOKEN "apify_api_..."
python "${CLAUDE_PLUGIN_ROOT}/scripts/python/cmd_setup.py" --set-key SUPABASE_URL "https://xxxx.supabase.co"
python "${CLAUDE_PLUGIN_ROOT}/scripts/python/cmd_setup.py" --set-key SUPABASE_SERVICE_ROLE_KEY "eyJ..."
python "${CLAUDE_PLUGIN_ROOT}/scripts/python/cmd_setup.py" --set-key SUPABASE_DB_URL "postgresql://..."
```

Niemals Keys im Chat-Verlauf hardcoden — immer ueber `--set-key` setzen, der schreibt in die geschuetzte `.env` Datei.

**Step 4 — Supabase-Verbindung testen:**

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/python/cmd_setup.py" --test-supabase
```

**Step 5 — DB-Migration anwenden:**

Wenn Supabase erreichbar aber Tabellen fehlen:

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/python/cmd_setup.py" --apply-migration
```

ODER manuell ueber Supabase SQL Editor:

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/python/cmd_setup.py" --print-migration
```

Output kopieren und in Supabase SQL-Editor einfuegen + ausfuehren.

## Python-Deps installieren

Wenn Exit-Code 2:

```bash
python -m pip install --user apify-client google-genai httpx pydantic pydantic-settings asyncpg aiofiles tenacity python-dotenv
```

## Wenn alles erledigt

Output zeigt:
```
CORE READY (Gemini + Apify configured)
  Supabase: OK — Supabase reachable
  Schema:   OK — all tables present
```

Dann kann der User mit `/ci-analyze <url>` oder `/ci-status` weitermachen.

## Failure-Handling

- **Python-Deps install schlaegt fehl:** Pruefe Python-Version (>=3.12 noetig). User dazu auffordern.
- **Supabase Connection-Refused:** DB-URL falsch oder Projekt schlaeft (Free-Tier pausiert nach Inaktivitaet — Supabase-Dashboard oeffnen und Projekt aufwecken)
- **Migration-Error:** SQL-Output mit `--print-migration` an User, manuell im SQL-Editor ausfuehren

## Security

- API-Keys leben in `~/.config/content-intel/.env` mit chmod 600 (owner-only)
- Plugin schreibt KEINE Keys in stdout/stderr/logs
- SQLite-Cache enthaelt keine Keys, nur User-Preferences + Audit-Log
