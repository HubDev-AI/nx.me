"""Tests for ``UserRepository.list_user_storage_keys`` and
``UserRepository.delete``.

Part of the delete-account hard-reset flow. The repo needs to enumerate
every blob owned by a user (across 4 Supabase storage buckets) *before*
the DB hard-delete cascades rows away — otherwise the storage keys
would be orphaned with no way to reconstruct them.

Mock pattern follows ``tests/test_username_availability_with_reservations.py``
— a ``_build_sb_serving_tables`` helper that routes ``sb.table(name)``
to per-table chain mocks terminating at ``.execute()``.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from app.repositories.user_repo import UserRepository


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _chain_returning(rows: list[dict]) -> MagicMock:
    """Mock PostgREST chain that returns ``rows`` from ``.execute()``.

    All filter methods (``select``, ``eq``, ``range``) are self-returning so
    the caller can compose any filter combination.
    """
    chain = MagicMock()
    chain.select.return_value = chain
    chain.eq.return_value = chain
    chain.range.return_value = chain
    chain.delete.return_value = chain
    chain.execute.return_value = MagicMock(data=rows)
    return chain


def _build_sb_serving_tables(
    uploads_rows: list[dict] | None = None,
    jobs_rows: list[dict] | None = None,
    posts_rows: list[dict] | None = None,
    users_rows: list[dict] | None = None,
) -> MagicMock:
    """Supabase client routing ``sb.table(name)`` to per-table chains.

    Each table's chain returns the configured rows exactly once — the
    paginator then exits because ``len(rows) < _PAGINATION_PAGE_SIZE``.
    """
    sb = MagicMock()

    uploads_chain = _chain_returning(uploads_rows or [])
    jobs_chain = _chain_returning(jobs_rows or [])
    posts_chain = _chain_returning(posts_rows or [])
    users_chain = _chain_returning(users_rows or [])

    def route(name: str) -> MagicMock:
        if name == "uploads":
            return uploads_chain
        if name == "jobs":
            return jobs_chain
        if name == "posts":
            return posts_chain
        if name == "users":
            return users_chain
        raise AssertionError(f"Unexpected table: {name}")

    sb.table.side_effect = route
    # Hold refs so tests can assert call counts on individual chains.
    sb._uploads_chain = uploads_chain
    sb._jobs_chain = jobs_chain
    sb._posts_chain = posts_chain
    sb._users_chain = users_chain
    return sb


# ----------------------------------------------------------------------
# list_user_storage_keys
# ----------------------------------------------------------------------


class TestListUserStorageKeys:
    def test_groups_by_bucket(self):
        sb = _build_sb_serving_tables(
            uploads_rows=[
                {"image_url": "raw-selfies/u/up1.jpg"},
                {"image_url": "raw-selfies/u/up2.jpg"},
            ],
            jobs_rows=[
                {
                    "before_image_url": "raw-selfies/u/before.jpg",
                    "after_image_url": "generated-images/u/after.jpg",
                }
            ],
            posts_rows=[
                {
                    "before_image_url": "post-images/u/post-before.jpg",
                    "after_image_url": "post-images/u/post-after.jpg",
                }
            ],
            users_rows=[{"avatar_storage_key": "avatars/u/avatar.jpg"}],
        )
        repo = UserRepository(sb)

        result = repo.list_user_storage_keys("u-1")

        assert set(result["raw-selfies"]) == {
            "raw-selfies/u/up1.jpg",
            "raw-selfies/u/up2.jpg",
            "raw-selfies/u/before.jpg",
        }
        assert result["generated-images"] == ["generated-images/u/after.jpg"]
        assert set(result["post-images"]) == {
            "post-images/u/post-before.jpg",
            "post-images/u/post-after.jpg",
        }
        assert result["avatars"] == ["avatars/u/avatar.jpg"]

    def test_ignores_null_urls(self):
        sb = _build_sb_serving_tables(
            uploads_rows=[{"image_url": "raw-selfies/u/only.jpg"}],
            jobs_rows=[{"before_image_url": None, "after_image_url": None}],
            posts_rows=[{"before_image_url": None, "after_image_url": None}],
            users_rows=[{"avatar_storage_key": None}],
        )
        repo = UserRepository(sb)

        result = repo.list_user_storage_keys("u-1")

        assert result["raw-selfies"] == ["raw-selfies/u/only.jpg"]
        assert result["generated-images"] == []
        assert result["post-images"] == []
        assert result["avatars"] == []
        # All four bucket keys are always present in the dict, even if empty.
        assert set(result.keys()) == {
            "raw-selfies",
            "generated-images",
            "post-images",
            "avatars",
        }

    def test_dedupes_before_image_against_upload_key(self):
        # Same storage key appears in uploads.image_url AND jobs.before_image_url —
        # should only show up once in the raw-selfies bucket.
        shared_key = "raw-selfies/u/same.jpg"
        sb = _build_sb_serving_tables(
            uploads_rows=[{"image_url": shared_key}],
            jobs_rows=[
                {"before_image_url": shared_key, "after_image_url": None},
            ],
            posts_rows=[],
            users_rows=[],
        )
        repo = UserRepository(sb)

        result = repo.list_user_storage_keys("u-1")

        assert result["raw-selfies"] == [shared_key]

    def test_paginates(self):
        # uploads returns two pages: one full page (1000 rows), one partial (50).
        # Expected: 1050 entries in raw-selfies, exactly 2 .range() calls.
        full_page = [{"image_url": f"raw-selfies/u/key-{i}.jpg"} for i in range(1000)]
        partial_page = [
            {"image_url": f"raw-selfies/u/key-{i}.jpg"} for i in range(1000, 1050)
        ]

        sb = MagicMock()

        # Stateful uploads chain: returns full_page on first execute,
        # partial_page on second.
        uploads_chain = MagicMock()
        uploads_chain.select.return_value = uploads_chain
        uploads_chain.eq.return_value = uploads_chain
        uploads_chain.range.return_value = uploads_chain
        uploads_chain.execute.side_effect = [
            MagicMock(data=full_page),
            MagicMock(data=partial_page),
        ]

        jobs_chain = _chain_returning([])
        posts_chain = _chain_returning([])
        users_chain = _chain_returning([])

        def route(name: str) -> MagicMock:
            if name == "uploads":
                return uploads_chain
            if name == "jobs":
                return jobs_chain
            if name == "posts":
                return posts_chain
            if name == "users":
                return users_chain
            raise AssertionError(f"Unexpected table: {name}")

        sb.table.side_effect = route

        repo = UserRepository(sb)
        result = repo.list_user_storage_keys("u-1")

        assert len(result["raw-selfies"]) == 1050
        # Exactly 2 .range() calls on the uploads chain — paginator stops
        # after the short page without speculatively issuing a third.
        assert uploads_chain.range.call_count == 2


# ----------------------------------------------------------------------
# delete
# ----------------------------------------------------------------------


class TestDelete:
    def test_returns_deleted_row_on_success(self):
        sb = _build_sb_serving_tables(users_rows=[{"id": "u-1"}])
        repo = UserRepository(sb)

        result = repo.delete("u-1")

        assert result == [{"id": "u-1"}]

    def test_returns_empty_when_already_gone(self):
        sb = _build_sb_serving_tables(users_rows=[])
        repo = UserRepository(sb)

        result = repo.delete("u-missing")

        assert result == []
