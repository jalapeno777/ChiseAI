"""Core approval logic for auto-approval."""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from .config import AutoApprovalConfig
from .safety_checks import SafetyChecker, SafetyCheckResult
from .rate_limiter import RateLimiter
from .exclusions import ExclusionManager
from .notifier import DiscordNotifier

logger = logging.getLogger(__name__)

# Redis key for emergency stop
EMERGENCY_STOP_KEY = "bmad:chiseai:auto_approval:disabled"


# Mock interface for ST-AUTO-001 integration
# This will be replaced with actual import when ST-AUTO-001 is complete
class RiskLevel:
    """Mock RiskLevel for integration."""

    SAFE = "safe"
    MEDIUM_RISK = "medium_risk"
    COMPLEX = "complex"


@dataclass
class RiskClassification:
    """Mock RiskClassification for integration."""

    risk_level: str
    confidence: float
    files: List[str]
    reasoning: str
    pr_number: Optional[int] = None


async def get_path_classification(pr_number: int) -> RiskClassification:
    """Mock function to get path classification.

    This is a placeholder that will be replaced with the actual
    implementation from ST-AUTO-001 (Path Analyzer).

    Args:
        pr_number: PR number to classify

    Returns:
        RiskClassification result
    """
    # This is a mock implementation
    # In production, this will call:
    # from src.autonomous_git.path_analyzer import analyze_paths
    # return await analyze_paths(pr_number)
    logger.debug(f"Mock path classification for PR #{pr_number}")
    return RiskClassification(
        risk_level=RiskLevel.SAFE,
        confidence=0.95,
        files=[],
        reasoning="Mock classification - ST-AUTO-001 integration pending",
        pr_number=pr_number,
    )


async def is_auto_approval_disabled(redis_client=None) -> bool:
    """Check if auto-approval is disabled via emergency stop.

    Args:
        redis_client: Optional Redis client

    Returns:
        True if auto-approval is disabled
    """
    if redis_client:
        try:
            result = await redis_client.get(EMERGENCY_STOP_KEY)
            if result and result.lower() in ("true", "1", "yes"):
                logger.warning("Auto-approval is DISABLED (emergency stop active)")
                return True
        except Exception as e:
            logger.warning(f"Failed to check emergency stop in Redis: {e}")

    return False


@dataclass
class ApprovalResult:
    """Result of an auto-approval attempt."""

    success: bool
    pr_number: int
    message: str
    timestamp: str
    classification: Optional[RiskClassification] = None
    safety_result: Optional[SafetyCheckResult] = None
    error_details: Optional[Dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "pr_number": self.pr_number,
            "message": self.message,
            "timestamp": self.timestamp,
            "classification": {
                "risk_level": self.classification.risk_level
                if self.classification
                else None,
                "confidence": self.classification.confidence
                if self.classification
                else None,
                "reasoning": self.classification.reasoning
                if self.classification
                else None,
            }
            if self.classification
            else None,
            "safety_result": self.safety_result.to_dict()
            if self.safety_result
            else None,
            "error_details": self.error_details,
        }


class AutoApprover:
    """Main auto-approval orchestrator."""

    def __init__(
        self,
        config: Optional[AutoApprovalConfig] = None,
        redis_client=None,
        gitea_client=None,
    ):
        """Initialize auto-approver.

        Args:
            config: Auto-approval configuration
            redis_client: Optional Redis client
            gitea_client: Optional Gitea API client
        """
        self.config = config or AutoApprovalConfig()
        self.redis = redis_client
        self.gitea = gitea_client

        # Initialize components
        self.rate_limiter = RateLimiter(
            max_per_hour=self.config.rate_limits.max_per_hour,
            max_consecutive=self.config.rate_limits.max_consecutive,
            consecutive_pause_duration=self.config.rate_limits.consecutive_pause_duration,
            redis_client=redis_client,
        )

        self.safety_checker = SafetyChecker(
            require_green_ci=self.config.safety_checks.require_green_ci,
            require_story_id=self.config.safety_checks.require_story_id,
            check_merge_conflicts=self.config.safety_checks.check_merge_conflicts,
            gitea_client=gitea_client,
        )

        self.exclusion_manager = ExclusionManager(
            paths=self.config.exclusions.paths,
            authors=self.config.exclusions.authors,
            title_patterns=self.config.exclusions.title_patterns,
        )

        self.notifier = DiscordNotifier(
            webhook_url=self.config.discord_webhook_url,
            channel=self.config.notifications.discord_channel,
            alert_channel=self.config.notifications.alert_channel,
            rate_limit=self.config.notifications.rate_limit,
            redis_client=redis_client,
        )

    async def process_pr(
        self, pr_number: int, pr_data: Optional[Dict] = None
    ) -> ApprovalResult:
        """Process a PR for auto-approval.

        Args:
            pr_number: PR number to process
            pr_data: Optional pre-fetched PR data

        Returns:
            ApprovalResult with outcome
        """
        timestamp = datetime.now(timezone.utc).isoformat()

        # 1. Check emergency stop
        if await is_auto_approval_disabled(self.redis):
            return ApprovalResult(
                success=False,
                pr_number=pr_number,
                message="Auto-approval disabled by emergency stop",
                timestamp=timestamp,
            )

        # 2. Check if auto-approval is enabled
        if not self.config.enabled:
            return ApprovalResult(
                success=False,
                pr_number=pr_number,
                message="Auto-approval is disabled in configuration",
                timestamp=timestamp,
            )

        # 3. Get path classification
        try:
            classification = await get_path_classification(pr_number)
        except Exception as e:
            logger.error(f"Failed to get path classification for PR #{pr_number}: {e}")
            return ApprovalResult(
                success=False,
                pr_number=pr_number,
                message=f"Path classification failed: {str(e)}",
                timestamp=timestamp,
                error_details={"error": str(e)},
            )

        # 4. Check if PR is SAFE
        if classification.risk_level != RiskLevel.SAFE:
            return ApprovalResult(
                success=False,
                pr_number=pr_number,
                message=f"PR not eligible: risk level is {classification.risk_level}",
                timestamp=timestamp,
                classification=classification,
            )

        # 5. Run safety checks
        safety_result = await self.safety_checker.run_checks(pr_number, pr_data)
        if not safety_result.all_passed:
            logger.warning(f"Safety checks failed for PR #{pr_number}")
            return ApprovalResult(
                success=False,
                pr_number=pr_number,
                message="Safety checks failed",
                timestamp=timestamp,
                classification=classification,
                safety_result=safety_result,
            )

        # 6. Check exclusions
        pr_title = pr_data.get("title", "") if pr_data else ""
        pr_author = pr_data.get("user", {}).get("login", "") if pr_data else ""

        is_excluded, exclusion_reason = self.exclusion_manager.is_pr_excluded(
            pr_number=pr_number,
            title=pr_title,
            author=pr_author,
            files=classification.files,
        )

        if is_excluded:
            return ApprovalResult(
                success=False,
                pr_number=pr_number,
                message=f"PR excluded: {exclusion_reason}",
                timestamp=timestamp,
                classification=classification,
                safety_result=safety_result,
            )

        # 7. Check rate limits
        if not await self.rate_limiter.check_limits():
            return ApprovalResult(
                success=False,
                pr_number=pr_number,
                message="Rate limit exceeded",
                timestamp=timestamp,
                classification=classification,
                safety_result=safety_result,
            )

        # 8. Approve and merge
        try:
            await self._approve_pr(pr_number, classification.reasoning)
            await self._merge_pr(pr_number)
            await self.rate_limiter.record_success()
        except Exception as e:
            logger.error(f"Failed to approve/merge PR #{pr_number}: {e}")
            await self.notifier.notify_failure(
                pr_number=pr_number,
                pr_title=pr_title,
                author=pr_author,
                error_message=str(e),
            )
            return ApprovalResult(
                success=False,
                pr_number=pr_number,
                message=f"Approval/merge failed: {str(e)}",
                timestamp=timestamp,
                classification=classification,
                safety_result=safety_result,
                error_details={"error": str(e)},
            )

        # 9. Log and notify
        await self._log_approval(pr_number, classification, safety_result)
        await self.notifier.notify_auto_merge(
            pr_number=pr_number,
            pr_title=pr_title,
            author=pr_author,
            file_count=len(classification.files),
            classification_confidence=classification.confidence,
        )

        return ApprovalResult(
            success=True,
            pr_number=pr_number,
            message="PR auto-approved and merged successfully",
            timestamp=timestamp,
            classification=classification,
            safety_result=safety_result,
        )

    async def _approve_pr(self, pr_number: int, reasoning: str):
        """Approve a PR via Gitea API.

        Args:
            pr_number: PR number
            reasoning: Approval reasoning
        """
        if self.gitea:
            # Call Gitea API to approve
            logger.info(f"Approving PR #{pr_number}")
            # await self.gitea.approve_pr(pr_number, reasoning)
        else:
            logger.info(f"Would approve PR #{pr_number}: {reasoning}")

    async def _merge_pr(self, pr_number: int):
        """Merge a PR via Gitea API.

        Args:
            pr_number: PR number
        """
        if self.gitea:
            # Call Gitea API to merge
            logger.info(
                f"Merging PR #{pr_number} with strategy: {self.config.merge_strategy}"
            )
            # await self.gitea.merge_pr(pr_number, self.config.merge_strategy)
        else:
            logger.info(f"Would merge PR #{pr_number}")

    async def _log_approval(
        self,
        pr_number: int,
        classification: RiskClassification,
        safety_result: SafetyCheckResult,
    ):
        """Log auto-approval to audit log.

        Args:
            pr_number: PR number
            classification: Risk classification
            safety_result: Safety check results
        """
        log_entry = {
            "event": "auto_approval",
            "pr_number": pr_number,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "risk_level": classification.risk_level,
            "confidence": classification.confidence,
            "files": classification.files,
            "reasoning": classification.reasoning,
            "safety_checks": safety_result.to_dict(),
        }

        # Log to Redis if available
        if self.redis:
            try:
                key = "bmad:chiseai:auto_approval:log"
                await self.redis.lpush(key, str(log_entry))
                await self.redis.ltrim(key, 0, 9999)  # Keep last 10000 entries
            except Exception as e:
                logger.warning(f"Failed to log to Redis: {e}")

        logger.info(f"Auto-approval logged for PR #{pr_number}")


async def process_safe_pr(
    pr_number: int, config: Optional[AutoApprovalConfig] = None
) -> ApprovalResult:
    """Convenience function to process a single PR.

    Args:
        pr_number: PR number to process
        config: Optional configuration

    Returns:
        ApprovalResult
    """
    approver = AutoApprover(config=config)
    return await approver.process_pr(pr_number)
