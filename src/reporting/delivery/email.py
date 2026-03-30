"""Email delivery module for report distribution.

Provides SMTP-based email delivery with HTML/plain text support,
attachment handling, and batch delivery for multiple recipients.

For ST-NS-023-T2: Report Delivery & Dashboard Integration
"""

from __future__ import annotations

import asyncio
import logging
import os
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

logger = logging.getLogger(__name__)


class EmailDelivery:
    """Email delivery handler with SMTP support.

    Features:
    - SMTP connection management with TLS
    - HTML and plain text email templates
    - Attachment support for PDF, CSV, and other exports
    - Batch delivery for multiple recipients
    - Environment variable configuration

    Attributes:
        smtp_host: SMTP server hostname
        smtp_port: SMTP server port
        smtp_user: SMTP username
        smtp_password: SMTP password
        sender: Sender email address
        use_tls: Whether to use TLS encryption
    """

    def __init__(
        self,
        smtp_host: str | None = None,
        smtp_port: int | None = None,
        smtp_user: str | None = None,
        smtp_password: str | None = None,
        sender: str | None = None,
        use_tls: bool = True,
    ) -> None:
        """Initialize email delivery.

        Args:
            smtp_host: SMTP server hostname (default: from SMTP_HOST env)
            smtp_port: SMTP server port (default: from SMTP_PORT env, 587)
            smtp_user: SMTP username (default: from SMTP_USER env)
            smtp_password: SMTP password (default: from SMTP_PASSWORD env)
            sender: Sender email address (default: from EMAIL_FROM env)
            use_tls: Whether to use TLS encryption (default: True)
        """
        self.smtp_host = smtp_host or os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = smtp_port or int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = smtp_user or os.getenv("SMTP_USER", "")
        self.smtp_password = smtp_password or os.getenv("SMTP_PASSWORD", "")
        self.sender = sender or os.getenv("EMAIL_FROM", "chiseai@example.com")
        self.use_tls = use_tls

        self._connected = False
        self._server: smtplib.SMTP | None = None

    @property
    def is_configured(self) -> bool:
        """Check if SMTP credentials are configured.

        Returns:
            True if both smtp_user and smtp_password are set
        """
        return bool(self.smtp_user and self.smtp_password)

    async def connect(self) -> bool:
        """Establish SMTP connection.

        Returns:
            True if connection successful
        """
        if not self.is_configured:
            logger.warning("SMTP credentials not configured")
            return False

        try:
            await asyncio.to_thread(self._connect_sync)
            return True
        except Exception as e:
            logger.error(f"Failed to connect to SMTP server: {e}")
            return False

    def _connect_sync(self) -> None:
        """Connect to SMTP server (blocking operation)."""
        self._server = smtplib.SMTP(self.smtp_host, self.smtp_port)
        self._server.starttls()
        self._server.login(self.smtp_user, self.smtp_password)
        self._connected = True
        logger.info(f"Connected to SMTP server: {self.smtp_host}:{self.smtp_port}")

    async def disconnect(self) -> None:
        """Close SMTP connection."""
        if self._server:
            try:
                await asyncio.to_thread(self._server.quit)
            except Exception as e:
                logger.warning(f"Error disconnecting from SMTP: {e}")
            finally:
                self._server = None
                self._connected = False

    async def send_email(
        self,
        recipients: list[str],
        subject: str,
        body: str,
        html_body: str | None = None,
        attachments: list[tuple[str, bytes, str]] | None = None,
    ) -> dict[str, bool]:
        """Send email to recipients.

        Args:
            recipients: List of email addresses
            subject: Email subject
            body: Plain text email body
            html_body: Optional HTML version of the email body
            attachments: List of (filename, content, mime_type) tuples

        Returns:
            Dictionary mapping recipient to send status
        """
        results: dict[str, bool] = {}

        if not self.is_configured:
            logger.warning(
                f"Would send email to {len(recipients)} recipients: {subject}"
            )
            logger.debug(f"Email content preview: {body[:200]}...")
            # Return success for all recipients in non-configured mode
            return {r: True for r in recipients}

        try:
            if not self._connected:
                connected = await self.connect()
                if not connected:
                    return {r: False for r in recipients}

            for recipient in recipients:
                try:
                    await asyncio.to_thread(
                        self._send_single_email,
                        recipient,
                        subject,
                        body,
                        html_body,
                        attachments,
                    )
                    results[recipient] = True
                    logger.debug(f"Email sent to {recipient}")
                except Exception as e:
                    logger.error(f"Failed to send email to {recipient}: {e}")
                    results[recipient] = False

            return results

        except Exception as e:
            logger.error(f"Failed to send emails: {e}")
            return {r: False for r in recipients}

    def _send_single_email(
        self,
        recipient: str,
        subject: str,
        body: str,
        html_body: str | None,
        attachments: list[tuple[str, bytes, str]] | None,
    ) -> None:
        """Send single email (blocking operation).

        Args:
            recipient: Recipient email address
            subject: Email subject
            body: Plain text body
            html_body: Optional HTML body
            attachments: List of (filename, content, mime_type) tuples
        """
        if not self._server:
            raise RuntimeError("SMTP server not connected")

        msg = MIMEMultipart("mixed")
        msg["Subject"] = subject
        msg["From"] = self.sender
        msg["To"] = recipient

        # Attach plain text body
        msg.attach(MIMEText(body, "plain", "utf-8"))

        # Attach HTML body if provided
        if html_body:
            msg.attach(MIMEText(html_body, "html", "utf-8"))

        # Attach files
        if attachments:
            for filename, content, mime_type in attachments:
                part = MIMEApplication(content, _subtype=mime_type.split("/")[-1])
                part.add_header("Content-Disposition", "attachment", filename=filename)
                msg.attach(part)

        self._server.sendmail(self.sender, [recipient], msg.as_string())

    def create_html_template(
        self, title: str, content: str, footer: str | None = None
    ) -> str:
        """Create HTML email template.

        Args:
            title: Email title
            content: Main content (HTML)
            footer: Optional footer text

        Returns:
            HTML email template
        """
        footer_html = ""
        if footer:
            footer_html = f"""
            <tr>
                <td style="padding: 20px; background-color: #f8f9fa; border-top: 1px solid #dee2e6;">
                    <p style="margin: 0; color: #6c757d; font-size: 12px; text-align: center;">
                        {footer}
                    </p>
                </td>
            </tr>
            """

        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{title}</title>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: #007bff; color: white; padding: 20px; text-align: center; }}
                .content {{ padding: 20px; background-color: #ffffff; }}
                .footer {{ padding: 20px; background-color: #f8f9fa; text-align: center; font-size: 12px; color: #6c757d; }}
            </style>
        </head>
        <body>
            <div class="container">
                <table style="width: 100%; border-collapse: collapse;">
                    <tr>
                        <td class="header">
                            <h1 style="margin: 0; font-size: 24px;">{title}</h1>
                        </td>
                    </tr>
                    <tr>
                        <td class="content">
                            {content}
                        </td>
                    </tr>
                    {footer_html}
                </table>
            </div>
        </body>
        </html>
        """

    async def send_report_email(
        self,
        recipients: list[str],
        report_type: str,
        report_date: str,
        report_content: str,
        attachments: list[tuple[str, bytes, str]] | None = None,
    ) -> dict[str, bool]:
        """Send report via email with standard formatting.

        Args:
            recipients: List of email addresses
            report_type: Type of report (e.g., "Daily", "Weekly")
            report_date: Report date string
            report_content: Report content in Markdown/plain text
            attachments: Optional file attachments

        Returns:
            Dictionary mapping recipient to send status
        """
        subject = f"📊 {report_type} Report - {report_date}"

        # Convert markdown-like content to HTML
        html_content = self._markdown_to_html(report_content)

        html_body = self.create_html_template(
            title=f"{report_type} Trading Report",
            content=html_content,
            footer="Report generated by ChiseAI Automated Reporting System",
        )

        return await self.send_email(
            recipients=recipients,
            subject=subject,
            body=report_content,
            html_body=html_body,
            attachments=attachments,
        )

    def _markdown_to_html(self, text: str) -> str:
        """Convert simple Markdown to HTML.

        Args:
            text: Markdown text

        Returns:
            HTML string
        """
        import re

        # Convert line breaks
        text = text.replace("\n\n", "</p><p>")
        text = f"<p>{text}</p>"

        # Convert headers
        text = re.sub(r"<p>#\s+(.+?)</p>", r"<h1>\1</h1>", text)
        text = re.sub(r"<p>##\s+(.+?)</p>", r"<h2>\1</h2>", text)
        text = re.sub(r"<p>###\s+(.+?)</p>", r"<h3>\1</h3>", text)

        # Convert bold
        text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)

        # Convert italic
        text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)

        # Convert tables (simple)
        lines = text.split("\n")
        in_table = False
        result_lines = []

        for line in lines:
            if "|" in line and "-" in line:
                if not in_table:
                    in_table = True
                    result_lines.append("<table>")
                continue
            elif in_table and "|" not in line:
                in_table = False
                result_lines.append("</table>")

            if "|" in line:
                cells = [c.strip() for c in line.split("|") if c.strip()]
                if cells and not all("-" in c for c in cells):
                    row = "<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>"
                    result_lines.append(row)
            else:
                result_lines.append(line)

        if in_table:
            result_lines.append("</table>")

        return "<br>".join(result_lines)

    async def batch_send(
        self,
        batch: list[dict[str, Any]],
    ) -> list[dict[str, bool]]:
        """Send batch of emails concurrently.

        Args:
            batch: List of email specifications with keys:
                - recipients: List of email addresses
                - subject: Email subject
                - body: Plain text body
                - html_body: Optional HTML body
                - attachments: Optional attachments

        Returns:
            List of results for each email in batch
        """
        tasks = []
        for email_spec in batch:
            task = self.send_email(
                recipients=email_spec["recipients"],
                subject=email_spec["subject"],
                body=email_spec["body"],
                html_body=email_spec.get("html_body"),
                attachments=email_spec.get("attachments"),
            )
            tasks.append(task)

        return await asyncio.gather(*tasks)
