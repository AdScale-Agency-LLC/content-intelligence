# Getting Started — content-intelligence

Komplettes Onboarding fuer neue Nutzer. Wenn du nur einen Reel analysieren willst → springe direkt zu [Schritt 4](#schritt-4--erstes-reel-analysieren).

---

## Schritt 1 — Installation

### Voraussetzungen
- **Claude Code** installiert (https://claude.com/claude-code)
- **Python 3.12+** (`python --version` muss `3.12.x` oder hoeher zeigen)
- **Git** (fuer den initialen Plugin-Pull)

### Plugin installieren

In Claude Code:
```
/plugin marketplace add nbadawi-hmd/content-intelligence
/plugin install content-intelligence@content-intelligence
```

Restart Claude Code damit alle 21 Skills sichtbar werden.

### Python-Dependencies

```bash
python -m pip install --user \
    apify-client google-genai httpx pydantic pydantic-settings \
    aiofiles tenacity python-dotenv numpy
```

Bei Errors: `python` durch `python3` ersetzen (Mac/Linux).

---

## Schritt 2 — API-Keys besorgen

### Gemini API Key (kostenlos)

1. Gehe zu https://aistudio.google.com/apikey
2. Login mit Google-Account
3. "Create API Key" → kopieren

**Free-Tier Limits:** 1500 Requests/Tag, 15 Requests/Minute. Reicht fuer ~50 Reels/Tag.

### Apify API Token

1. Account erstellen: https://console.apify.com/sign-up
2. **5 USD Free-Credit** beim Signup — reicht fuer ~1.500 Reel-Scrapes
3. https://console.apify.com/account/integrations → "Personal API Token" kopieren

---

## Schritt 3 — Setup

In Claude Code:
```
/ci-setup --interactive
```

Tippe deine zwei Keys ein wenn der Prompt erscheint. Sie werden in `~/.config/content-intel/.env` mit `chmod 600` gespeichert (owner-only).

Pruefe:
```
/ci-status
```

Sollte zeigen:
```
Configuration:
  Gemini + Apify:  READY
  TikTok actor:    CONFIGURED
```

---

## Schritt 4 — Erstes Reel analysieren

Probiere ein public Reel:
```
/ci-analyze https://www.instagram.com/reel/<SHORTCODE>/
```

Erste Analyse dauert **60-90 Sekunden** (Apify-Scrape ~30s + Gemini-Analyse ~60s).

Output:
```
Reel @account · 28s · de · IG
Posted: 2026-04-15 · Views: 12500  Likes: 850

HOOK [Score 78/100]
  Type: pattern_interrupt
  Visual: Person springt aus Schrank
  Text: "STOP! Bevor du das machst..."
  Why: Imperativ + Audio-Spike, bricht Scroll-Pattern

ANGLE: problem_solution
EMOTIONS: surprise (0-3s) -> curiosity (3-15s) -> urgency (15-28s)
CTA @ 25s: 'Kommentier INFO fuer den Plan' (explicit)
CUTS: 4.2 / 10s
COLORS: #1A1A1A #FFD700

SCORE
  Retention-Prediction: 72%
  Hook-Strength:        78/100
  Visual-Quality:       65/100
  CTA-Clarity:          80/100

TOP IMPROVEMENTS:
  1. Beat-Sync der Cuts unsauber bei 0:18
  2. Color-Palette inconsistent mit Brand-Farben
  3. Hook-Text zu lang fuer den 3s-Stopper

THEMES: finance, mindset, loss-aversion
TARGET: 25-40, money-anxiety, DE-Mainstream
```

---

## Schritt 5 — Klient anlegen + Bulk-Analyse

### Klient anlegen
```
/ci-client-add "Mein Klient" \
  --branche handwerk \
  --zielgruppe "30-55, regional, B2B+B2C" \
  --tonalitaet "du/locker, direkt" \
  --ig-handle meinklient \
  --competitor competitor1 \
  --competitor competitor2
```

### Bulk-Analyse: eigenes Profil
```
/ci-batch @meinklient --last 20 --client "Mein Klient" --is-own
```

(~10 Minuten fuer 20 Reels, parallel mit Concurrency 3)

### Bulk-Analyse: Competitors
```
/ci-batch @competitor1 --last 20 --client "Mein Klient"
/ci-batch @competitor2 --last 20 --client "Mein Klient"
```

---

## Schritt 6 — Audit + Skripte

### Performance-Audit
```
/ci-audit --client "Mein Klient"
```

Output: Benchmark eigene Reels vs. Competitor + Gap-Analyse + konkrete Empfehlungen.

### Skript generieren
```
/ci-script --client "Mein Klient" --thema "Asbest-Sanierung"
```

Der Skill zieht automatisch:
- Klienten-Profil (Tonalitaet, Do's/Don'ts)
- Top-Performer-Reels aus der DB
- Aktuelle Trends in der Nische

→ Output: Hook + Szenen-Breakdown + CTA + Score-Prediction.

### 3 Skript-Varianten fuer A/B
```
/ci-script-batch --client "Mein Klient" --thema "Asbest-Sanierung" --count 3
```

---

## Schritt 7 — Reports + Tracking

### Weekly Report
```
/ci-report --client "Mein Klient" --period weekly --save report.md
```

### Account dauerhaft tracken
```
/ci-track add @neuer_competitor --client "Mein Klient" --interval 24
/ci-track list
/ci-track run    # Manueller Scrape-Lauf
```

---

## Optional: Team-Sharing via Supabase

Wenn mehrere Personen das Plugin nutzen sollen und alle die selbe Datenbasis sehen wollen:

### 1. Supabase-Projekt anlegen
- https://supabase.com/dashboard/projects → "New Project"
- Name: `content-intelligence`
- Region: EU-Central oder EU-West
- Free-Tier reicht zum Anfang

### 2. Connection-String holen
- Project → Settings → "Connect"
- **Transaction pooler** waehlen (Port 6543, IPv4-compatible)
- Connection-String mit deinem Password ersetzen

### 3. API-Keys
- Settings → API → "Legacy anon, service_role keys"
- `anon` Key + `service_role` Key kopieren
- Settings → API → "URL"

### 4. In `.env` eintragen
```bash
python ~/.claude/plugins/content-intelligence/scripts/python/cmd_setup.py \
  --set-key SUPABASE_URL "https://xxxx.supabase.co"

python ~/.claude/plugins/content-intelligence/scripts/python/cmd_setup.py \
  --set-key SUPABASE_SERVICE_ROLE_KEY "eyJ..."

python ~/.claude/plugins/content-intelligence/scripts/python/cmd_setup.py \
  --set-key SUPABASE_DB_URL "postgresql://postgres.xxxx:password@..."
```

### 5. Migration anwenden
```bash
python -m pip install --user asyncpg
python ~/.claude/plugins/content-intelligence/scripts/python/cmd_supabase.py migrate
```

### 6. Verifizieren
```bash
python ~/.claude/plugins/content-intelligence/scripts/python/cmd_supabase.py status
```

Sollte 7 Tabellen zeigen (clients, reels, jobs, scripts, playbooks, tracked_accounts, embedding_versions).

**Hinweis:** Aktuell laufen alle Skills gegen die lokale SQLite-DB. Der Supabase-Sync-Skill (`/ci-sync push`) ist auf der Roadmap fuer Phase 6.

---

## Troubleshooting

### "Missing GEMINI_API_KEY"
→ `/ci-setup --interactive`

### "Apify run status=FAILED"
→ Reel ist privat oder geloescht. URL pruefen.

### "Gemini quota exceeded"
→ Free-Tier: 1500 RPD. Warte 24h ODER upgrade auf Paid-Tier.

### "database is locked"
→ Andere CI-Session laeuft parallel. Warten oder anderen Prozess killen.

### "Cannot extract shortcode from: ..."
→ URL hat ungewoehnliches Format. Direkter Reel-Link nutzen: `https://www.instagram.com/reel/ABC123/`

### Plugin updates
```
/plugin update content-intelligence@content-intelligence
```

---

## Tips

- **Erst Daten sammeln, dann Skripte generieren.** Mindestens 10 Reels in der DB fuer brauchbare Skript-Qualitaet. Ohne Daten = halluzinierte Output.
- **`--is-own` Flag** unbedingt setzen fuer eigene Reels — sonst sind Audit + Benchmarks falsch.
- **Klienten-Tonalitaet** im Profil eintragen. Skript-Engine respektiert Du vs. Sie.
- **TikTok URLs** funktionieren auch: `https://www.tiktok.com/@user/video/12345`
- **CSV-Export** fuer externe Reports: `/ci-export --client X --format csv --out report.csv`

---

## Hilfe

Issues / Feature-Requests: https://github.com/nbadawi-hmd/content-intelligence/issues
