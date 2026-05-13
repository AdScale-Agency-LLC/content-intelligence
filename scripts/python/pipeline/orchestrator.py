"""End-to-end pipeline orchestrator (SQLite primary store).

Flow per reel:
  1. Apify scrape (metadata + CDN URL)
  2. Download video to local temp
  3. Upload to Gemini File API
  4. Gemini analysis (ReelAnalysis structured JSON)
  5. Gemini embeddings (transcript / hook / summary)
  6. Upsert into LocalDB (SQLite) with client_id + is_own + created_by
  7. Cleanup local file
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from config import get_settings
from db.local_db import LocalDB, get_local_db
from pipeline.analyzer import ReelAnalyzer
from pipeline.scraper import ReelScraper, extract_shortcode
from schemas.reel import ReelAnalysis

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PipelineResult:
    reel_id: str
    shortcode: str
    account: str
    source: str
    analysis: ReelAnalysis


class ReelPipeline:
    """Composed end-to-end pipeline."""

    def __init__(
        self,
        scraper: ReelScraper,
        analyzer: ReelAnalyzer,
        db: LocalDB | None = None,
    ) -> None:
        self.scraper = scraper
        self.analyzer = analyzer
        self.db = db or get_local_db()

    async def process_url(
        self,
        url: str,
        *,
        client_id: str | None = None,
        is_own: bool = False,
        client_context: str | None = None,
        delete_local: bool = True,
    ) -> PipelineResult:
        s = get_settings()
        shortcode = extract_shortcode(url)
        job_id = self.db.enqueue_job(shortcode, client_id=client_id)

        local_path: Path | None = None
        try:
            # 1+2. Scrape + download
            self.db.update_job_status(job_id, "scraping")
            reel = await self.scraper.fetch_by_url(url)

            self.db.update_job_status(job_id, "downloading")
            local_path = await self.scraper.download_video(reel)

            # 3+4. Gemini analysis
            self.db.update_job_status(job_id, "analyzing")
            analysis = await self.analyzer.analyze(
                local_path,
                caption=reel.caption,
                account=reel.account,
                client_context=client_context,
            )

            # 5. Embeddings
            self.db.update_job_status(job_id, "embedding")
            embeddings = await self.analyzer.embed_analysis(analysis)

            # 6. DB upsert (SQLite)
            metadata = reel.model_dump()
            metadata["url"] = url
            reel_id = self.db.upsert_reel(
                metadata=metadata,
                analysis=analysis.model_dump(mode="json"),
                embeddings=embeddings,
                client_id=client_id,
                is_own=is_own,
                created_by=s.ci_user,
            )
            self.db.update_job_status(job_id, "stored")

            logger.info(
                "pipeline.done",
                extra={
                    "shortcode": reel.shortcode,
                    "account": reel.account,
                    "reel_id": reel_id,
                    "client_id": client_id,
                    "hook_score": analysis.hook.strength_score,
                },
            )
            return PipelineResult(
                reel_id=reel_id,
                shortcode=reel.shortcode,
                account=reel.account,
                source=reel.source,
                analysis=analysis,
            )

        except Exception as e:
            self.db.update_job_status(job_id, "failed", str(e))
            logger.exception("pipeline.failed", extra={"shortcode": shortcode, "error": str(e)})
            raise

        finally:
            if delete_local and local_path is not None:
                try:
                    local_path.unlink(missing_ok=True)
                except OSError as e:
                    logger.warning(
                        "pipeline.cleanup.failed",
                        extra={"path": str(local_path), "error": str(e)},
                    )


def build_pipeline() -> ReelPipeline:
    """Factory: build a complete pipeline with default deps."""
    from clients.apify import ApifyClient
    from clients.gemini import GeminiClient
    apify = ApifyClient()
    gemini = GeminiClient()
    scraper = ReelScraper(apify)
    analyzer = ReelAnalyzer(gemini)
    return ReelPipeline(scraper, analyzer)
