"""Meta-learning system for STRONG.

Provides meta-learning capabilities including MAML (Model-Agnostic Meta-Learning)
for fast adaptation to new tasks with few examples.

Example:
    >>> from src.strong_system.meta_learning import MetaLearningController
    >>> controller = MetaLearningController()
    >>> # Create task distribution
    >>> controller.add_task("classification", task_data)
    >>> # Sample episodes for meta-training
    >>> episodes = controller.sample_episodes(n_episodes=10, k_shot=5)
"""

from __future__ import annotations

from .controller import Episode, MetaLearningController, Task, TaskDistribution
from .models import LinearModel, MAML, MetaModel, ParameterStore, Reptile
from .training import EpisodeTrainer, MetaTrainingLoop, TrainingConfig, TrainingMetrics
from .utils import (
    TaskSampler,
    EpisodeBatcher,
    compute_accuracy,
    compute_meta_metrics,
    compute_adaptation_gain,
    create_sinusoid_task,
    create_classification_task,
)

__all__ = [
    # Controller
    "MetaLearningController",
    "Task",
    "TaskDistribution",
    "Episode",
    # Models
    "ParameterStore",
    "LinearModel",
    "MetaModel",
    "MAML",
    "Reptile",
    # Training
    "MetaTrainingLoop",
    "EpisodeTrainer",
    "TrainingConfig",
    "TrainingMetrics",
    # Utils
    "TaskSampler",
    "EpisodeBatcher",
    "compute_accuracy",
    "compute_meta_metrics",
    "compute_adaptation_gain",
    "create_sinusoid_task",
    "create_classification_task",
]
