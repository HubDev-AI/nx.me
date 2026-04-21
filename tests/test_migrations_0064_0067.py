"""Structural tests for migrations 0064–0067.

Validates that the SQL files exist and contain the expected DDL constructs.
These are static checks — no live DB required. The intent is to catch
regressions (accidental column rename, removed constraint) during CI before
the migrations reach a real Supabase instance.

When this test fails:
- A migration file is missing → verify app/migrations/ directory
- A required construct is absent → the migration SQL was edited without
  updating these expectations
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS = REPO_ROOT / "app" / "migrations"


def _read(filename: str) -> str:
    path = MIGRATIONS / filename
    assert path.is_file(), f"Migration file missing: {filename}"
    return path.read_text()


# ---------------------------------------------------------------------------
# 0064 — jobs makeup columns
# ---------------------------------------------------------------------------


class TestMigration0064:
    sql = _read("0064_jobs_makeup_lookup_index.sql")

    def test_adds_fal_request_id(self):
        assert "fal_request_id" in self.sql

    def test_adds_fal_url(self):
        assert "fal_url" in self.sql

    def test_adds_output_key(self):
        assert "output_key" in self.sql

    def test_adds_preset_slug(self):
        assert "preset_slug" in self.sql

    def test_adds_intensity(self):
        assert "intensity" in self.sql

    def test_adds_makeup_failure_reason(self):
        assert "makeup_failure_reason" in self.sql

    def test_adds_fal_idempotency_key(self):
        assert "fal_idempotency_key" in self.sql

    def test_adds_idempotency_key_body_hash(self):
        assert "idempotency_key_body_hash" in self.sql

    def test_intensity_check_allowlist(self):
        assert "subtle" in self.sql
        assert "light" in self.sql
        assert "medium" in self.sql
        assert "bold" in self.sql

    def test_makeup_failure_reason_check_allowlist(self):
        assert "refused" in self.sql
        assert "non_retryable" in self.sql
        assert "retryable" in self.sql

    def test_fal_idempotency_unique_index(self):
        assert "idx_jobs_fal_idempotency_key" in self.sql

    def test_makeup_lookup_index(self):
        assert "idx_jobs_makeup_user_completed" in self.sql
        assert "makeup_session" in self.sql


# ---------------------------------------------------------------------------
# 0065 — posts kind + makeup_job_id
# ---------------------------------------------------------------------------


class TestMigration0065:
    sql = _read("0065_posts_kind_and_makeup_job_id.sql")

    def test_drops_not_null_on_glow_up_job_id(self):
        assert "DROP NOT NULL" in self.sql.upper()
        assert "glow_up_job_id" in self.sql

    def test_adds_kind_column(self):
        assert "kind" in self.sql
        assert "'glowup'" in self.sql
        assert "'makeup'" in self.sql

    def test_adds_makeup_job_id_column(self):
        assert "makeup_job_id" in self.sql

    def test_adds_public_index_opt_in(self):
        assert "public_index_opt_in" in self.sql

    def test_adds_publish_rev(self):
        assert "publish_rev" in self.sql

    def test_xor_constraint_name(self):
        assert "posts_job_xor" in self.sql

    def test_xor_uses_not_valid_then_validate(self):
        sql_upper = self.sql.upper()
        assert "NOT VALID" in sql_upper
        assert "VALIDATE CONSTRAINT" in sql_upper

    def test_unique_index_for_makeup_posts(self):
        assert "idx_posts_live_makeup_job_id" in self.sql

    def test_no_explicit_begin_commit(self):
        """Migration runner handles the transaction; the file must not open its own."""
        sql_upper = self.sql.upper()
        # Lines with BEGIN/COMMIT as standalone statements (not inside a word)
        for keyword in ("BEGIN;", "COMMIT;"):
            assert keyword not in sql_upper, (
                f"Migration must not issue {keyword} — runner manages the transaction"
            )


# ---------------------------------------------------------------------------
# 0066 — credit_reserve action_type allowlist
# ---------------------------------------------------------------------------


class TestMigration0066:
    sql = _read("0066_credit_rpcs_action_type_makeup.sql")

    def test_includes_makeup_in_allowlist(self):
        assert "'makeup'" in self.sql

    def test_uses_create_or_replace(self):
        assert "CREATE OR REPLACE FUNCTION" in self.sql.upper()

    def test_retains_glowup_in_allowlist(self):
        assert "'glowup'" in self.sql

    def test_retains_ada_message_in_allowlist(self):
        assert "'ada_message'" in self.sql

    def test_makeup_cost_resolves_via_case(self):
        assert "WHEN 'makeup'" in self.sql


# ---------------------------------------------------------------------------
# 0067 — makeup_analyses table
# ---------------------------------------------------------------------------


class TestMigration0067:
    sql = _read("0067_makeup_analyses_table.sql")

    def test_creates_makeup_analyses_table(self):
        assert "CREATE TABLE" in self.sql.upper()
        assert "makeup_analyses" in self.sql

    def test_has_user_id_fk(self):
        assert "user_id" in self.sql
        assert "users(id)" in self.sql

    def test_has_job_id_fk(self):
        assert "job_id" in self.sql
        assert "jobs(id)" in self.sql

    def test_has_biometric_columns(self):
        assert "mst_bin" in self.sql
        assert "undertone" in self.sql
        assert "region_anchors" in self.sql

    def test_has_consent_columns(self):
        assert "consent_version" in self.sql
        assert "consent_at" in self.sql

    def test_has_user_created_at_index(self):
        assert "idx_makeup_analyses_user_created_at" in self.sql

    def test_has_created_at_index_for_purge_sweeper(self):
        assert "idx_makeup_analyses_created_at" in self.sql

    def test_on_delete_cascade_for_user(self):
        assert "ON DELETE CASCADE" in self.sql.upper()


# ---------------------------------------------------------------------------
# job_repo constants
# ---------------------------------------------------------------------------


class TestJobRepoConstants:
    def test_source_type_makeup_constant(self):
        from app.repositories.job_repo import SOURCE_TYPE_MAKEUP
        assert SOURCE_TYPE_MAKEUP == "makeup_session"

    def test_source_type_glowup_unchanged(self):
        from app.repositories.job_repo import SOURCE_TYPE_GLOWUP
        assert SOURCE_TYPE_GLOWUP == "glowup_analysis"

    def test_makeup_failure_reason_constants(self):
        from app.repositories.job_repo import (
            MAKEUP_FAILURE_NON_RETRYABLE,
            MAKEUP_FAILURE_REFUSED,
            MAKEUP_FAILURE_RETRYABLE,
        )
        assert MAKEUP_FAILURE_REFUSED == "refused"
        assert MAKEUP_FAILURE_NON_RETRYABLE == "non_retryable"
        assert MAKEUP_FAILURE_RETRYABLE == "retryable"

    def test_job_status_select_includes_makeup_columns(self):
        from app.repositories.job_repo import JOB_STATUS_SELECT
        for col in ("fal_request_id", "fal_url", "output_key", "preset_slug",
                    "intensity", "makeup_failure_reason", "user_tier_at_enqueue"):
            assert col in JOB_STATUS_SELECT, f"{col} missing from JOB_STATUS_SELECT"


# ---------------------------------------------------------------------------
# makeup_analysis_repo
# ---------------------------------------------------------------------------


class TestMakeupAnalysisRepo:
    def _make_sb(self, data=None):
        from unittest.mock import MagicMock
        execute_result = MagicMock()
        execute_result.data = data
        builder = MagicMock()
        builder.insert.return_value = builder
        builder.select.return_value = builder
        builder.update.return_value = builder
        builder.delete.return_value = builder
        builder.eq.return_value = builder
        builder.lt.return_value = builder
        builder.order.return_value = builder
        builder.limit.return_value = builder
        builder.maybe_single.return_value = builder
        builder.execute.return_value = execute_result
        sb = MagicMock()
        sb.table.return_value = builder
        return sb, builder, execute_result

    def test_insert_returns_first_row(self):
        from app.repositories.makeup_analysis_repo import MakeupAnalysisRepository
        sb, builder, er = self._make_sb([{"id": "a1"}])
        repo = MakeupAnalysisRepository(sb)
        result = repo.insert({"user_id": "u1", "consent_version": "v1"})
        assert result["id"] == "a1"

    def test_get_latest_for_user_returns_none_on_empty(self):
        from app.repositories.makeup_analysis_repo import MakeupAnalysisRepository
        sb, builder, er = self._make_sb(None)
        repo = MakeupAnalysisRepository(sb)
        assert repo.get_latest_for_user("u1") is None

    def test_get_latest_for_user_returns_row(self):
        from app.repositories.makeup_analysis_repo import MakeupAnalysisRepository
        sb, builder, er = self._make_sb({"id": "a1", "mst_bin": 5})
        repo = MakeupAnalysisRepository(sb)
        result = repo.get_latest_for_user("u1")
        assert result["mst_bin"] == 5

    def test_nullify_biometric_fields_updates_correct_columns(self):
        from app.repositories.makeup_analysis_repo import MakeupAnalysisRepository
        sb, builder, er = self._make_sb(None)
        repo = MakeupAnalysisRepository(sb)
        repo.nullify_biometric_fields("u1")
        update_payload = builder.update.call_args[0][0]
        assert update_payload["mst_bin"] is None
        assert update_payload["undertone"] is None
        assert update_payload["region_anchors"] is None

    def test_delete_older_than_uses_lt_on_created_at(self):
        from app.repositories.makeup_analysis_repo import MakeupAnalysisRepository
        sb, builder, er = self._make_sb(None)
        repo = MakeupAnalysisRepository(sb)
        repo.delete_older_than(90)
        # .lt() was called on "created_at"
        builder.lt.assert_called_once()
        col = builder.lt.call_args[0][0]
        assert col == "created_at"
