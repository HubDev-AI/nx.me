"""Tests for the published-state ``post_id`` surface on profile glowups.

Covers R6 (profile grid published indicator):
  - Response includes ``post_id`` when a live post exists for the glow-up job.
  - Response returns ``post_id=None`` when the glow-up has no post at all.
  - Response returns ``post_id=None`` when the only post is soft-deleted.
  - Response returns ``post_id=None`` when the only post is auto-hidden.
  - Response returns the live ``id`` when both a soft-deleted and a live
    post coexist for the same job (re-publish flow).

The LEFT JOIN in ``JobRepository.get_latest_jobs_for_sources`` returns
``posts`` as a nested array per row. The handler filters for the row
matching migration 0046's partial UNIQUE predicate
(``is_deleted = FALSE AND is_hidden = FALSE``); that index guarantees at
most one live match.
"""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from tests.conftest import MockSupabase, requires_routers


@requires_routers
class TestProfileGlowupsPostId:
    """Handler-level tests for the ``post_id`` surface on GET /users/.../history."""

    @staticmethod
    def _make_claims(user_id: str):
        from app.api.middleware.auth import UserClaims

        return UserClaims(sub=user_id, role="authenticated", exp=9999999999)

    @staticmethod
    def _make_user_repo(user_id: str, username: str = "alice") -> MagicMock:
        repo = MagicMock()
        repo.get_by_username = MagicMock(
            return_value={
                "id": user_id,
                "username": username,
                "display_name": "Alice",
                "avatar_storage_key": None,
                "created_at": "2026-01-01T00:00:00+00:00",
            }
        )
        return repo

    @staticmethod
    def _make_upload_repo(uploads: list[dict]) -> MagicMock:
        repo = MagicMock()
        repo.list_for_user = MagicMock(return_value=uploads)
        return repo

    @staticmethod
    def _make_glowup_analysis_repo(analyses: list[dict]) -> MagicMock:
        repo = MagicMock()
        sb = MockSupabase()
        sb.set_table_data("glowup_analyses", analyses)
        repo._sb = sb
        return repo

    @staticmethod
    def _make_job_repo(jobs: list[dict]) -> MagicMock:
        repo = MagicMock()
        repo.get_latest_jobs_for_sources = MagicMock(return_value=jobs)
        return repo

    @staticmethod
    def _make_image_repo() -> MagicMock:
        repo = MagicMock()
        repo.create_signed_url = MagicMock(
            side_effect=lambda b, k, _: f"signed://{b}/{k}"
        )
        return repo

    async def _call_handler(
        self,
        *,
        user_id: str,
        uploads: list[dict],
        analyses: list[dict],
        jobs: list[dict],
    ):
        from app.api.users import get_user_history

        return await get_user_history(
            username="alice",
            cursor=None,
            limit=20,
            claims=self._make_claims(user_id),
            user_repo=self._make_user_repo(user_id),
            upload_repo=self._make_upload_repo(uploads),
            job_repo=self._make_job_repo(jobs),
            glowup_analysis_repo=self._make_glowup_analysis_repo(analyses),
            image_repo=self._make_image_repo(),
        )

    @staticmethod
    def _fixture_ids() -> tuple[str, str, str, str]:
        """Return ``(user_id, upload_id, analysis_id, job_id)`` UUIDs."""
        return str(uuid4()), str(uuid4()), str(uuid4()), str(uuid4())

    @staticmethod
    def _uploads(user_id: str, upload_id: str) -> list[dict]:
        return [
            {
                "id": upload_id,
                "user_id": user_id,
                "image_url": "raw/key.jpg",
                "created_at": "2026-04-17T10:00:00+00:00",
            }
        ]

    @staticmethod
    def _analyses(upload_id: str, analysis_id: str) -> list[dict]:
        return [
            {
                "id": analysis_id,
                "upload_id": upload_id,
                "face_shape": "oval",
                "symmetry_score": 0.9,
                "recommendations": [],
            }
        ]

    @staticmethod
    def _job(analysis_id: str, job_id: str, posts: list[dict]) -> dict:
        return {
            "id": job_id,
            "status": "completed",
            "source_id": analysis_id,
            "after_image_url": "gen/key.jpg",
            "created_at": "2026-04-17T10:01:00+00:00",
            "saved_at": None,
            "posts": posts,
        }

    # --------------------------------------------------------------
    # Live post present
    # --------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_post_id_set_when_live_post_exists(self):
        user_id, upload_id, analysis_id, job_id = self._fixture_ids()
        live_post_id = str(uuid4())

        resp = await self._call_handler(
            user_id=user_id,
            uploads=self._uploads(user_id, upload_id),
            analyses=self._analyses(upload_id, analysis_id),
            jobs=[
                self._job(
                    analysis_id,
                    job_id,
                    posts=[
                        {
                            "id": live_post_id,
                            "is_deleted": False,
                            "is_hidden": False,
                        }
                    ],
                )
            ],
        )

        assert len(resp.entries) == 1
        assert resp.entries[0].post_id == live_post_id

    # --------------------------------------------------------------
    # No post at all
    # --------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_post_id_null_when_no_post(self):
        user_id, upload_id, analysis_id, job_id = self._fixture_ids()

        resp = await self._call_handler(
            user_id=user_id,
            uploads=self._uploads(user_id, upload_id),
            analyses=self._analyses(upload_id, analysis_id),
            jobs=[self._job(analysis_id, job_id, posts=[])],
        )

        assert len(resp.entries) == 1
        assert resp.entries[0].post_id is None

    @pytest.mark.asyncio
    async def test_post_id_null_when_posts_key_missing(self):
        """Defensive: a backend returning jobs without the nested ``posts``
        key (e.g. pre-migration) should still produce a valid response —
        handler must default to ``None`` rather than raise KeyError."""
        user_id, upload_id, analysis_id, job_id = self._fixture_ids()

        job_without_posts = {
            "id": job_id,
            "status": "completed",
            "source_id": analysis_id,
            "after_image_url": "gen/key.jpg",
            "created_at": "2026-04-17T10:01:00+00:00",
            "saved_at": None,
        }

        resp = await self._call_handler(
            user_id=user_id,
            uploads=self._uploads(user_id, upload_id),
            analyses=self._analyses(upload_id, analysis_id),
            jobs=[job_without_posts],
        )

        assert len(resp.entries) == 1
        assert resp.entries[0].post_id is None

    # --------------------------------------------------------------
    # Soft-deleted / auto-hidden post filtered out
    # --------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_post_id_null_when_post_soft_deleted(self):
        user_id, upload_id, analysis_id, job_id = self._fixture_ids()
        deleted_post_id = str(uuid4())

        resp = await self._call_handler(
            user_id=user_id,
            uploads=self._uploads(user_id, upload_id),
            analyses=self._analyses(upload_id, analysis_id),
            jobs=[
                self._job(
                    analysis_id,
                    job_id,
                    posts=[
                        {
                            "id": deleted_post_id,
                            "is_deleted": True,
                            "is_hidden": False,
                        }
                    ],
                )
            ],
        )

        assert len(resp.entries) == 1
        assert resp.entries[0].post_id is None

    @pytest.mark.asyncio
    async def test_post_id_null_when_post_auto_hidden(self):
        user_id, upload_id, analysis_id, job_id = self._fixture_ids()
        hidden_post_id = str(uuid4())

        resp = await self._call_handler(
            user_id=user_id,
            uploads=self._uploads(user_id, upload_id),
            analyses=self._analyses(upload_id, analysis_id),
            jobs=[
                self._job(
                    analysis_id,
                    job_id,
                    posts=[
                        {
                            "id": hidden_post_id,
                            "is_deleted": False,
                            "is_hidden": True,
                        }
                    ],
                )
            ],
        )

        assert len(resp.entries) == 1
        assert resp.entries[0].post_id is None

    # --------------------------------------------------------------
    # Re-publish: soft-deleted row + live row coexist
    # --------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_post_id_returns_live_row_when_deleted_row_also_present(
        self,
    ):
        """Re-publish flow: migration 0046's partial unique index lets a
        soft-deleted post coexist with a live one for the same job. The
        handler must skip the deleted row and surface the live id."""
        user_id, upload_id, analysis_id, job_id = self._fixture_ids()
        deleted_post_id = str(uuid4())
        live_post_id = str(uuid4())

        resp = await self._call_handler(
            user_id=user_id,
            uploads=self._uploads(user_id, upload_id),
            analyses=self._analyses(upload_id, analysis_id),
            jobs=[
                self._job(
                    analysis_id,
                    job_id,
                    posts=[
                        {
                            "id": deleted_post_id,
                            "is_deleted": True,
                            "is_hidden": False,
                        },
                        {
                            "id": live_post_id,
                            "is_deleted": False,
                            "is_hidden": False,
                        },
                    ],
                )
            ],
        )

        assert len(resp.entries) == 1
        assert resp.entries[0].post_id == live_post_id


# ---------------------------------------------------------------------------
# Model tests — verify optional default
# ---------------------------------------------------------------------------


@requires_routers
class TestHistoryEntryPostId:
    """Shape checks for the optional ``post_id`` field on HistoryEntry."""

    def test_history_entry_post_id_defaults_to_none(self):
        from app.api.users import HistoryEntry

        entry = HistoryEntry(
            analysis_id="a-1",
            job_id="j-1",
            status="completed",
            face_shape="oval",
            symmetry_score=0.87,
            recommendations=[],
            before_image_url=None,
            after_image_url=None,
            created_at="2026-04-17T10:00:00+00:00",
        )
        # Absent in payload → Pydantic default
        assert entry.post_id is None

    def test_history_entry_accepts_post_id(self):
        from app.api.users import HistoryEntry

        entry = HistoryEntry(
            analysis_id="a-1",
            job_id="j-1",
            status="completed",
            face_shape="oval",
            symmetry_score=0.87,
            recommendations=[],
            before_image_url=None,
            after_image_url=None,
            created_at="2026-04-17T10:00:00+00:00",
            post_id="p-42",
        )
        assert entry.post_id == "p-42"
