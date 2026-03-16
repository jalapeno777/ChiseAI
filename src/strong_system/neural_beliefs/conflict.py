"""Belief Conflict Resolver for detecting and resolving contradictory beliefs.

Provides detection of belief conflicts, resolution strategies, and
conflict history tracking.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum, auto
from typing import TYPE_CHECKING, Any

import numpy as np
from src.strong_system.belief_embeddings import ValidationError

if TYPE_CHECKING:
    from .belief import NeuralBelief


class ConflictStrategy(Enum):
    """Strategy for resolving belief conflicts.

    MERGE: Combine beliefs using weighted average
    PRIORITIZE: Keep the belief with higher confidence/evidence
    CONTEXTUALIZE: Keep both beliefs but add context to differentiate
    REJECT: Reject the new belief (keep existing)
    FLAG: Flag for manual review without automatic resolution
    """

    MERGE = auto()
    PRIORITIZE = auto()
    CONTEXTUALIZE = auto()
    REJECT = auto()
    FLAG = auto()


@dataclass
class ConflictResolution:
    """Record of a conflict resolution.

    Attributes:
        conflict_id: Unique identifier for this conflict
        belief_ids: IDs of beliefs involved in the conflict
        strategy: Strategy used to resolve the conflict
        winner_id: ID of the winning belief (if applicable)
        score: Conflict severity score (0-1)
        resolution_time: When the conflict was resolved
        metadata: Additional resolution metadata
    """

    conflict_id: str
    belief_ids: list[str]
    strategy: ConflictStrategy
    score: float
    resolution_time: datetime = field(default_factory=lambda: datetime.now(UTC))
    winner_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert resolution to dictionary."""
        return {
            "conflict_id": self.conflict_id,
            "belief_ids": self.belief_ids,
            "strategy": self.strategy.name,
            "winner_id": self.winner_id,
            "score": self.score,
            "resolution_time": self.resolution_time.isoformat(),
            "metadata": self.metadata,
        }


@dataclass
class ConflictConfig:
    """Configuration for conflict detection and resolution.

    Attributes:
        similarity_threshold: Threshold for considering beliefs similar (0-1)
        conflict_threshold: Threshold for considering beliefs conflicting (0-1)
        default_strategy: Default resolution strategy
        min_confidence_diff: Minimum confidence difference for PRIORITIZE
        merge_weight_fn: Function to compute merge weights
        enable_history: Whether to track resolution history
    """

    similarity_threshold: float = 0.8
    conflict_threshold: float = 0.3
    default_strategy: ConflictStrategy = ConflictStrategy.MERGE
    min_confidence_diff: float = 0.2
    merge_weight_fn: Callable[[NeuralBelief], float] | None = None
    enable_history: bool = True

    def __post_init__(self) -> None:
        """Validate configuration."""
        if not 0 <= self.similarity_threshold <= 1:
            raise ValidationError(
                f"similarity_threshold must be in [0, 1], got {self.similarity_threshold}"
            )
        if not 0 <= self.conflict_threshold <= 1:
            raise ValidationError(
                f"conflict_threshold must be in [0, 1], got {self.conflict_threshold}"
            )
        if self.similarity_threshold <= self.conflict_threshold:
            raise ValidationError(
                f"similarity_threshold ({self.similarity_threshold}) must be greater than "
                f"conflict_threshold ({self.conflict_threshold})"
            )


class BeliefConflictResolver:
    """Resolver for detecting and resolving belief conflicts.

    Detects contradictory beliefs based on vector similarity and confidence,
    applies resolution strategies, and tracks resolution history.

    Attributes:
        config: Conflict resolution configuration
        resolution_history: History of conflict resolutions
        pending_conflicts: Conflicts awaiting resolution
    """

    def __init__(self, config: ConflictConfig | None = None):
        """Initialize the conflict resolver.

        Args:
            config: Configuration (uses defaults if None)
        """
        self.config = config or ConflictConfig()
        self.resolution_history: list[ConflictResolution] = []
        self.pending_conflicts: list[dict[str, Any]] = []
        self._conflict_counter: int = 0

    def detect_conflict(
        self, belief1: NeuralBelief, belief2: NeuralBelief
    ) -> dict[str, Any] | None:
        """Detect if two beliefs are in conflict.

        Conflicts are detected when beliefs are similar (high cosine similarity)
        but have significant vector differences, suggesting contradiction.

        Args:
            belief1: First belief to compare
            belief2: Second belief to compare

        Returns:
            Conflict info dict if conflict detected, None otherwise
        """
        # Check dimension compatibility
        if belief1.dimension != belief2.dimension:
            return None

        # Compute similarity
        try:
            similarity = belief1.cosine_similarity(belief2)
        except ValidationError:
            return None

        # Beliefs must be similar in direction to be conflicting
        # (orthogonal beliefs aren't conflicting, they're independent)
        if similarity < self.config.conflict_threshold:
            return None

        # Compute conflict score based on:
        # 1. How similar the beliefs are (domain overlap)
        # 2. How different their vectors are (contradiction)
        # 3. Confidence levels (high confidence contradictions are worse)

        # Vector difference (normalized)
        distance = belief1.euclidean_distance(belief2)
        max_distance = 2.0  # Maximum Euclidean distance for unit vectors
        normalized_distance = min(distance / max_distance, 1.0)

        # Confidence factor (high confidence conflicts are more severe)
        avg_confidence = (belief1.confidence + belief2.confidence) / 2

        # Conflict score: high when beliefs are similar but vectors differ
        # and both have high confidence
        conflict_score = similarity * normalized_distance * avg_confidence

        # Only report if above threshold
        if conflict_score < 0.1:  # Minimum conflict threshold
            return None

        return {
            "belief1_id": belief1.belief_id,
            "belief2_id": belief2.belief_id,
            "similarity": similarity,
            "distance": distance,
            "conflict_score": conflict_score,
            "confidence1": belief1.confidence,
            "confidence2": belief2.confidence,
        }

    def find_conflicts(
        self,
        belief: NeuralBelief,
        candidates: list[NeuralBelief],
    ) -> list[dict[str, Any]]:
        """Find all conflicts between a belief and candidate beliefs.

        Args:
            belief: The belief to check for conflicts
            candidates: List of beliefs to check against

        Returns:
            List of conflict info dicts
        """
        conflicts = []
        for candidate in candidates:
            if candidate.belief_id == belief.belief_id:
                continue

            conflict = self.detect_conflict(belief, candidate)
            if conflict is not None:
                conflicts.append(conflict)

        # Sort by conflict score (highest first)
        conflicts.sort(key=lambda x: x["conflict_score"], reverse=True)
        return conflicts

    def resolve_conflict(
        self,
        belief1: NeuralBelief,
        belief2: NeuralBelief,
        strategy: ConflictStrategy | None = None,
    ) -> ConflictResolution:
        """Resolve a conflict between two beliefs.

        Args:
            belief1: First conflicting belief
            belief2: Second conflicting belief
            strategy: Resolution strategy (uses default if None)

        Returns:
            ConflictResolution record
        """
        strategy = strategy or self.config.default_strategy
        self._conflict_counter += 1

        # Detect conflict details
        conflict_info = self.detect_conflict(belief1, belief2)
        if conflict_info is None:
            # No actual conflict, create null resolution
            return ConflictResolution(
                conflict_id=f"conflict_{self._conflict_counter}",
                belief_ids=[belief1.belief_id, belief2.belief_id],
                strategy=strategy,
                score=0.0,
                metadata={"reason": "no_conflict_detected"},
            )

        score = conflict_info["conflict_score"]

        # Apply resolution strategy
        if strategy == ConflictStrategy.MERGE:
            winner_id = self._resolve_merge(belief1, belief2, conflict_info)
        elif strategy == ConflictStrategy.PRIORITIZE:
            winner_id = self._resolve_prioritize(belief1, belief2, conflict_info)
        elif strategy == ConflictStrategy.CONTEXTUALIZE:
            winner_id = self._resolve_contextualize(belief1, belief2, conflict_info)
        elif strategy == ConflictStrategy.REJECT:
            winner_id = belief1.belief_id  # Keep existing (belief1)
        elif strategy == ConflictStrategy.FLAG:
            winner_id = None  # No automatic resolution
        else:
            raise ValidationError(f"Unknown conflict strategy: {strategy}")

        resolution = ConflictResolution(
            conflict_id=f"conflict_{self._conflict_counter}",
            belief_ids=[belief1.belief_id, belief2.belief_id],
            strategy=strategy,
            score=score,
            winner_id=winner_id,
            metadata={
                "conflict_info": conflict_info,
                "confidence1": belief1.confidence,
                "confidence2": belief2.confidence,
            },
        )

        if self.config.enable_history:
            self.resolution_history.append(resolution)

        return resolution

    def _resolve_merge(
        self,
        belief1: NeuralBelief,
        belief2: NeuralBelief,
        conflict_info: dict[str, Any],
    ) -> str:
        """Merge two beliefs using weighted average.

        Args:
            belief1: First belief
            belief2: Second belief
            conflict_info: Conflict detection results

        Returns:
            ID of the merged belief (belief1, which is updated)
        """
        # Compute weights based on confidence
        conf1 = belief1.confidence
        conf2 = belief2.confidence

        # Apply custom weight function if configured
        if self.config.merge_weight_fn is not None:
            weight1 = self.config.merge_weight_fn(belief1)
            weight2 = self.config.merge_weight_fn(belief2)
        else:
            weight1 = conf1
            weight2 = conf2

        total_weight = weight1 + weight2
        if total_weight < 1e-10:
            # Equal weights if both have near-zero confidence
            w1 = w2 = 0.5
        else:
            w1 = weight1 / total_weight
            w2 = weight2 / total_weight

        # Merge vectors
        merged_vector = w1 * belief1.vector + w2 * belief2.vector

        # Merge confidence (higher confidence after merge due to consensus)
        merged_confidence = (
            max(conf1, conf2) + (1 - max(conf1, conf2)) * min(conf1, conf2) * 0.5
        )
        merged_confidence = min(merged_confidence, 1.0)

        # Update belief1 with merged values
        belief1.vector = merged_vector
        belief1.confidence = merged_confidence

        return belief1.belief_id

    def _resolve_prioritize(
        self,
        belief1: NeuralBelief,
        belief2: NeuralBelief,
        conflict_info: dict[str, Any],
    ) -> str:
        """Keep the belief with higher confidence.

        Args:
            belief1: First belief
            belief2: Second belief
            conflict_info: Conflict detection results

        Returns:
            ID of the winning belief
        """
        conf1 = belief1.confidence
        conf2 = belief2.confidence

        # Check if confidence difference is significant
        if abs(conf1 - conf2) < self.config.min_confidence_diff:
            # Too close to call, fall back to merge
            return self._resolve_merge(belief1, belief2, conflict_info)

        if conf1 >= conf2:
            return belief1.belief_id
        else:
            # Copy belief2 values to belief1
            belief1.vector = belief2.vector.copy()
            belief1.confidence = conf2
            return belief1.belief_id

    def _resolve_contextualize(
        self,
        belief1: NeuralBelief,
        belief2: NeuralBelief,
        conflict_info: dict[str, Any],
    ) -> str:
        """Keep both beliefs but add context to differentiate.

        Args:
            belief1: First belief
            belief2: Second belief
            conflict_info: Conflict detection results

        Returns:
            ID of the primary belief
        """
        # Add context to metadata indicating these are contextual variants
        belief1.metadata.custom["contextual_variant"] = "primary"
        belief1.metadata.custom["conflict_partner"] = belief2.belief_id

        belief2.metadata.custom["contextual_variant"] = "secondary"
        belief2.metadata.custom["conflict_partner"] = belief1.belief_id

        # Keep both beliefs (no vector modification)
        # Return belief1 as primary
        return belief1.belief_id

    def batch_resolve(
        self,
        beliefs: list[NeuralBelief],
        strategy: ConflictStrategy | None = None,
    ) -> list[ConflictResolution]:
        """Resolve all conflicts in a batch of beliefs.

        Args:
            beliefs: List of beliefs to check for conflicts
            strategy: Resolution strategy (uses default if None)

        Returns:
            List of ConflictResolution records
        """
        resolutions = []
        resolved_pairs: set[tuple[str, str]] = set()

        for i, belief1 in enumerate(beliefs):
            for belief2 in beliefs[i + 1 :]:
                # Skip if already resolved this pair
                pair = tuple(sorted([belief1.belief_id, belief2.belief_id]))
                if pair in resolved_pairs:
                    continue

                conflict = self.detect_conflict(belief1, belief2)
                if conflict is not None:
                    resolution = self.resolve_conflict(belief1, belief2, strategy)
                    resolutions.append(resolution)
                    resolved_pairs.add(pair)

        return resolutions

    def get_conflict_statistics(self) -> dict[str, Any]:
        """Get statistics about conflict resolution history."""
        if not self.resolution_history:
            return {
                "total_conflicts": 0,
                "avg_score": 0.0,
                "strategy_counts": {},
            }

        strategy_counts = {}
        for res in self.resolution_history:
            strategy_name = res.strategy.name
            strategy_counts[strategy_name] = strategy_counts.get(strategy_name, 0) + 1

        return {
            "total_conflicts": len(self.resolution_history),
            "avg_score": np.mean([r.score for r in self.resolution_history]),
            "max_score": max([r.score for r in self.resolution_history]),
            "strategy_counts": strategy_counts,
        }

    def clear_history(self) -> None:
        """Clear resolution history."""
        self.resolution_history.clear()
        self._conflict_counter = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert resolver to dictionary."""
        return {
            "config": {
                "similarity_threshold": self.config.similarity_threshold,
                "conflict_threshold": self.config.conflict_threshold,
                "default_strategy": self.config.default_strategy.name,
                "min_confidence_diff": self.config.min_confidence_diff,
                "enable_history": self.config.enable_history,
            },
            "resolution_history": [r.to_dict() for r in self.resolution_history],
            "statistics": self.get_conflict_statistics(),
        }
