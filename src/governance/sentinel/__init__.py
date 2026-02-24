"""
Task Decomposition Sentinel Module.

This module provides task size validation and decomposition enforcement
to prevent oversized tasks from being committed without proper approval.

Features:
- Task size validation against constitution bounds
- Dependency validation with circular dependency detection
- Scope conflict detection for parallel execution
- Redis ownership integration
- Approval workflow for oversized tasks

Feature Flag: chise:feature_flags:governance:task_sentinel_active

Story: ST-GOV-003
"""

from .approval_workflow import (
    ApprovalRequest,
    ApprovalResult,
    ApprovalStatus,
    ApprovalWorkflow,
)
from .conflict_detector import (
    Conflict,
    ConflictCheckResult,
    ConflictDetector,
    ConflictSeverity,
    ConflictType,
    ScopeDeclaration,
)
from .dependency_checker import (
    Dependency,
    DependencyChecker,
    DependencyCheckResult,
    DependencyDeclaration,
    DependencyType,
)
from .task_sentinel import (
    SentinelConfig,
    TaskInfo,
    TaskSentinel,
    ValidationResult,
)

__all__ = [
    # Core sentinel
    "TaskSentinel",
    "SentinelConfig",
    "TaskInfo",
    "ValidationResult",
    # Dependencies
    "DependencyChecker",
    "DependencyDeclaration",
    "DependencyCheckResult",
    "Dependency",
    "DependencyType",
    # Conflicts
    "ConflictDetector",
    "ScopeDeclaration",
    "ConflictCheckResult",
    "Conflict",
    "ConflictType",
    "ConflictSeverity",
    # Approvals
    "ApprovalWorkflow",
    "ApprovalRequest",
    "ApprovalResult",
    "ApprovalStatus",
]
