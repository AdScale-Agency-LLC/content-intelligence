# content-intelligence

**Agentur-grade Content-Intelligence-Plugin fuer Claude Code.**

Analysiert Instagram-Reels und TikTok-Videos mit Gemini 2.5 Flash, erkennt Trends, generiert produktionsreife Skripte basierend auf bewiesenen Top-Performer-Patterns. Multi-Client, lokal-first, Team-Sync optional via Supabase.

```
21 Skills · SQLite-first · Gemini 2.5 + Apify · Optional Supabase pgvector · ~0,4 ct/Reel
```

---

## Was es kann

| Use-Case | Skill |
|---|---|
| Ein Reel analysieren | `/ci-analyze <url>` |
| 20+ Reels von einem Account analysieren | `/ci-batch @username` |
| Klienten verwalten | `/ci-client-add`, `/ci-client-list`, `/ci-client-update` |
| Reels semantisch durchsuchen | `/ci-search "<query>"` |
| Hook-Library filtern | `/ci-hooks --hook-type X --min-score 70` |
| 2-5 Reels vergleichen | `/ci-compare <url1> <url2>` |
| Reel-Skript generieren | `/ci-script --client X --thema "..."` |
| Skript basierend auf Referenz-Reel | `/ci-script-from-ref --reference <url>` |
| Mehrere Skript-Varianten (A/B) | `/ci-script-batch --count 3` |
| Bestehendes Skript reviewen | `/ci-script-review --text "..."` |
| Trend-Report ueber Periode | `/ci-trends [--branche X]` |
| Viral-Outliers detecten | `/ci-viral` |
| Klienten-Audit + Empfehlungen | `/ci-audit --client X` |
| Strategie als Playbook speichern | `/ci-playbook --client X` |
| Weekly/Monthly Klienten-Report | `/ci-report --client X --period weekly` |
| Account dauerhaft tracken | `/ci-track add @user --client X` |
| Daten als CSV/JSON exportieren | `/ci-export --client X --format csv` |
| Dashboard | `/ci-status` |
| Setup | `/ci-setup --interactive` |

---

## Installation

### 1. Plugin installieren (Claude Code)

```bash
# Via Marketplace
claude plugin marketplace add AdScale-Agency-LLC/content-intelligence
claude plugin install content-intelligence@content-intelligence
```

Oder lokal aus dem Repo:
```bash
git clone https://github.com/AdScale-Agency-LLC/content-intelligence.git ~/.claude/plugins/content-intelligence
claude plugin marketplace add ~/.claude/plugins/content-intelligence
claude plugin install content-intelligence@content-intelligence
```

### 2. Python-Dependencies (einmalig)

```bash
python -m pip install --user \
    apify-client google-genai httpx pydantic pydantic-settings \
    aiofiles tenacity python-dotenv numpy
```

Optional fuer Team-Sync (Supabase):
```bash
python -m pip install --user asyncpg
```

### 3. API-Keys eintragen

In Claude Code einfach `/ci-setup` aufrufen — der Skill fragt interaktiv nach den Keys. Oder im Terminal:

```bash
python ~/.claude/plugins/content-intelligence/scripts/python/cmd_setup.py --interactive
```

Du brauchst zwei Keys:
- **Gemini API Key** — kostenlos: https://aistudio.google.com/apikey (Free-Tier reicht fuer ~50 Reels/Tag)
- **Apify API Token** — https://console.apify.com/account/integrations

Optional spaeter:
- Supabase-Keys fuer Team-Sharing (siehe [GETTING-STARTED.md](GETTING-STARTED.md))

### 4. Verifizieren

```bash
/ci-status
```

Sollte zeigen: `Gemini + Apify: READY`.

---

## Schnellstart-Workflow

```bash
# 1. Klienten anlegen
/ci-client-add "CS Abbruch" --branche abbruch --ig-handle csabbruch --competitor abbruch_berlin

# 2. Daten sammeln (ca. 10 Min fuer 20 Reels)
/ci-batch @csabbruch --last 20 --client "CS Abbruch" --is-own
/ci-batch @abbruch_berlin --last 20 --client "CS Abbruch"

# 3. Audit + Empfehlungen
/ci-audit --client "CS Abbruch"

# 4. Erstes Skript basierend auf den Daten
/ci-script --client "CS Abbruch" --thema "Asbest-Sanierung"

# 5. Klienten-Report fuer Weekly Review
/ci-report --client "CS Abbruch" --period weekly --save weekly-report.md
```

Details: siehe [GETTING-STARTED.md](GETTING-STARTED.md).

---

## Architektur

```
~/.claude/plugins/content-intelligence/
├── .claude-plugin/{plugin,marketplace}.json
├── skills/                    # 21 SKILL.md (Claude Code Skill Definitions)
├── scripts/python/
│   ├── config.py              # Pydantic Settings (.env-driven)
│   ├── clients/               # Gemini, Apify, Supabase, R2-Storage
│   ├── schemas/               # ReelAnalysis Pydantic Models
│   ├── pipeline/              # Scrape -> Download -> Analyze -> Embed -> Store
│   ├── db/
│   │   ├── local_db.py        # SQLite primary store (8 Tabellen)
│   │   ├── vector_search.py   # numpy brute-force cosine similarity
│   │   └── migration-001-init.sql  # optionale Supabase-Migration
│   ├── prompts/               # Gemini System-Prompts (Analyse + Skript)
│   ├── generators/            # script_gen, trend_agg, playbook_gen, report_gen
│   └── cmd_*.py               # 14 entry-points (einer pro Skill-Gruppe)
├── hooks/hooks.json           # SessionStart preflight
└── README.md
```

### Daten

- **API-Keys** → `~/.config/content-intel/.env` (chmod 600)
- **Lokale DB** → `~/.config/content-intel/ci.db` (SQLite, 8 Tabellen)
- **Optional shared DB** → Supabase (pgvector + 7 Tabellen via Migration)

### Vector-Suche

Embeddings als BLOB in SQLite gespeichert (1536 float32). Brute-force cosine via numpy:
- ≤ 5.000 Reels → <100ms
- ≤ 50.000 Reels → ~500ms
- ab da: Supabase pgvector HNSW (m=16, ef=64) empfohlen

---

## Multi-User / Team-Distribution

**Jeder User installiert mit eigenen API-Keys:**

1. Plugin installiert (siehe oben)
2. `/ci-setup --interactive` — eigene Keys eingeben
3. Daten landen erstmal lokal in der eigenen SQLite-DB

**Team-Sharing aktivieren** (alle User schreiben in dieselbe Supabase):
1. Supabase-Projekt aufsetzen (Plan dazu in [GETTING-STARTED.md](GETTING-STARTED.md))
2. Migration ausfuehren: `python cmd_supabase.py migrate`
3. Alle Team-Member tragen dieselben 3 Supabase-Keys in ihre eigene `.env`
4. Phase 6 `/ci-sync push` Skill (auf der Roadmap) macht den Sync

---

## Kosten

| Komponente | Kosten |
|---|---|
| Apify Scrape pro Reel | ~0,3 ct (instagram-reel-scraper) |
| Gemini 2.5 Flash Video-Analyse | ~0,1 ct (Free-Tier: 0 fuer ~50 Reels/Tag) |
| Embeddings (3 pro Reel) | vernachlaessigbar |
| Supabase Free-Tier | 0 EUR (pausiert nach 7d Inaktivitaet) |
| **Total pro Reel** | **~0,4 ct** |

Bei 100 Reels/Monat: ~40 ct. Bei 1.000 Reels/Monat: ~4 EUR.

---

## Roadmap

- [x] Phase 0-5: 21 Skills live, SQLite-first, Supabase ready
- [x] Production-Hardening: 10 P0/P1 Bugs gefixt
- [ ] Phase 6: `/ci-sync push` fuer Team-Synchronisation (SQLite → Supabase)
- [ ] Phase 7: Background-Cron fuer `/ci-track` (Windows Task Scheduler + n8n)
- [ ] Phase 8: YouTube-Shorts + Google-Maps-Local-Business Support

---

## License

MIT — siehe [LICENSE](LICENSE).

## Author

Nayl Badawi · AdScale Agency LLC
