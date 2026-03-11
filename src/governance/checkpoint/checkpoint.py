"""Main checkpoint orchestration module.

This module provides the CheckpointManager class that orchestrates:
- Running checkpoint audits
- Collecting evidence
- Storing state in Redis
- Reporting results
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from src.governance.checkpoint.evidence import CheckpointEvidence, EvidenceCollector
from src.governance.checkpoint.gates import GateChecker, GateSummary
from src.governance.checkpoint.state import (
    CheckpointRecord,
    StateManager,
)

logger = logging.getLogger(__name__)


@dataclass
class CheckpointConfig:
    """Configuration for checkpoint operations."""

    redis_host: str = field(
        default_factory=lambda: os.getenv("REDIS_HOST", "host.docker.internal")
    )
    redis_port: int = field(
        default_factory=lambda: int(os.getenv("REDIS_PORT", "6380"))
    )
    discord_channel_id: str = field(
        default_factory=lambda: os.getenv("DISCORD_DEVELOPMENT_CHANNEL_ID", "")
    )
    discord_bot_token: str = field(
        default_factory=lambda: os.getenv("DISCORD_BOT_TOKEN", "")
    )
    discord_webhook_url: str = field(
        default_factory=lambda: os.getenv("DISCORD_WEBHOOK_URL", "")
    )
    archive_dir: str = field(
        default_factory=lambda: os.getenv("CHECKPOINT_ARCHIVE_DIR", "logs/checkpoints")
    )
    auto_notify: bool = True
    auto_archive: bool = True


@dataclass
class CheckpointReport:
    """Report from a checkpoint run."""

    checkpoint_id: str
    timestamp: datetime
    summary: GateSummary
    evidence: CheckpointEvidence
    record: CheckpointRecord
    discord_posted: bool = False
    archived: bool = False

    @property
    def success(self) -> bool:
        """Check if checkpoint was successful (no failures)."""
        return self.summary.fail_count == 0

    @property
    def status(self) -> str:
        """Get overall status string."""
        if self.summary.fail_count > 0:
            return "FAILED"
        elif self.summary.check_count > 0:
            return "DEGRADED"
        return "HEALTHY"


class CheckpointManager:
    """Orchestrates checkpoint audits and reporting.

    This is the main entry point for checkpoint operations. It coordinates:
    - Gate validation (G1-G8)
    - Evidence collection
    - State management
    - Discord notifications
    - File archiving

    Example:
        ```python
        # Create manager with default config
        manager = CheckpointManager()

        # Run a checkpoint
        report = await manager.run_checkpoint()

        # Check results
        if report.success:
            print("All gates passing!")
        else:
            print(f"Failed gates: {report.summary.fail_count}")
        ```
    """

    def __init__(self, config: CheckpointConfig | None = None):
        """Initialize the checkpoint manager.

        Args:
            config: Optional configuration. Uses defaults if not provided.
        """
        self.config = config or CheckpointConfig()

        # Initialize components
        self._gate_checker = GateChecker(
            redis_host=self.config.redis_host,
            redis_port=self.config.redis_port,
        )
        self._evidence_collector = EvidenceCollector(
            redis_host=self.config.redis_host,
            redis_port=self.config.redis_port,
            archive_dir=self.config.archive_dir,
        )
        self._state_manager = StateManager(
            redis_host=self.config.redis_host,
            redis_port=self.config.redis_port,
        )

    async def run_checkpoint(
        self,
        checkpoint_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        notify: bool | None = None,
        archive: bool | None = None,
    ) -> CheckpointReport:
        """Run a complete checkpoint audit.

        This method:
        1. Creates a checkpoint record
        2. Runs all G1-G8 gate checks
        3. Collects and stores evidence
        4. Updates checkpoint state
        5. Optionally notifies Discord and archives

        Args:
            checkpoint_id: Optional checkpoint ID (generated if not provided)
            metadata: Optional metadata to attach
            notify: Whether to notify Discord (defaults to config.auto_notify)
            archive: Whether to archive to file (defaults to config.auto_archive)

        Returns:
            CheckpointReport with full results
        """
        notify = self.config.auto_notify if notify is None else notify
        archive = self.config.auto_archive if archive is None else archive

        # Create checkpoint record
        record = self._state_manager.create_checkpoint(
            checkpoint_id=checkpoint_id,
            metadata=metadata,
        )

        # Mark as running
        self._state_manager.start_checkpoint(record.checkpoint_id)

        logger.info(f"Running checkpoint {record.checkpoint_id}")

        try:
            # Run all gate checks
            summary = self._gate_checker.run_all_checks()

            # Complete the checkpoint
            self._state_manager.complete_checkpoint(record.checkpoint_id, summary)

            # Collect and store evidence
            evidence = self._evidence_collector.collect_and_store(
                summary=summary,
                metadata=metadata,
                archive=archive,
            )

            # Refresh record with final state
            record = self._state_manager.get_checkpoint(record.checkpoint_id)
            if not record:
                raise RuntimeError("Failed to retrieve updated checkpoint record")

            # Notify Discord if enabled
            discord_posted = False
            if notify:
                discord_posted = await self._notify_discord(evidence)

            report = CheckpointReport(
                checkpoint_id=record.checkpoint_id,
                timestamp=datetime.now(UTC),
                summary=summary,
                evidence=evidence,
                record=record,
                discord_posted=discord_posted,
                archived=archive and evidence.archived_path is not None,
            )

            logger.info(
                f"Checkpoint {record.checkpoint_id} completed: "
                f"{summary.pass_count} pass, {summary.check_count} check, {summary.fail_count} fail"
            )

            return report

        except Exception as e:
            logger.error(f"Checkpoint {record.checkpoint_id} failed: {e}")
            self._state_manager.fail_checkpoint(record.checkpoint_id, str(e))
            raise

    async def run_quick_check(self) -> GateSummary:
        """Run a quick gate check without full checkpoint overhead.

        This is useful for health checks or monitoring that don't need
        the full checkpoint record and evidence collection.

        Returns:
            GateSummary with all gate results
        """
        return self._gate_checker.run_all_checks()

    async def _notify_discord(self, evidence: CheckpointEvidence) -> bool:
        """Send checkpoint notification to Discord.

        Args:
            evidence: CheckpointEvidence to send

        Returns:
            True if notification was sent successfully
        """
        if not any(
            [
                self.config.discord_webhook_url,
                self.config.discord_bot_token,
            ]
        ):
            logger.debug("Discord not configured, skipping notification")
            return False

        try:
            message = self._evidence_collector.format_for_discord(evidence)
            return await self._post_discord(message)
        except Exception as e:
            logger.error(f"Failed to notify Discord: {e}")
            return False

    async def _post_discord(self, message: str) -> bool:
        """Post message to Discord via webhook or bot API.

        Args:
            message: Message to post

        Returns:
            True if posted successfully
        """
        # Try webhook first
        if self.config.discord_webhook_url:
            try:
                return await self._post_webhook(message)
            except Exception as e:
                logger.warning(f"Webhook post failed: {e}")

        # Fall back to bot API
        if self.config.discord_bot_token and self.config.discord_channel_id:
            try:
                return await self._post_bot_api(message)
            except Exception as e:
                logger.warning(f"Bot API post failed: {e}")

        return False

    async def _post_webhook(self, message: str) -> bool:
        """Post to Discord via webhook."""
        try:
            import aiohttp
        except ImportError:
            logger.warning("aiohttp not available, cannot post to Discord")
            return False

        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.config.discord_webhook_url,
                json={"content": message},
            ) as resp:
                if resp.status in (200, 204):
                    logger.info("Discord webhook post successful")
                    return True
                else:
                    logger.warning(f"Discord webhook failed: {resp.status}")
                    return False

    async def _post_bot_api(self, message: str) -> bool:
        """Post to Discord via bot API."""
        try:
            import aiohttp
        except ImportError:
            logger.warning("aiohttp not available, cannot post to Discord")
            return False

        url = f"https://discord.com/api/v10/channels/{self.config.discord_channel_id}/messages"
        headers = {
            "Authorization": f"Bot {self.config.discord_bot_token}",
            "Content-Type": "application/json",
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                headers=headers,
                json={"content": message},
            ) as resp:
                if resp.status == 200:
                    logger.info("Discord bot API post successful")
                    return True
                else:
                    logger.warning(f"Discord bot API failed: {resp.status}")
                    return False

    def get_latest_checkpoint(self) -> CheckpointRecord | None:
        """Get the most recent checkpoint record.

        Returns:
            CheckpointRecord if found, None otherwise
        """
        return self._state_manager.get_active_checkpoint()

    def get_checkpoint_history(
        self,
        limit: int = 10,
    ) -> list[CheckpointRecord]:
        """Get checkpoint history.

        Args:
            limit: Maximum number of records to retrieve

        Returns:
            List of CheckpointRecord objects
        """
        return self._state_manager.get_checkpoint_history(limit=limit)

    def is_healthy(self) -> bool:
        """Quick health check using latest checkpoint or fresh run.

        Returns:
            True if system is healthy (no failing gates)
        """
        # Try to get from latest checkpoint
        latest = self.get_latest_checkpoint()
        if latest and latest.summary:
            return latest.summary.fail_count == 0

        # Fall back to quick check
        summary = self._gate_checker.run_all_checks()
        return summary.fail_count == 0

    def get_failing_gates(self) -> list[str]:
        """Get list of currently failing gates.

        Returns:
            List of gate names (e.g., ["G1", "G4"])
        """
        return self._gate_checker.get_failing_gates()

    async def run_scheduled_checkpoint(self) -> int:
        """Run checkpoint for scheduled execution (e.g., cron).

        This method is designed to be called from cron jobs and returns
        an exit code suitable for shell scripts.

        Returns:
            0 if all gates pass, 1 if any gate fails
        """
        try:
            report = await self.run_checkpoint(
                metadata={"trigger": "scheduled", "source": "cron"},
            )

            if report.success:
                logger.info("Scheduled checkpoint passed all gates")
                return 0
            else:
                logger.warning(
                    f"Scheduled checkpoint failed {report.summary.fail_count} gates"
                )
                return 1

        except Exception as e:
            logger.error(f"Scheduled checkpoint failed with exception: {e}")
            return 1


# Convenience function for simple usage
async def run_checkpoint(
    checkpoint_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    notify: bool = True,
) -> CheckpointReport:
    """Run a checkpoint with default configuration.

    This is a convenience function for simple use cases.

    Args:
        checkpoint_id: Optional checkpoint ID
        metadata: Optional metadata
        notify: Whether to notify Discord

    Returns:
        CheckpointReport with results
    """
    manager = CheckpointManager()
    return await manager.run_checkpoint(
        checkpoint_id=checkpoint_id,
        metadata=metadata,
        notify=notify,
    )


# Synchronous version for scripts
def run_checkpoint_sync(
    checkpoint_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    notify: bool = True,
) -> CheckpointReport:
    """Run a checkpoint synchronously.

    This is useful for scripts that can't use async/await.

    Args:
        checkpoint_id: Optional checkpoint ID
        metadata: Optional metadata
        notify: Whether to notify Discord

    Returns:
        CheckpointReport with results
    """
    return asyncio.run(run_checkpoint(checkpoint_id, metadata, notify))
