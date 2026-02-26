#!/usr/bin/env python3
"""
Complex Path Gate for PR Lifecycle Management.

This module implements the human approval gate for COMPLEX-classified PRs,
integrating with the Path Analyzer (ST-AUTO-001) and GitReviewBot (ST-AUTO-003).

Usage:
    from scripts.pr_lifecycle.complex_path_gate import ComplexPathGate

    gate = ComplexPathGate()
    result = await gate.check_pr_status(pr_number=123)

    if result.is_complex and not result.is_approved:
        await gate.request_human_approval(pr_number=123)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

# Add src to path for imports
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from autonomous_git.path_analyzer import RiskLevel, analyze_paths
from autonomous_git.gitreviewbot import GiteaClient

logger = logging.getLogger(__name__)


class ApprovalStatus(Enum):
    """Human approval status for COMPLEX PRs."""

    PENDING = "pending"  # Waiting for human review
    APPROVED = "approved"  # Human has approved
    REJECTED = "rejected"  # Human has rejected
    EMERGENCY_OVERRIDE = "emergency_override"  # Emergency bypass used
    EXPIRED = "expired"  # Approval request timed out


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
    def from_dict(cls, data: dict[str, Any]) -> "ApprovalRecord":
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
class ComplexPathCheckResult:
    """Result of checking a PR against the complex path gate."""

    pr_number: int
    is_complex: bool
    risk_level: RiskLevel
    confidence: float
    files_analyzed: list[str]
    approval_status: ApprovalStatus
    approval_record: ApprovalRecord | None = None
    gitreviewbot_completed: bool = False
    gitreviewbot_decision: str | None = None
    requires_human_approval: bool = False
    can_merge: bool = False
    reasoning: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "pr_number": self.pr_number,
            "is_complex": self.is_complex,
            "risk_level": self.risk_level.value,
            "confidence": self.confidence,
            "files_analyzed": self.files_analyzed,
            "approval_status": self.approval_status.value,
            "approval_record": self.approval_record.to_dict()
            if self.approval_record
            else None,
            "gitreviewbot_completed": self.gitreviewbot_completed,
            "gitreviewbot_decision": self.gitreviewbot_decision,
            "requires_human_approval": self.requires_human_approval,
            "can_merge": self.can_merge,
            "reasoning": self.reasoning,
        }


class ComplexPathGate:
    """
    Gate for managing COMPLEX-classified PRs requiring human approval.

    This class integrates with:
    - Path Analyzer (ST-AUTO-001): To classify PRs as COMPLEX
    - GitReviewBot (ST-AUTO-003): To run pre-review before human notification
    - Gitea API: To check for human approvals
    - Discord: To notify #approvals channel

    Attributes:
        gitea_client: Client for Gitea API interactions
        audit_log_path: Path to store approval audit logs
        emergency_approvers: List of users authorized for emergency override
        approval_timeout_hours: Hours before approval request expires
    """

    def __init__(
        self,
        gitea_client: GiteaClient | None = None,
        audit_log_path: str | None = None,
        emergency_approvers: list[str] | None = None,
        approval_timeout_hours: int = 48,
    ):
        """
        Initialize the Complex Path Gate.

        Args:
            gitea_client: Optional Gitea client instance
            audit_log_path: Path to audit log file (default: data/complex_path_audit.log)
            emergency_approvers: List of authorized emergency approver usernames
            approval_timeout_hours: Hours before approval expires (default: 48)
        """
        self.gitea = gitea_client or GiteaClient()
        self.audit_log_path = Path(audit_log_path or "data/complex_path_audit.log")
        self.emergency_approvers = set(emergency_approvers or [])
        self.approval_timeout_hours = approval_timeout_hours

        # Ensure audit log directory exists
        self.audit_log_path.parent.mkdir(parents=True, exist_ok=True)

        # In-memory cache of approval states
        self._approval_cache: dict[int, ApprovalRecord] = {}

        logger.info(
            f"ComplexPathGate initialized with audit log: {self.audit_log_path}"
        )

    def is_complex_classification(
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

    async def check_pr_status(self, pr_number: int) -> ComplexPathCheckResult:
        """
        Check the complete status of a PR against the complex path gate.

        This method:
        1. Gets PR details from Gitea
        2. Analyzes file paths for COMPLEX classification
        3. Checks GitReviewBot review status
        4. Checks for human approval
        5. Determines if PR can merge

        Args:
            pr_number: The PR number to check

        Returns:
            ComplexPathCheckResult with full status
        """
        logger.info(f"Checking PR #{pr_number} against complex path gate")

        try:
            # Get PR details
            pr = await self.gitea.get_pr(pr_number)

            # Analyze file paths
            is_complex, risk_level, confidence = self.is_complex_classification(
                pr.files_changed
            )

            # Check GitReviewBot status (look for bot labels/comments)
            (
                gitreviewbot_completed,
                gitreviewbot_decision,
            ) = await self._check_gitreviewbot_status(pr_number)

            # Check human approval status
            approval_status, approval_record = await self._check_human_approval(
                pr_number
            )

            # Determine requirements
            requires_human_approval = is_complex
            can_merge = self._can_merge(
                is_complex=is_complex,
                approval_status=approval_status,
                gitreviewbot_completed=gitreviewbot_completed,
            )

            # Build reasoning
            reasoning = self._build_reasoning(
                is_complex=is_complex,
                risk_level=risk_level,
                approval_status=approval_status,
                gitreviewbot_completed=gitreviewbot_completed,
            )

            result = ComplexPathCheckResult(
                pr_number=pr_number,
                is_complex=is_complex,
                risk_level=risk_level,
                confidence=confidence,
                files_analyzed=pr.files_changed,
                approval_status=approval_status,
                approval_record=approval_record,
                gitreviewbot_completed=gitreviewbot_completed,
                gitreviewbot_decision=gitreviewbot_decision,
                requires_human_approval=requires_human_approval,
                can_merge=can_merge,
                reasoning=reasoning,
            )

            logger.info(
                f"PR #{pr_number} check complete: "
                f"complex={is_complex}, approved={approval_status.value}, can_merge={can_merge}"
            )

            return result

        except Exception as e:
            logger.error(f"Failed to check PR #{pr_number}: {e}")
            raise

    async def _check_gitreviewbot_status(
        self, pr_number: int
    ) -> tuple[bool, str | None]:
        """
        Check if GitReviewBot has reviewed the PR.

        Args:
            pr_number: The PR number

        Returns:
            Tuple of (completed, decision)
        """
        try:
            # Get PR labels
            pr = await self.gitea.get_pr(pr_number)
            labels = set(pr.labels)

            # Check for GitReviewBot labels
            bot_labels = {
                "bot-approved": "APPROVE",
                "bot-comment": "COMMENT",
                "bot-changes-requested": "REQUEST_CHANGES",
            }

            for label, decision in bot_labels.items():
                if label in labels:
                    return True, decision

            # Check for bot comments
            comments = await self.gitea.get_pr_comments(pr_number)
            for comment in comments:
                author = comment.get("user", {}).get("login", "")
                body = comment.get("body", "")

                if "GitReviewBot" in author or "🤖 GitReviewBot Analysis" in body:
                    # Extract decision from comment
                    if "Decision:** APPROVE" in body:
                        return True, "APPROVE"
                    elif "Decision:** REQUEST_CHANGES" in body:
                        return True, "REQUEST_CHANGES"
                    elif "Decision:** COMMENT" in body:
                        return True, "COMMENT"

            return False, None

        except Exception as e:
            logger.warning(f"Could not check GitReviewBot status: {e}")
            return False, None

    async def _check_human_approval(
        self, pr_number: int
    ) -> tuple[ApprovalStatus, ApprovalRecord | None]:
        """
        Check if a human has approved the PR.

        Args:
            pr_number: The PR number

        Returns:
            Tuple of (status, record)
        """
        # Check cache first
        if pr_number in self._approval_cache:
            record = self._approval_cache[pr_number]

            # Check if expired
            if self._is_approval_expired(record):
                return ApprovalStatus.EXPIRED, record

            return record.status, record

        # Check audit log for historical approvals
        record = self._load_approval_from_log(pr_number)
        if record:
            self._approval_cache[pr_number] = record

            if self._is_approval_expired(record):
                return ApprovalStatus.EXPIRED, record

            return record.status, record

        return ApprovalStatus.PENDING, None

    def _is_approval_expired(self, record: ApprovalRecord) -> bool:
        """Check if an approval has expired."""
        if record.status not in (
            ApprovalStatus.APPROVED,
            ApprovalStatus.EMERGENCY_OVERRIDE,
        ):
            return False

        age_hours = (datetime.now(UTC) - record.timestamp).total_seconds() / 3600
        return age_hours > self.approval_timeout_hours

    def _can_merge(
        self,
        is_complex: bool,
        approval_status: ApprovalStatus,
        gitreviewbot_completed: bool,
    ) -> bool:
        """
        Determine if a PR can be merged.

        Rules:
        - Non-COMPLEX PRs: Can merge (handled by other gates)
        - COMPLEX PRs: Need human approval (APPROVED or EMERGENCY_OVERRIDE)
        """
        if not is_complex:
            return True  # Not our concern

        return approval_status in (
            ApprovalStatus.APPROVED,
            ApprovalStatus.EMERGENCY_OVERRIDE,
        )

    def _build_reasoning(
        self,
        is_complex: bool,
        risk_level: RiskLevel,
        approval_status: ApprovalStatus,
        gitreviewbot_completed: bool,
    ) -> str:
        """Build human-readable reasoning for the result."""
        parts = [f"Risk level: {risk_level.value}"]

        if is_complex:
            parts.append("COMPLEX classification requires human approval")

            if not gitreviewbot_completed:
                parts.append("GitReviewBot pre-review pending")

            parts.append(f"Human approval status: {approval_status.value}")

            if approval_status == ApprovalStatus.EXPIRED:
                parts.append(
                    f"Approval expired (timeout: {self.approval_timeout_hours}h)"
                )
        else:
            parts.append("Not classified as COMPLEX - no human approval required")

        return "; ".join(parts)

    async def record_human_approval(
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

        self._approval_cache[pr_number] = record
        self._append_to_audit_log(record)

        logger.info(f"Recorded human approval for PR #{pr_number} by {approver}")

        return record

    async def record_human_rejection(
        self,
        pr_number: int,
        approver: str,
        reason: str,
    ) -> ApprovalRecord:
        """
        Record a human rejection for a PR.

        Args:
            pr_number: The PR number
            approver: Username of the rejecting human
            reason: Rejection reason (required)

        Returns:
            The created ApprovalRecord
        """
        record = ApprovalRecord(
            pr_number=pr_number,
            status=ApprovalStatus.REJECTED,
            approver=approver,
            reason=reason,
        )

        self._approval_cache[pr_number] = record
        self._append_to_audit_log(record)

        logger.info(f"Recorded human rejection for PR #{pr_number} by {approver}")

        return record

    async def emergency_override(
        self,
        pr_number: int,
        approver: str,
        justification: str,
    ) -> ApprovalRecord:
        """
        Apply emergency override for critical fixes.

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

        self._approval_cache[pr_number] = record
        self._append_to_audit_log(record)

        logger.warning(
            f"EMERGENCY OVERRIDE applied for PR #{pr_number} by {approver}. "
            f"Post-hoc review required."
        )

        return record

    def _append_to_audit_log(self, record: ApprovalRecord) -> None:
        """Append an approval record to the audit log."""
        try:
            with open(self.audit_log_path, "a") as f:
                json.dump(record.to_dict(), f)
                f.write("\n")
        except Exception as e:
            logger.error(f"Failed to write to audit log: {e}")

    def _load_approval_from_log(self, pr_number: int) -> ApprovalRecord | None:
        """Load the most recent approval record for a PR from the audit log."""
        if not self.audit_log_path.exists():
            return None

        try:
            latest_record = None

            with open(self.audit_log_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        data = json.loads(line)
                        if data.get("pr_number") == pr_number:
                            record = ApprovalRecord.from_dict(data)

                            # Keep the most recent record
                            if (
                                latest_record is None
                                or record.timestamp > latest_record.timestamp
                            ):
                                latest_record = record
                    except (json.JSONDecodeError, KeyError):
                        continue

            return latest_record

        except Exception as e:
            logger.error(f"Failed to read audit log: {e}")
            return None

    def get_audit_trail(self, pr_number: int | None = None) -> list[ApprovalRecord]:
        """
        Get audit trail for a PR or all PRs.

        Args:
            pr_number: Optional PR number to filter by

        Returns:
            List of approval records
        """
        if not self.audit_log_path.exists():
            return []

        records = []

        try:
            with open(self.audit_log_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        data = json.loads(line)
                        if pr_number is None or data.get("pr_number") == pr_number:
                            records.append(ApprovalRecord.from_dict(data))
                    except (json.JSONDecodeError, KeyError):
                        continue

            # Sort by timestamp
            records.sort(key=lambda r: r.timestamp)
            return records

        except Exception as e:
            logger.error(f"Failed to read audit log: {e}")
            return []


# Convenience function for standalone usage
async def check_pr_complex_status(pr_number: int) -> ComplexPathCheckResult:
    """
    Check if a PR requires human approval due to COMPLEX classification.

    Args:
        pr_number: The PR number to check

    Returns:
        ComplexPathCheckResult with full status
    """
    gate = ComplexPathGate()
    return await gate.check_pr_status(pr_number)


if __name__ == "__main__":
    # CLI for testing
    import argparse

    parser = argparse.ArgumentParser(description="Check PR against complex path gate")
    parser.add_argument("pr_number", type=int, help="PR number to check")
    parser.add_argument("--audit-log", help="Path to audit log")

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    async def main():
        gate = ComplexPathGate(audit_log_path=args.audit_log)
        result = await gate.check_pr_status(args.pr_number)

        print(json.dumps(result.to_dict(), indent=2))

    asyncio.run(main())
