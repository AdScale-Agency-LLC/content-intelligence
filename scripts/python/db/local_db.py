"""Local SQLite — primary store for the content-intelligence plugin.

Schema:
  - clients            : Agency client profiles (name, branche, IG-handle, competitors)
  - reels              : Analyzed reels (flattened ReelAnalysis + embeddings as BLOB)
  - scripts            : Generated reel scripts per client
  - playbooks          : Per-client content strategy
  - tracked_accounts   : Accounts to monitor automatically
  - jobs               : Pipeline job tracking (analyze queue)
  - prefs              : User preferences
  - invocations        : Audit log of skill invocations

Vector embeddings are stored as numpy-serialized BLOBs (1536 float32 = 6144 bytes).
Search via brute-force cosine similarity (numpy) — fast enough up to ~10k reels.

DB path: ~/.config/content-intel/ci.db
"""

from __future__ import annotations

import json
import sqlite3
import struct
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from config import LOCAL_DB_FILE, ensure_config_dir

SCHEMA_VERSION = 2

_SCHEMA = """
-- ---------- Meta ----------
CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- ---------- Clients ----------
CREATE TABLE IF NOT EXISTS clients (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    slug TEXT NOT NULL UNIQUE,
    branche TEXT,
    zielgruppe TEXT,
    tonalitaet TEXT,
    dos TEXT NOT NULL DEFAULT '[]',
    donts TEXT NOT NULL DEFAULT '[]',
    ig_handle TEXT,
    competitor_handles TEXT NOT NULL DEFAULT '[]',
    notes TEXT,
    created_by TEXT,
    created_at REAL NOT NULL DEFAULT (strftime('%s','now')),
    updated_at REAL NOT NULL DEFAULT (strftime('%s','now'))
);
CREATE INDEX IF NOT EXISTS idx_clients_slug ON clients(slug);
CREATE INDEX IF NOT EXISTS idx_clients_branche ON clients(branche);

-- ---------- Reels ----------
CREATE TABLE IF NOT EXISTS reels (
    id TEXT PRIMARY KEY,
    shortcode TEXT NOT NULL UNIQUE,
    source TEXT NOT NULL DEFAULT 'ig',
    url TEXT NOT NULL,

    -- Client linkage
    client_id TEXT REFERENCES clients(slug) ON DELETE SET NULL,
    is_own INTEGER NOT NULL DEFAULT 0,
    created_by TEXT,

    -- Account
    account TEXT NOT NULL,
    account_followers INTEGER,
    posted_at TEXT,
    scraped_at REAL NOT NULL DEFAULT (strftime('%s','now')),
    analyzed_at REAL NOT NULL DEFAULT (strftime('%s','now')),

    -- Engagement
    views INTEGER,
    likes INTEGER,
    comments INTEGER,
    saves INTEGER,
    shares INTEGER,
    engagement_rate REAL,

    -- Content
    caption TEXT,
    hashtags TEXT,                       -- JSON array
    mentions TEXT,                       -- JSON array
    audio_id TEXT,
    audio_title TEXT,
    audio_artist TEXT,

    -- Video
    duration_s INTEGER,
    video_url_cdn TEXT,

    -- Analysis (flat)
    language TEXT NOT NULL,
    summary TEXT NOT NULL,
    angle TEXT NOT NULL,
    content_themes TEXT NOT NULL DEFAULT '[]',
    target_audience_hint TEXT,

    hook_type TEXT NOT NULL,
    hook_text TEXT,
    hook_visual TEXT NOT NULL,
    hook_score INTEGER NOT NULL,
    hook_reasoning TEXT NOT NULL,

    -- Transcript
    transcript_full TEXT NOT NULL,
    transcript_segments TEXT NOT NULL DEFAULT '[]',

    -- JSONB equivalents
    visual_patterns TEXT NOT NULL DEFAULT '{}',
    text_overlays TEXT NOT NULL DEFAULT '[]',
    emotions TEXT NOT NULL DEFAULT '[]',
    color_palette TEXT NOT NULL DEFAULT '{}',
    cta_elements TEXT NOT NULL DEFAULT '[]',
    scene_changes_s TEXT NOT NULL DEFAULT '[]',
    music_sync_events_s TEXT NOT NULL DEFAULT '[]',

    -- Scores
    score_retention INTEGER,
    score_hook INTEGER,
    score_visual INTEGER,
    score_cta INTEGER,
    score_improvements TEXT NOT NULL DEFAULT '[]',

    -- Raw full Pydantic dump
    raw_analysis TEXT NOT NULL,

    -- Embeddings (binary: 1536 float32 = 6144 bytes each)
    transcript_emb BLOB,
    hook_emb BLOB,
    summary_emb BLOB,

    -- Soft-delete
    deleted_at REAL
);
CREATE INDEX IF NOT EXISTS idx_reels_client ON reels(client_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_reels_client_own ON reels(client_id, is_own) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_reels_account ON reels(account) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_reels_angle ON reels(angle) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_reels_hook_type ON reels(hook_type, hook_score) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_reels_posted ON reels(posted_at DESC) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_reels_analyzed ON reels(analyzed_at DESC) WHERE deleted_at IS NULL;

-- ---------- Scripts ----------
CREATE TABLE IF NOT EXISTS scripts (
    id TEXT PRIMARY KEY,
    client_id TEXT NOT NULL REFERENCES clients(slug) ON DELETE CASCADE,
    thema TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','approved','posted','archived')),

    hook_text TEXT,
    hook_type TEXT,
    angle TEXT,
    szenen TEXT NOT NULL DEFAULT '[]',     -- JSON array of scene objects
    cta TEXT,
    laenge_s INTEGER,
    full_script TEXT,                       -- Markdown rendering

    referenz_reels TEXT NOT NULL DEFAULT '[]',  -- JSON array of shortcodes
    trend_basis TEXT,
    score_prediction INTEGER,

    posted_shortcode TEXT,
    performance TEXT,                       -- JSON: nach posting

    created_by TEXT,
    created_at REAL NOT NULL DEFAULT (strftime('%s','now')),
    updated_at REAL NOT NULL DEFAULT (strftime('%s','now'))
);
CREATE INDEX IF NOT EXISTS idx_scripts_client ON scripts(client_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_scripts_status ON scripts(status);

-- ---------- Playbooks ----------
CREATE TABLE IF NOT EXISTS playbooks (
    id TEXT PRIMARY KEY,
    client_id TEXT NOT NULL REFERENCES clients(slug) ON DELETE CASCADE,
    top_hooks TEXT NOT NULL DEFAULT '[]',
    top_angles TEXT NOT NULL DEFAULT '[]',
    posting_freq TEXT,
    benchmark TEXT NOT NULL DEFAULT '{}',
    empfehlungen TEXT NOT NULL DEFAULT '[]',
    generated_at REAL NOT NULL DEFAULT (strftime('%s','now')),
    valid_until REAL,
    created_by TEXT
);
CREATE INDEX IF NOT EXISTS idx_playbooks_client ON playbooks(client_id, generated_at DESC);

-- ---------- Tracked Accounts ----------
CREATE TABLE IF NOT EXISTS tracked_accounts (
    id TEXT PRIMARY KEY,
    client_id TEXT NOT NULL REFERENCES clients(slug) ON DELETE CASCADE,
    handle TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'ig',
    is_own INTEGER NOT NULL DEFAULT 0,
    last_scraped REAL,
    reel_count INTEGER NOT NULL DEFAULT 0,
    interval_hours INTEGER NOT NULL DEFAULT 24,
    active INTEGER NOT NULL DEFAULT 1,
    created_by TEXT,
    created_at REAL NOT NULL DEFAULT (strftime('%s','now')),
    UNIQUE(client_id, handle, source)
);
CREATE INDEX IF NOT EXISTS idx_tracked_active ON tracked_accounts(active, last_scraped);

-- ---------- Jobs (pipeline queue) ----------
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    shortcode TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'ig',
    client_id TEXT,
    status TEXT NOT NULL DEFAULT 'queued',
    priority INTEGER NOT NULL DEFAULT 10,
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    enqueued_at REAL NOT NULL DEFAULT (strftime('%s','now')),
    started_at REAL,
    finished_at REAL,
    metadata TEXT NOT NULL DEFAULT '{}',
    UNIQUE(source, shortcode)
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status, priority, enqueued_at);

-- ---------- Prefs ----------
CREATE TABLE IF NOT EXISTS prefs (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at REAL NOT NULL DEFAULT (strftime('%s','now'))
);

-- ---------- Audit Log ----------
CREATE TABLE IF NOT EXISTS invocations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    skill TEXT NOT NULL,
    args TEXT,
    status TEXT NOT NULL,
    error TEXT,
    duration_ms INTEGER,
    ts REAL NOT NULL DEFAULT (strftime('%s','now'))
);
CREATE INDEX IF NOT EXISTS idx_invocations_ts ON invocations(ts DESC);
"""


# ============================================================
# Embedding serialization (1536 float32 = 6144 bytes)
# ============================================================


def embedding_to_blob(vec: list[float] | None) -> bytes | None:
    """Pack a float-list into a BLOB. None → None."""
    if vec is None:
        return None
    return struct.pack(f"{len(vec)}f", *vec)


def blob_to_embedding(blob: bytes | None) -> list[float] | None:
    """Unpack a BLOB back to a float-list. None → None."""
    if blob is None or len(blob) == 0:
        return None
    n = len(blob) // 4
    return list(struct.unpack(f"{n}f", blob))


# ============================================================
# Slug generation
# ============================================================


def make_slug(name: str) -> str:
    """Convert a client name to a kebab-case slug.

    Examples:
        'CS Abbruch'              → 'cs-abbruch'
        'Trautmann GmbH & Co. KG' → 'trautmann-gmbh-co-kg'
        'Müller Bestattungen'     → 'mueller-bestattungen'
    """
    if not name:
        return ""
    # Umlaut conversion
    s = name.lower()
    repl = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}
    for k, v in repl.items():
        s = s.replace(k, v)
    # Keep alphanumeric + hyphens, replace rest with hyphen
    out = []
    prev_dash = False
    for ch in s:
        if ch.isalnum():
            out.append(ch)
            prev_dash = False
        elif not prev_dash:
            out.append("-")
            prev_dash = True
    slug = "".join(out).strip("-")
    # Collapse multiple hyphens
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug


# ============================================================
# DB Class
# ============================================================


class LocalDB:
    """SQLite primary store."""

    def __init__(self, path: Path | None = None) -> None:
        ensure_config_dir()
        self.path = path or LOCAL_DB_FILE
        self._init_schema()

    def _init_schema(self) -> None:
        with self._conn() as c:
            c.executescript(_SCHEMA)
            current = c.execute(
                "SELECT value FROM schema_meta WHERE key = 'version'"
            ).fetchone()
            if current is None:
                c.execute(
                    "INSERT INTO schema_meta (key, value) VALUES ('version', ?)",
                    (str(SCHEMA_VERSION),),
                )
            elif int(current["value"]) < SCHEMA_VERSION:
                # Future: migration logic per version
                c.execute(
                    "UPDATE schema_meta SET value = ? WHERE key = 'version'",
                    (str(SCHEMA_VERSION),),
                )

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, isolation_level=None, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        # Wait up to 30s for the lock under concurrency (ci-batch with N parallel workers)
        conn.execute("PRAGMA busy_timeout=30000")
        try:
            yield conn
        finally:
            conn.close()

    # ============================================================
    # Clients
    # ============================================================

    def upsert_client(
        self,
        name: str,
        slug: str | None = None,
        branche: str | None = None,
        zielgruppe: str | None = None,
        tonalitaet: str | None = None,
        dos: list[str] | None = None,
        donts: list[str] | None = None,
        ig_handle: str | None = None,
        competitor_handles: list[str] | None = None,
        notes: str | None = None,
        created_by: str | None = None,
    ) -> dict:
        """Upsert a client by slug. Returns the row dict.

        Raises ValueError on empty name or slug (after normalization).
        Raises ValueError with a clean message if a name collision with a
        DIFFERENT slug exists (UNIQUE constraint on name).
        """
        name = (name or "").strip()
        if not name:
            raise ValueError("Client name is empty")
        if not slug:
            slug = make_slug(name)
        if not slug:
            raise ValueError(f"Cannot generate slug from name: {name!r}")
        import uuid
        cid = uuid.uuid4().hex[:16]

        with self._conn() as c:
            existing = c.execute(
                "SELECT * FROM clients WHERE slug = ?", (slug,)
            ).fetchone()

            if existing:
                # Update non-null fields only
                updates: list[str] = []
                params: list[Any] = []
                for field, val in [
                    ("name", name),
                    ("branche", branche),
                    ("zielgruppe", zielgruppe),
                    ("tonalitaet", tonalitaet),
                    ("dos", json.dumps(dos) if dos is not None else None),
                    ("donts", json.dumps(donts) if donts is not None else None),
                    ("ig_handle", ig_handle),
                    (
                        "competitor_handles",
                        json.dumps(competitor_handles) if competitor_handles is not None else None,
                    ),
                    ("notes", notes),
                ]:
                    if val is not None:
                        updates.append(f"{field} = ?")
                        params.append(val)
                if updates:
                    updates.append("updated_at = ?")
                    params.append(time.time())
                    params.append(slug)
                    c.execute(
                        f"UPDATE clients SET {', '.join(updates)} WHERE slug = ?",
                        params,
                    )
                row = c.execute("SELECT * FROM clients WHERE slug = ?", (slug,)).fetchone()
            else:
                try:
                    c.execute(
                        """
                        INSERT INTO clients (
                            id, name, slug, branche, zielgruppe, tonalitaet,
                            dos, donts, ig_handle, competitor_handles, notes, created_by
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            cid, name, slug, branche, zielgruppe, tonalitaet,
                            json.dumps(dos or []),
                            json.dumps(donts or []),
                            ig_handle,
                            json.dumps(competitor_handles or []),
                            notes,
                            created_by,
                        ),
                    )
                except sqlite3.IntegrityError as e:
                    # UNIQUE(name) collision: a client with the same name but
                    # different slug already exists. Surface it cleanly.
                    msg = str(e).lower()
                    if "name" in msg:
                        raise ValueError(
                            f"Client name '{name}' already exists with a different slug. "
                            f"Use --slug to disambiguate or rename."
                        ) from e
                    raise
                row = c.execute("SELECT * FROM clients WHERE slug = ?", (slug,)).fetchone()

        return self._client_row_to_dict(row)

    def get_client_by_slug(self, slug: str) -> dict | None:
        with self._conn() as c:
            row = c.execute("SELECT * FROM clients WHERE slug = ?", (slug,)).fetchone()
        return self._client_row_to_dict(row) if row else None

    def get_client_by_name(self, name: str) -> dict | None:
        with self._conn() as c:
            row = c.execute("SELECT * FROM clients WHERE LOWER(name) = LOWER(?)", (name,)).fetchone()
        return self._client_row_to_dict(row) if row else None

    def find_similar_clients(self, name: str, threshold: float = 0.6) -> list[dict]:
        """Fuzzy match using Python-level similarity (Jaccard on tokens)."""
        if not name.strip():
            return []
        target_tokens = set(make_slug(name).split("-"))
        if not target_tokens:
            return []

        with self._conn() as c:
            rows = c.execute("SELECT * FROM clients").fetchall()

        scored: list[tuple[float, dict]] = []
        for r in rows:
            cand_tokens = set(make_slug(r["name"]).split("-"))
            if not cand_tokens:
                continue
            inter = len(target_tokens & cand_tokens)
            union = len(target_tokens | cand_tokens)
            sim = inter / union if union else 0.0
            if sim >= threshold:
                d = self._client_row_to_dict(r)
                d["_similarity"] = sim
                scored.append((sim, d))

        scored.sort(reverse=True, key=lambda x: x[0])
        return [d for _, d in scored[:5]]

    def list_clients(self) -> list[dict]:
        """List all clients with reel-count + last-activity."""
        sql = """
        SELECT
            c.*,
            COUNT(r.id) FILTER (WHERE r.deleted_at IS NULL) AS reel_count,
            MAX(r.analyzed_at) AS last_analyzed
        FROM clients c
        LEFT JOIN reels r ON r.client_id = c.slug
        GROUP BY c.id
        ORDER BY last_analyzed DESC NULLS LAST, c.name ASC
        """
        with self._conn() as c:
            rows = c.execute(sql).fetchall()
        result = []
        for r in rows:
            d = self._client_row_to_dict(r)
            d["reel_count"] = r["reel_count"] or 0
            d["last_analyzed"] = r["last_analyzed"]
            result.append(d)
        return result

    def delete_client(self, slug: str) -> bool:
        with self._conn() as c:
            cur = c.execute("DELETE FROM clients WHERE slug = ?", (slug,))
            return cur.rowcount > 0

    def _client_row_to_dict(self, row: sqlite3.Row | None) -> dict | None:
        if row is None:
            return None
        d = dict(row)
        # Deserialize JSON fields
        for f in ("dos", "donts", "competitor_handles"):
            if f in d and isinstance(d[f], str):
                try:
                    d[f] = json.loads(d[f])
                except json.JSONDecodeError:
                    d[f] = []
        return d

    # ============================================================
    # Reels
    # ============================================================

    def upsert_reel(
        self,
        metadata: dict,
        analysis: dict,
        embeddings: dict[str, list[float] | None] | None = None,
        client_id: str | None = None,
        is_own: bool = False,
        created_by: str | None = None,
    ) -> str:
        """Upsert a reel. Returns the reel ID.

        metadata: ScrapedReel dict
        analysis: ReelAnalysis dict (model_dump)
        embeddings: {"transcript_emb": [...], "hook_emb": [...], "summary_emb": [...]}
        """
        import uuid

        # Compute engagement_rate
        eng = None
        views = metadata.get("views")
        if views:
            inter = sum(
                v or 0
                for v in (
                    metadata.get("likes"),
                    metadata.get("comments"),
                    metadata.get("saves"),
                    metadata.get("shares"),
                )
            )
            eng = inter / views if views > 0 else 0.0

        rid = uuid.uuid4().hex[:16]

        emb_t = embedding_to_blob((embeddings or {}).get("transcript_emb")) if embeddings else None
        emb_h = embedding_to_blob((embeddings or {}).get("hook_emb")) if embeddings else None
        emb_s = embedding_to_blob((embeddings or {}).get("summary_emb")) if embeddings else None

        shortcode = metadata["shortcode"]

        with self._conn() as c:
            existing = c.execute(
                "SELECT id FROM reels WHERE shortcode = ?", (shortcode,)
            ).fetchone()

            hook = analysis["hook"]
            score = analysis["score"]
            params = (
                metadata.get("source", "ig"),
                metadata.get("url", ""),
                client_id,
                1 if is_own else 0,
                created_by,
                metadata["account"],
                metadata.get("account_followers"),
                metadata.get("posted_at"),
                views,
                metadata.get("likes"),
                metadata.get("comments"),
                metadata.get("saves"),
                metadata.get("shares"),
                eng,
                metadata.get("caption", ""),
                json.dumps(metadata.get("hashtags", [])),
                json.dumps(metadata.get("mentions", [])),
                metadata.get("audio_id"),
                metadata.get("audio_title"),
                metadata.get("audio_artist"),
                int(metadata.get("duration_s", 0)) if metadata.get("duration_s") else None,
                metadata.get("video_url_cdn", ""),
                analysis["language"],
                analysis["summary"],
                analysis["angle"],
                json.dumps(analysis.get("content_themes", [])),
                analysis.get("target_audience_hint"),
                hook["type"],
                hook.get("text"),
                hook["visual_element"],
                hook["strength_score"],
                hook["reasoning"],
                analysis["transcript_full"],
                json.dumps(analysis.get("transcript_segments", [])),
                json.dumps(analysis.get("visual_patterns", {})),
                json.dumps(analysis.get("text_overlays", [])),
                json.dumps(analysis.get("emotions", [])),
                json.dumps(analysis.get("color_palette", {})),
                json.dumps(analysis.get("cta_elements", [])),
                json.dumps(analysis.get("scene_changes_s", [])),
                json.dumps(analysis.get("music_sync_events_s", [])),
                score.get("retention_prediction"),
                score.get("hook_strength"),
                score.get("visual_quality"),
                score.get("cta_clarity"),
                json.dumps(score.get("improvements", [])),
                json.dumps(analysis),
                emb_t,
                emb_h,
                emb_s,
            )

            if existing:
                # Update — preserve client_id if not given
                rid = existing["id"]
                c.execute(
                    """
                    UPDATE reels SET
                        source = ?, url = ?,
                        client_id = COALESCE(?, client_id),
                        is_own = ? OR is_own,
                        created_by = COALESCE(?, created_by),
                        account = ?, account_followers = ?, posted_at = ?,
                        analyzed_at = strftime('%s','now'),
                        views = ?, likes = ?, comments = ?, saves = ?, shares = ?,
                        engagement_rate = ?,
                        caption = ?, hashtags = ?, mentions = ?,
                        audio_id = ?, audio_title = ?, audio_artist = ?,
                        duration_s = ?, video_url_cdn = ?,
                        language = ?, summary = ?, angle = ?,
                        content_themes = ?, target_audience_hint = ?,
                        hook_type = ?, hook_text = ?, hook_visual = ?,
                        hook_score = ?, hook_reasoning = ?,
                        transcript_full = ?, transcript_segments = ?,
                        visual_patterns = ?, text_overlays = ?, emotions = ?,
                        color_palette = ?, cta_elements = ?,
                        scene_changes_s = ?, music_sync_events_s = ?,
                        score_retention = ?, score_hook = ?, score_visual = ?,
                        score_cta = ?, score_improvements = ?,
                        raw_analysis = ?,
                        transcript_emb = ?, hook_emb = ?, summary_emb = ?
                    WHERE id = ?
                    """,
                    params + (rid,),
                )
            else:
                c.execute(
                    """
                    INSERT INTO reels (
                        id, shortcode, source, url, client_id, is_own, created_by,
                        account, account_followers, posted_at,
                        views, likes, comments, saves, shares, engagement_rate,
                        caption, hashtags, mentions,
                        audio_id, audio_title, audio_artist,
                        duration_s, video_url_cdn,
                        language, summary, angle, content_themes, target_audience_hint,
                        hook_type, hook_text, hook_visual, hook_score, hook_reasoning,
                        transcript_full, transcript_segments,
                        visual_patterns, text_overlays, emotions,
                        color_palette, cta_elements,
                        scene_changes_s, music_sync_events_s,
                        score_retention, score_hook, score_visual, score_cta, score_improvements,
                        raw_analysis,
                        transcript_emb, hook_emb, summary_emb
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (rid, shortcode) + params,
                )

        return rid

    def get_reel(self, shortcode: str, include_embeddings: bool = False) -> dict | None:
        with self._conn() as c:
            row = c.execute(
                "SELECT * FROM reels WHERE shortcode = ? AND deleted_at IS NULL",
                (shortcode,),
            ).fetchone()
        return self._reel_row_to_dict(row, include_embeddings) if row else None

    def list_reels(
        self,
        client_id: str | None = None,
        account: str | None = None,
        is_own: bool | None = None,
        hook_type: str | None = None,
        min_score: int | None = None,
        limit: int = 100,
    ) -> list[dict]:
        filters = ["deleted_at IS NULL"]
        params: list[Any] = []
        if client_id is not None:
            filters.append("client_id = ?")
            params.append(client_id)
        if account is not None:
            filters.append("account = ?")
            params.append(account)
        if is_own is not None:
            filters.append("is_own = ?")
            params.append(1 if is_own else 0)
        if hook_type is not None:
            filters.append("hook_type = ?")
            params.append(hook_type)
        if min_score is not None:
            filters.append("hook_score >= ?")
            params.append(min_score)

        where = " AND ".join(filters)
        params.append(limit)
        sql = f"SELECT * FROM reels WHERE {where} ORDER BY analyzed_at DESC LIMIT ?"

        with self._conn() as c:
            rows = c.execute(sql, params).fetchall()
        return [self._reel_row_to_dict(r) for r in rows]

    def iter_reels_with_embedding(
        self,
        column: str = "summary_emb",
        client_id: str | None = None,
    ) -> Iterator[tuple[str, str, list[float], dict]]:
        """Iterate reels that have an embedding in `column`.

        Yields (reel_id, shortcode, embedding, summary_dict).
        Used by vector_search.py for brute-force cosine.
        """
        if column not in ("transcript_emb", "hook_emb", "summary_emb"):
            raise ValueError(f"Invalid column: {column}")

        filters = [f"{column} IS NOT NULL", "deleted_at IS NULL"]
        params: list[Any] = []
        if client_id is not None:
            filters.append("client_id = ?")
            params.append(client_id)
        where = " AND ".join(filters)

        sql = f"""
            SELECT id, shortcode, account, hook_text, summary, views, posted_at,
                   client_id, hook_type, hook_score, angle, {column}
            FROM reels WHERE {where}
        """
        with self._conn() as c:
            for row in c.execute(sql, params):
                emb = blob_to_embedding(row[column])
                if emb is None:
                    continue
                meta = {
                    "id": row["id"],
                    "shortcode": row["shortcode"],
                    "account": row["account"],
                    "hook_text": row["hook_text"],
                    "summary": row["summary"],
                    "views": row["views"],
                    "posted_at": row["posted_at"],
                    "client_id": row["client_id"],
                    "hook_type": row["hook_type"],
                    "hook_score": row["hook_score"],
                    "angle": row["angle"],
                }
                yield (row["id"], row["shortcode"], emb, meta)

    def _reel_row_to_dict(self, row: sqlite3.Row | None, include_embeddings: bool = False) -> dict | None:
        if row is None:
            return None
        d = dict(row)
        # Deserialize JSON fields
        for f in (
            "hashtags", "mentions", "content_themes", "transcript_segments",
            "visual_patterns", "text_overlays", "emotions", "color_palette",
            "cta_elements", "scene_changes_s", "music_sync_events_s",
            "score_improvements", "raw_analysis",
        ):
            if f in d and isinstance(d[f], str):
                try:
                    d[f] = json.loads(d[f])
                except json.JSONDecodeError:
                    pass
        # Convert is_own to bool
        if "is_own" in d:
            d["is_own"] = bool(d["is_own"])
        # Drop embeddings unless requested
        if not include_embeddings:
            for col in ("transcript_emb", "hook_emb", "summary_emb"):
                d.pop(col, None)
        else:
            for col in ("transcript_emb", "hook_emb", "summary_emb"):
                if col in d:
                    d[col] = blob_to_embedding(d[col])
        return d

    # ============================================================
    # Scripts
    # ============================================================

    def insert_script(
        self,
        client_id: str,
        thema: str,
        hook_text: str | None = None,
        hook_type: str | None = None,
        angle: str | None = None,
        szenen: list[dict] | None = None,
        cta: str | None = None,
        laenge_s: int | None = None,
        full_script: str | None = None,
        referenz_reels: list[str] | None = None,
        trend_basis: str | None = None,
        score_prediction: int | None = None,
        created_by: str | None = None,
    ) -> str:
        import uuid
        sid = uuid.uuid4().hex[:16]
        with self._conn() as c:
            c.execute(
                """
                INSERT INTO scripts (
                    id, client_id, thema, hook_text, hook_type, angle,
                    szenen, cta, laenge_s, full_script,
                    referenz_reels, trend_basis, score_prediction, created_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sid, client_id, thema, hook_text, hook_type, angle,
                    json.dumps(szenen or []),
                    cta, laenge_s, full_script,
                    json.dumps(referenz_reels or []),
                    trend_basis, score_prediction, created_by,
                ),
            )
        return sid

    def list_scripts(self, client_id: str | None = None, status: str | None = None, limit: int = 50) -> list[dict]:
        filters = []
        params: list[Any] = []
        if client_id:
            filters.append("client_id = ?")
            params.append(client_id)
        if status:
            filters.append("status = ?")
            params.append(status)
        where = ("WHERE " + " AND ".join(filters)) if filters else ""
        params.append(limit)
        sql = f"SELECT * FROM scripts {where} ORDER BY created_at DESC LIMIT ?"
        with self._conn() as c:
            rows = c.execute(sql, params).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            for f in ("szenen", "referenz_reels", "performance"):
                if d.get(f):
                    try:
                        d[f] = json.loads(d[f])
                    except (json.JSONDecodeError, TypeError):
                        pass
            result.append(d)
        return result

    # ============================================================
    # Playbooks
    # ============================================================

    def upsert_playbook(
        self,
        client_id: str,
        top_hooks: list[dict],
        top_angles: list[dict],
        posting_freq: str | None,
        benchmark: dict,
        empfehlungen: list[str],
        valid_until: float | None = None,
        created_by: str | None = None,
    ) -> str:
        import uuid
        pid = uuid.uuid4().hex[:16]
        with self._conn() as c:
            c.execute(
                """
                INSERT INTO playbooks (
                    id, client_id, top_hooks, top_angles, posting_freq,
                    benchmark, empfehlungen, valid_until, created_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pid, client_id,
                    json.dumps(top_hooks),
                    json.dumps(top_angles),
                    posting_freq,
                    json.dumps(benchmark),
                    json.dumps(empfehlungen),
                    valid_until,
                    created_by,
                ),
            )
        return pid

    def latest_playbook(self, client_id: str) -> dict | None:
        with self._conn() as c:
            row = c.execute(
                "SELECT * FROM playbooks WHERE client_id = ? ORDER BY generated_at DESC LIMIT 1",
                (client_id,),
            ).fetchone()
        if not row:
            return None
        d = dict(row)
        for f in ("top_hooks", "top_angles", "benchmark", "empfehlungen"):
            if d.get(f):
                try:
                    d[f] = json.loads(d[f])
                except json.JSONDecodeError:
                    pass
        return d

    # ============================================================
    # Tracked Accounts
    # ============================================================

    def add_tracked_account(
        self,
        client_id: str,
        handle: str,
        source: str = "ig",
        is_own: bool = False,
        interval_hours: int = 24,
        created_by: str | None = None,
    ) -> str:
        import uuid
        tid = uuid.uuid4().hex[:16]
        with self._conn() as c:
            try:
                c.execute(
                    """
                    INSERT INTO tracked_accounts (
                        id, client_id, handle, source, is_own, interval_hours, created_by
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (tid, client_id, handle.lstrip("@"), source, 1 if is_own else 0, interval_hours, created_by),
                )
            except sqlite3.IntegrityError:
                # Already tracked — update interval
                c.execute(
                    "UPDATE tracked_accounts SET interval_hours = ?, active = 1 "
                    "WHERE client_id = ? AND handle = ? AND source = ?",
                    (interval_hours, client_id, handle.lstrip("@"), source),
                )
                row = c.execute(
                    "SELECT id FROM tracked_accounts WHERE client_id = ? AND handle = ? AND source = ?",
                    (client_id, handle.lstrip("@"), source),
                ).fetchone()
                tid = row["id"]
        return tid

    def list_tracked_accounts(self, client_id: str | None = None) -> list[dict]:
        sql = "SELECT * FROM tracked_accounts"
        params: list[Any] = []
        if client_id:
            sql += " WHERE client_id = ?"
            params.append(client_id)
        with self._conn() as c:
            rows = c.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    # ============================================================
    # Jobs
    # ============================================================

    def enqueue_job(
        self,
        shortcode: str,
        source: str = "ig",
        priority: int = 10,
        client_id: str | None = None,
    ) -> str:
        import uuid
        jid = uuid.uuid4().hex[:16]
        with self._conn() as c:
            try:
                c.execute(
                    """
                    INSERT INTO jobs (id, shortcode, source, client_id, priority)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (jid, shortcode, source, client_id, priority),
                )
            except sqlite3.IntegrityError:
                # Already exists — get id
                row = c.execute(
                    "SELECT id FROM jobs WHERE source = ? AND shortcode = ?",
                    (source, shortcode),
                ).fetchone()
                jid = row["id"]
                # Re-queue if was failed
                c.execute(
                    "UPDATE jobs SET status = 'queued', last_error = NULL "
                    "WHERE id = ? AND status = 'failed'",
                    (jid,),
                )
        return jid

    def update_job_status(self, job_id: str, status: str, error: str | None = None) -> None:
        with self._conn() as c:
            c.execute(
                """
                UPDATE jobs SET
                    status = ?,
                    attempts = attempts + 1,
                    last_error = ?,
                    started_at = COALESCE(started_at, strftime('%s','now')),
                    finished_at = CASE WHEN ? IN ('stored', 'failed') THEN strftime('%s','now') ELSE finished_at END
                WHERE id = ?
                """,
                (status, error, status, job_id),
            )

    # ============================================================
    # Stats
    # ============================================================

    def stats(self) -> dict:
        with self._conn() as c:
            now = time.time()
            seven_days = now - (7 * 24 * 3600)
            stats = {
                "reels_total": c.execute(
                    "SELECT COUNT(*) AS n FROM reels WHERE deleted_at IS NULL"
                ).fetchone()["n"],
                "reels_7d": c.execute(
                    "SELECT COUNT(*) AS n FROM reels WHERE deleted_at IS NULL AND scraped_at > ?",
                    (seven_days,),
                ).fetchone()["n"],
                "clients_total": c.execute("SELECT COUNT(*) AS n FROM clients").fetchone()["n"],
                "scripts_total": c.execute("SELECT COUNT(*) AS n FROM scripts").fetchone()["n"],
                "jobs_queued": c.execute(
                    "SELECT COUNT(*) AS n FROM jobs WHERE status = 'queued'"
                ).fetchone()["n"],
                "jobs_failed": c.execute(
                    "SELECT COUNT(*) AS n FROM jobs WHERE status = 'failed'"
                ).fetchone()["n"],
                "tracked_total": c.execute("SELECT COUNT(*) AS n FROM tracked_accounts").fetchone()["n"],
                "invocations_total": c.execute("SELECT COUNT(*) AS n FROM invocations").fetchone()["n"],
                "db_size_mb": round(self.path.stat().st_size / 1024 / 1024, 2) if self.path.exists() else 0,
            }
        return stats

    # ============================================================
    # Prefs + Audit
    # ============================================================

    def set_pref(self, key: str, value: Any) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO prefs (key, value, updated_at) VALUES (?, ?, ?)",
                (key, json.dumps(value), time.time()),
            )

    def get_pref(self, key: str, default: Any = None) -> Any:
        with self._conn() as c:
            row = c.execute("SELECT value FROM prefs WHERE key = ?", (key,)).fetchone()
        return json.loads(row["value"]) if row else default

    def log_invocation(
        self,
        skill: str,
        args: dict | None = None,
        status: str = "ok",
        error: str | None = None,
        duration_ms: int | None = None,
    ) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT INTO invocations (skill, args, status, error, duration_ms) "
                "VALUES (?, ?, ?, ?, ?)",
                (skill, json.dumps(args or {}), status, error, duration_ms),
            )


_instance: LocalDB | None = None


def get_local_db() -> LocalDB:
    """Singleton accessor."""
    global _instance
    if _instance is None:
        _instance = LocalDB()
    return _instance
