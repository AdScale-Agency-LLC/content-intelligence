"""Scraper + video downloader step of the pipeline."""

from __future__ import annotations

import logging
import re
import tempfile
from pathlib import Path

import aiofiles
import httpx

from clients.apify import ApifyClient, ScrapedReel

logger = logging.getLogger(__name__)

_IG_SHORTCODE_RX = re.compile(r"/(reel|p|reels)/([A-Za-z0-9_-]+)")
_TIKTOK_ID_RX = re.compile(r"/video/(\d+)")


def extract_shortcode(url: str) -> str:
    """Pull shortcode/ID out of an IG or TikTok URL."""
    # IG patterns
    m = _IG_SHORTCODE_RX.search(url)
    if m:
        return m.group(2)
    # TikTok pattern
    m = _TIKTOK_ID_RX.search(url)
    if m:
        return m.group(1)
    # Last-segment fallback
    clean = url.strip().rstrip("/").split("/")[-1]
    if re.fullmatch(r"[A-Za-z0-9_-]+", clean):
        return clean
    raise ValueError(f"Cannot extract shortcode from: {url}")


class ReelScraper:
    """Apify-backed scraper + CDN video downloader."""

    def __init__(self, apify: ApifyClient, download_dir: str | Path | None = None) -> None:
        self.apify = apify
        self.download_dir = (
            Path(download_dir) if download_dir else Path(tempfile.gettempdir()) / "content_intel"
        )
        self.download_dir.mkdir(parents=True, exist_ok=True)

    async def fetch_by_url(self, url: str) -> ScrapedReel:
        return await self.apify.scrape_reel_url(url)

    # Hard cap to prevent disk-fill from malicious/misconfigured CDN
    MAX_VIDEO_BYTES = 250 * 1024 * 1024  # 250 MB

    async def download_video(
        self, reel: ScrapedReel, timeout_s: float = 120.0, max_bytes: int | None = None
    ) -> Path:
        """Download CDN video to local temp file. Caller is responsible for cleanup.

        Writes to a .partial file and renames on success — prevents truncated cache
        from being reused after an interrupted previous run.
        """
        out = self.download_dir / f"{reel.shortcode}.mp4"
        # Accept cache only if .partial sibling is absent (i.e. previous write completed)
        partial = out.with_suffix(".mp4.partial")
        if out.exists() and out.stat().st_size > 0 and not partial.exists():
            return out

        cap = max_bytes or self.MAX_VIDEO_BYTES
        total = 0
        async with httpx.AsyncClient(timeout=timeout_s, follow_redirects=True) as client:
            async with client.stream("GET", reel.video_url_cdn) as resp:
                resp.raise_for_status()
                async with aiofiles.open(partial, "wb") as fh:
                    async for chunk in resp.aiter_bytes(chunk_size=1024 * 256):
                        total += len(chunk)
                        if total > cap:
                            await fh.close()
                            partial.unlink(missing_ok=True)
                            raise RuntimeError(
                                f"Video exceeds max size {cap // 1024 // 1024} MB "
                                f"(shortcode={reel.shortcode})"
                            )
                        await fh.write(chunk)

        # Atomic rename: only swap into final path if download fully succeeded
        partial.replace(out)

        size_mb = out.stat().st_size / (1024 * 1024)
        logger.info(
            "scraper.download.done",
            extra={"shortcode": reel.shortcode, "size_mb": round(size_mb, 2), "path": str(out)},
        )
        return out
