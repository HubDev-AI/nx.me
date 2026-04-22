"""Copy fal output URLs to private Supabase storage (makeup-outputs bucket)."""

from __future__ import annotations

import logging

from supabase import Client

logger = logging.getLogger(__name__)

MAKEUP_OUTPUTS_BUCKET = "makeup-outputs"


class OutputCopier:
    """Downloads the fal CDN URL and uploads bytes to the private makeup-outputs bucket."""

    def __init__(self, supabase: Client) -> None:
        self._sb = supabase

    async def copy(self, fal_url: str, target_key: str) -> None:
        """Download *fal_url* and store at *target_key* in the makeup-outputs bucket.

        Raises on download failure or storage error — caller (pipeline Stage B) lets
        ARQ retry; Stage A is already committed so no duplicate fal call is issued.
        """
        import httpx

        async with httpx.AsyncClient(timeout=60.0) as http:
            resp = await http.get(fal_url)
            resp.raise_for_status()
            content = resp.content

        self._sb.storage.from_(MAKEUP_OUTPUTS_BUCKET).upload(
            path=target_key,
            file=content,
            file_options={"content-type": "image/jpeg", "upsert": "true"},
        )
        logger.info("Makeup output stored: %s/%s", MAKEUP_OUTPUTS_BUCKET, target_key)
