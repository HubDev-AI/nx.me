"""Tests for worker._resolve_source_url.

Primary path: glowup_analysis job → analyses.upload_id → uploads.image_url
→ signed URL. Validates each break point raises a clear ValueError so
upstream worker code fails visibly rather than passing ``None`` around.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.generation.worker import _resolve_source_url
from app.repositories.job_repo import SOURCE_TYPE_GLOWUP


def _build_repos(
    *,
    analysis_row: dict | None = None,
    upload_row: dict | None = None,
) -> tuple[MagicMock, MagicMock]:
    image_repo = MagicMock()
    image_repo._sb = MagicMock()
    image_repo.create_signed_url.return_value = "https://signed.example/key"

    glowup_repo = MagicMock()
    glowup_repo.get_by_id.return_value = analysis_row

    # UploadRepository is instantiated inside the function using image_repo._sb.
    # Monkey-patch by passing the row through the real constructor behaviour.
    from app.repositories import upload_repo as _upload_mod

    original_get_by_id = _upload_mod.UploadRepository.get_by_id

    def fake_get_by_id(self, *_args, **_kwargs):
        return upload_row

    _upload_mod.UploadRepository.get_by_id = fake_get_by_id  # type: ignore[assignment]
    # Restore at teardown via returned undo function
    image_repo._restore = lambda: setattr(
        _upload_mod.UploadRepository, "get_by_id", original_get_by_id
    )
    return image_repo, glowup_repo


class TestResolveSourceUrlHappyPath:
    def test_glowup_job_returns_signed_url(self):
        image_repo, glowup_repo = _build_repos(
            analysis_row={"upload_id": "upl-1"},
            upload_row={"image_url": "raw/abc.jpg"},
        )
        try:
            job = {
                "id": "job-1",
                "source_type": SOURCE_TYPE_GLOWUP,
                "source_id": "analysis-1",
            }
            url = _resolve_source_url(job, image_repo, glowup_repo)
            assert url == "https://signed.example/key"
            image_repo.create_signed_url.assert_called_once_with(
                "raw-selfies", "raw/abc.jpg", 300
            )
        finally:
            image_repo._restore()

    def test_direct_before_image_url_is_returned_verbatim(self):
        image_repo, glowup_repo = _build_repos()
        try:
            # No source_id — falls through to before_image_url branch.
            job = {
                "id": "job-2",
                "source_type": SOURCE_TYPE_GLOWUP,
                "source_id": None,
                "before_image_url": "https://direct.example/before.jpg",
            }
            url = _resolve_source_url(job, image_repo, glowup_repo)
            assert url == "https://direct.example/before.jpg"
            image_repo.create_signed_url.assert_not_called()
        finally:
            image_repo._restore()


class TestResolveSourceUrlFailures:
    def test_missing_analysis_row_raises(self):
        image_repo, glowup_repo = _build_repos(analysis_row=None)
        try:
            job = {
                "id": "job-3",
                "source_type": SOURCE_TYPE_GLOWUP,
                "source_id": "analysis-missing",
            }
            with pytest.raises(ValueError, match="Cannot resolve source image URL"):
                _resolve_source_url(job, image_repo, glowup_repo)
        finally:
            image_repo._restore()

    def test_analysis_without_upload_id_raises(self):
        image_repo, glowup_repo = _build_repos(analysis_row={"upload_id": None})
        try:
            job = {
                "id": "job-4",
                "source_type": SOURCE_TYPE_GLOWUP,
                "source_id": "analysis-1",
            }
            with pytest.raises(ValueError, match="Cannot resolve source image URL"):
                _resolve_source_url(job, image_repo, glowup_repo)
        finally:
            image_repo._restore()

    def test_upload_without_image_url_raises(self):
        image_repo, glowup_repo = _build_repos(
            analysis_row={"upload_id": "upl-1"},
            upload_row={"image_url": None},
        )
        try:
            job = {
                "id": "job-5",
                "source_type": SOURCE_TYPE_GLOWUP,
                "source_id": "analysis-1",
            }
            with pytest.raises(ValueError, match="Cannot resolve source image URL"):
                _resolve_source_url(job, image_repo, glowup_repo)
        finally:
            image_repo._restore()

    def test_unknown_source_type_raises(self):
        image_repo, glowup_repo = _build_repos()
        try:
            job = {
                "id": "job-6",
                "source_type": "unknown_type",
                "source_id": "x",
            }
            with pytest.raises(ValueError, match="Cannot resolve source image URL"):
                _resolve_source_url(job, image_repo, glowup_repo)
        finally:
            image_repo._restore()
