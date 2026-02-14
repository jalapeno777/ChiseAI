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
from src.brain.rollback_handler import (
    PostmortemReport,
    RollbackHandler,
    RollbackResult,
    RollbackStep,
    RollbackTrigger,
)
from src.brain.promotion_packet import (
    # Enums
    PacketStatus,
    ApprovalStatus,
    # Dataclasses
    ApprovalSignature,
    PromotionPacket,
    # Generator
    PacketGenerator,
    # Export functions
    export_to_markdown,
    export_to_json,
    # Validation functions
    is_complete,
    get_missing_fields,
    # Workflow functions
    add_signature,
    is_approved,
)

__all__ = [
    "BatchEvaluator",
    "EvaluationPersistence",
    "EvaluationResult",
    "EvaluationStatus",
    "Leaderboard",
    "LeaderboardConfig",
    "run_batch_evaluation",
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
]
