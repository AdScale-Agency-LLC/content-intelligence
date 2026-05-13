"""Core Gemini-powered reel analyzer + embedding generator.

Prompt location: ${CLAUDE_PLUGIN_ROOT}/scripts/python/prompts/reel_analysis.md
Resolves robustly via __file__ — works regardless of where Python is invoked from.
"""

from __future__ import annotations

import logging
from pathlib import Path

from clients.gemini import GeminiClient
from schemas.reel import ReelAnalysis

logger = logging.getLogger(__name__)

# Robust path resolution: this file lives at scripts/python/pipeline/analyzer.py
# Prompts are at scripts/python/prompts/ → ../prompts/
_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


class AnalyzerError(Exception):
    pass


class ReelAnalyzer:
    """Single-call Gemini pipeline: video -> ReelAnalysis (structured JSON)."""

    def __init__(self, gemini: GeminiClient, prompt_path: Path | None = None) -> None:
        self.gemini = gemini
        path = prompt_path or _PROMPTS_DIR / "reel_analysis.md"
        if not path.exists():
            raise AnalyzerError(
                f"Prompt file missing: {path}. "
                "The plugin is corrupted — reinstall."
            )
        self._system_prompt = path.read_text(encoding="utf-8")

    async def analyze(
        self,
        video_path: str | Path,
        caption: str | None = None,
        account: str | None = None,
        client_context: str | None = None,
    ) -> ReelAnalysis:
        """Upload + analyze a single reel. Deletes the uploaded Gemini file after."""
        file = await self.gemini.upload_video(video_path)
        try:
            prompt = self._system_prompt
            ctx_parts: list[str] = []
            if account:
                ctx_parts.append(f"Account: @{account}")
            if caption:
                ctx_parts.append(f"Original-Caption: {caption[:500]}")
            if client_context:
                ctx_parts.append(f"Klienten-Kontext: {client_context}")
            if ctx_parts:
                prompt += "\n\n### Kontext\n" + "\n".join(ctx_parts)

            analysis = await self.gemini.analyze_video(
                video_file=file,
                prompt=prompt,
                schema=ReelAnalysis,
                temperature=0.2,
            )
            logger.info(
                "analyzer.done",
                extra={
                    "hook_type": analysis.hook.type.value,
                    "hook_score": analysis.hook.strength_score,
                    "retention": analysis.score.retention_prediction,
                    "language": analysis.language,
                    "angle": analysis.angle.value,
                },
            )
            return analysis
        finally:
            await self.gemini.delete_file(file.name)

    async def embed_analysis(self, analysis: ReelAnalysis) -> dict[str, list[float]]:
        """Generate the three storage embeddings (transcript, hook, summary)."""
        hook_text = analysis.hook.text or analysis.hook.visual_element or ""
        texts = [
            analysis.transcript_full or analysis.summary,
            f"{analysis.hook.type.value}: {hook_text}. Reasoning: {analysis.hook.reasoning}",
            analysis.summary,
        ]
        vectors = await self.gemini.embed(texts, task_type="RETRIEVAL_DOCUMENT")
        return {
            "transcript_emb": vectors[0],
            "hook_emb": vectors[1],
            "summary_emb": vectors[2],
        }

    async def embed_query(self, text: str) -> list[float]:
        """Embed a search query (asymmetric retrieval)."""
        vectors = await self.gemini.embed([text], task_type="RETRIEVAL_QUERY")
        return vectors[0]
