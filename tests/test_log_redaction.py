"""Tests for BiometricFieldFilter in app.logging_config.

Verifies that INFO+ log records have biometric field values rewritten to
[REDACTED], while DEBUG records pass through unmodified.
"""

from __future__ import annotations

import logging

import pytest

from app.logging_config import BiometricFieldFilter


@pytest.fixture()
def filtered_logger(caplog):
    """Return a logger with BiometricFieldFilter attached and level=DEBUG."""
    logger = logging.getLogger("test_log_redaction")
    logger.setLevel(logging.DEBUG)
    filt = BiometricFieldFilter()
    logger.addFilter(filt)
    yield logger
    logger.removeFilter(filt)


class TestBiometricFieldFilter:
    def test_info_log_with_mst_bin_is_redacted(self, filtered_logger, caplog):
        with caplog.at_level(logging.INFO, logger="test_log_redaction"):
            filtered_logger.info("result: mst_bin=7 done")
        assert "[REDACTED]" in caplog.text
        assert "mst_bin=7" not in caplog.text

    def test_info_log_with_undertone_is_redacted(self, filtered_logger, caplog):
        with caplog.at_level(logging.INFO, logger="test_log_redaction"):
            filtered_logger.info("undertone: warm analysis complete")
        assert "[REDACTED]" in caplog.text

    def test_info_log_with_region_anchors_is_redacted(self, filtered_logger, caplog):
        with caplog.at_level(logging.INFO, logger="test_log_redaction"):
            filtered_logger.info("region_anchors=[[1,2],[3,4]] saved")
        assert "[REDACTED]" in caplog.text
        assert "region_anchors=[[1,2],[3,4]]" not in caplog.text

    def test_debug_log_passes_through_unredacted(self, filtered_logger, caplog):
        """DEBUG records must NOT be redacted — documents the env-gate contract."""
        with caplog.at_level(logging.DEBUG, logger="test_log_redaction"):
            filtered_logger.debug("debug mst_bin=5 undertone=cool")
        assert "mst_bin=5" in caplog.text
        assert "[REDACTED]" not in caplog.text

    def test_safe_info_log_is_unchanged(self, filtered_logger, caplog):
        with caplog.at_level(logging.INFO, logger="test_log_redaction"):
            filtered_logger.info("user uploaded a selfie ok")
        assert "user uploaded a selfie ok" in caplog.text
        assert "[REDACTED]" not in caplog.text

    def test_warning_with_biometric_is_redacted(self, filtered_logger, caplog):
        with caplog.at_level(logging.WARNING, logger="test_log_redaction"):
            filtered_logger.warning("unexpected mst_bin=12 value")
        assert "[REDACTED]" in caplog.text
        assert "mst_bin=12" not in caplog.text

    def test_filter_always_returns_true(self):
        filt = BiometricFieldFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="mst_bin=3", args=(), exc_info=None,
        )
        assert filt.filter(record) is True
