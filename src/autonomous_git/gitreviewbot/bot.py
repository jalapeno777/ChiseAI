"""Main GitReviewBot orchestrator."""

import asyncio
import contextlib
import hashlib
from datetime import UTC, datetime
from typing import Any

from .calibration import CalibrationTracker
from .confidence import ConfidenceScorer
from .critic import CriticReviewer
from .gitea_client import GiteaClient
from .models import CachedDiff, Decision, PRDetails
from .senior_dev import SeniorDevReviewer
from .synthesizer import DecisionSynthesizer


class GitReviewBot:
    """Main bot orchestrator for AI-powered PR reviews."""

    def __init__(
        self,
        gitea_client: GiteaClient | None = None,
        senior_dev: SeniorDevReviewer | None = None,
        critic: CriticReviewer | None = None,
        calibration: CalibrationTracker | None = None,
        enable_auto_merge: bool = False,
        cache_ttl_seconds: int = 86400,
    ):
        self.gitea = gitea_client or GiteaClient()
        self.senior_dev = senior_dev or SeniorDevReviewer()
        self.critic = critic or CriticReviewer()
        self.calibration = calibration or CalibrationTracker()
        self.enable_auto_merge = enable_auto_merge
        self.cache_ttl_seconds = cache_ttl_seconds

        # Initialize synthesizer with confidence scorer
        confidence_scorer = ConfidenceScorer()
        self.synthesizer = DecisionSynthesizer(confidence_scorer)

        # Diff cache for cost reduction
        self._diff_cache: dict[str, CachedDiff] = {}

    async def review_pr(
        self,
        pr_number: int,
        skip_cache: bool = False,
    ) -> Decision:
        """Review a PR and return decision."""
        # Get PR details
        pr = await self.gitea.get_pr(pr_number)

        # Get diff
        diff = await self.gitea.get_pr_diff(pr_number)

        # Check cache for similar diffs
        if not skip_cache:
            cached_result = self._check_diff_cache(diff)
            if cached_result:
                # Use cached result with adjusted confidence
                return self._adapt_cached_decision(cached_result, pr)

        # Extract story ID
        story_id = self.gitea.extract_story_id(pr.title)

        # Run dual-role reviews in parallel
        senior_dev_task = self.senior_dev.review(
            pr_title=pr.title,
            story_id=story_id,
            diff=diff,
            files=pr.files_changed,
        )
        critic_task = self.critic.review(
            pr_title=pr.title,
            story_id=story_id,
            diff=diff,
            files=pr.files_changed,
        )

        senior_dev_result, critic_result = await asyncio.gather(
            senior_dev_task,
            critic_task,
        )

        # Get CI status
        ci_passed = await self._check_ci_status(pr_number)

        # Calculate lines changed (approximate from diff)
        lines_changed = self._count_lines_changed(diff)

        # Synthesize decision
        decision = self.synthesizer.synthesize(
            senior_dev_result=senior_dev_result,
            critic_result=critic_result,
            pr_number=pr_number,
            pr_title=pr.title,
            story_id=story_id,
            files_changed=len(pr.files_changed),
            lines_changed=lines_changed,
            ci_passed=ci_passed,
        )

        # Cache the result
        self._cache_diff_result(diff, pr_number, pr.files_changed, senior_dev_result)

        # Log for calibration
        await self.calibration.log_review(decision)

        # Post review to Gitea
        await self.gitea.post_review(pr_number, decision)

        # Update labels
        await self._update_pr_labels(pr_number, decision)

        # Attempt auto-merge if eligible
        if decision.auto_merge_eligible and self.enable_auto_merge:
            await self._attempt_auto_merge(pr_number, decision)

        return decision

    async def _check_ci_status(self, pr_number: int) -> bool:
        """Check if all CI checks passed."""
        try:
            checks = await self.gitea.get_check_runs(pr_number)
            if not checks:
                return True  # No checks = pass by default

            return all(check.get("state") in ("success", "pending") for check in checks)
        except Exception:
            return False

    async def _update_pr_labels(self, pr_number: int, decision: Decision) -> None:
        """Update PR labels based on decision."""
        labels_to_add = []
        labels_to_remove = []

        if decision.decision.value == "APPROVE":
            labels_to_add.append("bot-approved")
            labels_to_remove.extend(["bot-comment", "bot-changes-requested"])
        elif decision.decision.value == "COMMENT":
            labels_to_add.append("bot-comment")
            labels_to_remove.extend(["bot-approved", "bot-changes-requested"])
        elif decision.decision.value == "REQUEST_CHANGES":
            labels_to_add.append("bot-changes-requested")
            labels_to_remove.extend(["bot-approved", "bot-comment"])

        if decision.auto_merge_eligible:
            labels_to_add.append("auto-merge-eligible")

        # Apply label changes
        for label in labels_to_remove:
            with contextlib.suppress(Exception):
                await self.gitea.remove_label(pr_number, label)

        for label in labels_to_add:
            with contextlib.suppress(Exception):
                await self.gitea.add_labels(pr_number, [label])

    async def _attempt_auto_merge(
        self,
        pr_number: int,
        decision: Decision,
    ) -> None:
        """Attempt to auto-merge a PR."""
        try:
            # Double-check eligibility
            if not decision.auto_merge_eligible:
                return

            # Log the auto-merge attempt
            await self.gitea.post_comment(
                pr_number,
                f"🤖 **Auto-merge triggered**\n\n"
                f"Confidence: {decision.confidence:.1f}%\n"
                f"Merging automatically as all criteria are met.",
            )

            # Perform merge
            await self.gitea.merge_pr(
                pr_number,
                merge_method="merge",
                delete_branch=False,
            )
        except Exception as e:
            # Log failure but don't fail the review
            await self.gitea.post_comment(
                pr_number,
                f"⚠️ **Auto-merge failed**: {str(e)}\n\nManual merge required.",
            )

    def _check_diff_cache(self, diff: str) -> CachedDiff | None:
        """Check if a similar diff is in cache."""
        diff_hash = self._hash_diff(diff)

        if diff_hash in self._diff_cache:
            cached = self._diff_cache[diff_hash]
            # Check TTL
            age = (datetime.now(UTC) - cached.created_at).total_seconds()
            if age < cached.ttl_seconds:
                return cached
            else:
                # Expired, remove from cache
                del self._diff_cache[diff_hash]

        return None

    def _cache_diff_result(
        self,
        diff: str,
        pr_number: int,
        files: list[str],
        result,
    ) -> None:
        """Cache review result for a diff."""
        diff_hash = self._hash_diff(diff)

        cached = CachedDiff(
            diff_hash=diff_hash,
            pr_number=pr_number,
            files=files,
            review_result=result,
            ttl_seconds=self.cache_ttl_seconds,
        )

        self._diff_cache[diff_hash] = cached

    def _adapt_cached_decision(
        self,
        cached: CachedDiff,
        pr: PRDetails,
    ) -> Decision:
        """Adapt a cached decision for a new PR."""
        # Use cached result but reduce confidence slightly
        adjusted_confidence = cached.review_result.confidence * 0.95

        return Decision(
            decision=cached.review_result.decision,
            confidence=adjusted_confidence,
            senior_dev_confidence=adjusted_confidence,
            critic_confidence=adjusted_confidence,
            blockers=cached.review_result.blockers,
            findings=cached.review_result.findings,
            violations=cached.review_result.violations,
            summary=f"Similar diff detected. {cached.review_result.summary}",
            auto_merge_eligible=False,  # Don't auto-merge cached results
            pr_number=pr.number,
            pr_title=pr.title,
            story_id=self.gitea.extract_story_id(pr.title),
        )

    def _hash_diff(self, diff: str) -> str:
        """Create a hash of the diff for caching."""
        # Normalize diff by removing line numbers and whitespace
        normalized = "\n".join(
            line
            for line in diff.split("\n")
            if not line.startswith("@@") and line.strip()
        )
        return hashlib.sha256(normalized.encode()).hexdigest()[:16]

    def _count_lines_changed(self, diff: str) -> int:
        """Count approximate lines changed in diff."""
        added = 0
        removed = 0

        for line in diff.split("\n"):
            if line.startswith("+") and not line.startswith("+++"):
                added += 1
            elif line.startswith("-") and not line.startswith("---"):
                removed += 1

        return added + removed

    async def record_feedback(
        self,
        pr_number: int,
        review_id: str,
        feedback_type: str,
        reviewer: str,
        comment: str | None = None,
    ) -> None:
        """Record human feedback on a review."""
        await self.calibration.record_feedback(
            pr_number, review_id, feedback_type, reviewer, comment
        )

    async def get_calibration_metrics(self, days: int = 7) -> dict[str, Any]:
        """Get calibration metrics."""
        metrics = await self.calibration.calculate_metrics(days)
        return metrics.model_dump()


# Convenience function for standalone usage
async def review_pr(
    pr_number: int,
    gitea_url: str | None = None,
    gitea_token: str | None = None,
    enable_auto_merge: bool = False,
) -> Decision:
    """Review a PR with default configuration."""
    gitea = GiteaClient(
        base_url=gitea_url,
        token=gitea_token,
    )

    bot = GitReviewBot(
        gitea_client=gitea,
        enable_auto_merge=enable_auto_merge,
    )

    try:
        return await bot.review_pr(pr_number)
    finally:
        await gitea.close()
