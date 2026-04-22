"""Tests for FalAiAdapter.apply_makeup_preset."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.generation.adapters.falai import (
    FalAiAdapter,
    MakeupAdapterError,
    MakeupAdapterResult,
)


def _make_fal_http_error(
    status_code: int, headers: dict | None = None, msg: str = "err"
):
    """Build a FalClientHTTPError-like mock."""
    from fal_client.client import FalClientHTTPError

    response = MagicMock()
    response.status_code = status_code
    response.headers = {}
    exc = FalClientHTTPError(
        message=msg,
        status_code=status_code,
        response_headers=headers or {},
        response=response,
    )
    return exc


class TestApplyMakeupPresetHappyPath:
    @pytest.mark.asyncio
    async def test_returns_makeup_adapter_result(self):
        """Happy path: fal returns valid output_url."""
        adapter = FalAiAdapter()

        fal_result = {"output_url": "https://fal.media/output.jpg"}

        async def fake_subscribe(
            endpoint, arguments, *, headers, on_enqueue, client_timeout
        ):
            on_enqueue("fal-req-123")
            return fal_result

        with (
            patch.object(
                adapter,
                "_ensure_public_url",
                return_value="https://example.com/selfie.jpg",
            ),
            patch("fal_client.subscribe_async", new=fake_subscribe),
        ):
            result = await adapter.apply_makeup_preset(
                "https://example.com/selfie.jpg",
                "bold_lips",
                "medium",
                idempotency_key="idem-123",
            )

        assert isinstance(result, MakeupAdapterResult)
        assert result.fal_request_id == "fal-req-123"
        assert result.fal_output_url == "https://fal.media/output.jpg"

    @pytest.mark.asyncio
    async def test_passes_idempotency_key_header(self):
        """X-Fal-Idempotency-Key header is included when idempotency_key provided."""
        adapter = FalAiAdapter()
        captured_headers: dict = {}

        async def fake_subscribe(
            endpoint, arguments, *, headers, on_enqueue, client_timeout
        ):
            captured_headers.update(headers)
            on_enqueue("rid")
            return {"output_url": "https://fal.media/out.jpg"}

        with (
            patch.object(
                adapter, "_ensure_public_url", return_value="https://x.com/img.jpg"
            ),
            patch("fal_client.subscribe_async", new=fake_subscribe),
        ):
            await adapter.apply_makeup_preset(
                "https://x.com/img.jpg", "smoky", "heavy", idempotency_key="key-abc"
            )

        assert captured_headers.get("X-Fal-Idempotency-Key") == "key-abc"
        assert "X-Fal-Store-IO" in captured_headers


class TestApplyMakeupPresetErrors:
    @pytest.mark.asyncio
    async def test_422_bad_request_raises_non_retryable(self):
        exc = _make_fal_http_error(422)
        adapter = FalAiAdapter()

        with (
            patch.object(
                adapter, "_ensure_public_url", return_value="https://x.com/img.jpg"
            ),
            patch("fal_client.subscribe_async", side_effect=exc),
        ):
            with pytest.raises(MakeupAdapterError) as info:
                await adapter.apply_makeup_preset("https://x.com/img.jpg", "s", "m")

        assert info.value.kind == "non_retryable"

    @pytest.mark.asyncio
    async def test_503_raises_retryable(self):
        exc = _make_fal_http_error(503)
        adapter = FalAiAdapter()

        with (
            patch.object(
                adapter, "_ensure_public_url", return_value="https://x.com/img.jpg"
            ),
            patch("fal_client.subscribe_async", side_effect=exc),
        ):
            with pytest.raises(MakeupAdapterError) as info:
                await adapter.apply_makeup_preset("https://x.com/img.jpg", "s", "m")

        assert info.value.kind == "retryable"

    @pytest.mark.asyncio
    async def test_timeout_raises_retryable(self):
        from fal_client.client import FalClientTimeoutError

        adapter = FalAiAdapter()

        with (
            patch.object(
                adapter, "_ensure_public_url", return_value="https://x.com/img.jpg"
            ),
            patch(
                "fal_client.subscribe_async",
                side_effect=FalClientTimeoutError(timeout=180.0),
            ),
        ):
            with pytest.raises(MakeupAdapterError) as info:
                await adapter.apply_makeup_preset("https://x.com/img.jpg", "s", "m")

        assert info.value.kind == "retryable"
        assert info.value.reason == "fal_timeout"

    @pytest.mark.asyncio
    async def test_401_raises_config_auth_invalid(self):
        exc = _make_fal_http_error(401)
        adapter = FalAiAdapter()

        with (
            patch.object(
                adapter, "_ensure_public_url", return_value="https://x.com/img.jpg"
            ),
            patch("fal_client.subscribe_async", side_effect=exc),
        ):
            with pytest.raises(MakeupAdapterError) as info:
                await adapter.apply_makeup_preset("https://x.com/img.jpg", "s", "m")

        assert info.value.kind == "config"
        assert info.value.reason == "fal_auth_invalid"

    @pytest.mark.asyncio
    async def test_402_raises_config_billing_required(self):
        exc = _make_fal_http_error(402)
        adapter = FalAiAdapter()

        with (
            patch.object(
                adapter, "_ensure_public_url", return_value="https://x.com/img.jpg"
            ),
            patch("fal_client.subscribe_async", side_effect=exc),
        ):
            with pytest.raises(MakeupAdapterError) as info:
                await adapter.apply_makeup_preset("https://x.com/img.jpg", "s", "m")

        assert info.value.kind == "config"
        assert info.value.reason == "fal_billing_required"

    @pytest.mark.asyncio
    async def test_429_raises_retryable_with_retry_after(self):
        exc = _make_fal_http_error(429, headers={"retry-after": "5"})
        adapter = FalAiAdapter()

        with (
            patch.object(
                adapter, "_ensure_public_url", return_value="https://x.com/img.jpg"
            ),
            patch("fal_client.subscribe_async", side_effect=exc),
        ):
            with pytest.raises(MakeupAdapterError) as info:
                await adapter.apply_makeup_preset("https://x.com/img.jpg", "s", "m")

        assert info.value.kind == "retryable"
        assert info.value.reason == "fal_rate_limited"
        assert info.value.retry_after == 5

    @pytest.mark.asyncio
    async def test_unknown_status_418_raises_retryable(self):
        exc = _make_fal_http_error(418)
        adapter = FalAiAdapter()

        with (
            patch.object(
                adapter, "_ensure_public_url", return_value="https://x.com/img.jpg"
            ),
            patch("fal_client.subscribe_async", side_effect=exc),
        ):
            with pytest.raises(MakeupAdapterError) as info:
                await adapter.apply_makeup_preset("https://x.com/img.jpg", "s", "m")

        assert info.value.kind == "retryable"
        assert "418" in info.value.reason

    @pytest.mark.asyncio
    async def test_malformed_200_missing_output_url_raises_non_retryable(self):
        """fal returns HTTP 200 but response body lacks output_url → non_retryable."""
        adapter = FalAiAdapter()

        async def fake_subscribe(
            endpoint, arguments, *, headers, on_enqueue, client_timeout
        ):
            on_enqueue("rid")
            return {"some_other_field": "value"}  # no output_url

        with (
            patch.object(
                adapter, "_ensure_public_url", return_value="https://x.com/img.jpg"
            ),
            patch("fal_client.subscribe_async", new=fake_subscribe),
        ):
            with pytest.raises(MakeupAdapterError) as info:
                await adapter.apply_makeup_preset("https://x.com/img.jpg", "s", "m")

        assert info.value.kind == "non_retryable"
        assert info.value.reason == "fal_malformed_response"
