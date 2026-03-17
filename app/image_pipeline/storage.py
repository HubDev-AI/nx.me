"""Storage adapters — port/adapter for image file persistence.

AC-4: Accepted images written to storage after metadata stripping.
AC-5: raw-selfies bucket is private; unsigned requests return 403.

Port/Adapter pattern:
  - StoragePort: interface
  - SupabaseStorageAdapter: real Supabase Storage (local CLI + staging/prod)
  - LocalStorageAdapter: filesystem fallback for offline dev
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Protocol

from app.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Port
# ---------------------------------------------------------------------------


class StoragePort(Protocol):
    """Interface for image storage adapters."""

    async def upload(self, bucket: str, key: str, data: bytes, content_type: str) -> str: ...

    async def create_signed_url(self, bucket: str, key: str, expires_in: int) -> str: ...


# ---------------------------------------------------------------------------
# Adapters
# ---------------------------------------------------------------------------


class SupabaseStorageAdapter:
    """Supabase Storage adapter — works with both local CLI and remote projects.

    Default for all environments. Local dev uses `supabase start` which
    provides a real Storage instance at http://127.0.0.1:54321.

    Delegates to ImageRepository so all storage calls go through one place.
    """

    def __init__(self, image_repo: "ImageRepository") -> None:
        from app.repositories.image_repo import ImageRepository  # noqa: F401 (type hint)
        self._image_repo = image_repo

    async def upload(self, bucket: str, key: str, data: bytes, content_type: str) -> str:
        self._image_repo.upload(bucket, key, data, content_type)
        return key

    async def create_signed_url(self, bucket: str, key: str, expires_in: int) -> str:
        return self._image_repo.create_signed_url(bucket, key, expires_in)


class LocalStorageAdapter:
    """Local filesystem adapter — offline dev fallback.

    Writes to ./local-storage/{bucket}/{key}. No signed URL support.
    """

    _BASE_DIR = Path("local-storage")

    def _safe_path(self, bucket: str, key: str) -> Path:
        """Resolve path and guard against path traversal."""
        base = self._BASE_DIR.resolve()
        path = (self._BASE_DIR / bucket / key).resolve()
        if not path.is_relative_to(base):
            raise ValueError(f"Path traversal detected: {key}")
        return path

    async def upload(self, bucket: str, key: str, data: bytes, content_type: str) -> str:  # noqa: ARG002
        path = self._safe_path(bucket, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        logger.info("Local storage: wrote %s (%d bytes)", path, len(data))
        return key

    async def create_signed_url(self, bucket: str, key: str, expires_in: int) -> str:  # noqa: ARG002
        path = self._safe_path(bucket, key)
        if not path.exists():
            raise FileNotFoundError(f"Local file not found: {path}")
        return f"file://{path.resolve()}"
