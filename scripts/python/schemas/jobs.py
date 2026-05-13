"""Job-tracking schemas for pipeline execution."""

from datetime import datetime
from enum import Enum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    QUEUED = "queued"
    SCRAPING = "scraping"
    DOWNLOADING = "downloading"
    ANALYZING = "analyzing"
    EMBEDDING = "embedding"
    STORED = "stored"
    FAILED = "failed"


class IngestRequest(BaseModel):
    url: str = Field(..., description="IG Reel / TikTok URL or shortcode")
    priority: int = Field(default=10, ge=0, le=20)
    source: Literal["ig", "tiktok"] = "ig"
    force_refresh: bool = False
    client_id: str | None = None
    metadata: dict = Field(default_factory=dict)


class IngestResponse(BaseModel):
    job_id: UUID
    shortcode: str
    status: JobStatus
    message: str


class Job(BaseModel):
    id: UUID
    shortcode: str
    source: str
    status: JobStatus
    priority: int
    attempts: int
    last_error: str | None
    enqueued_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    metadata: dict
