"""Request/response schemas for the makeup API."""

from __future__ import annotations

from pydantic import BaseModel, field_validator


class MakeupAnalyzeResponse(BaseModel):
    makeup_analysis_id: str
    mst_bin: int
    undertone: str
    recommended_presets: list[str]


class MakeupGenerateRequest(BaseModel):
    preset_slug: str
    intensity: str
    idempotency_key: str | None = None

    @field_validator("preset_slug", "intensity")
    @classmethod
    def _alphanumeric_underscore(cls, v: str) -> str:
        import re

        if not re.match(r"^[a-z0-9_]+$", v):
            raise ValueError("must match ^[a-z0-9_]+$")
        return v


class MakeupGenerateResponse(BaseModel):
    job_id: str
    status: str
    poll_url: str


class MakeupFairUseError(BaseModel):
    code: str
    message: str
    retry_after: int
