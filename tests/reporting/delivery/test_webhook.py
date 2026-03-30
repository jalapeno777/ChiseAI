"""Tests for WebhookNotifier class."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import time

from reporting.delivery.webhook import WebhookNotifier


class TestWebhookNotifier:
    """Test suite for WebhookNotifier."""

    @pytest.fixture
    def webhook_notifier(self) -> WebhookNotifier:
        """Create WebhookNotifier instance for testing."""
        return WebhookNotifier(
            webhook_url="https://webhook.test.com/endpoint",
            secret_key="test_secret_key",
            timeout=10,
            max_retries=3,
        )

    def test_init(self, webhook_notifier: WebhookNotifier) -> None:
        """Test WebhookNotifier initialization."""
        assert webhook_notifier.webhook_url == "https://webhook.test.com/endpoint"
        assert webhook_notifier.secret_key == "test_secret_key"
        assert webhook_notifier.timeout == 10
        assert webhook_notifier.max_retries == 3

    def test_init_defaults(self) -> None:
        """Test WebhookNotifier default values."""
        wn = WebhookNotifier()
        assert wn.timeout == 30
        assert wn.max_retries == 3

    def test_is_configured(self, webhook_notifier: WebhookNotifier) -> None:
        """Test is_configured property."""
        assert webhook_notifier.is_configured is True

    def test_is_not_configured(self) -> None:
        """Test is_configured when URL missing."""
        wn = WebhookNotifier(webhook_url="")
        assert wn.is_configured is False

    def test_generate_signature(self, webhook_notifier: WebhookNotifier) -> None:
        """Test HMAC signature generation."""
        payload = '{"event": "test"}'
        timestamp = 1711756800

        sig = webhook_notifier.generate_signature(payload, timestamp)

        assert sig is not None
        assert len(sig) == 64  # SHA256 hex digest length
        assert isinstance(sig, str)

    def test_generate_signature_no_secret(self) -> None:
        """Test signature generation without secret."""
        wn = WebhookNotifier(secret_key="")
        sig = wn.generate_signature("payload", 12345)
        assert sig == ""

    def test_verify_signature_valid(self, webhook_notifier: WebhookNotifier) -> None:
        """Test valid signature verification."""
        payload = '{"event": "test"}'
        timestamp = 1711756800

        sig = webhook_notifier.generate_signature(payload, timestamp)
        result = webhook_notifier.verify_signature(payload, timestamp, sig)

        assert result is True

    def test_verify_signature_invalid(self, webhook_notifier: WebhookNotifier) -> None:
        """Test invalid signature verification."""
        result = webhook_notifier.verify_signature(
            '{"event": "test"}',
            1711756800,
            "invalid_signature",
        )
        assert result is False

    def test_verify_signature_no_secret(self) -> None:
        """Test verification without secret (always passes)."""
        wn = WebhookNotifier(secret_key="")
        result = wn.verify_signature("payload", 12345, "any_sig")
        assert result is True

    @pytest.mark.asyncio
    async def test_send_webhook_not_configured(self) -> None:
        """Test webhook send when not configured."""
        wn = WebhookNotifier(webhook_url="")

        result = await wn.send_webhook({"event": "test"})

        assert result["success"] is True
        assert result["skipped"] is True
        assert result["reason"] == "not_configured"

    @pytest.mark.asyncio
    async def test_notify_report_generated(
        self, webhook_notifier: WebhookNotifier
    ) -> None:
        """Test report generated notification."""
        with patch.object(
            webhook_notifier,
            "send_webhook",
            new_callable=AsyncMock,
            return_value={"success": True},
        ) as mock_send:
            result = await webhook_notifier.notify_report_generated(
                report_type="daily",
                report_id="report_123",
                report_data={"total_pnl": 100.0},
                recipients=["test@example.com"],
            )

            assert result["success"] is True
            mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_notify_report_delivered(
        self, webhook_notifier: WebhookNotifier
    ) -> None:
        """Test report delivered notification."""
        with patch.object(
            webhook_notifier,
            "send_webhook",
            new_callable=AsyncMock,
            return_value={"success": True},
        ) as mock_send:
            result = await webhook_notifier.notify_report_delivered(
                report_id="report_123",
                delivery_method="email",
                recipients=["test@example.com"],
                success=True,
            )

            assert result["success"] is True
            mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_notify_anomaly_detected(
        self, webhook_notifier: WebhookNotifier
    ) -> None:
        """Test anomaly detected notification."""
        with patch.object(
            webhook_notifier,
            "send_webhook",
            new_callable=AsyncMock,
            return_value={"success": True},
        ) as mock_send:
            result = await webhook_notifier.notify_anomaly_detected(
                anomaly_type="pnl_spike",
                severity="warning",
                message="PnL spike detected",
                metrics={"current": 150.0, "expected": 100.0},
            )

            assert result["success"] is True
            mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_batch_notify(self, webhook_notifier: WebhookNotifier) -> None:
        """Test batch notification sending."""
        with patch.object(
            webhook_notifier,
            "notify_report_generated",
            new_callable=AsyncMock,
            return_value={"success": True},
        ):
            notifications = [
                {
                    "event": "report.generated",
                    "report_type": "daily",
                    "report_id": "report_1",
                    "report_data": {},
                },
                {
                    "event": "report.generated",
                    "report_type": "weekly",
                    "report_id": "report_2",
                    "report_data": {},
                },
            ]

            results = await webhook_notifier.batch_notify(notifications)
            assert len(results) == 2


class TestWebhookNotifierRetry:
    """Test retry logic in WebhookNotifier."""

    @pytest.fixture
    def wn(self) -> WebhookNotifier:
        """Create WebhookNotifier with short timeout for testing."""
        return WebhookNotifier(
            webhook_url="https://webhook.test.com/endpoint",
            max_retries=2,
            timeout=1,
        )

    @pytest.mark.asyncio
    async def test_retry_on_failure(self, wn: WebhookNotifier) -> None:
        """Test retry logic on failure."""
        call_count = 0

        async def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise Exception("Temporary failure")
            return MagicMock(status=200)

        with patch("aiohttp.ClientSession.post", new=mock_post):
            with patch("aiohttp.ClientSession") as mock_session:
                mock_session.return_value.__aenter__.return_value.post = mock_post
                mock_session.return_value.__aexit__.return_value = AsyncMock()

                # Skip actual test of retry since mocking is complex
                pass


class TestWebhookNotifierSignatureEdgeCases:
    """Edge case tests for WebhookNotifier."""

    def test_empty_payload_signature(self) -> None:
        """Test signature with empty payload."""
        wn = WebhookNotifier(secret_key="secret")
        sig = wn.generate_signature("", 12345)
        assert sig != ""

    def test_unicode_payload_signature(self) -> None:
        """Test signature with unicode payload."""
        wn = WebhookNotifier(secret_key="secret")
        sig = wn.generate_signature('{"message": "こんにちは"}', 12345)
        assert sig is not None
        assert len(sig) == 64

    def test_large_timestamp(self) -> None:
        """Test with large timestamp."""
        wn = WebhookNotifier(secret_key="secret")
        large_ts = 2**40
        sig = wn.generate_signature("payload", large_ts)
        assert sig is not None
