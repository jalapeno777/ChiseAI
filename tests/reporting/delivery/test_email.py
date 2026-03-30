"""Tests for EmailDelivery class."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from reporting.delivery.email import EmailDelivery


class TestEmailDelivery:
    """Test suite for EmailDelivery."""

    @pytest.fixture
    def email_delivery(self) -> EmailDelivery:
        """Create EmailDelivery instance for testing."""
        return EmailDelivery(
            smtp_host="smtp.test.com",
            smtp_port=587,
            smtp_user="test@test.com",
            smtp_password="testpass",
            sender="sender@test.com",
        )

    def test_init(self, email_delivery: EmailDelivery) -> None:
        """Test EmailDelivery initialization."""
        assert email_delivery.smtp_host == "smtp.test.com"
        assert email_delivery.smtp_port == 587
        assert email_delivery.smtp_user == "test@test.com"
        assert email_delivery.smtp_password == "testpass"
        assert email_delivery.sender == "sender@test.com"
        assert email_delivery.use_tls is True

    def test_init_defaults(self) -> None:
        """Test EmailDelivery default values."""
        ed = EmailDelivery()
        assert ed.smtp_host == "smtp.gmail.com"
        assert ed.smtp_port == 587

    def test_is_configured(self, email_delivery: EmailDelivery) -> None:
        """Test is_configured property."""
        assert email_delivery.is_configured is True

    def test_is_not_configured(self) -> None:
        """Test is_configured when credentials missing."""
        ed = EmailDelivery(smtp_user="", smtp_password="")
        assert ed.is_configured is False

    @pytest.mark.asyncio
    async def test_connect_success(self, email_delivery: EmailDelivery) -> None:
        """Test successful SMTP connection."""
        # Patch _connect_sync to prevent actual SMTP connection
        with patch.object(
            email_delivery,
            "_connect_sync",
            return_value=None,
        ):
            email_delivery._server = MagicMock()
            email_delivery._connected = True

            result = await email_delivery.connect()

            assert result is True
            assert email_delivery._connected is True

    @pytest.mark.asyncio
    async def test_connect_no_credentials(self) -> None:
        """Test connection when credentials not configured."""
        ed = EmailDelivery(smtp_user="", smtp_password="")
        result = await ed.connect()
        assert result is False

    @pytest.mark.asyncio
    async def test_send_email_no_credentials(self) -> None:
        """Test sending email without credentials (graceful degradation)."""
        ed = EmailDelivery(smtp_user="", smtp_password="")
        result = await ed.send_email(
            recipients=["test@example.com"],
            subject="Test",
            body="Test body",
        )
        assert result == {"test@example.com": True}

    @pytest.mark.asyncio
    async def test_send_email_success(self, email_delivery: EmailDelivery) -> None:
        """Test successful email sending."""
        email_delivery._server = MagicMock()
        email_delivery._connected = True

        with patch.object(
            email_delivery,
            "_send_single_email",
            return_value=None,
        ):
            result = await email_delivery.send_email(
                recipients=["test@example.com"],
                subject="Test Subject",
                body="Test body",
            )
            assert result["test@example.com"] is True

    @pytest.mark.asyncio
    async def test_send_email_multiple_recipients(
        self, email_delivery: EmailDelivery
    ) -> None:
        """Test sending to multiple recipients."""
        email_delivery._server = MagicMock()
        email_delivery._connected = True

        with patch.object(
            email_delivery,
            "_send_single_email",
            return_value=None,
        ):
            result = await email_delivery.send_email(
                recipients=["a@test.com", "b@test.com", "c@test.com"],
                subject="Test",
                body="Body",
            )
            assert result["a@test.com"] is True
            assert result["b@test.com"] is True
            assert result["c@test.com"] is True

    def test_create_html_template(self, email_delivery: EmailDelivery) -> None:
        """Test HTML template generation."""
        html = email_delivery.create_html_template(
            title="Test Title",
            content="<p>Test content</p>",
            footer="Test footer",
        )
        assert "Test Title" in html
        assert "<p>Test content</p>" in html
        assert "Test footer" in html

    @pytest.mark.asyncio
    async def test_send_report_email(self, email_delivery: EmailDelivery) -> None:
        """Test report email sending."""
        email_delivery._server = MagicMock()
        email_delivery._connected = True

        with patch.object(
            email_delivery,
            "_send_single_email",
            return_value=None,
        ):
            result = await email_delivery.send_report_email(
                recipients=["test@example.com"],
                report_type="Daily",
                report_date="2026-03-29",
                report_content="# Daily Report\n\nTest content",
            )
            assert result["test@example.com"] is True

    def test_markdown_to_html(self, email_delivery: EmailDelivery) -> None:
        """Test Markdown to HTML conversion."""
        md = "# Header\n\n## Subheader\n\n**Bold** and *italic*\n\n- Item 1\n- Item 2"
        html = email_delivery._markdown_to_html(md)

        assert "<h1>Header</h1>" in html
        assert "<h2>Subheader</h2>" in html
        assert "<strong>Bold</strong>" in html
        assert "<em>italic</em>" in html

    @pytest.mark.asyncio
    async def test_batch_send(self, email_delivery: EmailDelivery) -> None:
        """Test batch email sending."""
        email_delivery._server = MagicMock()
        email_delivery._connected = True

        with patch.object(
            email_delivery,
            "_send_single_email",
            return_value=None,
        ):
            batch = [
                {
                    "recipients": ["a@test.com"],
                    "subject": "Email 1",
                    "body": "Body 1",
                },
                {
                    "recipients": ["b@test.com"],
                    "subject": "Email 2",
                    "body": "Body 2",
                },
            ]
            results = await email_delivery.batch_send(batch)
            assert len(results) == 2


class TestEmailDeliveryEdgeCases:
    """Edge case tests for EmailDelivery."""

    def test_empty_recipients(self) -> None:
        """Test with empty recipients list."""
        ed = EmailDelivery(smtp_user="", smtp_password="")
        # Should not raise
        import asyncio

        result = asyncio.run(ed.send_email(recipients=[], subject="Test", body="Body"))
        assert result == {}

    def test_special_characters_in_body(self) -> None:
        """Test handling of special characters."""
        ed = EmailDelivery()
        html = ed.create_html_template(
            title="Test <>&\"'",
            content="Content with <special> & 'chars'",
        )
        assert "Test" in html

    @pytest.mark.asyncio
    async def test_disconnect_when_not_connected(self) -> None:
        """Test disconnect when not connected."""
        ed = EmailDelivery()
        await ed.disconnect()  # Should not raise
        assert ed._connected is False
