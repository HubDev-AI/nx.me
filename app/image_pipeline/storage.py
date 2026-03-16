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

from supabase import Client

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
    """

    def __init__(self, supabase: Client) -> None:
        self._supabase = supabase

    async def upload(self, bucket: str, key: str, data: bytes, content_type: str) -> str:
        self._supabase.storage.from_(bucket).upload(
            path=key,
            file=data,
            file_options={"content-type": content_type},
        )
        logger.info("Uploaded %s/%s (%d bytes)", bucket, key, len(data))
        return key

    async def create_signed_url(self, bucket: str, key: str, expires_in: int) -> str:
        result = self._supabase.storage.from_(bucket).create_signed_url(
            path=key,
            expires_in=expires_in,
        )
        return result["signedURL"]


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
