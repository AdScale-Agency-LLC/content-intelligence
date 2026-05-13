"""Plugin configuration (env-driven via Pydantic Settings).

Reads from ~/.config/content-intel/.env (created by /ci-setup).
Falls back to OS environment variables.

Optional fields (SUPABASE, R2, MONDAY) are tolerated as empty strings during
preflight checks — only GEMINI + APIFY are strictly required for Phase 0/1.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

CONFIG_DIR = Path.home() / ".config" / "content-intel"
ENV_FILE = CONFIG_DIR / ".env"
LOCAL_DB_FILE = CONFIG_DIR / "ci.db"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Core
    app_env: Literal["local", "staging", "prod"] = "local"
    log_level: str = "INFO"

    # User identity (for created_by tracking in shared DB)
    ci_user: str = Field(default_factory=lambda: os.environ.get("USER") or os.environ.get("USERNAME") or "unknown")

    # Gemini — required for analyze
    gemini_api_key: SecretStr = SecretStr("")
    gemini_model_analysis: str = "gemini-2.5-flash"
    gemini_model_embedding: str = "gemini-embedding-001"
    gemini_embedding_dim: int = Field(default=1536, ge=128, le=3072)

    # Apify — required for scrape
    apify_api_token: SecretStr = SecretStr("")
    apify_reel_actor: str = "apify/instagram-reel-scraper"
    apify_bulk_actor: str = "apidojo/instagram-scraper"
    apify_profile_actor: str = "apify/instagram-profile-scraper"  # Phase 4 /ci-track
    apify_tiktok_actor: str = "clockworks/tiktok-scraper"  # Default paid
    apify_tiktok_actor_free: str = "clockworks/free-tiktok-scraper"  # Fallback free
    apify_youtube_actor: str = "streamers/youtube-scraper"  # Phase 5+ YT Shorts
    apify_gmaps_actor: str = "compass/crawler-google-places"  # Phase 5+ Local-Business

    # Supabase — required for shared team-DB
    supabase_url: str = ""
    supabase_service_role_key: SecretStr = SecretStr("")
    supabase_db_url: SecretStr = SecretStr("")

    # Cloudflare R2 — Phase 5 only (tracking)
    r2_account_id: str = ""
    r2_access_key_id: SecretStr = SecretStr("")
    r2_secret_access_key: SecretStr = SecretStr("")
    r2_bucket_name: str = "content-intelligence"

    # Pipeline
    video_retention_days: int = 30
    max_concurrent_gemini: int = 5
    gemini_timeout_s: int = 300

    # Outputs (optional)
    monday_api_token: SecretStr = SecretStr("")
    monday_board_id: int = 5015883570
    slack_webhook_url: str = ""

    @property
    def r2_endpoint_url(self) -> str:
        return f"https://{self.r2_account_id}.r2.cloudflarestorage.com"

    def has_gemini(self) -> bool:
        return bool(self.gemini_api_key.get_secret_value())

    def has_apify(self) -> bool:
        return bool(self.apify_api_token.get_secret_value())

    def has_supabase(self) -> bool:
        return bool(self.supabase_db_url.get_secret_value()) and bool(self.supabase_url)

    def has_r2(self) -> bool:
        return bool(self.r2_account_id) and bool(self.r2_access_key_id.get_secret_value())


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Singleton settings accessor."""
    return Settings()


def ensure_config_dir() -> None:
    """Create ~/.config/content-intel/ if missing."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
