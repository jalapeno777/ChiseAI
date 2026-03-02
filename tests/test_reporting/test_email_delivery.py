"""Tests for email delivery functionality."""

from unittest.mock import Mock, patch

import pytest
from src.reporting.scheduler import ReportScheduler


class TestEmailDelivery:
    """Test email delivery implementation."""

    @pytest.fixture
    def scheduler(self):
        """Create a ReportScheduler instance for testing."""
        return ReportScheduler()

    @pytest.mark.asyncio
    async def test_send_email_success(self, scheduler):
        """Test successful email sending."""
        with patch.dict(
            "os.environ",
            {
                "SMTP_USER": "test@example.com",
                "SMTP_PASSWORD": "testpass",
                "SMTP_HOST": "smtp.test.com",
                "SMTP_PORT": "587",
            },
        ):
            with patch("smtplib.SMTP") as mock_smtp_class:
                mock_server = Mock()
                mock_smtp_class.return_value.__enter__ = Mock(return_value=mock_server)
                mock_smtp_class.return_value.__exit__ = Mock(return_value=False)

                result = await scheduler._send_email(
                    recipients=["recipient@example.com"],
                    content="Test body",
                    subject="Test Subject",
                )

                assert result is True
                mock_server.starttls.assert_called_once()
                mock_server.login.assert_called_once_with(
                    "test@example.com", "testpass"
                )
                mock_server.sendmail.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_email_no_credentials(self, scheduler):
        """Test graceful handling when SMTP not configured."""
        with patch.dict(
            "os.environ",
            {"SMTP_USER": "", "SMTP_PASSWORD": ""},
        ):
            result = await scheduler._send_email(
                recipients=["test@example.com"],
                subject="Test",
                content="Body",
            )
            # Should return True (graceful degradation)
            assert result is True

    @pytest.mark.asyncio
    async def test_send_email_failure(self, scheduler):
        """Test handling of SMTP failure."""
        with patch.dict(
            "os.environ",
            {
                "SMTP_USER": "test@example.com",
                "SMTP_PASSWORD": "testpass",
            },
        ):
            with patch("smtplib.SMTP") as mock_smtp_class:
                mock_smtp_class.side_effect = Exception("SMTP connection failed")

                result = await scheduler._send_email(
                    recipients=["test@example.com"],
                    subject="Test",
                    content="Body",
                )

                assert result is False

    @pytest.mark.asyncio
    async def test_send_email_multiple_recipients(self, scheduler):
        """Test sending email to multiple recipients."""
        with patch.dict(
            "os.environ",
            {
                "SMTP_USER": "test@example.com",
                "SMTP_PASSWORD": "testpass",
            },
        ):
            with patch("smtplib.SMTP") as mock_smtp_class:
                mock_server = Mock()
                mock_smtp_class.return_value.__enter__ = Mock(return_value=mock_server)
                mock_smtp_class.return_value.__exit__ = Mock(return_value=False)

                recipients = [
                    "user1@example.com",
                    "user2@example.com",
                    "user3@example.com",
                ]
                result = await scheduler._send_email(
                    recipients=recipients,
                    content="Test body",
                    subject="Test Subject",
                )

                assert result is True
                # Should send to each recipient
                assert mock_server.sendmail.call_count == len(recipients)

    @pytest.mark.asyncio
    async def test_send_email_with_html(self, scheduler):
        """Test sending email with HTML content."""
        with patch.dict(
            "os.environ",
            {
                "SMTP_USER": "test@example.com",
                "SMTP_PASSWORD": "testpass",
            },
        ):
            with patch("smtplib.SMTP") as mock_smtp_class:
                mock_server = Mock()
                mock_smtp_class.return_value.__enter__ = Mock(return_value=mock_server)
                mock_smtp_class.return_value.__exit__ = Mock(return_value=False)

                result = await scheduler._send_email(
                    recipients=["recipient@example.com"],
                    content="Plain text body",
                    subject="Test Subject",
                    html_content="<html><body>HTML body</body></html>",
                )

                assert result is True
                mock_server.sendmail.assert_called_once()

    def test_send_smtp_email(self, scheduler):
        """Test the blocking SMTP email sending method."""
        with patch("smtplib.SMTP") as mock_smtp_class:
            mock_server = Mock()
            mock_smtp_class.return_value.__enter__ = Mock(return_value=mock_server)
            mock_smtp_class.return_value.__exit__ = Mock(return_value=False)

            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText

            msg = MIMEMultipart("alternative")
            msg.attach(MIMEText("Test content", "plain"))

            scheduler._send_smtp_email(
                smtp_host="smtp.test.com",
                smtp_port=587,
                smtp_user="test@example.com",
                smtp_password="testpass",
                sender="sender@example.com",
                recipient="recipient@example.com",
                msg=msg,
            )

            mock_smtp_class.assert_called_once_with("smtp.test.com", 587)
            mock_server.starttls.assert_called_once()
            mock_server.login.assert_called_once_with("test@example.com", "testpass")
            mock_server.sendmail.assert_called_once()
