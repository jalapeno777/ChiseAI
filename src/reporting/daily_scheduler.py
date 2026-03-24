"""Daily summary scheduler for ChiseAI paper trading.

Schedules daily summary generation at midnight local time and sends
reports to Discord. Supports immediate test dispatch.

For PAPER-LIVE-001: Daily Summary Scheduler
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from datetime import UTC, datetime, timedelta
from typing import Any

import aiohttp
import yaml

from src.reporting.daily_generator import DailyReportGenerator
from src.reporting.models import DailyReport

logger = logging.getLogger(__name__)


class DailySummaryScheduler:
    """Schedule and manage daily summary reports.

    Features:
    - Schedule daily reports at configurable time (default: midnight)
    - Query paper trading metrics from InfluxDB/telemetry
    - Send reports to Discord #summaries channel
    - Support immediate test dispatch

    Attributes:
        config: Scheduler configuration
        report_generator: Daily report generator
        discord_webhook_url: Discord webhook URL for summaries
        test_channel_webhook: Discord webhook URL for test channel
    """

    def __init__(
        self,
        config_path: str | None = None,
        influxdb_client: Any | None = None,
    ) -> None:
        """Initialize daily summary scheduler.

        Args:
            config_path: Path to scheduler.yaml config file
            influxdb_client: InfluxDB client instance
        """
        self._config_path = config_path or "config/scheduler.yaml"
        self._config = self._load_config()
        self._report_generator = DailyReportGenerator(influxdb_client)
        self._running = False
        self._scheduler_task: asyncio.Task | None = None

        # Discord webhooks
        self._summaries_webhook = self._config.get("discord", {}).get(
            "summaries_webhook_url"
        ) or os.getenv("DISCORD_SUMMARIES_WEBHOOK_URL")
        self._test_webhook = self._config.get("discord", {}).get(
            "test_webhook_url"
        ) or os.getenv("DISCORD_TEST_WEBHOOK_URL")

        # Schedule settings
        schedule = self._config.get("schedule", {})
        self._schedule_time = schedule.get("time", "00:00")
        self._timezone = schedule.get("timezone", "UTC")
        self._check_interval = schedule.get("check_interval_seconds", 60)

        # Metrics settings
        metrics = self._config.get("metrics", {})
        self._influxdb_bucket = metrics.get("bucket", "chiseai")
        self._influxdb_org = metrics.get("org", "chiseai")

        logger.info(
            f"DailySummaryScheduler initialized: "
            f"schedule_time={self._schedule_time}, timezone={self._timezone}"
        )

    def _load_config(self) -> dict[str, Any]:
        """Load scheduler configuration from YAML file.

        Returns:
            Configuration dictionary
        """
        if os.path.exists(self._config_path):
            try:
                with open(self._config_path) as f:
                    return yaml.safe_load(f) or {}
            except Exception as e:
                logger.warning(f"Failed to load config from {self._config_path}: {e}")

        # Return default config
        return {
            "schedule": {"time": "00:00", "timezone": "UTC"},
            "discord": {},
            "metrics": {"bucket": "chiseai", "org": "chiseai"},
        }

    async def start(self) -> None:
        """Start the scheduler loop."""
        if self._running:
            logger.warning("Scheduler already running")
            return

        self._running = True
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        logger.info(
            f"Daily summary scheduler started "
            f"(runs at {self._schedule_time} {self._timezone})"
        )

    async def stop(self) -> None:
        """Stop the scheduler loop."""
        if not self._running:
            return

        self._running = False

        if self._scheduler_task and not self._scheduler_task.done():
            self._scheduler_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._scheduler_task

        logger.info("Daily summary scheduler stopped")

    async def _scheduler_loop(self) -> None:
        """Main scheduler loop."""
        while self._running:
            try:
                await self._check_schedule()
                await asyncio.sleep(self._check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Scheduler loop error: {e}")
                await asyncio.sleep(self._check_interval)

    async def _check_schedule(self) -> None:
        """Check if it's time to run the daily summary."""
        now = datetime.now(UTC)

        # Parse schedule time (HH:MM)
        try:
            hour, minute = map(int, self._schedule_time.split(":"))
        except ValueError:
            logger.error(f"Invalid schedule time format: {self._schedule_time}")
            return

        # Check if we should run now (within the last minute)
        if now.hour == hour and now.minute == minute:
            # Check if already run today
            last_run_key = f"daily_summary_last_run_{now.strftime('%Y%m%d')}"
            last_run = getattr(self, f"_{last_run_key}", None)

            if last_run != now.strftime("%Y%m%d"):
                logger.info("Triggering scheduled daily summary")
                await self.generate_and_send()
                setattr(self, f"_{last_run_key}", now.strftime("%Y%m%d"))

    async def generate_and_send(
        self,
        test_mode: bool = False,
        dry_run: bool = False,
        date: datetime | None = None,
    ) -> dict[str, Any]:
        """Generate and send daily summary report.

        Args:
            test_mode: Send to test channel instead of summaries channel
            dry_run: Generate report without sending
            date: Specific date for report (default: yesterday)

        Returns:
            Dictionary with result status and message info
        """
        try:
            # Generate report
            if date is None:
                date = datetime.now(UTC) - timedelta(days=1)

            logger.info(f"Generating daily summary for {date.strftime('%Y-%m-%d')}")
            report = await self._report_generator.generate_report(date=date)

            if dry_run:
                logger.info("Dry run mode - report generated but not sent")
                return {
                    "success": True,
                    "dry_run": True,
                    "report": report.to_dict(),
                    "message": "Report generated (dry run)",
                }

            # Format report for Discord
            content = self._format_discord_message(report)

            # Send to appropriate channel
            webhook_url = self._test_webhook if test_mode else self._summaries_webhook
            channel_name = "#test" if test_mode else "#summaries"

            if not webhook_url:
                error_msg = f"No webhook URL configured for {channel_name}"
                logger.error(error_msg)
                return {
                    "success": False,
                    "error": error_msg,
                    "report": report.to_dict(),
                }

            result = await self._send_to_discord(webhook_url, content, report)

            if result["success"]:
                logger.info(f"Daily summary sent to {channel_name}")
            else:
                logger.error(f"Failed to send daily summary: {result.get('error')}")

            return result

        except Exception as e:
            logger.error(f"Failed to generate/send daily summary: {e}")
            return {
                "success": False,
                "error": str(e),
            }

    def _format_discord_message(self, report: DailyReport) -> str:
        """Format report as Discord message.

        Args:
            report: Daily report to format

        Returns:
            Formatted message string
        """
        # Use the existing markdown format but adapt for Discord
        lines = [
            "📊 **Daily Trading Summary**",
            "",
            f"**Date:** {report.date.strftime('%Y-%m-%d')}",
            f"**Generated:** {report.generated_at.strftime('%Y-%m-%d %H:%M:%S UTC')}",
            "",
            "📈 **PnL Summary**",
            "```",
            f"Total PnL:       ${report.total_pnl:,.2f}",
            f"Realized PnL:    ${report.realized_pnl:,.2f}",
            f"Unrealized PnL:  ${report.unrealized_pnl:,.2f}",
            f"Portfolio Value: ${report.portfolio_value:,.2f}",
            "```",
            "",
            "📊 **Trade Statistics**",
            "```",
            f"Total Trades:    {report.total_trades}",
            f"Winning Trades:  {report.winning_trades}",
            f"Losing Trades:   {report.losing_trades}",
            f"Win Rate:        {report.win_rate:.1f}%",
            f"Avg PnL/Trade:   ${report.avg_pnl:,.2f}",
            "```",
            "",
            "⚠️ **Risk Metrics**",
            "```",
            f"Max Drawdown:    ${report.max_drawdown:,.2f} "
            f"({report.max_drawdown_pct:.1f}%)",
            f"Sharpe Ratio:    {report.risk_metrics.sharpe_ratio:.2f}",
            f"Volatility:      {report.risk_metrics.volatility:.2%}",
            f"Open Positions:  {report.open_positions}",
            "```",
            "",
            "🏆 **Best/Worst Trades**",
            "```",
            f"Best Trade:  ${report.trade_metrics.largest_win:,.2f}",
            f"Worst Trade: ${report.trade_metrics.largest_loss:,.2f}",
            "```",
            "",
            "---",
            "*Report generated by ChiseAI Automated Reporting System*",
        ]
        return "\n".join(lines)

    async def _send_to_discord(
        self,
        webhook_url: str,
        content: str,
        report: DailyReport,
    ) -> dict[str, Any]:
        """Send message to Discord webhook.

        Args:
            webhook_url: Discord webhook URL
            content: Message content
            report: The report being sent

        Returns:
            Dictionary with success status and message info
        """
        try:
            # Discord has a 2000 character limit for content
            # Split long messages if needed
            chunks = self._split_message(content, 1900)
            message_ids = []

            async with aiohttp.ClientSession() as session:
                for i, chunk in enumerate(chunks):
                    payload = {
                        "content": f"{chunk}",
                    }

                    async with session.post(
                        webhook_url,
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=30),
                    ) as response:
                        if response.status == 204:
                            # Discord returns 204 on success
                            # Try to get message ID from headers (if available)
                            message_id = response.headers.get(
                                "X-Message-ID", f"part_{i + 1}"
                            )
                            message_ids.append(message_id)
                            logger.debug(f"Discord message sent (part {i + 1})")
                        elif response.status == 429:
                            # Rate limited
                            retry_after = float(
                                response.headers.get("Retry-After", "5")
                            )
                            logger.warning(
                                f"Discord rate limited, retry after {retry_after}s"
                            )
                            return {
                                "success": False,
                                "error": f"Rate limited. Retry after {retry_after}s",
                                "retry_after": retry_after,
                            }
                        else:
                            body = await response.text()
                            error_msg = (
                                f"Discord webhook returned {response.status}: {body}"
                            )
                            logger.warning(error_msg)
                            return {
                                "success": False,
                                "error": error_msg,
                            }

            return {
                "success": True,
                "message_ids": message_ids,
                "report": report.to_dict(),
            }

        except Exception as e:
            logger.error(f"Failed to send Discord message: {e}")
            return {
                "success": False,
                "error": str(e),
            }

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

    async def health_check(self) -> dict[str, Any]:
        """Check scheduler health.

        Returns:
            Health status dictionary
        """
        # Test Discord connectivity
        discord_healthy = False
        discord_error = None

        if self._summaries_webhook:
            try:
                async with (
                    aiohttp.ClientSession() as session,
                    session.get(self._summaries_webhook) as resp,
                ):
                    # Webhooks return 200 with webhook info on GET
                    discord_healthy = resp.status in (200, 401, 403)
            except Exception as e:
                discord_error = str(e)

        return {
            "healthy": True,
            "running": self._running,
            "schedule": {
                "time": self._schedule_time,
                "timezone": self._timezone,
            },
            "discord": {
                "summaries_webhook_configured": bool(self._summaries_webhook),
                "test_webhook_configured": bool(self._test_webhook),
                "healthy": discord_healthy,
                "error": discord_error,
            },
            "influxdb": {
                "bucket": self._influxdb_bucket,
                "org": self._influxdb_org,
            },
        }

    def get_config(self) -> dict[str, Any]:
        """Get current scheduler configuration.

        Returns:
            Configuration dictionary
        """
        return {
            "schedule": {
                "time": self._schedule_time,
                "timezone": self._timezone,
                "check_interval_seconds": self._check_interval,
            },
            "discord": {
                "summaries_webhook_configured": bool(self._summaries_webhook),
                "test_webhook_configured": bool(self._test_webhook),
            },
            "metrics": {
                "bucket": self._influxdb_bucket,
                "org": self._influxdb_org,
            },
        }
