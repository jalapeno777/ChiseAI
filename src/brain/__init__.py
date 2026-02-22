"""Brain evaluation and management package.

This package provides tools for evaluating brain versions in parallel,
ranking them by weighted objectives, and managing promotion decisions.
"""

from src.brain.batch_evaluator import (
    BatchEvaluator,
    EvaluationPersistence,
    EvaluationResult,
    EvaluationStatus,
    Leaderboard,
    LeaderboardConfig,
    run_batch_evaluation,
)
from src.brain.promotion_packet import (
    # Dataclasses
    ApprovalSignature,
    ApprovalStatus,
    # Generator
    PacketGenerator,
    # Enums
    PacketStatus,
    PromotionPacket,
    # Workflow functions
    add_signature,
    export_to_json,
    # Export functions
    export_to_markdown,
    get_missing_fields,
    is_approved,
    # Validation functions
    is_complete,
)
from src.brain.rollback_handler import (
    PostmortemReport,
    RollbackHandler,
    RollbackResult,
    RollbackStep,
    RollbackTrigger,
)
from src.brain.shadow_testing import (
    LatencyStatistics,
    ShadowTestConfig,
    ShadowTester,
    ShadowTestResult,
    run_shadow_test,
)
from src.brain.version import (
    BrainVersion,
    InvalidVersionError,
    compare_versions,
    increment_major,
    increment_minor,
    increment_patch,
    validate_version,
)

__all__ = [
    # Version
    "BrainVersion",
    "InvalidVersionError",
    "compare_versions",
    "increment_major",
    "increment_minor",
    "increment_patch",
    "validate_version",
    # Batch Evaluator
    "BatchEvaluator",
    "EvaluationPersistence",
    "EvaluationResult",
    "EvaluationStatus",
    "Leaderboard",
    "LeaderboardConfig",
    "run_batch_evaluation",
    # Rollback Handler
    "PostmortemReport",
    "RollbackHandler",
    "RollbackResult",
    "RollbackStep",
    "RollbackTrigger",
    # Promotion Packet
    "PacketStatus",
    "ApprovalStatus",
    "ApprovalSignature",
    "PromotionPacket",
    "PacketGenerator",
    "export_to_markdown",
    "export_to_json",
    "is_complete",
    "get_missing_fields",
    "add_signature",
    "is_approved",
    # Shadow Testing
    "LatencyStatistics",
    "ShadowTestConfig",
    "ShadowTestResult",
    "ShadowTester",
    "run_shadow_test",
]
