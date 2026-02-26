#!/usr/bin/env python3
"""
Human Gate for COMPLEX-classified PRs.

This module implements the human approval gate for COMPLEX PRs as part of the
AI Swarm Autonomous PR Pipeline (ST-AUTO-004). It integrates with:
- Path Analyzer (ST-AUTO-001): For PR classification
- GitReviewBot (ST-AUTO-003): For pre-review summaries
- Discord: For notifications to #pr-reviews channel
- Redis: For approval state storage

Usage:
    from scripts.pr_lifecycle.human_gate import HumanGate

    gate = HumanGate()
    result = await gate.process_pr(pr_number=123)

    if result.requires_human_approval:
        await gate.request_approval(pr_number=123)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os

# Add src to path for imports
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from autonomous_git.path_analyzer import RiskLevel, analyze_paths

logger = logging.getLogger(__name__)


class ApprovalStatus(Enum):
    """Human approval status for COMPLEX PRs."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CHANGES_REQUESTED = "changes_requested"
    EMERGENCY_OVERRIDE = "emergency_override"
    EXPIRED = "expired"


@dataclass
class ApprovalRecord:
    """Record of an approval action."""

    pr_number: int
    status: ApprovalStatus
    approver: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    reason: str | None = None
    emergency_justification: str | None = None
    post_hoc_review_required: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "pr_number": self.pr_number,
            "status": self.status.value,
            "approver": self.approver,
            "timestamp": self.timestamp.isoformat(),
            "reason": self.reason,
            "emergency_justification": self.emergency_justification,
            "post_hoc_review_required": self.post_hoc_review_required,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ApprovalRecord:
        """Create from dictionary."""
        return cls(
            pr_number=data["pr_number"],
            status=ApprovalStatus(data["status"]),
            approver=data.get("approver"),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            reason=data.get("reason"),
            emergency_justification=data.get("emergency_justification"),
            post_hoc_review_required=data.get("post_hoc_review_required", False),
        )


@dataclass
class HumanGateResult:
    """Result of processing a PR through the human gate."""

    pr_number: int
    is_complex: bool
    risk_level: RiskLevel
    confidence: float
    files_analyzed: list[str]
    approval_status: ApprovalStatus
    approval_record: ApprovalRecord | None = None
    requires_human_approval: bool = False
    can_merge: bool = False
    reasoning: str = ""
    discord_notified: bool = False
    reminder_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "pr_number": self.pr_number,
            "is_complex": self.is_complex,
            "risk_level": self.risk_level.value
            if hasattr(self.risk_level, "value")
            else str(self.risk_level),
            "confidence": self.confidence,
            "files_analyzed": self.files_analyzed,
            "approval_status": self.approval_status.value,
            "approval_record": self.approval_record.to_dict()
            if self.approval_record
            else None,
            "requires_human_approval": self.requires_human_approval,
            "can_merge": self.can_merge,
            "reasoning": self.reasoning,
            "discord_notified": self.discord_notified,
            "reminder_count": self.reminder_count,
        }


class HumanGate:
    """
    Human approval gate for COMPLEX-classified PRs.

    This class manages the workflow for COMPLEX PRs requiring human approval:
    1. Classifies PRs using Path Analyzer
    2. Stores approval state in Redis
    3. Sends Discord notifications to #pr-reviews
    4. Manages reminder scheduling (every 4 hours)
    5. Handles emergency overrides with audit logging

    Attributes:
        redis_client: Redis client for state storage
        discord_webhook_url: Discord webhook URL for notifications
        emergency_approvers: List of users authorized for emergency override
        approval_timeout_hours: Hours before approval expires
        reminder_interval_hours: Hours between reminders
    """

    # Redis key patterns
    REDIS_STATUS_KEY = "bmad:chiseai:pr:human_gate:{pr_number}:status"
    REDIS_REVIEWER_KEY = "bmad:chiseai:pr:human_gate:{pr_number}:reviewer"
    REDIS_TIMESTAMP_KEY = "bmad:chiseai:pr:human_gate:{pr_number}:timestamp"
    REDIS_EMERGENCY_KEY = "bmad:chiseai:pr:human_gate:{pr_number}:emergency_override"
    REDIS_REMINDER_KEY = "bmad:chiseai:pr:human_gate:{pr_number}:reminder_count"
    REDIS_HISTORY_KEY = "bmad:chiseai:pr:human_gate:{pr_number}:history"

    def __init__(
        self,
        redis_client=None,
        discord_webhook_url: str | None = None,
        emergency_approvers: list[str] | None = None,
        approval_timeout_hours: int = 48,
        reminder_interval_hours: int = 4,
        dry_run: bool = False,
    ):
        """
        Initialize the Human Gate.

        Args:
            redis_client: Optional Redis client instance
            discord_webhook_url: Discord webhook URL for notifications
            emergency_approvers: List of authorized emergency approver usernames
            approval_timeout_hours: Hours before approval expires (default: 48)
            reminder_interval_hours: Hours between reminders (default: 4)
            dry_run: If True, don't actually send Discord notifications
        """
        self.redis = redis_client
        self.discord_webhook_url = discord_webhook_url or os.getenv(
            "DISCORD_PR_REVIEWS_WEBHOOK"
        )
        self.emergency_approvers = set(emergency_approvers or [])
        self.approval_timeout_hours = approval_timeout_hours
        self.reminder_interval_hours = reminder_interval_hours
        self.dry_run = dry_run

        # In-memory cache for approval states
        self._approval_cache: dict[int, ApprovalRecord] = {}

        logger.info(f"HumanGate initialized (dry_run={dry_run})")

    def _get_redis_key(self, pattern: str, pr_number: int) -> str:
        """Generate Redis key for a PR."""
        return pattern.format(pr_number=pr_number)

    def _is_complex_classification(
        self, files: list[str]
    ) -> tuple[bool, RiskLevel, float]:
        """
        Check if files are classified as COMPLEX using Path Analyzer.

        Args:
            files: List of file paths to analyze

        Returns:
            Tuple of (is_complex, risk_level, confidence)
        """
        try:
            result = analyze_paths(files=files, use_cache=True)
            is_complex = result.risk_level == RiskLevel.COMPLEX

            logger.info(
                f"Path analysis for {len(files)} files: "
                f"risk={result.risk_level.value}, confidence={result.confidence:.2%}"
            )

            return is_complex, result.risk_level, result.confidence

        except Exception as e:
            logger.error(f"Path analysis failed: {e}")
            # Conservative default: treat as COMPLEX if analysis fails
            return True, RiskLevel.COMPLEX, 0.5

    async def check_pr_status(
        self, pr_number: int, files: list[str] | None = None
    ) -> HumanGateResult:
        """
        Check the complete status of a PR against the human gate.

        Args:
            pr_number: The PR number to check
            files: Optional list of file paths (will fetch from Gitea if not provided)

        Returns:
            HumanGateResult with full status
        """
        logger.info(f"Checking PR #{pr_number} against human gate")

        try:
            # Get files if not provided
            if files is None:
                files = await self._get_pr_files(pr_number)

            # Analyze file paths
            is_complex, risk_level, confidence = self._is_complex_classification(files)

            # Check approval status from Redis
            approval_status, approval_record = await self._get_approval_status(
                pr_number
            )

            # Get reminder count
            reminder_count = await self._get_reminder_count(pr_number)

            # Determine requirements
            requires_human_approval = is_complex
            can_merge = self._can_merge(is_complex, approval_status)

            # Build reasoning
            reasoning = self._build_reasoning(
                is_complex=is_complex,
                risk_level=risk_level,
                approval_status=approval_status,
            )

            result = HumanGateResult(
                pr_number=pr_number,
                is_complex=is_complex,
                risk_level=risk_level,
                confidence=confidence,
                files_analyzed=files,
                approval_status=approval_status,
                approval_record=approval_record,
                requires_human_approval=requires_human_approval,
                can_merge=can_merge,
                reasoning=reasoning,
                reminder_count=reminder_count,
            )

            logger.info(
                f"PR #{pr_number} check complete: "
                f"complex={is_complex}, approved={approval_status.value}, can_merge={can_merge}"
            )

            return result

        except Exception as e:
            logger.error(f"Failed to check PR #{pr_number}: {e}")
            raise

    async def _get_pr_files(self, pr_number: int) -> list[str]:
        """Fetch files changed in a PR from Gitea."""
        # This is a placeholder - actual implementation would call Gitea API
        # For now, return empty list and let caller handle
        logger.warning(
            f"Fetching files for PR #{pr_number} not implemented, returning empty list"
        )
        return []

    async def _get_approval_status(
        self, pr_number: int
    ) -> tuple[ApprovalStatus, ApprovalRecord | None]:
        """
        Check approval status from Redis.

        Args:
            pr_number: The PR number

        Returns:
            Tuple of (status, record)
        """
        try:
            if self.redis is None:
                # Check cache
                if pr_number in self._approval_cache:
                    record = self._approval_cache[pr_number]
                    if self._is_approval_expired(record):
                        return ApprovalStatus.EXPIRED, record
                    return record.status, record
                return ApprovalStatus.PENDING, None

            # Check Redis
            status_key = self._get_redis_key(self.REDIS_STATUS_KEY, pr_number)
            status_value = self.redis.get(status_key)

            if status_value is None:
                return ApprovalStatus.PENDING, None

            # Build record from Redis data
            reviewer_key = self._get_redis_key(self.REDIS_REVIEWER_KEY, pr_number)
            timestamp_key = self._get_redis_key(self.REDIS_TIMESTAMP_KEY, pr_number)
            emergency_key = self._get_redis_key(self.REDIS_EMERGENCY_KEY, pr_number)

            record = ApprovalRecord(
                pr_number=pr_number,
                status=ApprovalStatus(
                    status_value.decode()
                    if isinstance(status_value, bytes)
                    else status_value
                ),
                approver=self.redis.get(reviewer_key),
                timestamp=datetime.fromisoformat(
                    self.redis.get(timestamp_key).decode()
                    if isinstance(self.redis.get(timestamp_key), bytes)
                    else self.redis.get(timestamp_key)
                )
                if self.redis.get(timestamp_key)
                else datetime.now(UTC),
                emergency_justification=self.redis.get(emergency_key),
                post_hoc_review_required=self.redis.get(emergency_key) is not None,
            )

            # Update cache
            self._approval_cache[pr_number] = record

            # Check expiration
            if self._is_approval_expired(record):
                return ApprovalStatus.EXPIRED, record

            return record.status, record

        except Exception as e:
            logger.error(f"Failed to get approval status from Redis: {e}")
            return ApprovalStatus.PENDING, None

    async def _get_reminder_count(self, pr_number: int) -> int:
        """Get the number of reminders sent for a PR."""
        try:
            if self.redis is None:
                return 0

            reminder_key = self._get_redis_key(self.REDIS_REMINDER_KEY, pr_number)
            count = self.redis.get(reminder_key)

            if count is None:
                return 0

            return int(count.decode() if isinstance(count, bytes) else count)

        except Exception as e:
            logger.error(f"Failed to get reminder count: {e}")
            return 0

    def _is_approval_expired(self, record: ApprovalRecord) -> bool:
        """Check if an approval has expired."""
        if record.status not in (
            ApprovalStatus.APPROVED,
            ApprovalStatus.EMERGENCY_OVERRIDE,
        ):
            return False

        age_hours = (datetime.now(UTC) - record.timestamp).total_seconds() / 3600
        return age_hours > self.approval_timeout_hours

    def _can_merge(self, is_complex: bool, approval_status: ApprovalStatus) -> bool:
        """
        Determine if a PR can be merged.

        Rules:
        - Non-COMPLEX PRs: Can merge
        - COMPLEX PRs: Need human approval (APPROVED or EMERGENCY_OVERRIDE)
        """
        if not is_complex:
            return True

        return approval_status in (
            ApprovalStatus.APPROVED,
            ApprovalStatus.EMERGENCY_OVERRIDE,
        )

    def _build_reasoning(
        self,
        is_complex: bool,
        risk_level: RiskLevel,
        approval_status: ApprovalStatus,
    ) -> str:
        """Build human-readable reasoning for the result."""
        parts = [
            f"Risk level: {risk_level.value if hasattr(risk_level, 'value') else str(risk_level)}"
        ]

        if is_complex:
            parts.append("COMPLEX classification requires human approval")
            parts.append(f"Human approval status: {approval_status.value}")

            if approval_status == ApprovalStatus.EXPIRED:
                parts.append(
                    f"Approval expired (timeout: {self.approval_timeout_hours}h)"
                )
        else:
            parts.append("Not classified as COMPLEX - no human approval required")

        return "; ".join(parts)

    async def request_approval(
        self,
        pr_number: int,
        pr_title: str,
        pr_author: str,
        pr_url: str,
        files: list[str],
        gitreviewbot_summary: str | None = None,
    ) -> bool:
        """
        Request human approval for a COMPLEX PR.

        Args:
            pr_number: The PR number
            pr_title: PR title
            pr_author: PR author username
            pr_url: URL to the PR
            files: List of files changed
            gitreviewbot_summary: Optional GitReviewBot summary

        Returns:
            True if notification sent successfully
        """
        logger.info(f"Requesting human approval for PR #{pr_number}")

        try:
            # Store pending status in Redis
            await self._store_approval_state(
                pr_number=pr_number,
                status=ApprovalStatus.PENDING,
            )

            # Send Discord notification
            notified = await self._send_discord_notification(
                pr_number=pr_number,
                pr_title=pr_title,
                pr_author=pr_author,
                pr_url=pr_url,
                files=files,
                gitreviewbot_summary=gitreviewbot_summary,
                is_reminder=False,
            )

            return notified

        except Exception as e:
            logger.error(f"Failed to request approval for PR #{pr_number}: {e}")
            return False

    async def _store_approval_state(
        self,
        pr_number: int,
        status: ApprovalStatus,
        approver: str | None = None,
        reason: str | None = None,
        emergency_justification: str | None = None,
    ) -> None:
        """Store approval state in Redis."""
        try:
            if self.redis is None:
                # Store in cache only
                record = ApprovalRecord(
                    pr_number=pr_number,
                    status=status,
                    approver=approver,
                    reason=reason,
                    emergency_justification=emergency_justification,
                    post_hoc_review_required=emergency_justification is not None,
                )
                self._approval_cache[pr_number] = record
                return

            # Store in Redis
            status_key = self._get_redis_key(self.REDIS_STATUS_KEY, pr_number)
            reviewer_key = self._get_redis_key(self.REDIS_REVIEWER_KEY, pr_number)
            timestamp_key = self._get_redis_key(self.REDIS_TIMESTAMP_KEY, pr_number)

            self.redis.set(status_key, status.value)
            self.redis.set(timestamp_key, datetime.now(UTC).isoformat())

            if approver:
                self.redis.set(reviewer_key, approver)

            if emergency_justification:
                emergency_key = self._get_redis_key(self.REDIS_EMERGENCY_KEY, pr_number)
                self.redis.set(emergency_key, emergency_justification)

            # Add to history
            history_key = self._get_redis_key(self.REDIS_HISTORY_KEY, pr_number)
            history_entry = {
                "status": status.value,
                "approver": approver,
                "timestamp": datetime.now(UTC).isoformat(),
                "reason": reason,
            }
            self.redis.rpush(history_key, json.dumps(history_entry))

            # Update cache
            record = ApprovalRecord(
                pr_number=pr_number,
                status=status,
                approver=approver,
                reason=reason,
                emergency_justification=emergency_justification,
                post_hoc_review_required=emergency_justification is not None,
            )
            self._approval_cache[pr_number] = record

        except Exception as e:
            logger.error(f"Failed to store approval state: {e}")
            raise

    async def _send_discord_notification(
        self,
        pr_number: int,
        pr_title: str,
        pr_author: str,
        pr_url: str,
        files: list[str],
        gitreviewbot_summary: str | None = None,
        is_reminder: bool = False,
        reminder_count: int = 0,
    ) -> bool:
        """
        Send Discord notification for approval request.

        Args:
            pr_number: The PR number
            pr_title: PR title
            pr_author: PR author
            pr_url: URL to the PR
            files: List of files changed
            gitreviewbot_summary: Optional GitReviewBot summary
            is_reminder: Whether this is a reminder notification
            reminder_count: Number of reminders sent so far

        Returns:
            True if notification sent successfully
        """
        if self.dry_run:
            logger.info(
                f"[DRY RUN] Would send Discord notification for PR #{pr_number}"
            )
            return True

        if not self.discord_webhook_url:
            logger.warning("No Discord webhook URL configured")
            return False

        try:
            import aiohttp

            # Build message
            if is_reminder:
                title = f"⏰ Reminder: PR #{pr_number} Awaiting Human Approval"
                color = 0xFFA500  # Orange
            else:
                title = "🚨 COMPLEX PR Requires Human Approval"
                color = 0xFF0000  # Red

            # Build file list (limit to first 10)
            file_list = "\n".join(f"- `{f}`" for f in files[:10])
            if len(files) > 10:
                file_list += f"\n- ... and {len(files) - 10} more files"

            # Build description
            description = (
                f"**PR #{pr_number}**: {pr_title}\n"
                f"**Author**: {pr_author}\n"
                f"**Files Changed**: {len(files)}\n\n"
                f"**Files**:\n{file_list}"
            )

            if gitreviewbot_summary:
                description += (
                    f"\n\n**GitReviewBot Summary**:\n{gitreviewbot_summary[:500]}..."
                )

            if is_reminder:
                description += (
                    f"\n\n**Reminder #{reminder_count}** - Please review soon!"
                )

            embed = {
                "title": title,
                "description": description,
                "color": color,
                "url": pr_url,
                "timestamp": datetime.now(UTC).isoformat(),
                "footer": {"text": "ChiseAI Human Gate"},
            }

            payload = {
                "content": "@here Human approval required for COMPLEX PR",
                "embeds": [embed],
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.discord_webhook_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                ) as response:
                    if response.status == 204:
                        logger.info(f"Discord notification sent for PR #{pr_number}")
                        return True
                    else:
                        logger.error(f"Discord notification failed: {response.status}")
                        return False

        except ImportError:
            logger.error("aiohttp not installed, cannot send Discord notification")
            return False
        except Exception as e:
            logger.error(f"Failed to send Discord notification: {e}")
            return False

    async def record_approval(
        self,
        pr_number: int,
        approver: str,
        reason: str | None = None,
    ) -> ApprovalRecord:
        """
        Record a human approval for a PR.

        Args:
            pr_number: The PR number
            approver: Username of the approving human
            reason: Optional approval reason

        Returns:
            The created ApprovalRecord
        """
        record = ApprovalRecord(
            pr_number=pr_number,
            status=ApprovalStatus.APPROVED,
            approver=approver,
            reason=reason,
        )

        await self._store_approval_state(
            pr_number=pr_number,
            status=ApprovalStatus.APPROVED,
            approver=approver,
            reason=reason,
        )

        # Send confirmation notification
        await self._send_approval_confirmation(pr_number, approver, approved=True)

        logger.info(f"Recorded human approval for PR #{pr_number} by {approver}")

        return record

    async def record_rejection(
        self,
        pr_number: int,
        reviewer: str,
        reason: str,
    ) -> ApprovalRecord:
        """
        Record a human rejection for a PR.

        Args:
            pr_number: The PR number
            reviewer: Username of the rejecting human
            reason: Rejection reason (required)

        Returns:
            The created ApprovalRecord
        """
        record = ApprovalRecord(
            pr_number=pr_number,
            status=ApprovalStatus.REJECTED,
            approver=reviewer,
            reason=reason,
        )

        await self._store_approval_state(
            pr_number=pr_number,
            status=ApprovalStatus.REJECTED,
            approver=reviewer,
            reason=reason,
        )

        # Send confirmation notification
        await self._send_approval_confirmation(
            pr_number, reviewer, approved=False, reason=reason
        )

        logger.info(f"Recorded human rejection for PR #{pr_number} by {reviewer}")

        return record

    async def record_changes_requested(
        self,
        pr_number: int,
        reviewer: str,
        comments: str,
    ) -> ApprovalRecord:
        """
        Record that changes have been requested for a PR.

        Args:
            pr_number: The PR number
            reviewer: Username of the requesting human
            comments: Comments explaining requested changes

        Returns:
            The created ApprovalRecord
        """
        record = ApprovalRecord(
            pr_number=pr_number,
            status=ApprovalStatus.CHANGES_REQUESTED,
            approver=reviewer,
            reason=comments,
        )

        await self._store_approval_state(
            pr_number=pr_number,
            status=ApprovalStatus.CHANGES_REQUESTED,
            approver=reviewer,
            reason=comments,
        )

        logger.info(f"Recorded changes requested for PR #{pr_number} by {reviewer}")

        return record

    async def emergency_override(
        self,
        pr_number: int,
        approver: str,
        justification: str,
    ) -> ApprovalRecord:
        """
        Apply emergency override for critical hotfixes.

        Args:
            pr_number: The PR number
            approver: Username of the approver (must be authorized)
            justification: Required justification for emergency override

        Returns:
            The created ApprovalRecord

        Raises:
            ValueError: If approver is not authorized for emergency override
        """
        if self.emergency_approvers and approver not in self.emergency_approvers:
            raise ValueError(
                f"User {approver} is not authorized for emergency override. "
                f"Authorized users: {', '.join(self.emergency_approvers)}"
            )

        record = ApprovalRecord(
            pr_number=pr_number,
            status=ApprovalStatus.EMERGENCY_OVERRIDE,
            approver=approver,
            reason="Emergency override for critical fix",
            emergency_justification=justification,
            post_hoc_review_required=True,
        )

        await self._store_approval_state(
            pr_number=pr_number,
            status=ApprovalStatus.EMERGENCY_OVERRIDE,
            approver=approver,
            reason="Emergency override for critical fix",
            emergency_justification=justification,
        )

        # Send emergency notification
        await self._send_emergency_notification(pr_number, approver, justification)

        logger.warning(
            f"EMERGENCY OVERRIDE applied for PR #{pr_number} by {approver}. "
            f"Post-hoc review required."
        )

        return record

    async def _send_approval_confirmation(
        self,
        pr_number: int,
        approver: str,
        approved: bool,
        reason: str | None = None,
    ) -> bool:
        """Send Discord confirmation of approval/rejection."""
        if self.dry_run or not self.discord_webhook_url:
            return True

        try:
            import aiohttp

            if approved:
                title = f"✅ PR #{pr_number} Approved"
                color = 0x00FF00  # Green
                description = f"PR #{pr_number} has been approved by {approver}"
            else:
                title = f"❌ PR #{pr_number} Rejected"
                color = 0xFF0000  # Red
                description = f"PR #{pr_number} has been rejected by {approver}"

            if reason:
                description += f"\n\n**Reason**: {reason}"

            embed = {
                "title": title,
                "description": description,
                "color": color,
                "timestamp": datetime.now(UTC).isoformat(),
            }

            payload = {
                "embeds": [embed],
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.discord_webhook_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                ) as response:
                    return response.status == 204

        except Exception as e:
            logger.error(f"Failed to send approval confirmation: {e}")
            return False

    async def _send_emergency_notification(
        self,
        pr_number: int,
        approver: str,
        justification: str,
    ) -> bool:
        """Send Discord notification for emergency override."""
        if self.dry_run or not self.discord_webhook_url:
            return True

        try:
            import aiohttp

            embed = {
                "title": "🚨 EMERGENCY OVERRIDE USED",
                "description": (
                    f"PR #{pr_number} was approved via emergency override by {approver}.\n\n"
                    f"**Justification**: {justification}\n\n"
                    f"**⚠️ Post-hoc review required**"
                ),
                "color": 0xFF0000,  # Red
                "timestamp": datetime.now(UTC).isoformat(),
            }

            payload = {
                "content": "@here Emergency override used - post-hoc review required",
                "embeds": [embed],
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.discord_webhook_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                ) as response:
                    return response.status == 204

        except Exception as e:
            logger.error(f"Failed to send emergency notification: {e}")
            return False

    async def send_reminder(self, pr_number: int) -> bool:
        """
        Send a reminder notification for a pending approval.

        Args:
            pr_number: The PR number

        Returns:
            True if reminder sent successfully
        """
        try:
            # Get current status
            status, record = await self._get_approval_status(pr_number)

            if status != ApprovalStatus.PENDING:
                logger.debug(f"PR #{pr_number} not pending, skipping reminder")
                return False

            # Increment reminder count
            current_count = await self._get_reminder_count(pr_number)
            new_count = current_count + 1

            if self.redis:
                reminder_key = self._get_redis_key(self.REDIS_REMINDER_KEY, pr_number)
                self.redis.set(reminder_key, str(new_count))

            # Send reminder notification
            # Note: In production, would fetch PR details from Gitea
            notified = await self._send_discord_notification(
                pr_number=pr_number,
                pr_title=f"PR #{pr_number}",
                pr_author="unknown",
                pr_url=f"https://gitea.example.com/pr/{pr_number}",
                files=[],
                is_reminder=True,
                reminder_count=new_count,
            )

            logger.info(f"Sent reminder #{new_count} for PR #{pr_number}")
            return notified

        except Exception as e:
            logger.error(f"Failed to send reminder for PR #{pr_number}: {e}")
            return False

    async def check_and_send_reminders(self) -> list[int]:
        """
        Check all pending PRs and send reminders if needed.

        Returns:
            List of PR numbers that received reminders
        """
        reminded_prs = []

        try:
            if self.redis is None:
                logger.warning("No Redis connection, cannot check for reminders")
                return reminded_prs

            # Scan for pending PRs
            # This is a simplified implementation - in production would query
            # Gitea for open PRs with pending approval status
            logger.info("Checking for PRs needing reminders")

            # For now, return empty list
            return reminded_prs

        except Exception as e:
            logger.error(f"Failed to check and send reminders: {e}")
            return reminded_prs

    async def get_approval_history(self, pr_number: int) -> list[dict]:
        """
        Get approval history for a PR.

        Args:
            pr_number: The PR number

        Returns:
            List of approval history entries
        """
        try:
            if self.redis is None:
                return []

            history_key = self._get_redis_key(self.REDIS_HISTORY_KEY, pr_number)
            history = self.redis.lrange(history_key, 0, -1)

            if not history:
                return []

            return [
                json.loads(entry.decode() if isinstance(entry, bytes) else entry)
                for entry in history
            ]

        except Exception as e:
            logger.error(f"Failed to get approval history: {e}")
            return []

    async def clear_approval_state(self, pr_number: int) -> bool:
        """
        Clear approval state for a PR (e.g., after merge or close).

        Args:
            pr_number: The PR number

        Returns:
            True if state cleared successfully
        """
        try:
            # Clear cache
            if pr_number in self._approval_cache:
                del self._approval_cache[pr_number]

            if self.redis is None:
                return True

            # Clear Redis keys
            keys = [
                self._get_redis_key(self.REDIS_STATUS_KEY, pr_number),
                self._get_redis_key(self.REDIS_REVIEWER_KEY, pr_number),
                self._get_redis_key(self.REDIS_TIMESTAMP_KEY, pr_number),
                self._get_redis_key(self.REDIS_EMERGENCY_KEY, pr_number),
                self._get_redis_key(self.REDIS_REMINDER_KEY, pr_number),
            ]

            for key in keys:
                self.redis.delete(key)

            logger.info(f"Cleared approval state for PR #{pr_number}")
            return True

        except Exception as e:
            logger.error(f"Failed to clear approval state: {e}")
            return False


# Convenience functions for standalone usage
async def check_pr_human_gate_status(
    pr_number: int,
    files: list[str] | None = None,
) -> HumanGateResult:
    """
    Check if a PR requires human approval due to COMPLEX classification.

    Args:
        pr_number: The PR number to check
        files: Optional list of file paths

    Returns:
        HumanGateResult with full status
    """
    gate = HumanGate()
    return await gate.check_pr_status(pr_number, files)


async def request_human_approval(
    pr_number: int,
    pr_title: str,
    pr_author: str,
    pr_url: str,
    files: list[str],
    gitreviewbot_summary: str | None = None,
) -> bool:
    """
    Request human approval for a COMPLEX PR.

    Args:
        pr_number: The PR number
        pr_title: PR title
        pr_author: PR author
        pr_url: URL to the PR
        files: List of files changed
        gitreviewbot_summary: Optional GitReviewBot summary

    Returns:
        True if request sent successfully
    """
    gate = HumanGate()
    return await gate.request_approval(
        pr_number=pr_number,
        pr_title=pr_title,
        pr_author=pr_author,
        pr_url=pr_url,
        files=files,
        gitreviewbot_summary=gitreviewbot_summary,
    )


if __name__ == "__main__":
    # CLI for testing
    import argparse

    parser = argparse.ArgumentParser(description="Human Gate for COMPLEX PRs")
    parser.add_argument("pr_number", type=int, help="PR number to check")
    parser.add_argument("--files", nargs="+", help="Files changed in PR")
    parser.add_argument("--dry-run", action="store_true", help="Dry run mode")

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    async def main():
        gate = HumanGate(dry_run=args.dry_run)
        result = await gate.check_pr_status(args.pr_number, args.files or [])

        print(json.dumps(result.to_dict(), indent=2))

    asyncio.run(main())
