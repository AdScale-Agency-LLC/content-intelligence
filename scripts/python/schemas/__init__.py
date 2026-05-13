"""Pydantic schemas for ReelAnalysis + Jobs."""

from schemas.reel import (
    Angle,
    ColorMood,
    ColorPalette,
    CTAElement,
    Emotion,
    EmotionSegment,
    Hook,
    HookType,
    OverallScore,
    ReelAnalysis,
    SimilarityMatch,
    SimilarityQuery,
    TextOverlay,
    TranscriptSegment,
    VisualPatterns,
)
from schemas.jobs import IngestRequest, IngestResponse, Job, JobStatus

__all__ = [
    "Angle",
    "ColorMood",
    "ColorPalette",
    "CTAElement",
    "Emotion",
    "EmotionSegment",
    "Hook",
    "HookType",
    "IngestRequest",
    "IngestResponse",
    "Job",
    "JobStatus",
    "OverallScore",
    "ReelAnalysis",
    "SimilarityMatch",
    "SimilarityQuery",
    "TextOverlay",
    "TranscriptSegment",
    "VisualPatterns",
]
