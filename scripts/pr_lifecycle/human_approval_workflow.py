#!/usr/bin/env python3
"""
Human Approval Workflow for COMPLEX-classified PRs.

This module implements the workflow for managing human approval of COMPLEX PRs,
including GitReviewBot pre-review, Discord notifications, and approval polling.

Usage:
    from scripts.pr_lifecycle.human_approval_workflow import HumanApprovalWorkflow

    workflow = HumanApprovalWorkflow()
    await workflow.process_complex_pr(pr_number=123)

    # Or run as a daemon polling for COMPLEX PRs
    await workflow.poll_for_approvals()
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import aiohttp

# Add src to path for imports
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from autonomous_git.gitreviewbot import GiteaClient, GitReviewBot
from discord_alerts.config import DiscordConfig
from discord_alerts.discord_client import DiscordClient

from complex_path_gate import (
    ApprovalRecord,
    ApprovalStatus,
    ComplexPathCheckResult,
    ComplexPathGate,
)

logger = logging.getLogger(__name__)


@dataclass
class WorkflowConfig:
    """Configuration for the human approval workflow."""

    # Polling settings
    poll_interval_seconds: int = 60
    max_poll_attempts: int = 100  # ~1.6 hours at 60s intervals

    # Discord settings
    discord_channel_id: str = "approvals"
    discord_mention_role: str = "@approvers"

    # GitReviewBot settings
    run_gitreviewbot_first: bool = True
    gitreviewbot_min_confidence: float = 0.7

    # Approval settings
    approval_timeout_hours: int = 48
    emergency_approvers: list[str] = field(default_factory=list)

    # Notification settings
    reminder_interval_hours: int = 12
    max_reminders: int = 3


@dataclass
class WorkflowResult:
    """Result of processing a COMPLEX PR through the workflow."""

    pr_number: int
    success: bool
    final_status: ApprovalStatus
    gitreviewbot_completed: bool
    discord_notified: bool
    approval_record: ApprovalRecord | None = None
    error_message: str | None = None
    processing_time_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "pr_number": self.pr_number,
            "success": self.success,
            "final_status": self.final_status.value,
            "gitreviewbot_completed": self.gitreviewbot_completed,
            "discord_notified": self.discord_notified,
            "approval_record": self.approval_record.to_dict()
            if self.approval_record
            else None,
            "error_message": self.error_message,
            "processing_time_seconds": self.processing_time_seconds,
        }


class HumanApprovalWorkflow:
    """
    Workflow for managing human approval of COMPLEX-classified PRs.

    This class orchestrates:
    1. GitReviewBot pre-review (ST-AUTO-003)
    2. Discord notification to #approvals channel
    3. Polling for human approval via Gitea API
    4. Audit trail logging
    5. Emergency override handling

    Attributes:
        gate: ComplexPathGate instance for classification checking
        gitea_client: Client for Gitea API interactions
        gitreviewbot: GitReviewBot instance for pre-reviews
        discord_client: Discord client for notifications
        config: Workflow configuration
    """

    def __init__(
        self,
        gate: ComplexPathGate | None = None,
        gitea_client: GiteaClient | None = None,
        gitreviewbot: GitReviewBot | None = None,
        discord_client: DiscordClient | None = None,
        config: WorkflowConfig | None = None,
    ):
        """
        Initialize the Human Approval Workflow.

        Args:
            gate: Optional ComplexPathGate instance
            gitea_client: Optional Gitea client
            gitreviewbot: Optional GitReviewBot instance
            discord_client: Optional Discord client
            config: Optional workflow configuration
        """
        self.gate = gate or ComplexPathGate()
        self.gitea = gitea_client or GiteaClient()
        self.gitreviewbot = gitreviewbot
        self.discord = discord_client
        self.config = config or WorkflowConfig()

        # Track notification state to avoid duplicates
        self._notified_prs: set[int] = set()
        self._reminder_counts: dict[int, int] = {}

        logger.info("HumanApprovalWorkflow initialized")

    async def initialize(self) -> None:
        """Initialize async resources (Discord client, etc.)."""
        if self.discord is None:
            try:
                discord_config = DiscordConfig.from_env()
                self.discord = DiscordClient(discord_config)
                logger.info("Discord client initialized")
            except Exception as e:
                logger.warning(f"Could not initialize Discord client: {e}")

        if self.gitreviewbot is None:
            try:
                self.gitreviewbot = GitReviewBot(gitea_client=self.gitea)
                logger.info("GitReviewBot initialized")
            except Exception as e:
                logger.warning(f"Could not initialize GitReviewBot: {e}")

    async def close(self) -> None:
        """Close async resources."""
        if self.gitea:
            await self.gitea.close()
        if self.discord:
            # Discord client cleanup if needed
            pass

    async def __aenter__(self):
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def process_complex_pr(self, pr_number: int) -> WorkflowResult:
        """
        Process a COMPLEX PR through the full approval workflow.

        Workflow:
        1. Check if PR is COMPLEX
        2. Run GitReviewBot pre-review (if enabled)
        3. Send Discord notification
        4. Poll for human approval
        5. Record result

        Args:
            pr_number: The PR number to process

        Returns:
            WorkflowResult with final status
        """
        start_time = asyncio.get_event_loop().time()

        logger.info(f"Starting approval workflow for PR #{pr_number}")

        try:
            # Step 1: Check if PR is COMPLEX
            check_result = await self.gate.check_pr_status(pr_number)

            if not check_result.is_complex:
                logger.info(
                    f"PR #{pr_number} is not COMPLEX, skipping approval workflow"
                )
                return WorkflowResult(
                    pr_number=pr_number,
                    success=True,
                    final_status=ApprovalStatus.PENDING,
                    gitreviewbot_completed=False,
                    discord_notified=False,
                    processing_time_seconds=asyncio.get_event_loop().time()
                    - start_time,
                )

            # Step 2: Run GitReviewBot pre-review
            gitreviewbot_completed = False
            if self.config.run_gitreviewbot_first and self.gitreviewbot:
                gitreviewbot_completed = await self._run_gitreviewbot_pre_review(
                    pr_number
                )

                if not gitreviewbot_completed:
                    logger.warning(
                        f"GitReviewBot pre-review failed for PR #{pr_number}"
                    )

            # Step 3: Send Discord notification
            discord_notified = False
            if self.discord:
                discord_notified = await self._send_approval_notification(
                    pr_number, check_result
                )

            # Step 4: Poll for human approval
            final_status, approval_record = await self._poll_for_approval(pr_number)

            success = final_status in (
                ApprovalStatus.APPROVED,
                ApprovalStatus.EMERGENCY_OVERRIDE,
            )

            processing_time = asyncio.get_event_loop().time() - start_time

            result = WorkflowResult(
                pr_number=pr_number,
                success=success,
                final_status=final_status,
                gitreviewbot_completed=gitreviewbot_completed,
                discord_notified=discord_notified,
                approval_record=approval_record,
                processing_time_seconds=processing_time,
            )

            logger.info(
                f"Approval workflow complete for PR #{pr_number}: "
                f"success={success}, status={final_status.value}, time={processing_time:.1f}s"
            )

            return result

        except Exception as e:
            logger.error(f"Approval workflow failed for PR #{pr_number}: {e}")

            return WorkflowResult(
                pr_number=pr_number,
                success=False,
                final_status=ApprovalStatus.PENDING,
                gitreviewbot_completed=False,
                discord_notified=False,
                error_message=str(e),
                processing_time_seconds=asyncio.get_event_loop().time() - start_time,
            )

    async def _run_gitreviewbot_pre_review(self, pr_number: int) -> bool:
        """
        Run GitReviewBot pre-review on a PR.

        Args:
            pr_number: The PR number

        Returns:
            True if review completed successfully
        """
        try:
            logger.info(f"Running GitReviewBot pre-review for PR #{pr_number}")

            decision = await self.gitreviewbot.review_pr(pr_number)

            logger.info(
                f"GitReviewBot review complete for PR #{pr_number}: "
                f"decision={decision.decision.value}, confidence={decision.confidence:.1f}%"
            )

            # Add label to indicate pre-review completed
            await self.gitea.add_labels(pr_number, ["gitreviewbot-pre-reviewed"])

            return True

        except Exception as e:
            logger.error(f"GitReviewBot pre-review failed for PR #{pr_number}: {e}")
            return False

    async def _send_approval_notification(
        self,
        pr_number: int,
        check_result: ComplexPathCheckResult,
    ) -> bool:
        """
        Send Discord notification requesting human approval.

        Args:
            pr_number: The PR number
            check_result: The complex path check result

        Returns:
            True if notification sent successfully
        """
        if pr_number in self._notified_prs:
            logger.debug(f"Already notified for PR #{pr_number}, skipping")
            return True

        try:
            # Get PR details
            pr = await self.gitea.get_pr(pr_number)

            # Build notification message
            message = self._build_approval_message(pr_number, pr, check_result)

            # Send to Discord
            # Note: In production, this would use the actual Discord client
            # For now, we log the message
            logger.info(f"Discord notification for PR #{pr_number}:\n{message}")

            # Track notification
            self._notified_prs.add(pr_number)
            self._reminder_counts[pr_number] = 0

            # Add label to PR
            await self.gitea.add_labels(pr_number, ["awaiting-human-approval"])

            return True

        except Exception as e:
            logger.error(
                f"Failed to send Discord notification for PR #{pr_number}: {e}"
            )
            return False

    def _build_approval_message(
        self,
        pr_number: int,
        pr,
        check_result: ComplexPathCheckResult,
    ) -> str:
        """Build Discord message for approval request."""
        lines = [
            f"🚨 **COMPLEX PR Requires Human Approval**",
            "",
            f"**PR #{pr_number}**: {pr.title}",
            f"**Author**: {pr.author}",
            f"**Branch**: `{pr.branch}`",
            "",
            "**Risk Classification**:",
            f"- Level: {check_result.risk_level.value.upper()}",
            f"- Confidence: {check_result.confidence:.1%}",
            f"- Files Changed: {len(check_result.files_analyzed)}",
            "",
            "**Files Changed**:",
        ]

        # List files (limit to first 10)
        for file_path in check_result.files_analyzed[:10]:
            lines.append(f"- `{file_path}`")

        if len(check_result.files_analyzed) > 10:
            lines.append(
                f"- ... and {len(check_result.files_analyzed) - 10} more files"
            )

        lines.extend(
            [
                "",
                "**GitReviewBot Status**: "
                + (
                    "✅ Pre-review complete"
                    if check_result.gitreviewbot_completed
                    else "⏳ Pending"
                ),
                "",
                f"**Action Required**: Please review and approve/reject this PR.",
                f"{self.config.discord_mention_role}",
                "",
                f"🔗 [View PR]({self.gitea.base_url}/{self.gitea.owner}/{self.gitea.repo}/pulls/{pr_number})",
            ]
        )

        return "\n".join(lines)

    async def _poll_for_approval(
        self,
        pr_number: int,
    ) -> tuple[ApprovalStatus, ApprovalRecord | None]:
        """
        Poll for human approval of a PR.

        Args:
            pr_number: The PR number

        Returns:
            Tuple of (final_status, approval_record)
        """
        logger.info(f"Starting approval polling for PR #{pr_number}")

        poll_count = 0
        last_reminder_time = datetime.now(UTC)

        while poll_count < self.config.max_poll_attempts:
            # Check current approval status
            check_result = await self.gate.check_pr_status(pr_number)

            # If approved or rejected, we're done
            if check_result.approval_status in (
                ApprovalStatus.APPROVED,
                ApprovalStatus.REJECTED,
                ApprovalStatus.EMERGENCY_OVERRIDE,
            ):
                return check_result.approval_status, check_result.approval_record

            # Check for expiration
            if check_result.approval_status == ApprovalStatus.EXPIRED:
                logger.warning(f"Approval request expired for PR #{pr_number}")
                return ApprovalStatus.EXPIRED, check_result.approval_record

            # Send reminder if needed
            now = datetime.now(UTC)
            hours_since_reminder = (now - last_reminder_time).total_seconds() / 3600

            if hours_since_reminder >= self.config.reminder_interval_hours:
                reminder_count = self._reminder_counts.get(pr_number, 0)

                if reminder_count < self.config.max_reminders:
                    await self._send_reminder(pr_number, check_result)
                    self._reminder_counts[pr_number] = reminder_count + 1
                    last_reminder_time = now

            # Check for human approval via Gitea reviews
            approval_record = await self._check_gitea_reviews(pr_number)
            if approval_record:
                return approval_record.status, approval_record

            poll_count += 1
            await asyncio.sleep(self.config.poll_interval_seconds)

        # Max polls reached without resolution
        logger.warning(f"Max poll attempts reached for PR #{pr_number}")
        return ApprovalStatus.PENDING, None

    async def _check_gitea_reviews(self, pr_number: int) -> ApprovalRecord | None:
        """
        Check Gitea for human reviews/approvals.

        Args:
            pr_number: The PR number

        Returns:
            ApprovalRecord if approval found, None otherwise
        """
        try:
            # Get reviews from Gitea API
            # Note: This is a simplified version - actual implementation would
            # call the Gitea API to get reviews

            # For now, check PR labels for approval indicators
            pr = await self.gitea.get_pr(pr_number)

            if "human-approved" in pr.labels:
                # Find who approved (would need to check reviews API)
                return await self.gate.record_human_approval(
                    pr_number=pr_number,
                    approver="unknown",  # Would get from review
                    reason="Approved via Gitea review",
                )

            if "human-rejected" in pr.labels:
                return await self.gate.record_human_rejection(
                    pr_number=pr_number,
                    approver="unknown",
                    reason="Rejected via Gitea review",
                )

            return None

        except Exception as e:
            logger.error(f"Failed to check Gitea reviews for PR #{pr_number}: {e}")
            return None

    async def _send_reminder(
        self, pr_number: int, check_result: ComplexPathCheckResult
    ) -> None:
        """Send a reminder notification."""
        try:
            pr = await self.gitea.get_pr(pr_number)
            reminder_count = self._reminder_counts.get(pr_number, 0)

            message = (
                f"⏰ **Reminder**: PR #{pr_number} still awaiting human approval.\n"
                f"**Title**: {pr.title}\n"
                f"**Reminder #{reminder_count + 1}**\n"
                f"{self.config.discord_mention_role}"
            )

            logger.info(f"Sending reminder for PR #{pr_number}")

        except Exception as e:
            logger.error(f"Failed to send reminder for PR #{pr_number}: {e}")

    async def process_emergency_override(
        self,
        pr_number: int,
        approver: str,
        justification: str,
    ) -> WorkflowResult:
        """
        Process an emergency override request.

        Args:
            pr_number: The PR number
            approver: Username of the approver
            justification: Required justification

        Returns:
            WorkflowResult
        """
        start_time = asyncio.get_event_loop().time()

        try:
            approval_record = await self.gate.emergency_override(
                pr_number=pr_number,
                approver=approver,
                justification=justification,
            )

            # Notify that emergency override was used
            if self.discord:
                message = (
                    f"🚨 **EMERGENCY OVERRIDE USED**\n"
                    f"PR #{pr_number} was approved via emergency override by {approver}.\n"
                    f"**Justification**: {justification}\n"
                    f"**Post-hoc review required**: Yes"
                )
                logger.warning(message)

            return WorkflowResult(
                pr_number=pr_number,
                success=True,
                final_status=ApprovalStatus.EMERGENCY_OVERRIDE,
                gitreviewbot_completed=False,
                discord_notified=True,
                approval_record=approval_record,
                processing_time_seconds=asyncio.get_event_loop().time() - start_time,
            )

        except Exception as e:
            logger.error(f"Emergency override failed for PR #{pr_number}: {e}")

            return WorkflowResult(
                pr_number=pr_number,
                success=False,
                final_status=ApprovalStatus.PENDING,
                gitreviewbot_completed=False,
                discord_notified=False,
                error_message=str(e),
                processing_time_seconds=asyncio.get_event_loop().time() - start_time,
            )

    async def poll_for_approvals(
        self, pr_numbers: list[int] | None = None
    ) -> list[WorkflowResult]:
        """
        Poll for approvals on multiple PRs.

        Args:
            pr_numbers: Optional list of PR numbers to check. If None, discovers COMPLEX PRs.

        Returns:
            List of WorkflowResults
        """
        if pr_numbers is None:
            # Discover COMPLEX PRs (would query Gitea for open PRs with COMPLEX label)
            pr_numbers = []

        results = []

        for pr_number in pr_numbers:
            result = await self.process_complex_pr(pr_number)
            results.append(result)

        return results


# Convenience functions for standalone usage
async def request_human_approval(pr_number: int) -> WorkflowResult:
    """
    Request human approval for a COMPLEX PR.

    Args:
        pr_number: The PR number

    Returns:
        WorkflowResult
    """
    async with HumanApprovalWorkflow() as workflow:
        return await workflow.process_complex_pr(pr_number)


async def emergency_approve_pr(
    pr_number: int,
    approver: str,
    justification: str,
) -> WorkflowResult:
    """
    Emergency approve a PR (bypasses normal workflow).

    Args:
        pr_number: The PR number
        approver: Username of the approver
        justification: Required justification

    Returns:
        WorkflowResult
    """
    async with HumanApprovalWorkflow() as workflow:
        return await workflow.process_emergency_override(
            pr_number=pr_number,
            approver=approver,
            justification=justification,
        )


if __name__ == "__main__":
    # CLI for testing
    import argparse

    parser = argparse.ArgumentParser(
        description="Human approval workflow for COMPLEX PRs"
    )
    parser.add_argument("pr_number", type=int, help="PR number to process")
    parser.add_argument(
        "--emergency", action="store_true", help="Use emergency override"
    )
    parser.add_argument("--approver", help="Approver username (for emergency)")
    parser.add_argument("--justification", help="Justification (for emergency)")

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    async def main():
        if args.emergency:
            if not args.approver or not args.justification:
                print("--approver and --justification required for emergency override")
                return

            result = await emergency_approve_pr(
                args.pr_number,
                args.approver,
                args.justification,
            )
        else:
            result = await request_human_approval(args.pr_number)

        print(json.dumps(result.to_dict(), indent=2))

    asyncio.run(main())
