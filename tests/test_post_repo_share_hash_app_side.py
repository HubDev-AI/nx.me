"""Tests for post_repo.insert_post share_hash parameter."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.repositories.post_repo import PostRepository


def _make_supabase(returned_row: dict | None = None):
    """Return a Supabase mock whose insert chain returns *returned_row*."""
    execute_result = MagicMock()
    execute_result.data = [returned_row or {"id": "post-1", "share_hash": "abc"}]

    builder = MagicMock()
    builder.insert.return_value = builder
    builder.execute.return_value = execute_result

    sb = MagicMock()
    sb.table.return_value = builder
    return sb, builder


class TestInsertPostShareHash:
    def test_omitting_share_hash_passes_row_unchanged(self):
        """Legacy glow-up callers pass no share_hash — row dict must be unmodified."""
        sb, builder = _make_supabase({"id": "p1", "share_hash": "default_from_pg"})
        repo = PostRepository(sb)
        original = {"user_id": "u1", "glow_up_job_id": "j1", "kind": "glowup"}

        repo.insert_post(original)

        inserted = builder.insert.call_args[0][0]
        assert inserted == original
        assert "share_hash" not in inserted

    def test_share_hash_kwarg_merges_into_insert(self):
        """Passing share_hash='abc123' must include it in the INSERT payload."""
        sb, builder = _make_supabase({"id": "p1", "share_hash": "abc123"})
        repo = PostRepository(sb)
        base_row = {"user_id": "u1", "makeup_job_id": "j1", "kind": "makeup"}

        repo.insert_post(base_row, share_hash="abc123")

        inserted = builder.insert.call_args[0][0]
        assert inserted["share_hash"] == "abc123"
        assert inserted["user_id"] == "u1"

    def test_share_hash_does_not_mutate_original_dict(self):
        """insert_post must not mutate the caller's dict when share_hash is given."""
        sb, _ = _make_supabase()
        repo = PostRepository(sb)
        original = {"user_id": "u1", "makeup_job_id": "j1"}

        repo.insert_post(original, share_hash="xyz")

        assert "share_hash" not in original

    def test_share_hash_none_omits_field(self):
        """Explicit share_hash=None must not add share_hash to the INSERT payload."""
        sb, builder = _make_supabase()
        repo = PostRepository(sb)
        row = {"user_id": "u1", "glow_up_job_id": "j1"}

        repo.insert_post(row, share_hash=None)

        inserted = builder.insert.call_args[0][0]
        assert "share_hash" not in inserted

    def test_returns_first_data_row(self):
        """insert_post must return result.data[0]."""
        sb, _ = _make_supabase({"id": "post-42", "share_hash": "s1"})
        repo = PostRepository(sb)
        result = repo.insert_post({"user_id": "u1", "glow_up_job_id": "j1"})
        assert result["id"] == "post-42"
