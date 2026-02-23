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

from .task_sentinel import (
    TaskSentinel,
    SentinelConfig,
    TaskInfo,
    ValidationResult,
)
from .dependency_checker import (
    DependencyChecker,
    DependencyDeclaration,
    DependencyCheckResult,
    Dependency,
    DependencyType,
)
from .conflict_detector import (
    ConflictDetector,
    ScopeDeclaration,
    ConflictCheckResult,
    Conflict,
    ConflictType,
    ConflictSeverity,
)
from .approval_workflow import (
    ApprovalWorkflow,
    ApprovalRequest,
    ApprovalResult,
    ApprovalStatus,
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
