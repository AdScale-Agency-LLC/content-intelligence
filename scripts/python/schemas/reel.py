"""Comprehensive ReelAnalysis schema - passed to Gemini as response_schema."""

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class HookType(str, Enum):
    QUESTION = "question"
    SHOCK = "shock"
    PATTERN_INTERRUPT = "pattern_interrupt"
    SOCIAL_PROOF = "social_proof"
    PROBLEM = "problem"
    LISTICLE = "listicle"
    STORY = "story"
    DEMONSTRATION = "demonstration"
    TRANSFORMATION = "transformation"
    OTHER = "other"


class Emotion(str, Enum):
    JOY = "joy"
    SURPRISE = "surprise"
    URGENCY = "urgency"
    TRUST = "trust"
    FOMO = "fomo"
    FEAR = "fear"
    ANGER = "anger"
    CURIOSITY = "curiosity"
    PRIDE = "pride"
    NEUTRAL = "neutral"


class ColorMood(str, Enum):
    WARM = "warm"
    COOL = "cool"
    HIGH_CONTRAST = "high_contrast"
    PASTEL = "pastel"
    MONOCHROME = "monochrome"
    VIBRANT = "vibrant"


class Angle(str, Enum):
    PROBLEM_SOLUTION = "problem_solution"
    LISTICLE = "listicle"
    STORY = "story"
    DEMONSTRATION = "demonstration"
    TRANSFORMATION = "transformation"
    EDUCATIONAL = "educational"
    ENTERTAINMENT = "entertainment"
    TESTIMONIAL = "testimonial"
    UGC = "ugc"
    OTHER = "other"


class Hook(BaseModel):
    type: HookType = Field(..., description="Hook-Typ (Enum)")
    text: str | None = Field(
        None, description="Hook-Text (exaktes Zitat) wenn gesprochen oder eingeblendet"
    )
    visual_element: str = Field(..., description="Was sieht der Viewer in den ersten 3s?")
    strength_score: int = Field(..., ge=1, le=100, description="Hook-Staerke 1-100")
    reasoning: str = Field(
        ..., max_length=400, description="Warum funktioniert dieser Hook? (max 2 Saetze)"
    )


class VisualPatterns(BaseModel):
    cut_frequency_per_10s: float = Field(..., ge=0, description="Durchschnittliche Schnitte/10s")
    dominant_camera_perspective: Literal[
        "selfie", "third_person", "overhead", "product_closeup", "mixed"
    ]
    zoom_events_count: int = Field(..., ge=0)
    transitions: list[str] = Field(
        default_factory=list, description="Transition-Typen, z.B. cut, fade, whip, match_cut"
    )


class TextOverlay(BaseModel):
    timestamp_s: float = Field(..., ge=0)
    position: Literal["top", "center", "bottom", "left", "right"]
    text: str
    purpose: Literal["caption", "emphasis", "cta", "context", "joke", "brand", "other"]


class EmotionSegment(BaseModel):
    start_s: float = Field(..., ge=0)
    end_s: float = Field(..., ge=0)
    emotion: Emotion
    intensity: Literal["low", "medium", "high"]


class ColorPalette(BaseModel):
    primary_hex: list[str] = Field(
        ..., min_length=1, max_length=5, description="3-5 dominante Hex-Farben"
    )
    overall_mood: ColorMood
    brand_consistent: bool = Field(..., description="Konsistente Brand-Farbwelt erkennbar?")


class CTAElement(BaseModel):
    timestamp_s: float = Field(..., ge=0)
    type: Literal["verbal", "visual", "both"]
    content: str = Field(..., description="Exakter CTA-Inhalt")
    position: str | None = None
    strength: Literal["implicit", "explicit", "urgent"]


class TranscriptSegment(BaseModel):
    start_s: float = Field(..., ge=0)
    end_s: float = Field(..., ge=0)
    text: str
    speaker: str | None = None


class OverallScore(BaseModel):
    retention_prediction: int = Field(
        ..., ge=1, le=100, description="Vorhergesagte Retention in %"
    )
    hook_strength: int = Field(..., ge=1, le=100)
    visual_quality: int = Field(..., ge=1, le=100)
    cta_clarity: int = Field(..., ge=1, le=100)
    improvements: list[str] = Field(
        ...,
        min_length=1,
        max_length=5,
        description="3-5 konkrete Verbesserungsvorschlaege, keine Generics",
    )


class ReelAnalysis(BaseModel):
    """Komplette Gemini-Video-Analyse eines einzelnen Reels.

    Passed to Gemini als response_schema - Output-Format ist JSON.
    """

    # Metadata
    language: str = Field(..., description="ISO-639-1, z.B. 'de', 'en', 'mixed'")
    duration_s: float = Field(..., ge=0)
    summary: str = Field(..., max_length=600, description="1-3 Saetze, was passiert im Reel")
    angle: Angle

    # Core Analysis
    hook: Hook
    visual_patterns: VisualPatterns
    text_overlays: list[TextOverlay] = Field(default_factory=list)
    emotions: list[EmotionSegment] = Field(default_factory=list)
    color_palette: ColorPalette
    scene_changes_s: list[float] = Field(
        default_factory=list, description="Timestamps aller Schnitte in Sekunden"
    )
    cta_elements: list[CTAElement] = Field(default_factory=list)
    music_sync_events_s: list[float] = Field(
        default_factory=list, description="Timestamps wo Schnitte auf Beat fallen"
    )

    # Transcript (Gemini parst Audio mit)
    transcript_full: str = Field(..., description="Komplettes Transkript, Original-Sprache(n)")
    transcript_segments: list[TranscriptSegment] = Field(default_factory=list)

    # Score
    score: OverallScore

    # Derived
    content_themes: list[str] = Field(
        default_factory=list,
        max_length=10,
        description="3-10 Themen-Tags, deutsch lowercase",
    )
    target_audience_hint: str | None = Field(
        None, description="Wenn ableitbar: Zielgruppen-Hypothese"
    )


class SimilarityQuery(BaseModel):
    """Input fuer Semantic-Search-Endpoint."""

    query_text: str
    query_type: Literal["hook", "transcript", "summary"] = "hook"
    top_k: int = Field(default=10, ge=1, le=100)
    min_score: float | None = Field(None, ge=0, le=1)
    filter_account: str | None = None
    filter_angle: Angle | None = None
    filter_client_id: str | None = None


class SimilarityMatch(BaseModel):
    shortcode: str
    account: str
    similarity: float
    hook_text: str | None
    summary: str
    views: int | None
    posted_at: str | None
    client_id: str | None = None
