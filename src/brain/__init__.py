"""Brain CI/CD Pipeline - Version and Evaluate.

This package provides the Brain CI/CD pipeline for ChiseAI, including:
- Version management (semantic versioning)
- Evaluation framework (batch evaluation for 3-5 versions)
- Shadow testing
- Promotion gating with human approval packets
- Rollback capabilities with safety checks

Usage:
    from brain import BrainVersion, VersionManager
    from brain import BrainEvaluator, BatchEvaluator
    from brain import ShadowTester
    from brain import PromotionGate, PromotionPacket
    from brain import RollbackManager, RollbackHandler

Stories Implemented:
- ST-CHISE-002: Brain Evaluation Framework - Batching + BrainEval
- ST-CHISE-003: Brain Promotion Packet - Evidence + Rollback
- ST-CHISE-005: Chise v1 Rollback Plan - Safety + Rollback Steps
"""

# Existing modules
from brain.evaluation import BrainEvaluator, EvaluationResult, EvaluationMetrics
from brain.promotion import PromotionGate, PromotionPacket
from brain.shadow_tester import ShadowTestResult, ShadowTester
from brain.versioning import BrainVersion, VersionManager

# New ST-CHISE-002: Batch Evaluation
from brain.batch_evaluator import (
    BatchEvaluator,
    BatchEvaluationConfig,
    EvaluationStatus as BatchEvaluationStatus,
    Leaderboard,
)

# New ST-CHISE-003: Promotion Packet
from brain.promotion_packet import (
    ApprovalRecord,
    PacketStatus,
    PromotionPacket as NewPromotionPacket,
    PromotionPacketGenerator,
    RollbackPlan,
    RollbackStep,
    SafetyCheck,
    SafetyCheckStatus,
)

# New ST-CHISE-005: Rollback Handler
from brain.rollback_handler import (
    RollbackHandler,
    RollbackOutcome,
    RollbackStatus,
    RollbackStepResult,
    RollbackTrigger,
    SafetyCheckResult,
    SystemState,
)

__all__ = [
    # Versioning
    "BrainVersion",
    "VersionManager",
    # Evaluation (existing)
    "BrainEvaluator",
    "EvaluationResult",
    "EvaluationMetrics",
    # Evaluation (ST-CHISE-002 - new batch evaluation)
    "BatchEvaluator",
    "BatchEvaluationConfig",
    "BatchEvaluationStatus",
    "Leaderboard",
    # Shadow Testing
    "ShadowTester",
    "ShadowTestResult",
    # Promotion (existing)
    "PromotionGate",
    "PromotionPacket",
    # Promotion (ST-CHISE-003 - new packet generator)
    "NewPromotionPacket",
    "PromotionPacketGenerator",
    "PacketStatus",
    "ApprovalRecord",
    "RollbackPlan",
    "RollbackStep",
    "SafetyCheck",
    "SafetyCheckStatus",
    # Rollback (ST-CHISE-005 - new rollback handler)
    "RollbackHandler",
    "RollbackOutcome",
    "RollbackStatus",
    "RollbackStepResult",
    "RollbackTrigger",
    "SafetyCheckResult",
    "SystemState",
]
