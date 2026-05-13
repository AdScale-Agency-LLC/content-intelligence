"""Script Generator — kombiniert Klienten-Profil + Top-Performer + Trends → Skript.

Workflow:
  1. Klienten-Profil laden (Tonalitaet, Zielgruppe, Branche, Do's/Don'ts)
  2. Top-N Performer aus DB ziehen (eigene + Competitor mix)
  3. Aktuelle Trends aggregieren
  4. Prompt zusammenbauen mit Few-Shot-Examples
  5. Gemini generate_content mit Pydantic-Schema
  6. Script in DB speichern
  7. Markdown-Rendering fuer User-Output
"""

from __future__ import annotations

import json
import logging
from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from clients.gemini import GeminiClient
from db.local_db import get_local_db
from schemas.reel import Angle, HookType

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


# ============================================================
# Output Schema
# ============================================================


class ScenePurpose(str, Enum):
    HOOK = "hook"
    SETUP = "setup"
    PAYOFF = "payoff"
    CTA = "cta"
    TRANSITION = "transition"
    BUILD = "build"


class Scene(BaseModel):
    nummer: int = Field(..., ge=1)
    zeitspanne_s: str = Field(..., description="z.B. '0-3' oder '15-18'")
    visual: str = Field(..., description="Was sieht der Viewer")
    audio: str = Field(..., description="Was wird gesagt / welche Musik")
    text_overlay: str | None = Field(None, description="On-Screen-Text (falls noetig)")
    purpose: ScenePurpose


class GeneratedScript(BaseModel):
    hook_text: str = Field(..., description="Exakter Hook-Text (gesprochen oder eingeblendet)")
    hook_type: HookType
    angle: Angle
    szenen: list[Scene] = Field(..., min_length=2, max_length=10)
    cta_text: str = Field(..., description="Konkreter Call-to-Action")
    cta_type: Literal["implicit", "explicit", "urgent"]
    laenge_s: int = Field(..., ge=7, le=180)
    score_prediction: int = Field(..., ge=1, le=100)
    score_reasoning: str = Field(..., max_length=400)
    referenz_shortcodes: list[str] = Field(default_factory=list, max_length=10)
    rationale: str = Field(..., max_length=800)


# ============================================================
# Context Assembly
# ============================================================


def _format_top_performer(reel: dict, max_chars: int = 350) -> str:
    """Format a reel as a compact reference line for the prompt."""
    score = reel.get("hook_score", 0)
    htype = reel.get("hook_type", "?")
    text = reel.get("hook_text") or f"(visual: {reel.get('hook_visual', '?')[:80]})"
    angle = reel.get("angle", "?")
    reasoning = (reel.get("hook_reasoning") or "")[:150]
    views = reel.get("views") or 0
    summary = (reel.get("summary") or "")[:120]
    return (
        f"- shortcode={reel['shortcode']} score={score}/100 type={htype} angle={angle} views={views}\n"
        f"  hook: {text!r}\n"
        f"  why: {reasoning}\n"
        f"  summary: {summary}"
    )[:max_chars]


def gather_context(
    client_slug: str | None,
    thema: str,
    constraint_hook_type: str | None = None,
    constraint_angle: str | None = None,
    top_n: int = 12,
) -> tuple[str, list[str]]:
    """Build the full prompt context and return (prompt_addition, referenced_shortcodes)."""
    db = get_local_db()
    lines: list[str] = []
    referenced: list[str] = []

    # 1. Client profile
    if client_slug:
        client = db.get_client_by_slug(client_slug)
        if client:
            lines.append(f"## Klient: {client['name']}")
            if client.get("branche"):
                lines.append(f"Branche: {client['branche']}")
            if client.get("zielgruppe"):
                lines.append(f"Zielgruppe: {client['zielgruppe']}")
            if client.get("tonalitaet"):
                lines.append(f"Tonalitaet: {client['tonalitaet']}")
            if client.get("dos"):
                lines.append(f"Do's: {', '.join(client['dos'])}")
            if client.get("donts"):
                lines.append(f"Don'ts: {', '.join(client['donts'])}")
            lines.append("")

    # 2. Thema
    lines.append(f"## Thema")
    lines.append(thema)
    lines.append("")

    # 3. Constraints
    if constraint_hook_type or constraint_angle:
        lines.append("## Constraints")
        if constraint_hook_type:
            lines.append(f"- Hook-Type muss sein: {constraint_hook_type}")
        if constraint_angle:
            lines.append(f"- Angle muss sein: {constraint_angle}")
        lines.append("")

    # 4. Top performers (eigene + branche)
    top_own = db.list_reels(client_id=client_slug, is_own=True, min_score=60, limit=top_n // 2) if client_slug else []
    top_comp = db.list_reels(client_id=client_slug, is_own=False, min_score=70, limit=top_n - len(top_own)) if client_slug else []

    if top_own or top_comp:
        lines.append("## Top-Performer (Inspiration aus DB)")
        if top_own:
            lines.append("### Eigene Top-Reels:")
            for r in top_own:
                lines.append(_format_top_performer(r))
                referenced.append(r["shortcode"])
            lines.append("")
        if top_comp:
            lines.append("### Competitor/Branche Top-Reels:")
            for r in top_comp:
                lines.append(_format_top_performer(r))
                referenced.append(r["shortcode"])
            lines.append("")
    else:
        # Fallback: use top across all reels
        all_top = db.list_reels(min_score=75, limit=top_n)
        if all_top:
            lines.append("## Top-Performer (allgemeine Inspiration — kein Klient-spezifischer Datensatz)")
            for r in all_top:
                lines.append(_format_top_performer(r))
                referenced.append(r["shortcode"])
            lines.append("")
        else:
            lines.append("## Hinweis")
            lines.append("Keine Top-Performer-Daten in der DB. Skript basiert auf allgemeinem Best-Practice.")
            lines.append("")

    return "\n".join(lines), referenced


# ============================================================
# Generation
# ============================================================


async def generate_script(
    thema: str,
    client_slug: str | None = None,
    constraint_hook_type: str | None = None,
    constraint_angle: str | None = None,
    temperature: float = 0.4,
) -> tuple[GeneratedScript, list[str]]:
    """Generate a script. Returns (GeneratedScript, referenced_shortcodes)."""
    prompt_file = _PROMPTS_DIR / "script_gen.md"
    if not prompt_file.exists():
        raise FileNotFoundError(f"Script prompt missing: {prompt_file}")
    system_prompt = prompt_file.read_text(encoding="utf-8")

    context_text, referenced = gather_context(
        client_slug=client_slug,
        thema=thema,
        constraint_hook_type=constraint_hook_type,
        constraint_angle=constraint_angle,
    )

    user_prompt = (
        f"Hier ist der Kontext:\n\n{context_text}\n\n"
        f"Generiere jetzt das Reel-Skript als JSON nach Schema."
    )

    full_prompt = system_prompt + "\n\n" + user_prompt

    gemini = GeminiClient()

    logger.info("script_gen.start", extra={"client": client_slug, "thema": thema[:80]})
    # Uses retry + empty-response guard from GeminiClient
    script = await gemini.generate_structured(
        prompt=full_prompt,
        schema=GeneratedScript,
        temperature=temperature,
        max_output_tokens=4096,
    )

    logger.info(
        "script_gen.done",
        extra={
            "hook_type": script.hook_type.value,
            "angle": script.angle.value,
            "score_prediction": script.score_prediction,
            "n_scenes": len(script.szenen),
        },
    )
    return script, referenced


# ============================================================
# Rendering
# ============================================================


def render_markdown(script: GeneratedScript, thema: str, client_name: str | None = None) -> str:
    """Render script as readable Markdown."""
    lines = []
    h = f"# Reel-Skript: {thema}"
    if client_name:
        h += f" — {client_name}"
    lines.append(h)
    lines.append("")
    lines.append(f"**Score-Prediction:** {script.score_prediction}/100")
    lines.append(f"**Hook-Type:** {script.hook_type.value}  |  **Angle:** {script.angle.value}  |  **Laenge:** ~{script.laenge_s}s")
    lines.append("")
    lines.append(f"**Score-Reasoning:** {script.score_reasoning}")
    lines.append("")

    lines.append(f"## Hook")
    lines.append(f"> {script.hook_text}")
    lines.append("")

    lines.append("## Szenen-Breakdown")
    for s in script.szenen:
        lines.append(f"### Szene {s.nummer} ({s.zeitspanne_s}s) — {s.purpose.value}")
        lines.append(f"- **Visual:** {s.visual}")
        lines.append(f"- **Audio:** {s.audio}")
        if s.text_overlay:
            lines.append(f"- **Text-Overlay:** {s.text_overlay}")
        lines.append("")

    lines.append(f"## CTA ({script.cta_type})")
    lines.append(f"> {script.cta_text}")
    lines.append("")

    if script.referenz_shortcodes:
        lines.append("## Referenz-Reels")
        for sc in script.referenz_shortcodes:
            lines.append(f"- `{sc}`")
        lines.append("")

    lines.append("## Rationale")
    lines.append(script.rationale)

    return "\n".join(lines)


def save_script(
    script: GeneratedScript,
    client_slug: str,
    thema: str,
    full_markdown: str,
    trend_basis: str | None = None,
    created_by: str | None = None,
) -> str:
    """Save the generated script to the DB. Returns script ID."""
    db = get_local_db()
    sid = db.insert_script(
        client_id=client_slug,
        thema=thema,
        hook_text=script.hook_text,
        hook_type=script.hook_type.value,
        angle=script.angle.value,
        szenen=[s.model_dump() for s in script.szenen],
        cta=f"[{script.cta_type}] {script.cta_text}",
        laenge_s=script.laenge_s,
        full_script=full_markdown,
        referenz_reels=script.referenz_shortcodes,
        trend_basis=trend_basis,
        score_prediction=script.score_prediction,
        created_by=created_by,
    )
    return sid
