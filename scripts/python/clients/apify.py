"""Apify client wrapper for Instagram + TikTok scraping.

BUG FIXES (vs. content-intelligence/src original — from Audit-A 2026-05-08):
  1. Type filter logic (line 119): previously `type not in (...) and not videoUrl`
     could miss valid reels — now: accept if videoUrl present OR type matches
  2. scrape_hashtag missing timeout_secs — added
  3. posted_at type coercion: handles both string ISO and unix timestamps
  4. .call() is async-blocking — kept as-is (it's the right API in apify-client async)
     but added explicit timeout on all three methods
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from apify_client import ApifyClientAsync
from pydantic import BaseModel, Field

from config import get_settings

logger = logging.getLogger(__name__)


class ApifyError(Exception):
    """Base Apify error."""


class ScrapedReel(BaseModel):
    """Normalized Apify reel output."""

    shortcode: str
    account: str
    caption: str = ""
    hashtags: list[str] = Field(default_factory=list)
    mentions: list[str] = Field(default_factory=list)
    video_url_cdn: str
    thumbnail_url: str = ""
    duration_s: float = 0.0
    posted_at: str | None = None
    views: int | None = None
    likes: int | None = None
    comments: int | None = None
    saves: int | None = None
    shares: int | None = None
    audio_id: str | None = None
    audio_title: str | None = None
    audio_artist: str | None = None
    account_followers: int | None = None
    source: str = "ig"
    raw: dict = Field(default_factory=dict)


def _coerce_posted_at(raw: Any) -> str | None:
    """Convert various Apify timestamp formats to ISO string.

    Apify actors return EITHER an ISO string ("2026-04-15T12:34:56Z") OR a unix
    timestamp (int/float seconds). We normalize to ISO 8601 UTC.
    """
    if raw is None:
        return None
    if isinstance(raw, str):
        return raw  # assume already ISO
    if isinstance(raw, (int, float)):
        try:
            return datetime.fromtimestamp(raw, tz=timezone.utc).isoformat()
        except (ValueError, OSError, OverflowError):
            return None
    return str(raw)


def _normalize_reel(raw: dict[str, Any], source: str = "ig") -> ScrapedReel:
    """Apify actors return slightly different shapes - normalize here."""
    shortcode = (
        raw.get("shortCode") or raw.get("shortcode") or raw.get("id")
        or raw.get("aweme_id") or ""
    )
    if not shortcode:
        raise ValueError(f"No shortcode/id in reel: keys={list(raw.keys())[:10]}")
    video_url = (
        raw.get("videoUrl")
        or raw.get("downloadedVideo")
        or raw.get("video_url")
        or raw.get("videoMeta", {}).get("downloadAddr")  # TikTok
        or ""
    )
    if not video_url:
        raise ValueError(f"No video URL in reel: shortcode={shortcode}")

    music_info = raw.get("musicInfo") or {}

    return ScrapedReel(
        shortcode=shortcode,
        account=raw.get("ownerUsername") or raw.get("username") or raw.get("owner", ""),
        caption=raw.get("caption") or raw.get("text") or "",
        hashtags=raw.get("hashtags") or [],
        mentions=raw.get("mentions") or [],
        video_url_cdn=video_url,
        thumbnail_url=raw.get("displayUrl") or raw.get("thumbnail_url", "") or raw.get("cover", ""),
        duration_s=float(raw.get("videoDuration") or raw.get("duration", 0) or 0),
        posted_at=_coerce_posted_at(raw.get("timestamp") or raw.get("takenAt") or raw.get("createTime")),
        views=raw.get("videoViewCount") or raw.get("videoPlayCount") or raw.get("views") or raw.get("playCount"),
        likes=raw.get("likesCount") or raw.get("likes") or raw.get("diggCount"),
        comments=raw.get("commentsCount") or raw.get("comments") or raw.get("commentCount"),
        saves=raw.get("savesCount") or raw.get("saves") or raw.get("collectCount"),
        shares=raw.get("sharesCount") or raw.get("shares") or raw.get("shareCount"),
        audio_id=music_info.get("audio_id") or raw.get("audioId"),
        audio_title=music_info.get("song_name") or raw.get("musicMeta", {}).get("musicName"),
        audio_artist=music_info.get("artist_name") or raw.get("musicMeta", {}).get("musicAuthor"),
        account_followers=raw.get("ownerFollowersCount") or raw.get("followersCount"),
        source=source,
        raw=raw,
    )


def _is_video_item(item: dict[str, Any]) -> bool:
    """Accept item if it's clearly a video/reel.

    BUG FIX: original logic rejected valid items where type wasn't set.
    New logic: accept if type matches OR videoUrl is present.
    """
    if item.get("videoUrl") or item.get("downloadedVideo"):
        return True
    item_type = item.get("type", "").lower()
    if item_type in ("video", "reel", "carousel-video"):
        return True
    if item.get("videoMeta") or item.get("videoPlayCount"):
        return True
    return False


class ApifyClient:
    """Async wrapper around ApifyClientAsync."""

    def __init__(self, token: str | None = None, prefer_free_tiktok: bool = False) -> None:
        s = get_settings()
        tok = token or s.apify_api_token.get_secret_value()
        if not tok:
            raise ApifyError("APIFY_API_TOKEN missing. Run /ci-setup to configure.")
        self._client = ApifyClientAsync(tok)
        self._reel_actor = s.apify_reel_actor
        self._bulk_actor = s.apify_bulk_actor
        self._profile_actor = s.apify_profile_actor
        # TikTok: paid actor by default, fallback to free if requested
        self._tiktok_actor = s.apify_tiktok_actor_free if prefer_free_tiktok else s.apify_tiktok_actor
        self._youtube_actor = s.apify_youtube_actor
        self._gmaps_actor = s.apify_gmaps_actor

    def _detect_source(self, url: str) -> str:
        """Detect platform from URL."""
        u = url.lower()
        if "tiktok.com" in u:
            return "tiktok"
        return "ig"

    async def scrape_reel_url(self, url: str, timeout_s: int = 180) -> ScrapedReel:
        """Scrape a single Reel/TikTok URL."""
        source = self._detect_source(url)
        logger.info("apify.reel.start", extra={"url": url, "source": source})

        if source == "tiktok":
            actor = self._tiktok_actor
            # clockworks/tiktok-scraper input shape (per Apify docs 2026)
            run_input = {
                "postURLs": [url],
                "resultsPerPage": 1,
                "shouldDownloadVideos": False,  # we download separately via httpx
                "shouldDownloadCovers": False,
                "shouldDownloadSubtitles": False,
                "shouldDownloadSlideshowImages": False,
            }
        else:
            actor = self._reel_actor
            run_input = {"directUrls": [url], "resultsLimit": 1}

        run = await self._client.actor(actor).call(
            run_input=run_input,
            timeout_secs=timeout_s,
        )
        if run is None or "defaultDatasetId" not in run:
            raise ApifyError(f"Apify run failed for {url}: {run}")
        status = (run.get("status") or "").upper()
        if status and status != "SUCCEEDED":
            msg = run.get("statusMessage") or ""
            raise ApifyError(f"Apify run status={status} for {url}: {msg[:200]}")

        items = [i async for i in self._client.dataset(run["defaultDatasetId"]).iterate_items()]
        if not items:
            raise ApifyError(f"Apify returned no items for {url}")

        reel = _normalize_reel(items[0], source=source)
        logger.info(
            "apify.reel.done",
            extra={"shortcode": reel.shortcode, "account": reel.account, "views": reel.views},
        )
        return reel

    async def scrape_account_top(
        self, username: str, limit: int = 30, timeout_s: int = 600
    ) -> list[ScrapedReel]:
        """Scrape top N reels from an IG account (bulk actor)."""
        logger.info("apify.account.start", extra={"username": username, "limit": limit})
        run = await self._client.actor(self._bulk_actor).call(
            run_input={
                "usernames": [username.lstrip("@")],
                "resultsType": "posts",
                "resultsLimit": limit,
                "onlyPostsNewerThan": "30 days",
            },
            timeout_secs=timeout_s,
        )
        if run is None or "defaultDatasetId" not in run:
            raise ApifyError(f"Apify account scrape failed for @{username}: {run}")
        status = (run.get("status") or "").upper()
        if status and status != "SUCCEEDED":
            msg = run.get("statusMessage") or ""
            raise ApifyError(f"Apify account scrape status={status} for @{username}: {msg[:200]}")

        items = [i async for i in self._client.dataset(run["defaultDatasetId"]).iterate_items()]
        reels: list[ScrapedReel] = []
        for item in items:
            if not _is_video_item(item):
                continue
            try:
                reels.append(_normalize_reel(item, source="ig"))
            except ValueError as e:
                logger.warning("apify.skip", extra={"error": str(e)})
        logger.info("apify.account.done", extra={"username": username, "count": len(reels)})
        return reels

    async def scrape_hashtag(
        self,
        hashtag: str,
        limit: int = 50,
        min_views: int | None = 10_000,
        timeout_s: int = 600,  # BUG FIX: was missing
    ) -> list[ScrapedReel]:
        """Scrape top reels under a hashtag, optionally filtered by min-views."""
        logger.info("apify.hashtag.start", extra={"hashtag": hashtag, "limit": limit})
        run = await self._client.actor(self._bulk_actor).call(
            run_input={
                "hashtags": [hashtag.lstrip("#")],
                "resultsType": "posts",
                "resultsLimit": limit,
            },
            timeout_secs=timeout_s,
        )
        if run is None or "defaultDatasetId" not in run:
            raise ApifyError(f"Apify hashtag scrape failed for #{hashtag}: {run}")
        status = (run.get("status") or "").upper()
        if status and status != "SUCCEEDED":
            msg = run.get("statusMessage") or ""
            raise ApifyError(f"Apify hashtag scrape status={status} for #{hashtag}: {msg[:200]}")

        items = [i async for i in self._client.dataset(run["defaultDatasetId"]).iterate_items()]
        reels: list[ScrapedReel] = []
        for item in items:
            if not _is_video_item(item):
                continue
            try:
                reel = _normalize_reel(item, source="ig")
                if min_views is not None and (reel.views or 0) < min_views:
                    continue
                reels.append(reel)
            except ValueError:
                continue
        logger.info("apify.hashtag.done", extra={"hashtag": hashtag, "count": len(reels)})
        return reels
