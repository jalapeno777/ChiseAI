"""Contracts for autonomous cognition cycles."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class CycleResult:
    """Result bundle for a full autonomous cognition cycle."""

    run_id: str
    started_at: str
    completed_at: str
    status: str
    self_assessment_status: str
    belief_conflicts: int = 0
    belief_revisions: int = 0
    experiments_run: int = 0
    promotions: int = 0
    rejections: int = 0
    autonomy_level_before: str = "supervised"
    autonomy_level_after: str = "supervised"
    constitution_violations: int = 0
    artifact_paths: dict[str, str] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "status": self.status,
            "self_assessment_status": self.self_assessment_status,
            "belief_conflicts": self.belief_conflicts,
            "belief_revisions": self.belief_revisions,
            "experiments_run": self.experiments_run,
            "promotions": self.promotions,
            "rejections": self.rejections,
            "autonomy_level_before": self.autonomy_level_before,
            "autonomy_level_after": self.autonomy_level_after,
            "constitution_violations": self.constitution_violations,
            "artifact_paths": self.artifact_paths,
            "metrics": self.metrics,
        }

    @classmethod
    def create(cls, run_id: str) -> CycleResult:
        now = datetime.now(UTC).isoformat()
        return cls(
            run_id=run_id,
            started_at=now,
            completed_at=now,
            status="running",
            self_assessment_status="unknown",
        )
