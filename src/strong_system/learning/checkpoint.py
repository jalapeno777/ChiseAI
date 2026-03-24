"""Gradient checkpoint management for memory-efficient learning.

Provides the CheckpointManager class for managing gradient checkpoints with
integration to GraphOptimizer from STRONG-001-A-S3. Supports memory-efficient
checkpointing strategies and checkpoint persistence.

Example:
    >>> from src.strong_system.learning import GradientCheckpointManager
    >>> from src.strong_system.computational_graph import Graph, Node
    >>> import numpy as np
    >>>
    >>> # Create graph and manager
    >>> graph = Graph()
    >>> manager = GradientCheckpointManager()
    >>>
    >>> # Add checkpoints
    >>> for i in range(10):
    ...     node = Node(np.random.randn(100), name=f"layer_{i}")
    ...     manager.add_checkpoint(node, layer_id=i)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from src.strong_system.computational_graph.node import Node
from src.strong_system.computational_graph.optimizer import (
    CheckpointStrategy,
    GraphOptimizer,
)

if TYPE_CHECKING:
    pass


class CheckpointFormat(Enum):
    """Format for checkpoint serialization."""

    NUMPY = auto()  # NumPy .npz format
    JSON = auto()  # JSON with base64 encoding
    HDF5 = auto()  # HDF5 format (if available)


@dataclass
class CheckpointMetadata:
    """Metadata for a gradient checkpoint.

    Attributes:
        layer_id: Identifier for the layer/checkpoint
        step_number: Training step when checkpoint was created
        timestamp: ISO format timestamp
        shape: Shape of the checkpointed data
        dtype: Data type of the checkpointed data
        memory_bytes: Memory size in bytes
        description: Optional description
    """

    layer_id: str
    step_number: int = 0
    timestamp: str = ""
    shape: tuple[int, ...] = field(default_factory=tuple)
    dtype: str = "float64"
    memory_bytes: int = 0
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert metadata to dictionary."""
        return {
            "layer_id": self.layer_id,
            "step_number": self.step_number,
            "timestamp": self.timestamp,
            "shape": self.shape,
            "dtype": self.dtype,
            "memory_bytes": self.memory_bytes,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CheckpointMetadata:
        """Create metadata from dictionary."""
        return cls(
            layer_id=data["layer_id"],
            step_number=data.get("step_number", 0),
            timestamp=data.get("timestamp", ""),
            shape=tuple(data.get("shape", [])),
            dtype=data.get("dtype", "float64"),
            memory_bytes=data.get("memory_bytes", 0),
            description=data.get("description", ""),
        )


@dataclass
class Checkpoint:
    """A single gradient checkpoint.

    Attributes:
        data: Checkpointed numpy array
        metadata: Checkpoint metadata
    """

    data: np.ndarray
    metadata: CheckpointMetadata

    def to_dict(self) -> dict[str, Any]:
        """Convert checkpoint to dictionary."""
        return {
            "data": self.data.tobytes(),
            "metadata": self.metadata.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Checkpoint:
        """Create checkpoint from dictionary."""
        metadata = CheckpointMetadata.from_dict(data["metadata"])
        array_data = np.frombuffer(
            data["data"], dtype=np.dtype(metadata.dtype)
        ).reshape(metadata.shape)
        return cls(data=array_data, metadata=metadata)


class GradientCheckpointManager:
    """Manager for gradient checkpoints with GraphOptimizer integration.

    Provides comprehensive checkpoint management including:
    - Checkpoint creation and storage
    - Memory-efficient checkpointing strategies
    - Integration with GraphOptimizer
    - Checkpoint persistence (save/load)
    - Memory usage tracking

    Attributes:
        checkpoints: Dictionary of stored checkpoints
        strategy: Checkpoint strategy (from GraphOptimizer)
        memory_limit_mb: Memory limit for checkpoints
        current_step: Current training step
    """

    def __init__(
        self,
        strategy: CheckpointStrategy = CheckpointStrategy.SELECTIVE,
        memory_limit_mb: float = 1024.0,
        checkpoint_interval: int = 5,
    ):
        """Initialize the checkpoint manager.

        Args:
            strategy: Checkpointing strategy
            memory_limit_mb: Memory limit in MB
            checkpoint_interval: Layers/steps between checkpoints
        """
        self.checkpoints: dict[str, Checkpoint] = {}
        self.strategy = strategy
        self.memory_limit_mb = memory_limit_mb
        self.checkpoint_interval = checkpoint_interval
        self.current_step = 0
        self._memory_used_bytes = 0
        self._optimizer: GraphOptimizer | None = None

    def set_optimizer(self, optimizer: GraphOptimizer) -> None:
        """Set the GraphOptimizer for integration.

        Args:
            optimizer: GraphOptimizer instance
        """
        self._optimizer = optimizer

    def should_checkpoint(
        self,
        layer_id: str,
        layer_idx: int | None = None,
        node: Node | None = None,
    ) -> bool:
        """Determine if a checkpoint should be created.

        Args:
            layer_id: Identifier for the layer
            layer_idx: Optional layer index
            node: Optional node to check

        Returns:
            True if checkpoint should be created
        """
        if self.strategy == CheckpointStrategy.NONE:
            return False

        if self.strategy == CheckpointStrategy.ALL:
            return True

        if self.strategy == CheckpointStrategy.SELECTIVE:
            # Checkpoint based on interval and heuristics
            if layer_idx is not None:
                if layer_idx % self.checkpoint_interval == 0:
                    return True

            # Checkpoint nodes with high fan-out
            return bool(node is not None and len(node.children) >= 3)

        if self.strategy == CheckpointStrategy.MEMORY_BOUND:
            # Checkpoint when memory would exceed limit
            current_mb = self.get_memory_usage_mb()
            if current_mb >= self.memory_limit_mb * 0.8:
                return True

        return False

    def add_checkpoint(
        self,
        node: Node,
        layer_id: str,
        description: str = "",
        step_number: int | None = None,
    ) -> Checkpoint | None:
        """Add a checkpoint for a node.

        Args:
            node: Node to checkpoint
            layer_id: Identifier for this checkpoint
            description: Optional description
            step_number: Optional step number (uses current if None)

        Returns:
            Created checkpoint or None if not checkpointed
        """
        from datetime import UTC, datetime

        step = step_number if step_number is not None else self.current_step

        # Create metadata
        metadata = CheckpointMetadata(
            layer_id=layer_id,
            step_number=step,
            timestamp=datetime.now(UTC).isoformat(),
            shape=node.value.shape,
            dtype=str(node.value.dtype),
            memory_bytes=node.value.nbytes,
            description=description,
        )

        # Create checkpoint
        checkpoint = Checkpoint(
            data=node.value.copy(),
            metadata=metadata,
        )

        # Check memory limit and evict oldest checkpoints until we have room
        new_memory_mb = metadata.memory_bytes / (1024 * 1024)
        while (
            self.get_memory_usage_mb() + new_memory_mb > self.memory_limit_mb
            and self.checkpoints
        ):
            self._evict_oldest_checkpoint()

        # Store checkpoint
        self.checkpoints[layer_id] = checkpoint
        self._memory_used_bytes += metadata.memory_bytes

        return checkpoint

    def get_checkpoint(self, layer_id: str) -> Checkpoint | None:
        """Get a checkpoint by layer ID.

        Args:
            layer_id: Identifier for the checkpoint

        Returns:
            Checkpoint or None if not found
        """
        return self.checkpoints.get(layer_id)

    def restore_checkpoint(self, layer_id: str, node: Node) -> bool:
        """Restore a checkpoint to a node.

        Args:
            layer_id: Identifier for the checkpoint
            node: Node to restore to

        Returns:
            True if restored successfully
        """
        checkpoint = self.get_checkpoint(layer_id)
        if checkpoint is None:
            return False

        node.value = checkpoint.data.copy()
        return True

    def remove_checkpoint(self, layer_id: str) -> bool:
        """Remove a checkpoint.

        Args:
            layer_id: Identifier for the checkpoint

        Returns:
            True if removed successfully
        """
        if layer_id not in self.checkpoints:
            return False

        checkpoint = self.checkpoints.pop(layer_id)
        self._memory_used_bytes -= checkpoint.metadata.memory_bytes

        return True

    def clear(self) -> None:
        """Clear all checkpoints."""
        self.checkpoints.clear()
        self._memory_used_bytes = 0

    def get_memory_usage_mb(self) -> float:
        """Get current memory usage in MB."""
        return self._memory_used_bytes / (1024 * 1024)

    def get_checkpoint_count(self) -> int:
        """Get number of stored checkpoints."""
        return len(self.checkpoints)

    def get_checkpoint_ids(self) -> list[str]:
        """Get list of checkpoint IDs."""
        return list(self.checkpoints.keys())

    def save_checkpoints(
        self,
        path: str | Path,
        format: CheckpointFormat = CheckpointFormat.NUMPY,
    ) -> None:
        """Save checkpoints to disk.

        Args:
            path: Path to save to
            format: Serialization format
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        if format == CheckpointFormat.NUMPY:
            self._save_numpy(path)
        elif format == CheckpointFormat.JSON:
            self._save_json(path)
        else:
            raise ValueError(f"Unsupported format: {format}")

    def load_checkpoints(
        self,
        path: str | Path,
        format: CheckpointFormat = CheckpointFormat.NUMPY,
    ) -> None:
        """Load checkpoints from disk.

        Args:
            path: Path to load from
            format: Serialization format
        """
        path = Path(path)

        if not path.exists():
            raise FileNotFoundError(f"Checkpoint file not found: {path}")

        if format == CheckpointFormat.NUMPY:
            self._load_numpy(path)
        elif format == CheckpointFormat.JSON:
            self._load_json(path)
        else:
            raise ValueError(f"Unsupported format: {format}")

    def create_checkpoint_plan(
        self,
        num_layers: int,
        memory_budget_mb: float | None = None,
    ) -> list[int]:
        """Create a checkpointing plan for a network.

        Args:
            num_layers: Number of layers in the network
            memory_budget_mb: Optional memory budget

        Returns:
            List of layer indices to checkpoint
        """
        plan = []

        if self.strategy == CheckpointStrategy.NONE:
            return plan

        if self.strategy == CheckpointStrategy.ALL:
            return list(range(num_layers))

        if self.strategy in (
            CheckpointStrategy.SELECTIVE,
            CheckpointStrategy.MEMORY_BOUND,
        ):
            # Checkpoint at regular intervals
            for i in range(0, num_layers, self.checkpoint_interval):
                plan.append(i)

            # Always checkpoint first and last
            if 0 not in plan:
                plan.insert(0, 0)
            if (num_layers - 1) not in plan:
                plan.append(num_layers - 1)

        return sorted(plan)

    def step(self) -> None:
        """Increment the training step counter."""
        self.current_step += 1

    def get_stats(self) -> dict[str, Any]:
        """Get checkpoint manager statistics."""
        return {
            "checkpoint_count": len(self.checkpoints),
            "memory_usage_mb": self.get_memory_usage_mb(),
            "memory_limit_mb": self.memory_limit_mb,
            "strategy": self.strategy.name,
            "current_step": self.current_step,
            "checkpoint_ids": list(self.checkpoints.keys()),
        }

    def _evict_oldest_checkpoint(self) -> None:
        """Evict the oldest checkpoint to free memory."""
        if not self.checkpoints:
            return

        # Find oldest checkpoint by step number
        oldest_id = min(
            self.checkpoints.keys(),
            key=lambda k: self.checkpoints[k].metadata.step_number,
        )

        self.remove_checkpoint(oldest_id)

    def _save_numpy(self, path: Path) -> None:
        """Save checkpoints in NumPy format."""
        data_dict = {}
        metadata_dict = {}

        for layer_id, checkpoint in self.checkpoints.items():
            # Sanitize layer_id for numpy
            safe_id = layer_id.replace("/", "_").replace(".", "_")
            data_dict[f"data_{safe_id}"] = checkpoint.data
            metadata_dict[f"meta_{safe_id}"] = json.dumps(checkpoint.metadata.to_dict())

        np.savez_compressed(path, **data_dict, **metadata_dict)

    def _load_numpy(self, path: Path) -> None:
        """Load checkpoints from NumPy format."""
        data = np.load(path, allow_pickle=True)

        self.clear()

        # Find all data keys
        data_keys = [k for k in data if k.startswith("data_")]

        for data_key in data_keys:
            # Extract layer_id
            layer_id = data_key[5:]  # Remove "data_" prefix

            # Find corresponding metadata
            meta_key = f"meta_{layer_id}"
            if meta_key in data:
                metadata_dict = json.loads(str(data[meta_key]))
                metadata = CheckpointMetadata.from_dict(metadata_dict)
            else:
                # Create default metadata
                metadata = CheckpointMetadata(layer_id=layer_id)

            # Create checkpoint
            checkpoint = Checkpoint(
                data=data[data_key],
                metadata=metadata,
            )

            self.checkpoints[layer_id] = checkpoint
            self._memory_used_bytes += metadata.memory_bytes

    def _save_json(self, path: Path) -> None:
        """Save checkpoints in JSON format."""
        import base64

        checkpoint_list = []
        for layer_id, checkpoint in self.checkpoints.items():
            data_b64 = base64.b64encode(checkpoint.data.tobytes()).decode("utf-8")
            checkpoint_list.append(
                {
                    "layer_id": layer_id,
                    "data": data_b64,
                    "metadata": checkpoint.metadata.to_dict(),
                }
            )

        with open(path, "w") as f:
            json.dump(checkpoint_list, f)

    def _load_json(self, path: Path) -> None:
        """Load checkpoints from JSON format."""
        import base64

        with open(path) as f:
            checkpoint_list = json.load(f)

        self.clear()

        for item in checkpoint_list:
            layer_id = item["layer_id"]
            metadata = CheckpointMetadata.from_dict(item["metadata"])

            # Decode data
            data_bytes = base64.b64decode(item["data"])
            array_data = np.frombuffer(data_bytes, dtype=np.dtype(metadata.dtype))
            array_data = array_data.reshape(metadata.shape)

            checkpoint = Checkpoint(data=array_data, metadata=metadata)
            self.checkpoints[layer_id] = checkpoint
            self._memory_used_bytes += metadata.memory_bytes


def create_checkpoint_manager_from_optimizer(
    optimizer: GraphOptimizer,
    memory_limit_mb: float = 1024.0,
) -> GradientCheckpointManager:
    """Create a checkpoint manager from a GraphOptimizer.

    Args:
        optimizer: GraphOptimizer instance
        memory_limit_mb: Memory limit in MB

    Returns:
        Configured GradientCheckpointManager
    """
    # Extract strategy from optimizer config
    strategy = optimizer.config.checkpoint_strategy

    manager = GradientCheckpointManager(
        strategy=strategy,
        memory_limit_mb=memory_limit_mb,
    )
    manager.set_optimizer(optimizer)

    return manager
