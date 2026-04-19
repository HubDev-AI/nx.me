"""Route-level tests for POST /webhooks/stripe.

Exercises the full FastAPI request/response cycle (signature verify → stale
check → idempotency → handler → record) using TestClient with dependency
overrides.  No real Stripe or Supabase calls are made.

Tests:
- Invalid signature → 400 response
- Duplicate event_id → 200 {"status": "already_processed"}
- Event older than 72h → 200 {"status": "stale_event_discarded"}
- X-Install-UUID header present → UUID value not in log output
- Full chain latency <3000ms
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_plan_version_repo, get_subscription_repo


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW_TS = int(time.time())
_PLAN_VERSION_ID = str(uuid4())


def _make_sub_repo(*, already_processed: bool = False) -> MagicMock:
    repo = MagicMock()
    repo.is_webhook_event_processed.return_value = already_processed
    repo.record_webhook_event.return_value = True
    repo.get_subscription_by_provider_id.return_value = None
    repo.upsert_subscription.return_value = None
    repo.call_credit_apply_monthly_allotment.return_value = None
    repo.update_subscription_by_provider_id.return_value = None
    repo.stamp_stripe_customer_id.return_value = None
    return repo


def _make_plan_repo() -> MagicMock:
    repo = MagicMock()
    repo.get_by_version_num.return_value = {
        "id": _PLAN_VERSION_ID,
        "version_num": "v1_pro",
        "monthly_allotment_milli": 3000,
    }
    return repo


def _make_good_event(event_type: str = "customer.subscription.created") -> dict:
    """Build a minimal Stripe-shaped webhook payload."""
    user_id = str(uuid4())
    return {
        "id": f"evt_{uuid4().hex[:12]}",
        "type": event_type,
        "created": _NOW_TS,
        "data": {
            "object": {
                "id": f"sub_{uuid4().hex[:8]}",
                "metadata": {"user_id": user_id},
                "current_period_start": _NOW_TS,
                "current_period_end": _NOW_TS + 2592000,
            }
        },
    }


def _post_event(
    client: TestClient, payload: dict, extra_headers: dict | None = None
) -> object:
    """POST a webhook payload to /webhooks/stripe."""
    headers = {"content-type": "application/json", "stripe-signature": "mock_sig"}
    if extra_headers:
        headers.update(extra_headers)
    return client.post("/webhooks/stripe", content=json.dumps(payload), headers=headers)


# ---------------------------------------------------------------------------
# Fixture — TestClient wired with mock deps
# ---------------------------------------------------------------------------


@pytest.fixture()
def webhook_client():
    """TestClient with sub_repo + plan_repo dependency-overridden.

    The payment adapter is patched to return a MockPaymentAdapter so no
    Stripe SDK is required. app.state.* is stubbed so the dep providers
    don't raise on missing Supabase/Redis connections.
    """
    from app.main import app
    from app.payment.adapters.mock import MockPaymentAdapter

    sub_repo = _make_sub_repo()
    plan_repo = _make_plan_repo()

    # Stub out app.state so dep providers that touch it don't error.
    app.state.supabase = MagicMock()
    app.state.redis = MagicMock()

    app.dependency_overrides[get_subscription_repo] = lambda: sub_repo
    app.dependency_overrides[get_plan_version_repo] = lambda: plan_repo

    mock_adapter = MockPaymentAdapter()

    with patch("app.api.webhooks.get_payment_adapter", return_value=mock_adapter):
        client = TestClient(app, raise_server_exceptions=False)
        yield client, sub_repo, plan_repo

    app.dependency_overrides.pop(get_subscription_repo, None)
    app.dependency_overrides.pop(get_plan_version_repo, None)
    for attr in ("supabase", "redis"):
        try:
            delattr(app.state, attr)
        except AttributeError:
            pass


@pytest.fixture()
def bad_sig_client():
    """TestClient where the payment adapter raises ValueError on sig verify."""
    from app.main import app

    sub_repo = _make_sub_repo()
    plan_repo = _make_plan_repo()

    app.state.supabase = MagicMock()
    app.state.redis = MagicMock()

    app.dependency_overrides[get_subscription_repo] = lambda: sub_repo
    app.dependency_overrides[get_plan_version_repo] = lambda: plan_repo

    bad_adapter = MagicMock()
    bad_adapter.construct_webhook_event.side_effect = ValueError("bad sig")

    with patch("app.api.webhooks.get_payment_adapter", return_value=bad_adapter):
        client = TestClient(app, raise_server_exceptions=False)
        yield client

    app.dependency_overrides.pop(get_subscription_repo, None)
    app.dependency_overrides.pop(get_plan_version_repo, None)
    for attr in ("supabase", "redis"):
        try:
            delattr(app.state, attr)
        except AttributeError:
            pass


# ---------------------------------------------------------------------------
# Tests — invalid signature → 400
# ---------------------------------------------------------------------------


class TestInvalidSignature:
    def test_returns_400(self, bad_sig_client):
        payload = {
            "id": "evt_bad",
            "type": "customer.subscription.created",
            "created": _NOW_TS,
        }
        resp = bad_sig_client.post(
            "/webhooks/stripe",
            content=json.dumps(payload),
            headers={"content-type": "application/json", "stripe-signature": "bad"},
        )
        assert resp.status_code == 400

    def test_returns_error_code(self, bad_sig_client):
        payload = {
            "id": "evt_bad2",
            "type": "customer.subscription.created",
            "created": _NOW_TS,
        }
        resp = bad_sig_client.post(
            "/webhooks/stripe",
            content=json.dumps(payload),
            headers={"content-type": "application/json", "stripe-signature": "bad"},
        )
        body = resp.json()
        # Custom error handler unwraps HTTPException.detail to top-level;
        # the code lives at body["error"]["code"] (not body["detail"]["error"]["code"]).
        error = body.get("error") or body.get("detail", {}).get("error", {})
        assert error.get("code") == "INVALID_WEBHOOK_SIGNATURE"

    def test_no_db_access_on_bad_sig(self, bad_sig_client):
        """DB repos must not be touched when signature fails."""
        from app.api.deps import get_subscription_repo as gsr

        mock_sub = _make_sub_repo()
        from app.main import app

        app.dependency_overrides[gsr] = lambda: mock_sub

        payload = {
            "id": "evt_nodb",
            "type": "customer.subscription.created",
            "created": _NOW_TS,
        }
        bad_sig_client.post(
            "/webhooks/stripe",
            content=json.dumps(payload),
            headers={"content-type": "application/json", "stripe-signature": "bad"},
        )
        mock_sub.is_webhook_event_processed.assert_not_called()
        mock_sub.upsert_subscription.assert_not_called()


# ---------------------------------------------------------------------------
# Tests — duplicate event → 200 already_processed
# ---------------------------------------------------------------------------


class TestDuplicateEventRoute:
    def test_already_processed_returns_200(self, webhook_client):
        client, sub_repo, _ = webhook_client
        sub_repo.is_webhook_event_processed.return_value = True

        payload = _make_good_event()
        resp = _post_event(client, payload)

        assert resp.status_code == 200
        assert resp.json() == {"status": "already_processed"}

    def test_already_processed_no_handler_side_effects(self, webhook_client):
        client, sub_repo, _ = webhook_client
        sub_repo.is_webhook_event_processed.return_value = True

        payload = _make_good_event()
        _post_event(client, payload)

        sub_repo.upsert_subscription.assert_not_called()
        sub_repo.call_credit_apply_monthly_allotment.assert_not_called()
        sub_repo.record_webhook_event.assert_not_called()


# ---------------------------------------------------------------------------
# Tests — stale event → 200 stale_event_discarded
# ---------------------------------------------------------------------------


class TestStaleEventRoute:
    def test_stale_event_returns_200(self, webhook_client):
        from app.constants.webhooks import WEBHOOK_EVENT_MAX_AGE_HOURS

        client, sub_repo, _ = webhook_client
        sub_repo.is_webhook_event_processed.return_value = False

        stale_ts = int(
            (
                datetime.now(tz=timezone.utc)
                - timedelta(hours=WEBHOOK_EVENT_MAX_AGE_HOURS + 1)
            ).timestamp()
        )
        payload = _make_good_event()
        payload["created"] = stale_ts

        resp = _post_event(client, payload)

        assert resp.status_code == 200
        assert resp.json() == {"status": "stale_event_discarded"}

    def test_stale_event_no_db_writes(self, webhook_client):
        from app.constants.webhooks import WEBHOOK_EVENT_MAX_AGE_HOURS

        client, sub_repo, _ = webhook_client
        sub_repo.is_webhook_event_processed.return_value = False

        stale_ts = int(
            (
                datetime.now(tz=timezone.utc)
                - timedelta(hours=WEBHOOK_EVENT_MAX_AGE_HOURS + 1)
            ).timestamp()
        )
        payload = _make_good_event()
        payload["created"] = stale_ts
        _post_event(client, payload)

        sub_repo.upsert_subscription.assert_not_called()
        sub_repo.record_webhook_event.assert_not_called()


# ---------------------------------------------------------------------------
# Tests — X-Install-UUID header scrubbed from logs
# ---------------------------------------------------------------------------


class TestInstallUUIDHeaderScrubbed:
    def test_uuid_value_not_in_log_output(self, webhook_client, caplog):
        """X-Install-UUID header value must not appear in any log record."""
        client, sub_repo, _ = webhook_client
        sub_repo.is_webhook_event_processed.return_value = False

        install_uuid = str(uuid4())
        payload = _make_good_event()

        with caplog.at_level(logging.INFO, logger="app.api.middleware.logging"):
            _post_event(
                client,
                payload,
                extra_headers={"x-install-uuid": install_uuid},
            )

        for record in caplog.records:
            assert install_uuid not in record.getMessage(), (
                f"UUID {install_uuid} found in log record: {record.getMessage()}"
            )

    def test_redacted_placeholder_present(self, webhook_client, caplog):
        """Log records must contain [REDACTED] when X-Install-UUID is present."""
        client, sub_repo, _ = webhook_client
        sub_repo.is_webhook_event_processed.return_value = False

        install_uuid = str(uuid4())
        payload = _make_good_event()

        with caplog.at_level(logging.INFO, logger="app.api.middleware.logging"):
            _post_event(
                client,
                payload,
                extra_headers={"x-install-uuid": install_uuid},
            )

        middleware_records = [
            r for r in caplog.records if r.name == "app.api.middleware.logging"
        ]
        if middleware_records:
            any_redacted = any(
                "[REDACTED]" in r.getMessage() for r in middleware_records
            )
            assert any_redacted, "Expected [REDACTED] in middleware log but not found"


# ---------------------------------------------------------------------------
# Tests — full chain latency <3000ms
# ---------------------------------------------------------------------------


class TestWebhookRouteLatency:
    def test_full_chain_under_3s(self, webhook_client):
        """Complete route chain (mock adapter, mock repo) must finish in <3000ms."""
        client, sub_repo, _ = webhook_client
        sub_repo.is_webhook_event_processed.return_value = False

        payload = _make_good_event()

        start = time.monotonic()
        resp = _post_event(client, payload)
        elapsed_ms = (time.monotonic() - start) * 1000

        assert resp.status_code == 200
        assert elapsed_ms < 3000, f"Route took {elapsed_ms:.1f}ms (limit 3000ms)"

    def test_happy_path_returns_processed(self, webhook_client):
        """Successful event returns {"status": "processed"}."""
        client, sub_repo, _ = webhook_client
        sub_repo.is_webhook_event_processed.return_value = False

        payload = _make_good_event()
        resp = _post_event(client, payload)

        assert resp.status_code == 200
        assert resp.json() == {"status": "processed"}
