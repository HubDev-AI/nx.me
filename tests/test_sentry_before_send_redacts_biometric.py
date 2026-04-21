"""Tests for app.observability.sentry_before_send.before_send.

Verifies that biometric fields (mst_bin, undertone, region_anchors) are
scrubbed from all three carriers before the event leaves the process.
"""

from __future__ import annotations

import copy

from app.observability.sentry_before_send import before_send


def _make_event(**overrides) -> dict:
    return {"extra": {}, "breadcrumbs": {"values": []}, "exception": None, **overrides}


class TestExtraRedaction:
    def test_mst_bin_removed_from_extra(self):
        event = _make_event(extra={"mst_bin": 7, "other": "ok"})
        result = before_send(event, {})
        assert result["extra"]["mst_bin"] == "[REDACTED]"
        assert result["extra"]["other"] == "ok"

    def test_undertone_removed_from_extra(self):
        event = _make_event(extra={"undertone": "warm"})
        result = before_send(event, {})
        assert result["extra"]["undertone"] == "[REDACTED]"

    def test_region_anchors_removed_from_extra(self):
        event = _make_event(extra={"region_anchors": {"left_eye": [1, 2]}})
        result = before_send(event, {})
        assert result["extra"]["region_anchors"] == "[REDACTED]"

    def test_all_three_biometric_fields_redacted(self):
        event = _make_event(
            extra={
                "mst_bin": 4,
                "undertone": "cool",
                "region_anchors": {"nose": [0, 0]},
                "safe_field": "keep_me",
            }
        )
        result = before_send(event, {})
        assert result["extra"]["mst_bin"] == "[REDACTED]"
        assert result["extra"]["undertone"] == "[REDACTED]"
        assert result["extra"]["region_anchors"] == "[REDACTED]"
        assert result["extra"]["safe_field"] == "keep_me"

    def test_no_extra_key_does_not_raise(self):
        event = {"breadcrumbs": None, "exception": None}
        before_send(event, {})  # must not raise


class TestBreadcrumbRedaction:
    def test_biometric_in_breadcrumb_data_is_redacted(self):
        event = _make_event(
            breadcrumbs={
                "values": [
                    {"message": "analyze", "data": {"mst_bin": 3, "other": "x"}}
                ]
            }
        )
        result = before_send(event, {})
        assert result["breadcrumbs"]["values"][0]["data"]["mst_bin"] == "[REDACTED]"
        assert result["breadcrumbs"]["values"][0]["data"]["other"] == "x"

    def test_biometric_in_list_of_breadcrumbs(self):
        """Edge case: biometric field nested in breadcrumbs list."""
        event = _make_event(
            breadcrumbs=[
                {"data": {"undertone": "warm"}},
                {"data": {"safe": "value"}},
            ]
        )
        result = before_send(event, {})
        assert result["breadcrumbs"][0]["data"]["undertone"] == "[REDACTED]"
        assert result["breadcrumbs"][1]["data"]["safe"] == "value"

    def test_breadcrumb_without_data_is_safe(self):
        event = _make_event(
            breadcrumbs={"values": [{"message": "no data here"}]}
        )
        before_send(event, {})  # must not raise


class TestFrameLocalRedaction:
    def _build_event_with_frame_vars(self, frame_vars: dict) -> dict:
        return {
            "extra": {},
            "breadcrumbs": None,
            "exception": {
                "values": [
                    {
                        "stacktrace": {
                            "frames": [
                                {"vars": frame_vars},
                            ]
                        }
                    }
                ]
            },
        }

    def test_mst_bin_in_frame_vars_redacted(self):
        event = self._build_event_with_frame_vars({"mst_bin": 9, "x": 1})
        result = before_send(event, {})
        frame = result["exception"]["values"][0]["stacktrace"]["frames"][0]
        assert frame["vars"]["mst_bin"] == "[REDACTED]"
        assert frame["vars"]["x"] == 1

    def test_region_anchors_in_frame_vars_redacted(self):
        event = self._build_event_with_frame_vars({"region_anchors": {"a": [0, 0]}})
        result = before_send(event, {})
        frame = result["exception"]["values"][0]["stacktrace"]["frames"][0]
        assert frame["vars"]["region_anchors"] == "[REDACTED]"

    def test_frame_without_vars_is_safe(self):
        event = {
            "extra": {},
            "breadcrumbs": None,
            "exception": {
                "values": [{"stacktrace": {"frames": [{"function": "foo"}]}}]
            },
        }
        before_send(event, {})  # must not raise

    def test_event_without_exception_is_safe(self):
        event = _make_event(extra={"mst_bin": 1})
        result = before_send(event, {})
        assert result["extra"]["mst_bin"] == "[REDACTED]"


class TestReturnValue:
    def test_returns_the_same_event_object(self):
        event = _make_event(extra={"x": 1})
        result = before_send(event, {})
        assert result is event

    def test_modifies_in_place(self):
        event = _make_event(extra={"mst_bin": 2})
        original_id = id(event["extra"])
        before_send(event, {})
        assert id(event["extra"]) == original_id
