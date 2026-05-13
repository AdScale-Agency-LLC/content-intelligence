---
name: ci-analyze
description: "Instagram Reel oder TikTok-Video analysieren mit Gemini 2.5 Flash. UNBEDINGT nutzen bei 'ci-analyze', 'analysier das Reel', 'schau dir den Hook an', 'TikTok analysieren', 'Content-Analyse', 'Hook-Analyse', oder wenn User Instagram-Reel-URL / TikTok-URL postet mit Analyse-Wunsch. Strukturierter Output: Hook (Type + Score), Angle, Emotion-Timeline, CTA, Color-Palette, Cuts/10s, Top-3-Improvements, Retention-Prediction, Transcript. Speichert in lokaler DB mit Klienten-Zuordnung. NICHT fuer mehrere Reels gleichzeitig (das ist /ci-batch)."
argument-hint: "<reel-url> [--client \"Name\"] [--is-own]"
allowed-tools: Bash, Read
effort: medium
user-invocable: true
---

# /ci-analyze — Strukturierte Reel-/TikTok-Analyse

Du analysierst ein einzelnes IG-Reel oder TikTok-Video. Pipeline: Apify scrape → MP4 download → Gemini File API → Pydantic-strukturierte Analyse → Embeddings → SQLite-DB.

## Step 1 — Input parsen

User-Input enthaelt:
- URL (zwingend): IG-Reel (`instagram.com/reel/...` oder `/p/...`) oder TikTok (`tiktok.com/@user/video/...`)
- Optional `--client "Klientenname"`: ordnet das Reel einem Klienten zu (auto-created wenn neu)
- Optional `--is-own`: markiert als eigenes Content (statt Competitor)

Wenn User nur eine URL postet ohne explicit `--client`, frag NICHT zurueck — analysiere unzugeordnet. Der User kann spaeter zuordnen.

Wenn User Klienten nennt aber keinen `--is-own` Flag setzt: standardmaessig als Competitor behandeln (es sei denn der Kontext sagt klar "unser Reel").

## Step 2 — Preflight

Erstaufruf jeder Session:
```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/python/cmd_setup.py" --check
```

Exit-Codes:
- `0` — ready, fortfahren ohne Output
- `2` — Python-Deps fehlen → User informieren, `python -m pip install --user ...` Hinweis
- `3` — Pflicht-Keys fehlen → User soll `/ci-setup` ausfuehren

## Step 3 — Analyse ausfuehren

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/python/cmd_analyze.py" "<url>" [--client "Name"] [--is-own] [--output pretty]
```

Default-Verhalten:
- Apify-Scrape (~30s)
- MP4-Download in temp dir
- Gemini File API + Analyse (~60-90s)
- Embeddings (~5s)
- Speicherung in SQLite (`~/.config/content-intel/ci.db`)
- MP4 wird geloescht
- Output: formatierter Reel-Report

Wenn Reel schon analysiert wurde (idempotent): zeigt existierende Daten ohne Re-Analyse. Mit `--force` neu analysieren.

## Step 4 — Output formatieren

Das Skript gibt bereits formatierten Text. **Du musst nichts uebersetzen oder umformulieren** — den Output 1:1 an den User zeigen.

Wenn der User eine **zusaetzliche Frage** stellte (z.B. "warum funktioniert der Hook?"), beantworte sie danach mit Bezug auf konkrete Felder aus der Analyse — zitiere Hook-Reasoning, Score, Improvements.

## Beispiele

```
User: analysier das mal https://instagram.com/reel/ABC123 fuer CS Abbruch
```
→ `python cmd_analyze.py https://instagram.com/reel/ABC123 --client "CS Abbruch"`

```
User: schau dir https://www.tiktok.com/@user/video/9876 an, ist das ein guter Hook?
```
→ `python cmd_analyze.py https://www.tiktok.com/@user/video/9876`
→ Output zeigen + Hook-Score + Reasoning kommentieren

```
User: ist das unser eigenes Reel: https://instagram.com/reel/XYZ — Klient Trautmann
```
→ `python cmd_analyze.py https://instagram.com/reel/XYZ --client Trautmann --is-own`

## Failure-Modes

- **Apify fail (Reel privat/geloescht):** Sage User direkt, schlage URL-Check vor. Kein Retry.
- **Gemini Quota:** Free-Tier ist 1500 RPD / 15 RPM. Bei Quota-Fail: "Quota erreicht, warte X Min ODER upgrade auf Paid".
- **MP4 download timeout:** IG-CDN flapped. Skript retryt nicht aggressiv — User informieren mit klarer Message.
- **Schema-Validation fail:** Sehr selten. Log raw response, "Gemini hat unsauberen Output, retry mit --force".

## Cost (Awareness)

- Apify Scrape: ~0,3 ct
- Gemini 2.5 Flash Video-Analyse: ~0,1 ct (Free-Tier: 0)
- Embeddings: vernachlaessigbar
- **Total: ~0,4 ct pro Reel** (oder 0 im Free-Tier)

## Self-Audit (Pflicht vor Lieferung)

- [ ] Skript hat exit 0 zurueckgegeben (keine roten Errors)
- [ ] Hook-Score plausibel (50-90 Range, nicht 100, nicht <10)
- [ ] Improvements sind konkret, nicht generisch ("besserer Hook" waere ein Fail-Indikator)
- [ ] Wenn Klient gegeben: client_id ist gesetzt
- [ ] Output rendert auf Deutsch lesbar
