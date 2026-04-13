"""Tests for structured face-analysis error payloads.

Verifies that backend face errors emit:
  {
    "error": {
      "code": "<mobile-taxonomy code>",
      "message": "...",
      "details": {"zone": "...", "reason": "..."}
    }
  }

The mobile's parseApiError recognises these codes as 'faceAnalysis' kind.
Pattern: unit tests calling production code directly with mock dependencies
(consistent with test_refund.py and the rest of the test suite).
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock
from fastapi import HTTPException


try:
    from app.face_analysis.models import (
        FACE_ERROR_NOT_DETECTED,
        FACE_ERROR_TOO_CLOSE,
        FACE_ERROR_TOO_FAR,
        FACE_ERROR_LIGHTING_TOO_DARK,
        FACE_ERROR_LIGHTING_TOO_BRIGHT,
        FACE_ERROR_OBSCURED,
        FaceErrorDetails,
    )
    from app.face_analysis.landmark_extractor import LandmarkExtractor
    from app.api.errors import ApiError, api_error_handler

    _FACE_ERRORS_AVAILABLE = True
except (ImportError, AttributeError):
    _FACE_ERRORS_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not _FACE_ERRORS_AVAILABLE, reason="face_errors module unavailable"
)

# Mobile FACE_ERROR_CODES set (must stay in sync with mobile/lib/errors.ts)
_MOBILE_FACE_CODES = {
    "face_not_detected",
    "face_too_close",
    "face_too_far",
    "lighting_too_dark",
    "lighting_too_bright",
    "face_obscured",
}

_VALID_ZONES = {"center", "top", "bottom", "left", "right", "whole"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_minimal_valid_image_bytes() -> bytes:
    """Return a 1x1 white JPEG so PIL can open it without error."""
    import io
    from PIL import Image as PILImage

    buf = io.BytesIO()
    img = PILImage.new("RGB", (1, 1), color=(255, 255, 255))
    img.save(buf, format="JPEG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Error code taxonomy tests
# ---------------------------------------------------------------------------


class TestFaceErrorCodeTaxonomy:
    """Verify constants match the mobile's expected code set."""

    def test_face_error_not_detected_in_mobile_set(self):
        assert FACE_ERROR_NOT_DETECTED in _MOBILE_FACE_CODES

    def test_face_error_too_close_in_mobile_set(self):
        assert FACE_ERROR_TOO_CLOSE in _MOBILE_FACE_CODES

    def test_face_error_too_far_in_mobile_set(self):
        assert FACE_ERROR_TOO_FAR in _MOBILE_FACE_CODES

    def test_face_error_lighting_too_dark_in_mobile_set(self):
        assert FACE_ERROR_LIGHTING_TOO_DARK in _MOBILE_FACE_CODES

    def test_face_error_lighting_too_bright_in_mobile_set(self):
        assert FACE_ERROR_LIGHTING_TOO_BRIGHT in _MOBILE_FACE_CODES

    def test_face_error_obscured_in_mobile_set(self):
        assert FACE_ERROR_OBSCURED in _MOBILE_FACE_CODES

    def test_all_codes_are_lowercase(self):
        """Mobile taxonomy uses lowercase — ensure no uppercase codes."""
        codes = [
            FACE_ERROR_NOT_DETECTED,
            FACE_ERROR_TOO_CLOSE,
            FACE_ERROR_TOO_FAR,
            FACE_ERROR_LIGHTING_TOO_DARK,
            FACE_ERROR_LIGHTING_TOO_BRIGHT,
            FACE_ERROR_OBSCURED,
        ]
        for code in codes:
            assert code == code.lower(), f"Code {code!r} must be lowercase"


# ---------------------------------------------------------------------------
# FaceErrorDetails dataclass tests
# ---------------------------------------------------------------------------


class TestFaceErrorDetails:
    """Tests for FaceErrorDetails dataclass."""

    def test_zone_and_reason_fields(self):
        details = FaceErrorDetails(zone="center", reason="Face occupies >80% of frame")
        assert details.zone == "center"
        assert details.reason == "Face occupies >80% of frame"

    def test_whole_zone(self):
        details = FaceErrorDetails(zone="whole", reason="No face found in image")
        assert details.zone in _VALID_ZONES

    def test_immutable(self):
        details = FaceErrorDetails(zone="top", reason="Head cut off")
        with pytest.raises((AttributeError, TypeError)):
            details.zone = "bottom"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ApiError details support tests
# ---------------------------------------------------------------------------


class TestApiErrorWithDetails:
    """Verify ApiError supports optional details field."""

    def test_api_error_without_details(self):
        err = ApiError(status_code=422, code="face_not_detected", message="No face")
        assert err.details is None
        assert err.detail == {
            "error": {"code": "face_not_detected", "message": "No face"}
        }

    def test_api_error_with_details(self):
        details = {"zone": "center", "reason": "Face occupies >80% of frame"}
        err = ApiError(
            status_code=422,
            code="face_too_close",
            message="Move further away",
            details=details,
        )
        assert err.details == details
        error_body = err.detail["error"]
        assert error_body["code"] == "face_too_close"
        assert error_body["details"]["zone"] == "center"
        assert error_body["details"]["reason"] == "Face occupies >80% of frame"

    def test_api_error_details_in_http_detail(self):
        """The detail dict (used by FastAPI's HTTPException serialization) must contain details."""
        err = ApiError(
            status_code=422,
            code="face_obscured",
            message="Remove sunglasses",
            details={"zone": "center", "reason": "Eyes not visible"},
        )
        assert "details" in err.detail["error"]

    @pytest.mark.asyncio
    async def test_api_error_handler_includes_details(self):
        """api_error_handler response body must include details when present."""
        request = MagicMock()
        err = ApiError(
            status_code=422,
            code="face_too_close",
            message="Move away from camera",
            details={"zone": "center", "reason": "Face occupies >80% of frame"},
        )
        response = await api_error_handler(request, err)
        import json

        body = json.loads(response.body)
        assert body["error"]["code"] == "face_too_close"
        assert body["error"]["details"]["zone"] == "center"
        assert "reason" in body["error"]["details"]

    @pytest.mark.asyncio
    async def test_api_error_handler_no_details_key_when_none(self):
        """api_error_handler must NOT include a 'details' key when details is None."""
        request = MagicMock()
        err = ApiError(status_code=400, code="bad_request", message="Bad")
        response = await api_error_handler(request, err)
        import json

        body = json.loads(response.body)
        assert "details" not in body["error"]


# ---------------------------------------------------------------------------
# LandmarkExtractor error shape tests
# ---------------------------------------------------------------------------


class TestLandmarkExtractorErrorShape:
    """Verify LandmarkExtractor raises HTTPException with the expected payload shape."""

    def test_corrupted_image_raises_structured_error(self):
        """Non-image bytes must produce a face_not_detected error with zone+reason."""
        extractor = LandmarkExtractor()
        with pytest.raises(HTTPException) as exc_info:
            extractor.extract(b"not an image at all")

        exc = exc_info.value
        assert exc.status_code == 422
        error = exc.detail["error"]
        assert error["code"] == FACE_ERROR_NOT_DETECTED
        assert error["code"] in _MOBILE_FACE_CODES
        assert "details" in error
        assert error["details"]["zone"] in _VALID_ZONES
        assert "reason" in error["details"]

    def test_no_face_raises_structured_error(self):
        """An image where MediaPipe detects no faces must raise face_not_detected with details."""
        extractor = LandmarkExtractor()

        # Simulate MediaPipe returning empty landmarks.
        # mediapipe is imported lazily inside extract(), so we patch via sys.modules.
        import sys

        mp_mock = MagicMock()
        fake_result = MagicMock()
        fake_result.face_landmarks = []

        mock_landmarker = MagicMock()
        mock_landmarker.detect.return_value = fake_result
        mock_cm = MagicMock()
        mock_cm.__enter__ = MagicMock(return_value=mock_landmarker)
        mock_cm.__exit__ = MagicMock(return_value=False)
        mp_mock.tasks.vision.FaceLandmarker.create_from_options.return_value = mock_cm

        original_mp = sys.modules.get("mediapipe")
        sys.modules["mediapipe"] = mp_mock
        try:
            with pytest.raises(HTTPException) as exc_info:
                extractor.extract(_make_minimal_valid_image_bytes())
        finally:
            if original_mp is None:
                sys.modules.pop("mediapipe", None)
            else:
                sys.modules["mediapipe"] = original_mp

        exc = exc_info.value
        assert exc.status_code == 422
        error = exc.detail["error"]
        assert error["code"] == FACE_ERROR_NOT_DETECTED
        assert error["code"] in _MOBILE_FACE_CODES
        assert error["details"]["zone"] in _VALID_ZONES
        assert isinstance(error["details"]["reason"], str)
        assert len(error["details"]["reason"]) > 0

    def test_multiple_faces_raises_structured_error(self):
        """An image with multiple faces must raise face_not_detected with details."""
        extractor = LandmarkExtractor()

        # Two sets of landmarks
        fake_landmark = MagicMock()
        fake_landmark.x = 0.5
        fake_landmark.y = 0.5
        fake_landmark.z = 0.0
        face1 = [fake_landmark] * 478
        face2 = [fake_landmark] * 478

        fake_result = MagicMock()
        fake_result.face_landmarks = [face1, face2]

        import sys

        mp_mock = MagicMock()
        mock_landmarker = MagicMock()
        mock_landmarker.detect.return_value = fake_result
        mock_cm = MagicMock()
        mock_cm.__enter__ = MagicMock(return_value=mock_landmarker)
        mock_cm.__exit__ = MagicMock(return_value=False)
        mp_mock.tasks.vision.FaceLandmarker.create_from_options.return_value = mock_cm

        original_mp = sys.modules.get("mediapipe")
        sys.modules["mediapipe"] = mp_mock
        try:
            with pytest.raises(HTTPException) as exc_info:
                extractor.extract(_make_minimal_valid_image_bytes())
        finally:
            if original_mp is None:
                sys.modules.pop("mediapipe", None)
            else:
                sys.modules["mediapipe"] = original_mp

        exc = exc_info.value
        assert exc.status_code == 422
        error = exc.detail["error"]
        assert error["code"] in _MOBILE_FACE_CODES
        assert "details" in error
        assert error["details"]["zone"] in _VALID_ZONES
        assert "multiple" in error["details"]["reason"].lower()

    def test_error_code_is_not_uppercase(self):
        """All face error codes from LandmarkExtractor must be lowercase (mobile taxonomy)."""
        extractor = LandmarkExtractor()
        with pytest.raises(HTTPException) as exc_info:
            extractor.extract(b"garbage")
        code = exc_info.value.detail["error"]["code"]
        assert code == code.lower(), f"Error code {code!r} must be lowercase"
