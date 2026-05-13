"""Gemini 2.5 File API client - All-in-One video analysis + embeddings.

Uses the `google-genai` SDK.

Improvements vs. content-intelligence/src original:
- Exception-class-based retry detection (no fragile substring matching)
- Defensive empty-response handling
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TypeVar

from google import genai
from google.genai import types
from pydantic import BaseModel
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from config import get_settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# HTTP error codes that warrant a retry
_RETRYABLE_TOKENS = ("429", "503", "504", "rate limit", "timeout", "unavailable", "deadline")


class GeminiError(Exception):
    """Base Gemini error."""


class GeminiFileProcessingError(GeminiError):
    """File failed to process (PROCESSING -> FAILED or timeout)."""


class GeminiRetryableError(GeminiError):
    """Transient error, will be retried via tenacity."""


def _is_retryable(exc: BaseException) -> bool:
    """Check if an exception is worth retrying based on its message."""
    msg = str(exc).lower()
    return any(tok in msg for tok in _RETRYABLE_TOKENS)


class GeminiClient:
    """Async wrapper around google-genai for video analysis + embeddings."""

    def __init__(
        self,
        api_key: str | None = None,
        analysis_model: str | None = None,
        embedding_model: str | None = None,
        file_poll_interval_s: float = 3.0,
        file_poll_timeout_s: float = 300.0,
    ) -> None:
        s = get_settings()
        key = api_key or s.gemini_api_key.get_secret_value()
        if not key:
            raise GeminiError("GEMINI_API_KEY missing. Run /ci-setup to configure.")
        self._client = genai.Client(api_key=key)
        self.analysis_model = analysis_model or s.gemini_model_analysis
        self.embedding_model = embedding_model or s.gemini_model_embedding
        self._file_poll_interval_s = file_poll_interval_s
        self._file_poll_timeout_s = file_poll_timeout_s

    async def __aenter__(self) -> GeminiClient:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        return None

    # ---------- File API ----------

    async def upload_video(self, video_path: str | Path) -> types.File:
        """Upload a video file and poll until state is ACTIVE."""
        path = Path(video_path)
        if not path.exists():
            raise FileNotFoundError(f"Video not found: {path}")

        size_mb = path.stat().st_size / (1024 * 1024)
        logger.info(
            "gemini.upload.start",
            extra={"path": str(path), "size_mb": round(size_mb, 2)},
        )

        file = await self._client.aio.files.upload(file=str(path))

        def _state_name(f) -> str:
            # Defensive: SDK shape can differ; fall back to UNKNOWN to keep polling
            try:
                return getattr(f.state, "name", str(f.state)) or "UNKNOWN"
            except AttributeError:
                return "UNKNOWN"

        elapsed = 0.0
        while _state_name(file) in ("PROCESSING", "UNKNOWN"):
            if elapsed >= self._file_poll_timeout_s:
                raise GeminiFileProcessingError(
                    f"File processing timeout after {elapsed}s: {file.name}"
                )
            await asyncio.sleep(self._file_poll_interval_s)
            elapsed += self._file_poll_interval_s
            file = await self._client.aio.files.get(name=file.name)

        if _state_name(file) != "ACTIVE":
            raise GeminiFileProcessingError(
                f"File not ACTIVE after processing: state={_state_name(file)}, name={file.name}"
            )

        logger.info(
            "gemini.upload.done",
            extra={"file_name": file.name, "elapsed_s": elapsed, "size_mb": round(size_mb, 2)},
        )
        return file

    async def delete_file(self, file_name: str) -> None:
        """Cleanup - delete an uploaded file (non-fatal)."""
        try:
            await self._client.aio.files.delete(name=file_name)
        except Exception as e:
            logger.warning(
                "gemini.delete.failed",
                extra={"file_name": file_name, "error": str(e)},
            )

    # ---------- Generation ----------

    async def analyze_video(
        self,
        video_file: types.File,
        prompt: str,
        schema: type[T],
        *,
        temperature: float = 0.2,
        max_output_tokens: int = 8192,
    ) -> T:
        """Analyze a video with structured JSON output matching `schema`."""
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=2, min=2, max=30),
            retry=retry_if_exception_type(GeminiRetryableError),
            reraise=True,
        ):
            with attempt:
                try:
                    response = await self._client.aio.models.generate_content(
                        model=self.analysis_model,
                        contents=[video_file, prompt],
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            response_schema=schema,
                            temperature=temperature,
                            max_output_tokens=max_output_tokens,
                        ),
                    )
                except Exception as e:
                    if _is_retryable(e):
                        logger.warning(
                            "gemini.analyze.retryable",
                            extra={"model": self.analysis_model, "error": str(e)[:200]},
                        )
                        raise GeminiRetryableError(str(e)) from e
                    raise

                text = (response.text or "").strip()
                if not text:
                    finish_reason = "unknown"
                    if response.candidates:
                        fr = getattr(response.candidates[0], "finish_reason", None)
                        finish_reason = str(fr) if fr else "n/a"
                    raise GeminiError(
                        f"Empty response from {self.analysis_model} (finish_reason={finish_reason})"
                    )
                return schema.model_validate_json(text)

        raise GeminiError("Unreachable: analyze_video exhausted retries without result")

    # ---------- Structured text generation (no video) ----------

    async def generate_structured(
        self,
        prompt: str,
        schema: type[T] | None = None,
        *,
        temperature: float = 0.4,
        max_output_tokens: int = 4096,
    ) -> T | dict:
        """Text-only structured-JSON generation with retry. Reuses the same retry
        logic as analyze_video — raises on empty response (no silent {} fallback).

        If `schema` is given, returns a parsed instance. Otherwise returns dict
        from json.loads.
        """
        import json as _json

        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=2, min=2, max=30),
            retry=retry_if_exception_type(GeminiRetryableError),
            reraise=True,
        ):
            with attempt:
                try:
                    cfg_kwargs: dict[str, object] = {
                        "response_mime_type": "application/json",
                        "temperature": temperature,
                        "max_output_tokens": max_output_tokens,
                    }
                    if schema is not None:
                        cfg_kwargs["response_schema"] = schema
                    response = await self._client.aio.models.generate_content(
                        model=self.analysis_model,
                        contents=[prompt],
                        config=types.GenerateContentConfig(**cfg_kwargs),
                    )
                except Exception as e:
                    if _is_retryable(e):
                        logger.warning(
                            "gemini.structured.retryable",
                            extra={"model": self.analysis_model, "error": str(e)[:200]},
                        )
                        raise GeminiRetryableError(str(e)) from e
                    raise

                text = (response.text or "").strip()
                if not text:
                    finish_reason = "unknown"
                    if response.candidates:
                        fr = getattr(response.candidates[0], "finish_reason", None)
                        finish_reason = str(fr) if fr else "n/a"
                    raise GeminiError(
                        f"Empty response from {self.analysis_model} (finish_reason={finish_reason})"
                    )
                if schema is not None:
                    return schema.model_validate_json(text)
                return _json.loads(text)

        raise GeminiError("Unreachable: generate_structured exhausted retries")

    # ---------- Embeddings ----------

    async def embed(
        self,
        texts: list[str],
        *,
        task_type: str = "RETRIEVAL_DOCUMENT",
        output_dimensionality: int | None = None,
    ) -> list[list[float]]:
        """Generate embeddings via `gemini-embedding-001`."""
        if not texts:
            return []

        s = get_settings()
        dim = output_dimensionality or s.gemini_embedding_dim

        # Filter out empty strings (Gemini rejects them)
        valid = [(i, t) for i, t in enumerate(texts) if t and t.strip()]
        if not valid:
            return [[0.0] * dim for _ in texts]

        if len(valid) < len(texts):
            logger.warning(
                "gemini.embed.empty_inputs",
                extra={"n_empty": len(texts) - len(valid), "n_total": len(texts)},
            )
        valid_texts = [t for _, t in valid]
        result = await self._client.aio.models.embed_content(
            model=self.embedding_model,
            contents=valid_texts,
            config=types.EmbedContentConfig(
                task_type=task_type,
                output_dimensionality=dim,
            ),
        )
        valid_vecs = [list(e.values) for e in result.embeddings]

        # Re-stitch into original order, fill empty slots with zero-vector
        out: list[list[float]] = [[0.0] * dim for _ in texts]
        for (orig_idx, _), vec in zip(valid, valid_vecs, strict=False):
            out[orig_idx] = vec
        return out
