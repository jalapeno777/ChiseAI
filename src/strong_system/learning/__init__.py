"""Learning module for gradient-based belief updates.

Provides gradient computation, backpropagation, checkpointing, and learning rate
scheduling for training neural belief networks.

Modules:
    gradient_engine: Core gradient computation for belief operations
    backprop: Backpropagation through deep belief networks
    checkpoint: Gradient checkpoint management
    scheduler: Learning rate scheduling

Example:
    >>> from src.strong_system.learning import (
    ...     GradientEngine,
    ...     BeliefBackpropagator,
    ...     GradientCheckpointManager,
    ...     StepLR,
    ... )
"""

from src.strong_system.learning.backprop import (
    BackpropConfig,
    BackpropStats,
    BeliefBackpropagator,
    CheckpointManager,
    DeepBeliefTrainer,
)
from src.strong_system.learning.checkpoint import (
    Checkpoint,
    CheckpointFormat,
    CheckpointMetadata,
    GradientCheckpointManager,
    create_checkpoint_manager_from_optimizer,
)
from src.strong_system.learning.gradient_engine import (
    BeliefGradientFunction,
    GradientConfig,
    GradientEngine,
    GradientStats,
)
from src.strong_system.learning.scheduler import (
    ConstantLR,
    CosineAnnealingLR,
    CyclicalLR,
    ExponentialLR,
    LRScheduler,
    MetaLearningScheduler,
    ReduceLROnPlateau,
    SchedulerConfig,
    SchedulerState,
    StepLR,
    WarmupScheduler,
    create_scheduler,
)

__all__ = [
    # Gradient Engine
    "GradientEngine",
    "GradientConfig",
    "GradientStats",
    "BeliefGradientFunction",
    # Backpropagation
    "BeliefBackpropagator",
    "BackpropConfig",
    "BackpropStats",
    "CheckpointManager",
    "DeepBeliefTrainer",
    # Checkpointing
    "GradientCheckpointManager",
    "Checkpoint",
    "CheckpointMetadata",
    "CheckpointFormat",
    "create_checkpoint_manager_from_optimizer",
    # Scheduling
    "LRScheduler",
    "ConstantLR",
    "StepLR",
    "ExponentialLR",
    "CosineAnnealingLR",
    "ReduceLROnPlateau",
    "CyclicalLR",
    "WarmupScheduler",
    "MetaLearningScheduler",
    "SchedulerConfig",
    "SchedulerState",
    "create_scheduler",
]
