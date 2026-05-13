"""Cloudflare R2 storage client (S3-compatible via aioboto3).

NOT USED in Phase 0-4. Activated in Phase 5 (/ci-track persistent MP4s).

R2-Struktur: s3://{bucket}/{yyyy-mm}/{source}/{shortcode}.mp4
Lifecycle-Policy: MP4 nach 30 Tagen via Supabase cleanup_expired_mp4().
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from config import get_settings

logger = logging.getLogger(__name__)


class R2Error(Exception):
    """Base R2 error."""


class R2Storage:
    """Thin wrapper around aioboto3 S3 client configured for Cloudflare R2."""

    def __init__(self) -> None:
        # Lazy import — aioboto3 is heavy and not needed in Phase 0-4
        try:
            import aioboto3  # noqa: F401
        except ImportError as e:
            raise R2Error(
                "aioboto3 not installed. R2 is Phase 5 only. "
                "Install: pip install aioboto3"
            ) from e

        s = get_settings()
        if not s.has_r2():
            raise R2Error("R2 credentials missing. Run /ci-setup --enable-r2.")

        import aioboto3
        self._session = aioboto3.Session()
        self._endpoint = s.r2_endpoint_url
        self._bucket = s.r2_bucket_name
        self._access_key = s.r2_access_key_id.get_secret_value()
        self._secret_key = s.r2_secret_access_key.get_secret_value()

    def _build_key(self, shortcode: str, source: str = "ig", ext: str = "mp4") -> str:
        ym = datetime.now(timezone.utc).strftime("%Y-%m")
        return f"{ym}/{source}/{shortcode}.{ext}"

    async def upload_file(
        self,
        local_path: str | Path,
        shortcode: str,
        source: str = "ig",
        content_type: str = "video/mp4",
    ) -> str:
        local = Path(local_path)
        if not local.exists():
            raise FileNotFoundError(f"Local file missing: {local}")

        key = self._build_key(shortcode, source, ext=local.suffix.lstrip(".") or "mp4")

        async with self._session.client(
            "s3",
            endpoint_url=self._endpoint,
            aws_access_key_id=self._access_key,
            aws_secret_access_key=self._secret_key,
            region_name="auto",
        ) as s3:
            with local.open("rb") as fh:
                await s3.upload_fileobj(
                    fh, self._bucket, key,
                    ExtraArgs={"ContentType": content_type},
                )

        logger.info(
            "r2.upload.done",
            extra={"bucket": self._bucket, "key": key, "size_mb": local.stat().st_size // 1024 // 1024},
        )
        return key

    async def presigned_url(self, key: str, expires_s: int = 3600) -> str:
        async with self._session.client(
            "s3",
            endpoint_url=self._endpoint,
            aws_access_key_id=self._access_key,
            aws_secret_access_key=self._secret_key,
            region_name="auto",
        ) as s3:
            url: str = await s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": key},
                ExpiresIn=expires_s,
            )
        return url

    async def delete_key(self, key: str) -> None:
        async with self._session.client(
            "s3",
            endpoint_url=self._endpoint,
            aws_access_key_id=self._access_key,
            aws_secret_access_key=self._secret_key,
            region_name="auto",
        ) as s3:
            await s3.delete_object(Bucket=self._bucket, Key=key)
        logger.info("r2.delete.done", extra={"key": key})
