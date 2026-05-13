"""Supabase client - asyncpg pool for pgvector + shared team DB.

Schema additions for team-shared DB:
  - reels.client_id (TEXT, FK to clients.slug)
  - reels.is_own (BOOL)
  - reels.created_by (TEXT, user audit)
  - clients/scripts/playbooks/tracked_accounts (new tables, see migration-002)
"""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import asyncpg

from clients.apify import ScrapedReel
from config import get_settings
from schemas.reel import ReelAnalysis, SimilarityMatch, SimilarityQuery

logger = logging.getLogger(__name__)


def _vec_literal(values: list[float]) -> str:
    """Format a Python list as pgvector literal '[1.0,2.0,...]'."""
    return "[" + ",".join(f"{v:.7g}" for v in values) + "]"


class SupabaseError(Exception):
    """Base Supabase error."""


class SupabaseDB:
    """asyncpg pool wrapper for the content-intelligence schema."""

    def __init__(self, dsn: str | None = None, min_size: int = 2, max_size: int = 10) -> None:
        s = get_settings()
        self._dsn = dsn or s.supabase_db_url.get_secret_value()
        if not self._dsn:
            raise SupabaseError(
                "SUPABASE_DB_URL missing. Run /ci-setup to configure shared team DB."
            )
        self._min_size = min_size
        self._max_size = max_size
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        if self._pool is not None:
            return
        # Disable statement caching for pgbouncer transaction-mode compatibility
        # (Supabase pooler runs in transaction mode which doesn't support prepared statements)
        self._pool = await asyncpg.create_pool(
            dsn=self._dsn,
            min_size=self._min_size,
            max_size=self._max_size,
            command_timeout=60.0,
            statement_cache_size=0,
        )

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[asyncpg.Connection]:
        if self._pool is None:
            await self.connect()
        assert self._pool is not None
        async with self._pool.acquire() as conn:
            yield conn

    async def ping(self) -> bool:
        """Test connection."""
        try:
            async with self.acquire() as conn:
                result = await conn.fetchval("SELECT 1")
                return result == 1
        except Exception as e:
            logger.warning("supabase.ping.failed", extra={"error": str(e)[:200]})
            return False

    # ---------- Reels ----------

    async def upsert_reel(
        self,
        metadata: ScrapedReel,
        analysis: ReelAnalysis,
        embeddings: dict[str, list[float]],
        r2_key: str | None = None,
        client_id: str | None = None,
        is_own: bool = False,
        created_by: str | None = None,
    ) -> str:
        """Upsert a reel. Returns the reel UUID."""
        s = get_settings()
        created_by = created_by or s.ci_user

        engagement_rate: float | None = None
        if metadata.views and metadata.views > 0:
            inter = sum(
                v or 0
                for v in (metadata.likes, metadata.comments, metadata.saves, metadata.shares)
            )
            engagement_rate = inter / metadata.views

        sql = """
        INSERT INTO reels (
            shortcode, source, account, account_followers, posted_at, scraped_at, analyzed_at,
            views, likes, comments, saves, shares, engagement_rate,
            caption, hashtags, mentions, audio_id, audio_title, audio_artist,
            duration_s, video_url_cdn, r2_key, thumbnail_url,
            language, summary, angle, content_themes, target_audience_hint,
            hook_type, hook_text, hook_visual, hook_score, hook_reasoning,
            transcript_full, transcript_segments,
            visual_patterns, text_overlays, emotions, color_palette,
            scene_changes_s, cta_elements, music_sync_events_s,
            score_retention, score_hook, score_visual, score_cta, score_improvements,
            raw_analysis,
            transcript_emb, hook_emb, summary_emb,
            client_id, is_own, created_by
        ) VALUES (
            $1, $2, $3, $4, $5::timestamptz, NOW(), NOW(),
            $6, $7, $8, $9, $10, $11,
            $12, $13, $14, $15, $16, $17,
            $18, $19, $20, $21,
            $22, $23, $24, $25, $26,
            $27, $28, $29, $30, $31,
            $32, $33::jsonb,
            $34::jsonb, $35::jsonb, $36::jsonb, $37::jsonb,
            $38::numeric[], $39::jsonb, $40::numeric[],
            $41, $42, $43, $44, $45,
            $46::jsonb,
            $47::vector, $48::vector, $49::vector,
            $50, $51, $52
        )
        ON CONFLICT (shortcode) DO UPDATE SET
            views = EXCLUDED.views,
            likes = EXCLUDED.likes,
            comments = EXCLUDED.comments,
            saves = EXCLUDED.saves,
            shares = EXCLUDED.shares,
            engagement_rate = EXCLUDED.engagement_rate,
            analyzed_at = NOW(),
            raw_analysis = EXCLUDED.raw_analysis,
            client_id = COALESCE(EXCLUDED.client_id, reels.client_id),
            is_own = EXCLUDED.is_own OR reels.is_own
        RETURNING id::text
        """

        async with self.acquire() as conn:
            row = await conn.fetchrow(
                sql,
                metadata.shortcode,
                metadata.source,
                metadata.account,
                metadata.account_followers,
                metadata.posted_at,
                metadata.views,
                metadata.likes,
                metadata.comments,
                metadata.saves,
                metadata.shares,
                engagement_rate,
                metadata.caption,
                metadata.hashtags,
                metadata.mentions,
                metadata.audio_id,
                metadata.audio_title,
                metadata.audio_artist,
                int(metadata.duration_s) if metadata.duration_s else None,
                metadata.video_url_cdn,
                r2_key,
                metadata.thumbnail_url,
                analysis.language,
                analysis.summary,
                analysis.angle.value if hasattr(analysis.angle, "value") else str(analysis.angle),
                analysis.content_themes,
                analysis.target_audience_hint or None,
                analysis.hook.type.value
                if hasattr(analysis.hook.type, "value")
                else str(analysis.hook.type),
                analysis.hook.text,
                analysis.hook.visual_element,
                analysis.hook.strength_score,
                analysis.hook.reasoning,
                analysis.transcript_full,
                json.dumps([seg.model_dump() for seg in analysis.transcript_segments]),
                json.dumps(analysis.visual_patterns.model_dump()),
                json.dumps([t.model_dump() for t in analysis.text_overlays]),
                json.dumps([e.model_dump(mode="json") for e in analysis.emotions]),
                json.dumps(analysis.color_palette.model_dump(mode="json")),
                analysis.scene_changes_s,
                json.dumps([c.model_dump() for c in analysis.cta_elements]),
                analysis.music_sync_events_s,
                analysis.score.retention_prediction,
                analysis.score.hook_strength,
                analysis.score.visual_quality,
                analysis.score.cta_clarity,
                analysis.score.improvements,
                json.dumps(analysis.model_dump(mode="json")),
                _vec_literal(embeddings["transcript_emb"]),
                _vec_literal(embeddings["hook_emb"]),
                _vec_literal(embeddings["summary_emb"]),
                client_id,
                is_own,
                created_by,
            )
        reel_id: str = row["id"]
        logger.info(
            "supabase.upsert",
            extra={"shortcode": metadata.shortcode, "reel_id": reel_id, "client_id": client_id},
        )
        return reel_id

    # ---------- Similarity Search ----------

    async def search_similar(
        self, query_embedding: list[float], query: SimilarityQuery
    ) -> list[SimilarityMatch]:
        """Cosine similarity on selected embedding column, optional filters."""
        col_map = {
            "hook": "hook_emb",
            "transcript": "transcript_emb",
            "summary": "summary_emb",
        }
        col = col_map[query.query_type]

        filters = ["deleted_at IS NULL"]
        params: list[Any] = [_vec_literal(query_embedding), query.top_k]
        i = 3
        if query.filter_account:
            filters.append(f"account = ${i}")
            params.append(query.filter_account)
            i += 1
        if query.filter_angle:
            filters.append(f"angle = ${i}")
            params.append(query.filter_angle.value)
            i += 1
        if query.filter_client_id:
            filters.append(f"client_id = ${i}")
            params.append(query.filter_client_id)
            i += 1

        where = f"WHERE {' AND '.join(filters)}"
        sql = f"""
        SELECT
            shortcode, account, hook_text, summary, views, client_id,
            to_char(posted_at, 'YYYY-MM-DD') AS posted_at,
            1 - ({col} <=> $1::vector) AS similarity
        FROM reels
        {where}
        ORDER BY {col} <=> $1::vector
        LIMIT $2
        """

        async with self.acquire() as conn:
            rows = await conn.fetch(sql, *params)

        matches = [
            SimilarityMatch(
                shortcode=r["shortcode"],
                account=r["account"],
                similarity=float(r["similarity"]),
                hook_text=r["hook_text"],
                summary=r["summary"],
                views=r["views"],
                posted_at=r["posted_at"],
                client_id=r["client_id"],
            )
            for r in rows
        ]
        if query.min_score is not None:
            matches = [m for m in matches if m.similarity >= query.min_score]
        return matches

    # ---------- Clients (NEW — team-shared) ----------

    async def upsert_client(
        self,
        name: str,
        slug: str,
        branche: str | None = None,
        zielgruppe: str | None = None,
        tonalitaet: str | None = None,
        dos: list[str] | None = None,
        donts: list[str] | None = None,
        ig_handle: str | None = None,
        competitor_handles: list[str] | None = None,
    ) -> dict:
        """Upsert a client by slug. Returns the row dict."""
        s = get_settings()
        sql = """
        INSERT INTO clients (
            name, slug, branche, zielgruppe, tonalitaet,
            dos, donts, ig_handle, competitor_handles, created_by
        ) VALUES (
            $1, $2, $3, $4, $5,
            $6::jsonb, $7::jsonb, $8, $9::jsonb, $10
        )
        ON CONFLICT (slug) DO UPDATE SET
            name = EXCLUDED.name,
            branche = COALESCE(EXCLUDED.branche, clients.branche),
            zielgruppe = COALESCE(EXCLUDED.zielgruppe, clients.zielgruppe),
            tonalitaet = COALESCE(EXCLUDED.tonalitaet, clients.tonalitaet),
            dos = COALESCE(EXCLUDED.dos, clients.dos),
            donts = COALESCE(EXCLUDED.donts, clients.donts),
            ig_handle = COALESCE(EXCLUDED.ig_handle, clients.ig_handle),
            competitor_handles = COALESCE(EXCLUDED.competitor_handles, clients.competitor_handles),
            updated_at = NOW()
        RETURNING *
        """
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                sql,
                name,
                slug,
                branche,
                zielgruppe,
                tonalitaet,
                json.dumps(dos or []),
                json.dumps(donts or []),
                ig_handle,
                json.dumps(competitor_handles or []),
                s.ci_user,
            )
        return dict(row) if row else {}

    async def list_clients(self) -> list[dict]:
        """List all clients with reel-count + last-activity."""
        sql = """
        SELECT
            c.id::text, c.name, c.slug, c.branche, c.ig_handle,
            c.created_by, c.created_at, c.updated_at,
            COUNT(r.id) FILTER (WHERE r.deleted_at IS NULL) AS reel_count,
            MAX(r.analyzed_at) AS last_analyzed
        FROM clients c
        LEFT JOIN reels r ON r.client_id = c.slug
        GROUP BY c.id, c.name, c.slug, c.branche, c.ig_handle, c.created_by, c.created_at, c.updated_at
        ORDER BY last_analyzed DESC NULLS LAST, c.name ASC
        """
        async with self.acquire() as conn:
            rows = await conn.fetch(sql)
        return [dict(r) for r in rows]

    async def get_client_by_slug(self, slug: str) -> dict | None:
        sql = "SELECT * FROM clients WHERE slug = $1"
        async with self.acquire() as conn:
            row = await conn.fetchrow(sql, slug)
        return dict(row) if row else None

    async def get_client_by_name(self, name: str) -> dict | None:
        sql = "SELECT * FROM clients WHERE LOWER(name) = LOWER($1)"
        async with self.acquire() as conn:
            row = await conn.fetchrow(sql, name)
        return dict(row) if row else None

    async def find_similar_clients(self, name: str, threshold: float = 0.6) -> list[dict]:
        """Fuzzy match for typo detection. Uses pg_trgm similarity."""
        sql = """
        SELECT id::text, name, slug, similarity(name, $1) AS sim
        FROM clients
        WHERE similarity(name, $1) > $2
        ORDER BY sim DESC
        LIMIT 5
        """
        async with self.acquire() as conn:
            rows = await conn.fetch(sql, name, threshold)
        return [dict(r) for r in rows]

    # ---------- Stats ----------

    async def stats(self) -> dict[str, Any]:
        """Aggregate stats for /ci-status."""
        sql = """
        SELECT
            (SELECT COUNT(*) FROM reels WHERE deleted_at IS NULL) AS reels_total,
            (SELECT COUNT(*) FROM reels WHERE deleted_at IS NULL AND scraped_at > NOW() - INTERVAL '7 days') AS reels_7d,
            (SELECT COUNT(*) FROM clients) AS clients_total,
            (SELECT COUNT(*) FROM jobs WHERE status = 'queued') AS jobs_queued,
            (SELECT COUNT(*) FROM jobs WHERE status = 'failed') AS jobs_failed,
            (SELECT COUNT(*) FROM tracked_accounts) AS tracked_total
        """
        async with self.acquire() as conn:
            row = await conn.fetchrow(sql)
        return dict(row) if row else {}

    # ---------- Jobs ----------

    async def enqueue_job(
        self,
        shortcode: str,
        source: str = "ig",
        priority: int = 10,
        client_id: str | None = None,
    ) -> str:
        sql = """
        INSERT INTO jobs (shortcode, source, status, priority, metadata)
        VALUES ($1, $2, 'queued', $3, $4::jsonb)
        ON CONFLICT (source, shortcode) DO UPDATE SET
            priority = LEAST(jobs.priority, EXCLUDED.priority),
            status = CASE WHEN jobs.status = 'failed' THEN 'queued' ELSE jobs.status END
        RETURNING id::text
        """
        meta = json.dumps({"client_id": client_id} if client_id else {})
        async with self.acquire() as conn:
            row = await conn.fetchrow(sql, shortcode, source, priority, meta)
        return row["id"]

    async def update_job_status(
        self, job_id: str, status: str, error: str | None = None
    ) -> None:
        sql = """
        UPDATE jobs SET
            status = $2,
            attempts = attempts + 1,
            last_error = $3,
            started_at = COALESCE(started_at, NOW()),
            finished_at = CASE WHEN $2 IN ('stored', 'failed') THEN NOW() ELSE finished_at END
        WHERE id = $1
        """
        async with self.acquire() as conn:
            await conn.execute(sql, job_id, status, error)
