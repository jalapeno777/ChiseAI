"""
Reflection loop implementations.

This module implements micro, meso, and macro reflection loops
with storage in Redis and promotion to Qdrant.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from .artifacts import (
    AutomationTarget,
    FailureObservation,
    FailureType,
    KPISnapshot,
    PromotionCandidate,
    ReflectionArtifact,
    ReflectionType,
    ReflectionValidator,
    RootCause,
    Severity,
    create_reflection_artifact,
)

logger = logging.getLogger(__name__)


class ReflectionStorage:
    """Handles storage of reflection artifacts."""

    # Redis key patterns
    MICRO_KEY = "bmad:chiseai:reflection:micro:{story_id}"
    MESO_KEY = "bmad:chiseai:reflection:story:{story_id}"
    MACRO_DAILY_KEY = "bmad:chiseai:reflection:macro:daily:{date}"
    MACRO_WEEKLY_KEY = "bmad:chiseai:reflection:macro:weekly:{year_week}"
    KPI_SNAPSHOT_KEY = "bmad:chiseai:kpi:snapshot"

    # TTL in seconds
    MICRO_TTL = 7 * 24 * 60 * 60  # 7 days
    MESO_TTL = 90 * 24 * 60 * 60  # 90 days

    def __init__(
        self, redis_client: Any | None = None, qdrant_client: Any | None = None
    ):
        """
        Initialize storage with optional clients.

        Args:
            redis_client: Redis client instance
            qdrant_client: Qdrant client instance
        """
        self.redis = redis_client
        self.qdrant = qdrant_client

    def _get_redis(self) -> Any:
        """Get Redis client, raising error if not configured."""
        if self.redis is None:
            raise RuntimeError("Redis client not configured")
        return self.redis

    def _get_qdrant(self) -> Any:
        """Get Qdrant client, raising error if not configured."""
        if self.qdrant is None:
            raise RuntimeError("Qdrant client not configured")
        return self.qdrant

    def store_micro_reflection(
        self,
        story_id: str,
        action: str,
        result: str,
        duration_ms: int | None = None,
        error: str | None = None,
    ) -> ReflectionArtifact:
        """
        Store a micro-reflection for a single action.

        Args:
            story_id: Story identifier
            action: Action performed (e.g., "tool_call", "file_edit")
            result: Result of the action
            duration_ms: Optional duration in milliseconds
            error: Optional error message if action failed

        Returns:
            Created reflection artifact
        """
        what_changed = f"Action: {action}\nResult: {result}"
        if duration_ms:
            what_changed += f"\nDuration: {duration_ms}ms"

        failures = []
        if error:
            failures.append(
                FailureObservation(
                    type=(
                        FailureType.TEST_FAILURE
                        if "test" in error.lower()
                        else FailureType.CI_FAILURE
                    ),
                    timestamp=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                    description=error,
                    severity=Severity.MEDIUM,
                )
            )

        artifact = create_reflection_artifact(
            story_id=story_id,
            reflection_type=ReflectionType.MICRO,
            what_changed=what_changed,
            failures_observed=failures if failures else None,
        )

        # Validate before storing
        is_valid, errors = ReflectionValidator.validate_artifact(artifact)
        if not is_valid:
            logger.error(f"Invalid micro-reflection: {errors}")
            raise ValueError(f"Invalid artifact: {errors}")

        # Store in Redis with TTL
        key = self.MICRO_KEY.format(story_id=story_id)
        self._get_redis().lpush(key, artifact.to_json())
        self._get_redis().expire(key, self.MICRO_TTL)

        logger.info(f"Stored micro-reflection for {story_id}")
        return artifact

    def store_meso_reflection(
        self,
        story_id: str,
        what_changed: str,
        kpi_snapshot: KPISnapshot | None = None,
        failures_observed: list[FailureObservation] | None = None,
        root_causes: list[RootCause] | None = None,
        next_automation_targets: list[AutomationTarget] | None = None,
        promotion_candidates: list[PromotionCandidate] | None = None,
    ) -> ReflectionArtifact:
        """
        Store a meso-reflection at story closure.

        Args:
            story_id: Story identifier
            what_changed: Summary of changes
            kpi_snapshot: Optional KPI metrics
            failures_observed: Optional list of failures
            root_causes: Optional list of root causes
            next_automation_targets: Optional list of automation targets
            promotion_candidates: Optional list of promotion candidates

        Returns:
            Created reflection artifact
        """
        artifact = create_reflection_artifact(
            story_id=story_id,
            reflection_type=ReflectionType.MESO,
            what_changed=what_changed,
            kpi_snapshot=kpi_snapshot,
            failures_observed=failures_observed,
            root_causes=root_causes,
            next_automation_targets=next_automation_targets,
            promotion_candidates=promotion_candidates,
        )

        # Validate before storing
        is_valid, errors = ReflectionValidator.validate_artifact(artifact)
        if not is_valid:
            logger.error(f"Invalid meso-reflection: {errors}")
            raise ValueError(f"Invalid artifact: {errors}")

        # Store in Redis with TTL
        key = self.MESO_KEY.format(story_id=story_id)
        self._get_redis().set(key, artifact.to_json())
        self._get_redis().expire(key, self.MESO_TTL)

        logger.info(f"Stored meso-reflection for {story_id}")

        # Check promotion criteria
        if self._should_promote_to_qdrant(artifact):
            self._promote_to_qdrant(artifact)

        return artifact

    def store_macro_reflection(
        self,
        period: str,
        what_changed: str,
        kpi_snapshot: KPISnapshot,
        failures_observed: list[FailureObservation],
        root_causes: list[RootCause],
        next_automation_targets: list[AutomationTarget],
        promotion_candidates: list[PromotionCandidate],
    ) -> ReflectionArtifact:
        """
        Store a macro-reflection for daily/weekly retro.

        Args:
            period: Period type ("daily" or "weekly")
            what_changed: Summary of changes and trends
            kpi_snapshot: Aggregated KPI metrics
            failures_observed: List of failures in period
            root_causes: List of root causes identified
            next_automation_targets: List of automation targets
            promotion_candidates: List of promotion candidates

        Returns:
            Created reflection artifact
        """
        now = datetime.now(UTC)
        story_id = f"ST-MACRO-{period.upper()}-{now.strftime('%Y%m%d')}"

        artifact = create_reflection_artifact(
            story_id=story_id,
            reflection_type=ReflectionType.MACRO,
            what_changed=what_changed,
            kpi_snapshot=kpi_snapshot,
            failures_observed=failures_observed,
            root_causes=root_causes,
            next_automation_targets=next_automation_targets,
            promotion_candidates=promotion_candidates,
        )

        # Validate before storing
        is_valid, errors = ReflectionValidator.validate_artifact(artifact)
        if not is_valid:
            logger.error(f"Invalid macro-reflection: {errors}")
            raise ValueError(f"Invalid artifact: {errors}")

        # Store in Redis
        if period == "daily":
            key = self.MACRO_DAILY_KEY.format(date=now.strftime("%Y%m%d"))
        else:
            year_week = now.strftime("%Y-W%U")
            key = self.MACRO_WEEKLY_KEY.format(year_week=year_week)

        self._get_redis().set(key, artifact.to_json())

        # Always promote macro reflections to Qdrant
        self._promote_to_qdrant(artifact)

        logger.info(f"Stored macro-reflection for {period}")
        return artifact

    def _should_promote_to_qdrant(self, artifact: ReflectionArtifact) -> bool:
        """
        Check if artifact meets promotion criteria to Qdrant.

        Promotion criteria:
        - Coverage > 85% AND CI pass rate > 95%
        - OR has failures with root causes (for learning)
        - OR has promotion candidates
        """
        if artifact.kpi_snapshot:
            coverage = artifact.kpi_snapshot.coverage or 0
            ci_pass_rate = artifact.kpi_snapshot.ci_pass_rate or 0

            if coverage > 0.85 and ci_pass_rate > 0.95:
                return True

        if artifact.failures_observed and artifact.root_causes:
            return True

        return bool(artifact.promotion_candidates)

    def _promote_to_qdrant(self, artifact: ReflectionArtifact) -> None:
        """Promote artifact to Qdrant for long-term storage and search."""
        try:
            qdrant = self._get_qdrant()

            # Create a simple vector from artifact data
            # In production, this would use an embedding model
            vector = self._create_embedding(artifact)

            payload = {
                "story_id": artifact.story_id,
                "reflection_type": artifact.reflection_type.value,
                "timestamp": artifact.timestamp,
                "what_changed": artifact.what_changed,
                "has_failures": len(artifact.failures_observed) > 0,
            }

            # Use story_id + timestamp as point ID
            point_id = f"{artifact.story_id}:{artifact.timestamp}"

            qdrant.upsert(
                collection_name="reflection_artifacts",
                points=[
                    {
                        "id": point_id,
                        "vector": vector,
                        "payload": payload,
                    }
                ],
            )

            logger.info(f"Promoted reflection to Qdrant: {artifact.story_id}")
        except Exception as e:
            logger.error(f"Failed to promote to Qdrant: {e}")
            # Don't raise - promotion failure shouldn't block storage

    def _create_embedding(self, artifact: ReflectionArtifact) -> list[float]:
        """
        Create a simple embedding vector from artifact.

        In production, this would use a proper embedding model.
        For now, we create a simple hash-based vector.
        """
        # Simple approach: hash the content and create a sparse vector
        content = f"{artifact.story_id} {artifact.what_changed}"
        hash_val = hash(content)

        # Create a 1536-dim vector (standard for many embedding models)
        # Use hash to seed deterministic pseudo-random values
        import random

        rng = random.Random(hash_val)
        return [rng.random() for _ in range(1536)]

    def get_micro_reflections(
        self, story_id: str, limit: int = 100
    ) -> list[ReflectionArtifact]:
        """Get micro-reflections for a story."""
        key = self.MICRO_KEY.format(story_id=story_id)
        data = self._get_redis().lrange(key, 0, limit - 1)

        artifacts = []
        for item in data:
            try:
                artifact = ReflectionArtifact.from_json(item)
                artifacts.append(artifact)
            except Exception as e:
                logger.warning(f"Failed to parse reflection: {e}")

        return artifacts

    def get_meso_reflection(self, story_id: str) -> ReflectionArtifact | None:
        """Get meso-reflection for a story."""
        key = self.MESO_KEY.format(story_id=story_id)
        data = self._get_redis().get(key)

        if data:
            return ReflectionArtifact.from_json(data)
        return None

    def get_macro_reflection(
        self, period: str, date_str: str | None = None
    ) -> ReflectionArtifact | None:
        """Get macro-reflection for a period."""
        if date_str is None:
            date_str = datetime.now(UTC).strftime("%Y%m%d")

        if period == "daily":
            key = self.MACRO_DAILY_KEY.format(date=date_str)
        else:
            year_week = datetime.strptime(date_str, "%Y%m%d").strftime("%Y-W%U")
            key = self.MACRO_WEEKLY_KEY.format(year_week=year_week)

        data = self._get_redis().get(key)

        if data:
            return ReflectionArtifact.from_json(data)
        return None


class ReflectionLoops:
    """Main class for executing reflection loops."""

    def __init__(
        self, redis_client: Any | None = None, qdrant_client: Any | None = None
    ):
        """
        Initialize reflection loops.

        Args:
            redis_client: Redis client instance
            qdrant_client: Qdrant client instance
        """
        self.storage = ReflectionStorage(redis_client, qdrant_client)

    def micro_loop(
        self,
        story_id: str,
        action: str,
        result: str,
        duration_ms: int | None = None,
        error: str | None = None,
    ) -> ReflectionArtifact:
        """
        Execute micro-reflection loop after an action.

        Args:
            story_id: Story identifier
            action: Action performed
            result: Result of action
            duration_ms: Optional duration
            error: Optional error message

        Returns:
            Created reflection artifact
        """
        logger.debug(f"Executing micro-loop for {story_id}: {action}")
        return self.storage.store_micro_reflection(
            story_id=story_id,
            action=action,
            result=result,
            duration_ms=duration_ms,
            error=error,
        )

    def meso_loop(
        self,
        story_id: str,
        what_changed: str,
        kpi_snapshot: KPISnapshot | None = None,
        failures_observed: list[FailureObservation] | None = None,
        root_causes: list[RootCause] | None = None,
        next_automation_targets: list[AutomationTarget] | None = None,
        promotion_candidates: list[PromotionCandidate] | None = None,
    ) -> ReflectionArtifact:
        """
        Execute meso-reflection loop at story closure.

        Args:
            story_id: Story identifier
            what_changed: Summary of changes
            kpi_snapshot: Optional KPI metrics
            failures_observed: Optional list of failures
            root_causes: Optional list of root causes
            next_automation_targets: Optional list of automation targets
            promotion_candidates: Optional list of promotion candidates

        Returns:
            Created reflection artifact
        """
        logger.info(f"Executing meso-loop for {story_id}")
        return self.storage.store_meso_reflection(
            story_id=story_id,
            what_changed=what_changed,
            kpi_snapshot=kpi_snapshot,
            failures_observed=failures_observed,
            root_causes=root_causes,
            next_automation_targets=next_automation_targets,
            promotion_candidates=promotion_candidates,
        )

    def macro_loop(
        self,
        period: str,
        stories_completed: list[str],
        aggregate_kpis: KPISnapshot | None = None,
    ) -> ReflectionArtifact:
        """
        Execute macro-reflection loop for daily/weekly retro.

        Args:
            period: Period type ("daily" or "weekly")
            stories_completed: List of story IDs completed in period
            aggregate_kpis: Optional pre-computed aggregate KPIs

        Returns:
            Created reflection artifact
        """
        logger.info(f"Executing macro-loop for {period}")

        # Aggregate data from meso-reflections
        all_failures = []
        all_root_causes = []
        all_automation_targets = []
        all_promotion_candidates = []

        for story_id in stories_completed:
            reflection = self.storage.get_meso_reflection(story_id)
            if reflection:
                all_failures.extend(reflection.failures_observed)
                all_root_causes.extend(reflection.root_causes)
                all_automation_targets.extend(reflection.next_automation_targets)
                all_promotion_candidates.extend(reflection.promotion_candidates)

        # Compute aggregate KPIs if not provided
        if aggregate_kpis is None:
            aggregate_kpis = self._compute_aggregate_kpis(stories_completed)

        # Generate summary
        what_changed = self._generate_macro_summary(
            period, stories_completed, all_failures, all_root_causes
        )

        return self.storage.store_macro_reflection(
            period=period,
            what_changed=what_changed,
            kpi_snapshot=aggregate_kpis,
            failures_observed=all_failures,
            root_causes=all_root_causes,
            next_automation_targets=all_automation_targets,
            promotion_candidates=all_promotion_candidates,
        )

    def _compute_aggregate_kpis(self, story_ids: list[str]) -> KPISnapshot:
        """Compute aggregate KPIs from story reflections."""
        total_coverage = 0.0
        total_ci_pass_rate = 0.0
        total_cycle_time = 0.0
        total_tests = 0
        count = 0

        for story_id in story_ids:
            reflection = self.storage.get_meso_reflection(story_id)
            if reflection and reflection.kpi_snapshot:
                count += 1
                if reflection.kpi_snapshot.coverage:
                    total_coverage += reflection.kpi_snapshot.coverage
                if reflection.kpi_snapshot.ci_pass_rate:
                    total_ci_pass_rate += reflection.kpi_snapshot.ci_pass_rate
                if reflection.kpi_snapshot.cycle_time_hours:
                    total_cycle_time += reflection.kpi_snapshot.cycle_time_hours
                if reflection.kpi_snapshot.test_count:
                    total_tests += reflection.kpi_snapshot.test_count

        if count == 0:
            return KPISnapshot()

        return KPISnapshot(
            coverage=total_coverage / count,
            ci_pass_rate=total_ci_pass_rate / count,
            cycle_time_hours=total_cycle_time / count,
            test_count=total_tests,
        )

    def _generate_macro_summary(
        self,
        period: str,
        stories_completed: list[str],
        failures: list[FailureObservation],
        root_causes: list[RootCause],
    ) -> str:
        """Generate summary text for macro-reflection."""
        lines = [
            f"Macro-reflection for {period} period",
            "",
            f"Stories completed: {len(stories_completed)}",
        ]

        if stories_completed:
            lines.append("Story IDs: " + ", ".join(stories_completed))

        lines.append("")
        lines.append(f"Failures observed: {len(failures)}")
        lines.append(f"Root causes identified: {len(root_causes)}")

        if root_causes:
            lines.append("")
            lines.append("Top root cause categories:")
            categories = {}
            for rc in root_causes:
                categories[rc.category.value] = categories.get(rc.category.value, 0) + 1
            for cat, count in sorted(categories.items(), key=lambda x: -x[1])[:3]:
                lines.append(f"  - {cat}: {count}")

        return "\n".join(lines)
