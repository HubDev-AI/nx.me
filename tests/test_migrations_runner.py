"""Regression tests for app.migrations.run._split_sql.

Guards against the 2026-04-20 incident where migration 0052 used the bare
marker ``-- DOWN`` (no colon) and the runner treated the whole file — including
the DROP TABLE in the DOWN section — as UP SQL. The signup_grants_issued
table was created and dropped in the same transaction, leaving
_schema_migrations flagged as applied while the table did not exist.
"""

from pathlib import Path

import pytest

from app.migrations.run import _split_sql


def _write(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "0099_fake.sql"
    path.write_text(content)
    return path


def test_split_sql_canonical_marker_with_colon(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "CREATE TABLE t ();\n\n-- DOWN:\nDROP TABLE t;\n",
    )
    up, down = _split_sql(path)
    assert up == "CREATE TABLE t ();"
    assert down == "DROP TABLE t;"


def test_split_sql_marker_without_colon_is_accepted(tmp_path: Path) -> None:
    """The regression: a bare `-- DOWN` marker must be recognised so the
    DROP TABLE in the DOWN section is NOT executed as part of UP."""
    path = _write(
        tmp_path,
        "CREATE TABLE t ();\n\n-- DOWN\nDROP TABLE t;\n",
    )
    up, down = _split_sql(path)
    assert up == "CREATE TABLE t ();"
    assert down == "DROP TABLE t;"


def test_split_sql_no_marker_returns_full_file_as_up(tmp_path: Path) -> None:
    path = _write(tmp_path, "CREATE TABLE t ();\n")
    up, down = _split_sql(path)
    assert up == "CREATE TABLE t ();"
    assert down == ""


def test_split_sql_marker_with_trailing_whitespace(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "CREATE TABLE t ();\n\n-- DOWN:   \nDROP TABLE t;\n",
    )
    up, down = _split_sql(path)
    assert up == "CREATE TABLE t ();"
    assert down == "DROP TABLE t;"


def test_split_sql_marker_in_comment_block_is_ignored(tmp_path: Path) -> None:
    """Marker must be at the start of a line. An inline `-- DOWN` inside a
    comment or a string literal must not split."""
    path = _write(
        tmp_path,
        "-- Note: this is not a -- DOWN marker\nCREATE TABLE t ();\n",
    )
    up, down = _split_sql(path)
    assert up == "-- Note: this is not a -- DOWN marker\nCREATE TABLE t ();"
    assert down == ""
