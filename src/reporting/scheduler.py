"""Report scheduler for automated report generation and delivery.

Provides cron-like scheduling for reports with:
- Discord webhook integration
- Email delivery (optional)
- Report archival to disk
- Configurable schedules

For PAPER-003-003: Automated Reporting and Anomaly Detection
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import smtplib
from datetime import UTC, datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

import aiohttp

from .anomaly_detector import AnomalyDetector
from .daily_generator import DailyReportGenerator
from .models import AnomalyAlert, PaperHealthReport, ReportSchedule
from .weekly_generator import WeeklyPerformanceReport

logger = logging.getLogger(__name__)


class ReportScheduler:
    """Schedule and manage automated report generation.

    Features:
    - Cron-like scheduling for daily and weekly reports
    - Discord webhook integration for notifications
    - Email delivery support (optional)
    - Report archival to disk
    - Anomaly detection and alerting

    Attributes:
        daily_generator: Daily report generator
        weekly_generator: Weekly report generator
        anomaly_detector: Anomaly detector
        schedules: List of configured schedules
        output_dir: Directory for report archival
    """

    def __init__(
        self,
        influxdb_client: Any | None = None,
        output_dir: str = "./reports",
        default_discord_webhook: str | None = None,
    ) -> None:
        """Initialize report scheduler.

        Args:
            influxdb_client: InfluxDB client instance
            output_dir: Directory for report archival
            default_discord_webhook: Default Discord webhook URL
        """
        self.daily_generator = DailyReportGenerator(influxdb_client)
        self.weekly_generator = WeeklyPerformanceReport(influxdb_client)
        self.anomaly_detector = AnomalyDetector(influxdb_client)

        self._schedules: list[ReportSchedule] = []
        self._output_dir = output_dir
        self._default_discord_webhook = default_discord_webhook
        self._running = False
        self._scheduler_task: asyncio.Task | None = None
        self._check_interval = 60  # Check every minute

        # Ensure output directory exists
        os.makedirs(output_dir, exist_ok=True)

        logger.info(f"ReportScheduler initialized: output_dir={output_dir}")

    def add_schedule(
        self,
        name: str,
        report_type: str,
        cron_expression: str,
        discord_webhook: str | None = None,
        email_recipients: list[str] | None = None,
        enabled: bool = True,
    ) -> ReportSchedule:
        """Add a new report schedule.

        Args:
            name: Schedule name
            report_type: "daily" or "weekly"
            cron_expression: Cron expression (e.g., "0 9 * * *" for 9 AM daily)
            discord_webhook: Discord webhook URL (optional)
            email_recipients: List of email addresses (optional)
            enabled: Whether schedule is enabled

        Returns:
            Created ReportSchedule
        """
        schedule = ReportSchedule(
            name=name,
            report_type=report_type,
            cron_expression=cron_expression,
            enabled=enabled,
            discord_webhook=discord_webhook or self._default_discord_webhook,
            email_recipients=email_recipients or [],
            output_dir=self._output_dir,
        )

        self._schedules.append(schedule)
        logger.info(f"Added schedule: {name} ({report_type}) - {cron_expression}")

        return schedule

    def remove_schedule(self, name: str) -> bool:
        """Remove a schedule by name.

        Args:
            name: Schedule name to remove

        Returns:
            True if removed, False if not found
        """
        for i, schedule in enumerate(self._schedules):
            if schedule.name == name:
                self._schedules.pop(i)
                logger.info(f"Removed schedule: {name}")
                return True
        return False

    def get_schedules(self) -> list[ReportSchedule]:
        """Get all configured schedules.

        Returns:
            List of ReportSchedule objects
        """
        return self._schedules.copy()

    async def start(self) -> None:
        """Start the scheduler loop."""
        if self._running:
            logger.warning("Scheduler already running")
            return

        self._running = True
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        logger.info("Report scheduler started")

    async def stop(self) -> None:
        """Stop the scheduler loop."""
        if not self._running:
            return

        self._running = False

        if self._scheduler_task and not self._scheduler_task.done():
            self._scheduler_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._scheduler_task

        logger.info("Report scheduler stopped")

    async def _scheduler_loop(self) -> None:
        """Main scheduler loop."""
        while self._running:
            try:
                await self._check_schedules()
                await asyncio.sleep(self._check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Scheduler loop error: {e}")
                await asyncio.sleep(self._check_interval)

    async def _check_schedules(self) -> None:
        """Check all schedules and trigger due reports."""
        now = datetime.now(UTC)

        for schedule in self._schedules:
            if not schedule.enabled:
                continue

            # Check if schedule is due
            if self._is_due(schedule, now):
                try:
                    await self._execute_schedule(schedule, now)
                except Exception as e:
                    logger.error(f"Error executing schedule {schedule.name}: {e}")

    def _is_due(self, schedule: ReportSchedule, now: datetime) -> bool:
        """Check if a schedule is due to run.

        Args:
            schedule: Schedule to check
            now: Current datetime

        Returns:
            True if schedule is due
        """
        # Simple cron parsing (minute hour day month day_of_week)
        parts = schedule.cron_expression.split()
        if len(parts) != 5:
            logger.warning(f"Invalid cron expression: {schedule.cron_expression}")
            return False

        minute, hour, day, month, day_of_week = parts

        # Check if already run this period
        if schedule.last_run:
            if schedule.report_type == "daily":
                # Check if already run today
                if schedule.last_run.date() == now.date():
                    return False
            elif schedule.report_type == "weekly":
                # Check if already run this week
                if schedule.last_run.isocalendar()[1] == now.isocalendar()[1]:
                    return False

        # Check time match
        if minute != "*" and int(minute) != now.minute:
            return False
        if hour != "*" and int(hour) != now.hour:
            return False
        if day != "*" and int(day) != now.day:
            return False
        if month != "*" and int(month) != now.month:
            return False
        return not (day_of_week != "*" and int(day_of_week) != now.weekday())

    async def _execute_schedule(
        self,
        schedule: ReportSchedule,
        now: datetime,
    ) -> None:
        """Execute a schedule.

        Args:
            schedule: Schedule to execute
            now: Current datetime
        """
        logger.info(f"Executing schedule: {schedule.name}")

        # Update last run time
        schedule.last_run = now

        # Generate report based on type
        if schedule.report_type == "daily":
            await self._generate_and_send_daily(schedule)
        elif schedule.report_type == "weekly":
            await self._generate_and_send_weekly(schedule)
        elif schedule.report_type == "paper_health":
            await self._generate_and_send_paper_health(schedule)

        # Run anomaly detection
        await self._run_anomaly_detection(schedule)

    async def _generate_and_send_daily(self, schedule: ReportSchedule) -> None:
        """Generate and send daily report.

        Args:
            schedule: Schedule configuration
        """
        try:
            # Generate report for yesterday
            report = await self.daily_generator.generate_report()

            # Save to disk
            await self._save_report(report, "daily", schedule)

            # Send to Discord
            if schedule.discord_webhook:
                await self._send_to_discord(
                    schedule.discord_webhook,
                    report.to_markdown(),
                    f"📊 Daily Trading Summary - {report.date.strftime('%Y-%m-%d')}",
                )

            # Send email (if configured)
            if schedule.email_recipients:
                await self._send_email(
                    schedule.email_recipients,
                    report.to_markdown(),
                    f"Daily Trading Summary - {report.date.strftime('%Y-%m-%d')}",
                )

            logger.info(f"Daily report sent for {report.date.strftime('%Y-%m-%d')}")

        except Exception as e:
            logger.error(f"Failed to generate/send daily report: {e}")

    async def _generate_and_send_weekly(self, schedule: ReportSchedule) -> None:
        """Generate and send weekly report.

        Args:
            schedule: Schedule configuration
        """
        try:
            # Generate report
            report = await self.weekly_generator.generate_report()

            # Save to disk
            await self._save_report(report, "weekly", schedule)

            # Send to Discord
            if schedule.discord_webhook:
                await self._send_to_discord(
                    schedule.discord_webhook,
                    report.to_markdown(),
                    f"📈 Weekly Performance Report - {report.start_date.strftime('%Y-%m-%d')} to {report.end_date.strftime('%Y-%m-%d')}",
                )

            # Send email (if configured)
            if schedule.email_recipients:
                await self._send_email(
                    schedule.email_recipients,
                    report.to_markdown(),
                    f"Weekly Performance Report - {report.start_date.strftime('%Y-%m-%d')} to {report.end_date.strftime('%Y-%m-%d')}",
                )

            logger.info(
                f"Weekly report sent for {report.start_date.strftime('%Y-%m-%d')} to "
                f"{report.end_date.strftime('%Y-%m-%d')}"
            )

        except Exception as e:
            logger.error(f"Failed to generate/send weekly report: {e}")

    async def _run_anomaly_detection(self, schedule: ReportSchedule) -> None:
        """Run anomaly detection and send alerts.

        Args:
            schedule: Schedule configuration
        """
        try:
            alerts = await self.anomaly_detector.detect_all()

            for alert in alerts:
                # Save alert to disk
                await self._save_alert(alert, schedule)

                # Send alert to Discord
                if schedule.discord_webhook:
                    await self._send_to_discord(
                        schedule.discord_webhook,
                        alert.to_markdown(),
                        f"🚨 Anomaly Detected - {alert.anomaly_type.value}",
                    )

                logger.warning(f"Anomaly alert sent: {alert.anomaly_type.value}")

        except Exception as e:
            logger.error(f"Failed to run anomaly detection: {e}")

    async def _save_report(
        self,
        report: Any,
        report_type: str,
        schedule: ReportSchedule,
    ) -> None:
        """Save report to disk.

        Args:
            report: Report object to save
            report_type: "daily" or "weekly"
            schedule: Schedule configuration
        """
        # Create directory structure
        report_dir = os.path.join(schedule.output_dir, report_type)
        os.makedirs(report_dir, exist_ok=True)

        # Generate filename
        now = datetime.now(UTC)
        filename = f"{report_type}_{now.strftime('%Y%m%d_%H%M%S')}.json"
        filepath = os.path.join(report_dir, filename)

        # Save as JSON
        with open(filepath, "w") as f:
            json.dump(report.to_dict(), f, indent=2)

        logger.debug(f"Report saved: {filepath}")

        # Clean up old reports
        await self._cleanup_old_reports(report_dir, schedule.archive_days)

    async def _save_alert(
        self,
        alert: AnomalyAlert,
        schedule: ReportSchedule,
    ) -> None:
        """Save alert to disk.

        Args:
            alert: Alert to save
            schedule: Schedule configuration
        """
        alert_dir = os.path.join(schedule.output_dir, "alerts")
        os.makedirs(alert_dir, exist_ok=True)

        now = datetime.now(UTC)
        filename = (
            f"alert_{alert.anomaly_type.value}_{now.strftime('%Y%m%d_%H%M%S')}.json"
        )
        filepath = os.path.join(alert_dir, filename)

        with open(filepath, "w") as f:
            json.dump(alert.to_dict(), f, indent=2)

        logger.debug(f"Alert saved: {filepath}")

    async def _cleanup_old_reports(self, directory: str, max_days: int) -> None:
        """Clean up old reports.

        Args:
            directory: Directory to clean
            max_days: Maximum age in days
        """
        cutoff = datetime.now(UTC) - timedelta(days=max_days)

        try:
            for filename in os.listdir(directory):
                filepath = os.path.join(directory, filename)
                if os.path.isfile(filepath):
                    mtime = datetime.fromtimestamp(os.path.getmtime(filepath), UTC)
                    if mtime < cutoff:
                        os.remove(filepath)
                        logger.debug(f"Removed old report: {filepath}")
        except Exception as e:
            logger.warning(f"Failed to cleanup old reports: {e}")

    async def _send_to_discord(
        self,
        webhook_url: str,
        content: str,
        title: str,
    ) -> bool:
        """Send message to Discord webhook.

        Args:
            webhook_url: Discord webhook URL
            content: Message content (Markdown)
            title: Message title

        Returns:
            True if sent successfully
        """
        try:
            # Discord has a 2000 character limit for content
            # Split long messages if needed
            chunks = self._split_message(content, 1900)

            async with aiohttp.ClientSession() as session:
                for i, chunk in enumerate(chunks):
                    payload = {
                        "content": (
                            f"**{title}** (Part {i + 1}/{len(chunks)})\n\n{chunk}"
                            if len(chunks) > 1
                            else f"**{title}**\n\n{chunk}"
                        ),
                    }

                    async with session.post(
                        webhook_url,
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=30),
                    ) as response:
                        if response.status == 204:
                            logger.debug(f"Discord message sent (part {i + 1})")
                        else:
                            logger.warning(
                                f"Discord webhook returned {response.status}"
                            )
                            return False

            return True

        except Exception as e:
            logger.error(f"Failed to send Discord message: {e}")
            return False

    async def _send_email(
        self,
        recipients: list[str],
        content: str,
        subject: str,
        html_content: str | None = None,
    ) -> bool:
        """Send email using configured SMTP server.

        Args:
            recipients: List of email addresses
            content: Email body (Markdown/plain text)
            subject: Email subject
            html_content: Optional HTML version of the email body

        Returns:
            True if sent successfully, False otherwise
        """
        try:
            # Get SMTP configuration from environment
            smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
            smtp_port = int(os.getenv("SMTP_PORT", "587"))
            smtp_user = os.getenv("SMTP_USER")
            smtp_password = os.getenv("SMTP_PASSWORD")
            sender = os.getenv("EMAIL_FROM", "chiseai@example.com")

            if not smtp_user or not smtp_password:
                logger.warning(
                    "SMTP credentials not configured, logging instead of sending"
                )
                logger.info(
                    f"Would send email to {len(recipients)} recipients: {subject}"
                )
                logger.debug(f"Email content preview: {content[:200]}...")
                return True  # Graceful degradation

            # Create message for each recipient
            success = True
            for recipient in recipients:
                msg = MIMEMultipart("alternative")
                msg["Subject"] = subject
                msg["From"] = sender
                msg["To"] = recipient

                # Attach plain text body
                msg.attach(MIMEText(content, "plain"))

                # Attach HTML body if provided
                if html_content:
                    msg.attach(MIMEText(html_content, "html"))

                # Connect to SMTP server and send
                # Use asyncio.to_thread for blocking smtplib operations
                await asyncio.to_thread(
                    self._send_smtp_email,
                    smtp_host,
                    smtp_port,
                    smtp_user,
                    smtp_password,
                    sender,
                    recipient,
                    msg,
                )

            logger.info(f"Email sent successfully to {len(recipients)} recipients")
            return success

        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False

    def _send_smtp_email(
        self,
        smtp_host: str,
        smtp_port: int,
        smtp_user: str,
        smtp_password: str,
        sender: str,
        recipient: str,
        msg: MIMEMultipart,
    ) -> None:
        """Send email via SMTP (blocking operation).

        Args:
            smtp_host: SMTP server hostname
            smtp_port: SMTP server port
            smtp_user: SMTP username
            smtp_password: SMTP password
            sender: Sender email address
            recipient: Recipient email address
            msg: Email message object
        """
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()  # Enable TLS
            server.login(smtp_user, smtp_password)
            server.sendmail(sender, [recipient], msg.as_string())

    def _split_message(self, content: str, max_length: int) -> list[str]:
        """Split message into chunks.

        Args:
            content: Message content
            max_length: Maximum chunk length

        Returns:
            List of message chunks
        """
        if len(content) <= max_length:
            return [content]

        chunks = []
        lines = content.split("\n")
        current_chunk = ""

        for line in lines:
            if len(current_chunk) + len(line) + 1 > max_length:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = line + "\n"
            else:
                current_chunk += line + "\n"

        if current_chunk:
            chunks.append(current_chunk.strip())

        return chunks

    async def _generate_and_send_paper_health(self, schedule: ReportSchedule) -> None:
        """Generate and send paper health report.

        Args:
            schedule: Schedule configuration

        For PAPER-004: Daily paper trading health/performance reports
        """
        try:
            from portfolio.paper_tracker import PaperTracker

            paper_tracker = PaperTracker()
        except Exception as e:
            logger.warning(f"Could not initialize PaperTracker: {e}")
            paper_tracker = None

        try:
            # Generate paper health report
            report = await self.daily_generator.generate_paper_health_report(
                paper_tracker=paper_tracker
            )

            # Save to disk
            await self._save_paper_health_report(report, schedule)

            # Send to Discord
            if schedule.discord_webhook:
                status_emoji = {
                    "HEALTHY": "✅",
                    "DEGRADED": "⚠️",
                    "CRITICAL": "🚨",
                }.get(report.health_metrics.overall_health, "⚠️")

                await self._send_to_discord(
                    schedule.discord_webhook,
                    report.to_markdown(),
                    f"{status_emoji} Paper Trading Health Report - {report.date.strftime('%Y-%m-%d')}",
                )

            # Send email (if configured)
            if schedule.email_recipients:
                await self._send_email(
                    schedule.email_recipients,
                    report.to_markdown(),
                    f"Paper Trading Health Report - {report.date.strftime('%Y-%m-%d')}",
                )

            # Log summary
            status = report.health_metrics.overall_health
            all_pass = report.health_metrics.all_pass
            logger.info(
                f"Paper health report sent: date={report.date.strftime('%Y-%m-%d')}, "
                f"status={status}, all_pass={all_pass}"
            )

            if report.warnings:
                for warning in report.warnings:
                    logger.warning(f"Paper health warning: {warning}")

        except Exception as e:
            logger.error(f"Failed to generate/send paper health report: {e}")

    async def _save_paper_health_report(
        self,
        report: PaperHealthReport,
        schedule: ReportSchedule,
    ) -> None:
        """Save paper health report to disk.

        Args:
            report: Paper health report to save
            schedule: Schedule configuration
        """
        import json
        import os

        # Create directory structure: reports/paper/daily/YYYY-MM-DD/
        report_dir = os.path.join(schedule.output_dir, "paper", "daily")
        date_dir = os.path.join(report_dir, report.date.strftime("%Y-%m-%d"))
        os.makedirs(date_dir, exist_ok=True)

        # Save as JSON
        json_path = os.path.join(date_dir, "report.json")
        with open(json_path, "w") as f:
            json.dump(report.to_dict(), f, indent=2)

        # Save as Markdown
        md_path = os.path.join(date_dir, "report.md")
        with open(md_path, "w") as f:
            f.write(report.to_markdown())

        logger.debug(f"Paper health report saved: {json_path}, {md_path}")

        # Clean up old reports
        await self._cleanup_old_paper_health_reports(report_dir, schedule.archive_days)

    async def _cleanup_old_paper_health_reports(
        self,
        report_dir: str,
        max_days: int,
    ) -> None:
        """Clean up old paper health reports.

        Args:
            report_dir: Base directory for paper health reports
            max_days: Maximum age in days
        """
        import shutil
        from datetime import UTC

        cutoff = datetime.now(UTC) - timedelta(days=max_days)
        daily_dir = os.path.join(report_dir, "daily")

        if not os.path.exists(daily_dir):
            return

        try:
            for date_str in os.listdir(daily_dir):
                date_dir = os.path.join(daily_dir, date_str)
                if not os.path.isdir(date_dir):
                    continue

                try:
                    dir_date = datetime.strptime(date_str, "%Y-%m-%d").replace(
                        tzinfo=UTC
                    )
                    if dir_date < cutoff:
                        shutil.rmtree(date_dir)
                        logger.debug(f"Removed old paper health report: {date_dir}")
                except ValueError:
                    # Invalid directory name format
                    continue
        except Exception as e:
            logger.warning(f"Failed to cleanup old paper health reports: {e}")

    async def generate_report_now(
        self,
        report_type: str,
        use_mock_data: bool = False,
    ) -> Any:
        """Generate a report immediately (manual trigger).

        Args:
            report_type: "daily" or "weekly"
            use_mock_data: Use mock data for testing

        Returns:
            Generated report
        """
        if report_type == "daily":
            return await self.daily_generator.generate_report(
                use_mock_data=use_mock_data
            )
        elif report_type == "weekly":
            return await self.weekly_generator.generate_report(
                use_mock_data=use_mock_data
            )
        else:
            raise ValueError(f"Unknown report type: {report_type}")

    async def detect_anomalies_now(self) -> list[AnomalyAlert]:
        """Run anomaly detection immediately (manual trigger).

        Returns:
            List of detected anomalies
        """
        return await self.anomaly_detector.detect_all()
