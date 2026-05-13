-- =====================================================================
-- Content Intelligence Plugin — Migration 001 (Init)
-- =====================================================================
-- Project: content-intelligence Claude Code Plugin
-- Date:    2026-05-12
-- Author:  Nayl + Claude
--
-- Scope:
--   * Base reels schema (from content-intelligence/src) — adapted for team-sharing
--   * NEW: clients, scripts, playbooks, tracked_accounts (agency-grade)
--   * NEW: client_id + is_own + created_by on reels
--   * pgvector HNSW indexes (m=16, ef_construction=64)
--   * pg_trgm for fuzzy client-name matching
--
-- Idempotent: alle CREATE-Statements mit IF NOT EXISTS
-- Run on Supabase via: psql "$SUPABASE_DB_URL" -f migration-001-init.sql
-- Or via Supabase SQL Editor (paste and run)
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- 1. EXTENSIONS
-- ---------------------------------------------------------------------

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS pg_trgm;


-- ---------------------------------------------------------------------
-- 2. ENUMS
-- ---------------------------------------------------------------------

DO $$ BEGIN
    CREATE TYPE job_status AS ENUM (
        'queued', 'scraping', 'downloading', 'analyzing', 'embedding', 'stored', 'failed'
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE reel_source AS ENUM ('ig', 'tiktok');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE reel_angle AS ENUM (
        'problem_solution', 'listicle', 'story', 'demonstration', 'transformation',
        'educational', 'entertainment', 'testimonial', 'ugc', 'other'
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE hook_type AS ENUM (
        'question', 'shock', 'pattern_interrupt', 'social_proof', 'problem',
        'listicle', 'story', 'demonstration', 'transformation', 'other'
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE script_status AS ENUM ('draft', 'approved', 'posted', 'archived');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;


-- ---------------------------------------------------------------------
-- 3. TABLE: clients (NEW — team-shared client profiles)
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS clients (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name                text NOT NULL,
    slug                text NOT NULL,
    branche             text,
    zielgruppe          text,
    tonalitaet          text,
    dos                 jsonb NOT NULL DEFAULT '[]'::jsonb,
    donts               jsonb NOT NULL DEFAULT '[]'::jsonb,
    ig_handle           text,
    competitor_handles  jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_by          text,
    created_at          timestamptz NOT NULL DEFAULT NOW(),
    updated_at          timestamptz NOT NULL DEFAULT NOW(),

    CONSTRAINT clients_slug_unique UNIQUE (slug),
    CONSTRAINT clients_name_unique UNIQUE (name)
);

CREATE INDEX IF NOT EXISTS idx_clients_slug ON clients(slug);
CREATE INDEX IF NOT EXISTS idx_clients_name_trgm ON clients USING gin (name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_clients_branche ON clients(branche);

COMMENT ON TABLE clients IS 'Agency client profiles. Slug is used as foreign-key target in reels.client_id. Trigram index on name enables fuzzy duplicate detection.';


-- ---------------------------------------------------------------------
-- 4. TABLE: reels (core analyzed reels — with client_id extension)
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS reels (
    -- Identity
    id                       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    shortcode                text NOT NULL,
    source                   reel_source NOT NULL DEFAULT 'ig',
    tenant_id                text NOT NULL DEFAULT 'adscale',

    -- Client linkage (NEW)
    client_id                text REFERENCES clients(slug) ON DELETE SET NULL,
    is_own                   boolean NOT NULL DEFAULT FALSE,
    created_by               text,

    -- Account-Metadata
    account                  text NOT NULL,
    account_followers        bigint,
    posted_at                timestamptz,
    scraped_at               timestamptz NOT NULL DEFAULT NOW(),
    analyzed_at              timestamptz NOT NULL DEFAULT NOW(),

    -- Engagement
    views                    bigint,
    likes                    bigint,
    comments                 bigint,
    saves                    bigint,
    shares                   bigint,
    engagement_rate          numeric(8,5),

    -- Original content
    caption                  text,
    hashtags                 text[] DEFAULT ARRAY[]::text[],
    mentions                 text[] DEFAULT ARRAY[]::text[],
    audio_id                 text,
    audio_title              text,
    audio_artist             text,

    -- Video refs
    duration_s               integer,
    video_url_cdn            text,
    r2_key                   text,
    thumbnail_url            text,
    mp4_expires_at           timestamptz,

    -- Analysis
    language                 text NOT NULL,
    summary                  text NOT NULL,
    angle                    reel_angle NOT NULL,
    content_themes           text[] DEFAULT ARRAY[]::text[],
    target_audience_hint     text,

    -- Hook
    hook_type                hook_type NOT NULL,
    hook_text                text,
    hook_visual              text NOT NULL,
    hook_score               integer NOT NULL CHECK (hook_score BETWEEN 1 AND 100),
    hook_reasoning           text NOT NULL,

    -- Transcript
    transcript_full          text NOT NULL,
    transcript_segments      jsonb NOT NULL DEFAULT '[]'::jsonb,

    -- Visual / Color / Overlays / CTA
    visual_patterns          jsonb NOT NULL DEFAULT '{}'::jsonb,
    text_overlays            jsonb NOT NULL DEFAULT '[]'::jsonb,
    emotions                 jsonb NOT NULL DEFAULT '[]'::jsonb,
    color_palette            jsonb NOT NULL DEFAULT '{}'::jsonb,
    cta_elements             jsonb NOT NULL DEFAULT '[]'::jsonb,

    -- Timestamps arrays
    scene_changes_s          numeric[] DEFAULT ARRAY[]::numeric[],
    music_sync_events_s      numeric[] DEFAULT ARRAY[]::numeric[],

    -- Score
    score_retention          integer CHECK (score_retention BETWEEN 1 AND 100),
    score_hook               integer CHECK (score_hook BETWEEN 1 AND 100),
    score_visual             integer CHECK (score_visual BETWEEN 1 AND 100),
    score_cta                integer CHECK (score_cta BETWEEN 1 AND 100),
    score_improvements       text[] DEFAULT ARRAY[]::text[],

    -- Raw
    raw_analysis             jsonb NOT NULL,

    -- Embeddings
    transcript_emb           vector(1536),
    hook_emb                 vector(1536),
    summary_emb              vector(1536),

    -- Soft-delete
    deleted_at               timestamptz,

    CONSTRAINT reels_shortcode_unique UNIQUE (shortcode),
    CONSTRAINT reels_engagement_nonneg CHECK (engagement_rate IS NULL OR engagement_rate >= 0)
);

-- HNSW vector indexes
CREATE INDEX IF NOT EXISTS idx_reels_transcript_emb_hnsw
    ON reels USING hnsw (transcript_emb vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS idx_reels_hook_emb_hnsw
    ON reels USING hnsw (hook_emb vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS idx_reels_summary_emb_hnsw
    ON reels USING hnsw (summary_emb vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Filter indexes
CREATE INDEX IF NOT EXISTS idx_reels_account_posted
    ON reels (account, posted_at DESC NULLS LAST)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_reels_angle
    ON reels (angle)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_reels_client
    ON reels (client_id)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_reels_client_own
    ON reels (client_id, is_own)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_reels_mp4_expiry
    ON reels (mp4_expires_at)
    WHERE r2_key IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_reels_transcript_trgm
    ON reels USING gin (transcript_full gin_trgm_ops)
    WHERE deleted_at IS NULL;


-- ---------------------------------------------------------------------
-- 5. TABLE: jobs (Postgres-native queue)
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS jobs (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    shortcode       text NOT NULL,
    source          reel_source NOT NULL DEFAULT 'ig',
    status          job_status NOT NULL DEFAULT 'queued',
    priority        integer NOT NULL DEFAULT 10 CHECK (priority BETWEEN 0 AND 20),
    attempts        integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    last_error      text,
    enqueued_at     timestamptz NOT NULL DEFAULT NOW(),
    started_at      timestamptz,
    finished_at     timestamptz,
    metadata        jsonb NOT NULL DEFAULT '{}'::jsonb,

    CONSTRAINT jobs_source_shortcode_unique UNIQUE (source, shortcode)
);

CREATE INDEX IF NOT EXISTS idx_jobs_queue_poll
    ON jobs (priority ASC, enqueued_at ASC)
    WHERE status IN ('queued', 'failed');

CREATE INDEX IF NOT EXISTS idx_jobs_status_started ON jobs (status, started_at);
CREATE INDEX IF NOT EXISTS idx_jobs_finished ON jobs (finished_at) WHERE finished_at IS NOT NULL;


-- ---------------------------------------------------------------------
-- 6. TABLE: scripts (NEW — generated reel scripts per client)
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS scripts (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id           text NOT NULL REFERENCES clients(slug) ON DELETE CASCADE,
    thema               text NOT NULL,
    status              script_status NOT NULL DEFAULT 'draft',

    -- Generated content
    hook_text           text,
    hook_type           hook_type,
    angle               reel_angle,
    szenen              jsonb NOT NULL DEFAULT '[]'::jsonb,
    cta                 text,
    laenge_s            integer,
    full_script         text,                       -- Markdown rendering

    -- Pattern provenance
    referenz_reels      text[] DEFAULT ARRAY[]::text[],
    trend_basis         text,
    score_prediction    integer CHECK (score_prediction BETWEEN 1 AND 100),

    -- Post-posting performance
    posted_shortcode    text,                       -- if posted, link to actual reel
    performance         jsonb,                      -- views/er/etc nach posting

    created_by          text,
    created_at          timestamptz NOT NULL DEFAULT NOW(),
    updated_at          timestamptz NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_scripts_client ON scripts(client_id);
CREATE INDEX IF NOT EXISTS idx_scripts_status ON scripts(status);
CREATE INDEX IF NOT EXISTS idx_scripts_created ON scripts(created_at DESC);


-- ---------------------------------------------------------------------
-- 7. TABLE: playbooks (NEW — per-client content strategy)
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS playbooks (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id       text NOT NULL REFERENCES clients(slug) ON DELETE CASCADE,
    top_hooks       jsonb NOT NULL DEFAULT '[]'::jsonb,
    top_angles      jsonb NOT NULL DEFAULT '[]'::jsonb,
    posting_freq    text,
    benchmark       jsonb NOT NULL DEFAULT '{}'::jsonb,
    empfehlungen    jsonb NOT NULL DEFAULT '[]'::jsonb,
    generated_at    timestamptz NOT NULL DEFAULT NOW(),
    valid_until     timestamptz,
    created_by      text
);

CREATE INDEX IF NOT EXISTS idx_playbooks_client ON playbooks(client_id, generated_at DESC);


-- ---------------------------------------------------------------------
-- 8. TABLE: tracked_accounts (NEW — /ci-track targets)
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS tracked_accounts (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id       text NOT NULL REFERENCES clients(slug) ON DELETE CASCADE,
    handle          text NOT NULL,
    source          reel_source NOT NULL DEFAULT 'ig',
    is_own          boolean NOT NULL DEFAULT FALSE,
    last_scraped    timestamptz,
    reel_count      integer NOT NULL DEFAULT 0,
    interval_hours  integer NOT NULL DEFAULT 24 CHECK (interval_hours >= 1),
    active          boolean NOT NULL DEFAULT TRUE,
    created_by      text,
    created_at      timestamptz NOT NULL DEFAULT NOW(),

    CONSTRAINT tracked_unique UNIQUE (client_id, handle, source)
);

CREATE INDEX IF NOT EXISTS idx_tracked_active ON tracked_accounts(active, last_scraped);


-- ---------------------------------------------------------------------
-- 9. TABLE: embedding_versions (re-embed tracking)
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS embedding_versions (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    reel_id      uuid NOT NULL REFERENCES reels(id) ON DELETE CASCADE,
    model        text NOT NULL,
    dim          integer NOT NULL CHECK (dim > 0),
    column_name  text NOT NULL CHECK (column_name IN ('transcript_emb', 'hook_emb', 'summary_emb')),
    created_at   timestamptz NOT NULL DEFAULT NOW(),

    CONSTRAINT embedding_versions_unique UNIQUE (reel_id, column_name)
);

CREATE INDEX IF NOT EXISTS idx_embedding_versions_reel ON embedding_versions (reel_id);


-- ---------------------------------------------------------------------
-- 10. TRIGGERS
-- ---------------------------------------------------------------------

-- Auto-set mp4_expires_at on reel insert
CREATE OR REPLACE FUNCTION set_mp4_expires_at() RETURNS trigger AS $$
BEGIN
    IF NEW.r2_key IS NOT NULL AND NEW.mp4_expires_at IS NULL THEN
        NEW.mp4_expires_at := NOW() + INTERVAL '30 days';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_reels_set_mp4_expires ON reels;
CREATE TRIGGER trg_reels_set_mp4_expires
    BEFORE INSERT OR UPDATE OF r2_key ON reels
    FOR EACH ROW EXECUTE FUNCTION set_mp4_expires_at();

-- updated_at auto-update on clients + scripts
CREATE OR REPLACE FUNCTION touch_updated_at() RETURNS trigger AS $$
BEGIN
    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_clients_touch ON clients;
CREATE TRIGGER trg_clients_touch
    BEFORE UPDATE ON clients
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

DROP TRIGGER IF EXISTS trg_scripts_touch ON scripts;
CREATE TRIGGER trg_scripts_touch
    BEFORE UPDATE ON scripts
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();


-- ---------------------------------------------------------------------
-- 11. UTILITY FUNCTIONS
-- ---------------------------------------------------------------------

CREATE OR REPLACE FUNCTION cleanup_expired_mp4() RETURNS TABLE(cleaned_count bigint) AS $$
DECLARE n bigint;
BEGIN
    UPDATE reels
    SET r2_key = NULL, video_url_cdn = NULL, thumbnail_url = NULL
    WHERE mp4_expires_at < NOW() AND r2_key IS NOT NULL;
    GET DIAGNOSTICS n = ROW_COUNT;
    RETURN QUERY SELECT n;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION requeue_failed_jobs() RETURNS TABLE(requeued_count bigint) AS $$
DECLARE n bigint;
BEGIN
    UPDATE jobs
    SET status = 'queued', last_error = NULL, started_at = NULL, finished_at = NULL
    WHERE status = 'failed' AND attempts < 3
      AND finished_at < NOW() - INTERVAL '5 minutes';
    GET DIAGNOSTICS n = ROW_COUNT;
    RETURN QUERY SELECT n;
END;
$$ LANGUAGE plpgsql;


COMMIT;

-- =====================================================================
-- END Migration 001
-- =====================================================================
-- Verify:
--   SELECT extname FROM pg_extension WHERE extname IN ('vector','pgcrypto','pg_trgm');
--   SELECT table_name FROM information_schema.tables
--     WHERE table_schema = 'public' AND table_name IN
--     ('clients','reels','jobs','scripts','playbooks','tracked_accounts','embedding_versions');
-- =====================================================================
