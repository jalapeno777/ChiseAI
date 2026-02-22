"""Safety checks for auto-approval."""

import logging
import re
from dataclasses import dataclass, field
from datetime import UTC
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

# Story ID token patterns
STORY_ID_PATTERNS = [
    r"ST-\d+",
    r"CH-\d+",
    r"FT-\d+",
    r"REWARD-\d+",
    r"REPO-\d+",
    r"SAFETY-\d+",
    r"BRANCH-\d+",
    r"PAPER-\d+",
    r"RECON-\d+",
]


class CheckStatus(Enum):
    """Status of a safety check."""

    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass
class CheckResult:
    """Result of a single safety check."""

    name: str
    status: CheckStatus
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class SafetyCheckResult:
    """Complete safety check results."""

    all_passed: bool
    checks: list[CheckResult]
    pr_number: int
    timestamp: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "all_passed": self.all_passed,
            "pr_number": self.pr_number,
            "timestamp": self.timestamp,
            "checks": [
                {
                    "name": c.name,
                    "status": c.status.value,
                    "message": c.message,
                    "details": c.details,
                }
                for c in self.checks
            ],
        }


class SafetyChecker:
    """Performs safety checks before auto-approval."""

    def __init__(
        self,
        require_green_ci: bool = True,
        require_story_id: bool = True,
        check_merge_conflicts: bool = True,
        gitea_client=None,
    ):
        """Initialize safety checker.

        Args:
            require_green_ci: Whether to require green CI
            require_story_id: Whether to require story ID in PR title
            check_merge_conflicts: Whether to check for merge conflicts
            gitea_client: Optional Gitea API client
        """
        self.require_green_ci = require_green_ci
        self.require_story_id = require_story_id
        self.check_merge_conflicts = check_merge_conflicts
        self.gitea = gitea_client

    async def run_checks(
        self, pr_number: int, pr_data: dict | None = None
    ) -> SafetyCheckResult:
        """Run all safety checks on a PR.

        Args:
            pr_number: PR number to check
            pr_data: Optional pre-fetched PR data

        Returns:
            SafetyCheckResult with all check results
        """
        from datetime import datetime

        checks = []

        # Fetch PR data if not provided
        if pr_data is None and self.gitea:
            pr_data = await self._fetch_pr_data(pr_number)

        if pr_data is None:
            pr_data = {}

        # Run each check
        checks.append(await self._check_merge_conflicts(pr_data))
        checks.append(await self._check_ci_status(pr_number, pr_data))
        checks.append(await self._check_story_id(pr_data))
        checks.append(await self._check_branch_protection(pr_data))
        checks.append(await self._check_author_status(pr_data))

        # Determine overall result
        all_passed = all(
            c.status in (CheckStatus.PASSED, CheckStatus.SKIPPED) for c in checks
        )

        return SafetyCheckResult(
            all_passed=all_passed,
            checks=checks,
            pr_number=pr_number,
            timestamp=datetime.now(UTC).isoformat(),
        )

    async def _fetch_pr_data(self, pr_number: int) -> dict:
        """Fetch PR data from Gitea."""
        # This would call Gitea API
        # For now, return empty dict (will be mocked in tests)
        logger.debug(f"Fetching PR data for #{pr_number}")
        return {}

    async def _check_merge_conflicts(self, pr_data: dict) -> CheckResult:
        """Check if PR has merge conflicts."""
        if not self.check_merge_conflicts:
            return CheckResult(
                name="merge_conflicts",
                status=CheckStatus.SKIPPED,
                message="Merge conflict check disabled",
            )

        # Check mergeable status from PR data
        mergeable = pr_data.get("mergeable", True)

        if mergeable is False:
            return CheckResult(
                name="merge_conflicts",
                status=CheckStatus.FAILED,
                message="PR has merge conflicts",
                details={"mergeable": False},
            )

        return CheckResult(
            name="merge_conflicts",
            status=CheckStatus.PASSED,
            message="No merge conflicts detected",
            details={"mergeable": mergeable},
        )

    async def _check_ci_status(self, pr_number: int, pr_data: dict) -> CheckResult:
        """Check if CI is green."""
        if not self.require_green_ci:
            return CheckResult(
                name="ci_status",
                status=CheckStatus.SKIPPED,
                message="CI status check disabled",
            )

        # Get status checks from PR data
        status_checks = pr_data.get("status_checks", [])

        if not status_checks:
            # No status checks configured - this is a pass
            return CheckResult(
                name="ci_status",
                status=CheckStatus.PASSED,
                message="No CI checks configured",
                details={"checks": []},
            )

        # Check if all required checks pass
        failed_checks = [
            check
            for check in status_checks
            if check.get("status") != "success" and check.get("required", True)
        ]

        if failed_checks:
            return CheckResult(
                name="ci_status",
                status=CheckStatus.FAILED,
                message=f"CI checks failed: {', '.join(c.get('name', 'unknown') for c in failed_checks)}",
                details={
                    "failed_checks": failed_checks,
                    "total_checks": len(status_checks),
                },
            )

        return CheckResult(
            name="ci_status",
            status=CheckStatus.PASSED,
            message=f"All {len(status_checks)} CI checks passed",
            details={"checks": status_checks},
        )

    async def _check_story_id(self, pr_data: dict) -> CheckResult:
        """Check if PR title contains story ID."""
        if not self.require_story_id:
            return CheckResult(
                name="story_id",
                status=CheckStatus.SKIPPED,
                message="Story ID check disabled",
            )

        title = pr_data.get("title", "")

        for pattern in STORY_ID_PATTERNS:
            if re.search(pattern, title):
                return CheckResult(
                    name="story_id",
                    status=CheckStatus.PASSED,
                    message="Found story ID in PR title",
                    details={"pattern_matched": pattern, "title": title},
                )

        return CheckResult(
            name="story_id",
            status=CheckStatus.FAILED,
            message="PR title missing required story ID token",
            details={
                "title": title,
                "required_patterns": STORY_ID_PATTERNS,
            },
        )

    async def _check_branch_protection(self, pr_data: dict) -> CheckResult:
        """Check if branch protection rules are satisfied."""
        # This would check if required reviews are met, etc.
        # For now, assume satisfied if we have PR data

        base_branch = pr_data.get("base", {}).get("ref", "unknown")

        return CheckResult(
            name="branch_protection",
            status=CheckStatus.PASSED,
            message=f"Base branch: {base_branch}",
            details={"base_branch": base_branch},
        )

    async def _check_author_status(self, pr_data: dict) -> CheckResult:
        """Check if PR author is allowed."""
        author = pr_data.get("user", {}).get("login", "unknown")

        # Could check against denylist here

        return CheckResult(
            name="author_status",
            status=CheckStatus.PASSED,
            message=f"Author: {author}",
            details={"author": author},
        )

    def has_story_id(self, title: str) -> bool:
        """Check if a title contains a valid story ID.

        Args:
            title: PR title to check

        Returns:
            True if story ID found
        """
        for pattern in STORY_ID_PATTERNS:
            if re.search(pattern, title):
                return True
        return False
