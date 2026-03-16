"""Memory profiling and optimization utilities for computational graphs.

Provides tools for profiling memory usage, tracking peak memory consumption,
and optimizing memory allocation during graph execution.

Example:
    >>> from src.strong_system.computational_graph import Node
    >>> from src.strong_system.computational_graph.memory import MemoryProfiler
    >>> import numpy as np
    >>>
    >>> # Profile memory usage
    >>> with MemoryProfiler() as profiler:
    ...     x = Node(np.random.randn(1000, 1000), name="x")
    ...     y = x * 2
    ...     z = y + 1
    >>> print(profiler.get_report())
"""

from __future__ import annotations

import gc
import sys
import time
import tracemalloc
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    from src.strong_system.computational_graph.graph import Graph
    from src.strong_system.computational_graph.node import Node


@dataclass
class MemorySnapshot:
    """A snapshot of memory usage at a point in time.

    Attributes:
        timestamp: Time when the snapshot was taken
        current_memory_mb: Current memory usage in MB
        peak_memory_mb: Peak memory usage in MB
        node_count: Number of nodes in the graph
        node_memory_mb: Memory used by nodes in MB
        description: Optional description of the snapshot
    """

    timestamp: float
    current_memory_mb: float
    peak_memory_mb: float
    node_count: int = 0
    node_memory_mb: float = 0.0
    description: str = ""


@dataclass
class MemoryReport:
    """Comprehensive memory usage report.

    Attributes:
        start_time: When profiling started
        end_time: When profiling ended
        duration_seconds: Total profiling duration
        peak_memory_mb: Peak memory usage during profiling
        final_memory_mb: Memory usage at end of profiling
        snapshots: List of memory snapshots
        node_breakdown: Memory breakdown by node
        recommendations: List of optimization recommendations
    """

    start_time: float
    end_time: float
    duration_seconds: float
    peak_memory_mb: float
    final_memory_mb: float
    snapshots: list[MemorySnapshot] = field(default_factory=list)
    node_breakdown: dict[str, float] = field(default_factory=dict)
    recommendations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert report to dictionary format.

        Returns:
            Dictionary representation of the report
        """
        return {
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_seconds": self.duration_seconds,
            "peak_memory_mb": round(self.peak_memory_mb, 2),
            "final_memory_mb": round(self.final_memory_mb, 2),
            "snapshots": [
                {
                    "timestamp": s.timestamp,
                    "current_memory_mb": round(s.current_memory_mb, 2),
                    "peak_memory_mb": round(s.peak_memory_mb, 2),
                    "node_count": s.node_count,
                    "node_memory_mb": round(s.node_memory_mb, 2),
                    "description": s.description,
                }
                for s in self.snapshots
            ],
            "node_breakdown": {k: round(v, 2) for k, v in self.node_breakdown.items()},
            "recommendations": self.recommendations,
        }

    def __str__(self) -> str:
        """Return formatted string representation of the report."""
        lines = [
            "=" * 60,
            "MEMORY PROFILING REPORT",
            "=" * 60,
            f"Duration: {self.duration_seconds:.2f} seconds",
            f"Peak Memory: {self.peak_memory_mb:.2f} MB",
            f"Final Memory: {self.final_memory_mb:.2f} MB",
            f"Memory Delta: {self.final_memory_mb - self.snapshots[0].current_memory_mb if self.snapshots else 0:.2f} MB",
            "",
            "Memory Snapshots:",
            "-" * 60,
        ]

        for i, snapshot in enumerate(self.snapshots):
            lines.append(
                f"  [{i}] {snapshot.description or 'Snapshot'}: "
                f"{snapshot.current_memory_mb:.2f} MB "
                f"(peak: {snapshot.peak_memory_mb:.2f} MB)"
            )

        if self.node_breakdown:
            lines.extend(["", "Node Memory Breakdown:", "-" * 60])
            sorted_nodes = sorted(
                self.node_breakdown.items(), key=lambda x: x[1], reverse=True
            )
            for node_name, memory in sorted_nodes[:10]:  # Top 10
                lines.append(f"  {node_name}: {memory:.2f} MB")

        if self.recommendations:
            lines.extend(["", "Recommendations:", "-" * 60])
            for i, rec in enumerate(self.recommendations, 1):
                lines.append(f"  {i}. {rec}")

        lines.append("=" * 60)
        return "\n".join(lines)


class MemoryProfiler:
    """Context manager for profiling memory usage.

    Tracks memory consumption during graph construction and execution,
    providing detailed reports on memory usage patterns.

    Attributes:
        enabled: Whether profiling is enabled
        track_nodes: Whether to track individual node memory usage
        snapshots: List of memory snapshots taken during profiling
    """

    def __init__(
        self,
        enabled: bool = True,
        track_nodes: bool = True,
        snapshot_interval: float = 0.0,
    ):
        """Initialize the memory profiler.

        Args:
            enabled: Whether to enable profiling
            track_nodes: Whether to track individual node memory
            snapshot_interval: Interval in seconds for automatic snapshots (0 = disabled)
        """
        self.enabled = enabled
        self.track_nodes = track_nodes
        self.snapshot_interval = snapshot_interval
        self.snapshots: list[MemorySnapshot] = []
        self._start_time: float = 0.0
        self._tracemalloc_started = False
        self._node_memory: dict[str, float] = defaultdict(float)
        self._last_snapshot_time: float = 0.0

    def __enter__(self) -> MemoryProfiler:
        """Start memory profiling.

        Returns:
            Self for context manager usage
        """
        if not self.enabled:
            return self

        # Start tracemalloc for detailed tracking
        tracemalloc.start()
        self._tracemalloc_started = True

        # Force garbage collection for clean baseline
        gc.collect()

        self._start_time = time.time()
        self._last_snapshot_time = self._start_time

        # Take initial snapshot
        self.take_snapshot("Initial")

        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Stop memory profiling and finalize report."""
        if not self.enabled:
            return

        # Take final snapshot
        self.take_snapshot("Final")

        # Stop tracemalloc
        if self._tracemalloc_started:
            tracemalloc.stop()
            self._tracemalloc_started = False

    def take_snapshot(self, description: str = "") -> MemorySnapshot:
        """Take a memory snapshot.

        Args:
            description: Optional description of the snapshot

        Returns:
            The snapshot that was taken
        """
        if not self.enabled:
            return MemorySnapshot(
                timestamp=time.time(),
                current_memory_mb=0.0,
                peak_memory_mb=0.0,
                description=description,
            )

        current, peak = tracemalloc.get_traced_memory()
        current_mb = current / (1024 * 1024)
        peak_mb = peak / (1024 * 1024)

        snapshot = MemorySnapshot(
            timestamp=time.time(),
            current_memory_mb=current_mb,
            peak_memory_mb=peak_mb,
            description=description,
        )

        self.snapshots.append(snapshot)
        self._last_snapshot_time = time.time()

        return snapshot

    def track_node(self, node: Node, description: str = "") -> None:
        """Track memory usage of a specific node.

        Args:
            node: The node to track
            description: Optional description
        """
        if not self.enabled or not self.track_nodes:
            return

        # Calculate node memory
        node_memory = 0.0
        if hasattr(node.value, "nbytes"):
            node_memory += node.value.nbytes / (1024 * 1024)
        else:
            node_memory += 8 / (1024 * 1024)  # Assume 8 bytes for scalar

        node_name = node.name or f"node_{id(node)}"
        self._node_memory[node_name] = node_memory

        # Check if we should take an automatic snapshot
        if (
            self.snapshot_interval > 0
            and time.time() - self._last_snapshot_time >= self.snapshot_interval
        ):
            self.take_snapshot(description or f"After {node_name}")

    def get_report(self) -> MemoryReport:
        """Generate a comprehensive memory report.

        Returns:
            MemoryReport with all profiling data
        """
        if not self.snapshots:
            return MemoryReport(
                start_time=self._start_time,
                end_time=time.time(),
                duration_seconds=0.0,
                peak_memory_mb=0.0,
                final_memory_mb=0.0,
            )

        start_time = self.snapshots[0].timestamp
        end_time = self.snapshots[-1].timestamp
        duration = end_time - start_time

        peak_memory = max(s.peak_memory_mb for s in self.snapshots)
        final_memory = self.snapshots[-1].current_memory_mb

        # Generate recommendations
        recommendations = self._generate_recommendations(peak_memory, final_memory)

        return MemoryReport(
            start_time=start_time,
            end_time=end_time,
            duration_seconds=duration,
            peak_memory_mb=peak_memory,
            final_memory_mb=final_memory,
            snapshots=self.snapshots.copy(),
            node_breakdown=dict(self._node_memory),
            recommendations=recommendations,
        )

    def _generate_recommendations(
        self, peak_memory: float, final_memory: float
    ) -> list[str]:
        """Generate optimization recommendations based on profiling data.

        Args:
            peak_memory: Peak memory usage in MB
            final_memory: Final memory usage in MB

        Returns:
            List of recommendation strings
        """
        recommendations: list[str] = []

        # Check for memory growth pattern
        if len(self.snapshots) >= 2:
            initial_memory = self.snapshots[0].current_memory_mb
            memory_growth = final_memory - initial_memory

            if memory_growth > 100:  # More than 100MB growth
                recommendations.append(
                    f"Significant memory growth detected ({memory_growth:.1f} MB). "
                    "Consider implementing gradient checkpointing."
                )

        # Check for high peak memory
        if peak_memory > 1024:  # More than 1GB
            recommendations.append(
                f"Peak memory usage is high ({peak_memory:.1f} MB). "
                "Consider operator fusion or batch size reduction."
            )

        # Check for node memory distribution
        if self._node_memory:
            total_node_memory = sum(self._node_memory.values())
            if total_node_memory > peak_memory * 0.5:  # Nodes use >50% of peak
                top_node = max(self._node_memory.items(), key=lambda x: x[1])
                recommendations.append(
                    f"Node '{top_node[0]}' uses significant memory ({top_node[1]:.1f} MB). "
                    "Consider reducing tensor size or using sparse representations."
                )

        # Check snapshot pattern
        if len(self.snapshots) > 3:
            memory_increases = sum(
                1
                for i in range(1, len(self.snapshots))
                if self.snapshots[i].current_memory_mb
                > self.snapshots[i - 1].current_memory_mb
            )
            if (
                memory_increases > len(self.snapshots) * 0.7
            ):  # >70% snapshots show increase
                recommendations.append(
                    "Memory consistently increases across snapshots. "
                    "Check for memory leaks or unnecessary tensor retention."
                )

        if not recommendations:
            recommendations.append("Memory usage looks healthy. No immediate concerns.")

        return recommendations

    def compare_snapshots(self, index1: int, index2: int) -> dict[str, Any]:
        """Compare two snapshots and return differences.

        Args:
            index1: Index of first snapshot
            index2: Index of second snapshot

        Returns:
            Dictionary with comparison results
        """
        if index1 < 0 or index1 >= len(self.snapshots):
            raise ValueError(f"Invalid snapshot index: {index1}")
        if index2 < 0 or index2 >= len(self.snapshots):
            raise ValueError(f"Invalid snapshot index: {index2}")

        snap1 = self.snapshots[index1]
        snap2 = self.snapshots[index2]

        memory_delta = snap2.current_memory_mb - snap1.current_memory_mb
        time_delta = snap2.timestamp - snap1.timestamp

        return {
            "snapshot1": {
                "index": index1,
                "description": snap1.description,
                "memory_mb": snap1.current_memory_mb,
            },
            "snapshot2": {
                "index": index2,
                "description": snap2.description,
                "memory_mb": snap2.current_memory_mb,
            },
            "memory_delta_mb": round(memory_delta, 2),
            "time_delta_seconds": round(time_delta, 2),
            "memory_growth_rate_mb_per_sec": (
                round(memory_delta / time_delta, 2) if time_delta > 0 else 0.0
            ),
        }


@contextmanager
def profile_memory(description: str = ""):
    """Context manager for simple memory profiling.

    Args:
        description: Description of the profiling session

    Yields:
        MemoryProfiler instance

    Example:
        >>> with profile_memory("Building model") as profiler:
        ...     x = Node(np.array([1.0, 2.0]))
        ...     y = x * 2
        >>> print(profiler.get_report())
    """
    profiler = MemoryProfiler()
    with profiler:
        yield profiler


def estimate_graph_memory(
    graph: Graph, include_gradients: bool = True
) -> dict[str, float]:
    """Estimate memory usage of a computational graph.

    Args:
        graph: The computational graph
        include_gradients: Whether to include gradient memory estimates

    Returns:
        Dictionary with memory breakdown
    """
    total_bytes = 0
    node_bytes = 0
    gradient_bytes = 0

    node_breakdown: dict[str, float] = {}

    for node_id, node in graph.nodes.items():
        # Value memory
        if hasattr(node.value, "nbytes"):
            node_mem = node.value.nbytes
        else:
            node_mem = 8

        node_bytes += node_mem
        total_bytes += node_mem

        node_name = node.name or f"node_{node_id}"
        node_breakdown[node_name] = node_mem / (1024 * 1024)

        # Gradient memory (if computed)
        if include_gradients:
            if node.gradient is not None and hasattr(node.gradient, "nbytes"):
                grad_mem = node.gradient.nbytes
                gradient_bytes += grad_mem
                total_bytes += grad_mem
            elif node.gradient is not None:
                gradient_bytes += 8
                total_bytes += 8

    return {
        "total_mb": total_bytes / (1024 * 1024),
        "node_values_mb": node_bytes / (1024 * 1024),
        "gradients_mb": gradient_bytes / (1024 * 1024),
        "node_breakdown": node_breakdown,
    }


def get_object_size(obj: Any) -> int:
    """Get the memory size of an object in bytes.

    Recursively calculates size including referenced objects.

    Args:
        obj: The object to measure

    Returns:
        Size in bytes
    """
    size = sys.getsizeof(obj)

    if isinstance(obj, dict):
        size += sum(get_object_size(k) + get_object_size(v) for k, v in obj.items())
    elif isinstance(obj, (list, tuple, set)):
        size += sum(get_object_size(item) for item in obj)
    elif isinstance(obj, np.ndarray):
        size += obj.nbytes

    return size


def format_memory_size(bytes_size: float) -> str:
    """Format a byte size as a human-readable string.

    Args:
        bytes_size: Size in bytes

    Returns:
        Formatted string (e.g., "1.5 MB")
    """
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if bytes_size < 1024.0:
            return f"{bytes_size:.2f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.2f} PB"


class MemoryOptimizer:
    """Optimizer for reducing memory usage in computational graphs.

    Provides strategies for memory optimization:
    - In-place operations where safe
    - Memory pooling for temporary tensors
    - Gradient accumulation for large batches
    """

    def __init__(self, max_memory_mb: float = 1024.0):
        """Initialize the memory optimizer.

        Args:
            max_memory_mb: Maximum memory budget in MB
        """
        self.max_memory_mb = max_memory_mb
        self._memory_pool: dict[tuple[int, ...], list[np.ndarray]] = defaultdict(list)

    def allocate_tensor(
        self, shape: tuple[int, ...], dtype: np.dtype = np.float64
    ) -> np.ndarray:
        """Allocate a tensor, potentially from the memory pool.

        Args:
            shape: Shape of the tensor
            dtype: Data type

        Returns:
            Allocated tensor
        """
        # Try to reuse from pool
        if shape in self._memory_pool and self._memory_pool[shape]:
            tensor = self._memory_pool[shape].pop()
            # Verify shape and dtype match
            if tensor.shape == shape and tensor.dtype == dtype:
                return tensor

        # Allocate new tensor
        return np.empty(shape, dtype=dtype)

    def release_tensor(self, tensor: np.ndarray) -> None:
        """Release a tensor back to the memory pool.

        Args:
            tensor: The tensor to release
        """
        if tensor is not None:
            self._memory_pool[tensor.shape].append(tensor)

    def clear_pool(self) -> None:
        """Clear the memory pool."""
        self._memory_pool.clear()
        gc.collect()

    def estimate_peak_memory(
        self, graph: Graph, batch_size: int = 1, sequence_length: int = 1
    ) -> float:
        """Estimate peak memory usage for graph execution.

        Args:
            graph: The computational graph
            batch_size: Batch size for estimation
            sequence_length: Sequence length for estimation

        Returns:
            Estimated peak memory in MB
        """
        base_memory = estimate_graph_memory(graph)["total_mb"]

        # Scale by batch and sequence
        scaled_memory = base_memory * batch_size * sequence_length

        # Add overhead for gradients (typically 2x for forward + backward)
        total_estimate = scaled_memory * 2.5

        return total_estimate

    def suggest_batch_size(self, graph: Graph, sequence_length: int = 1) -> int:
        """Suggest optimal batch size given memory constraints.

        Args:
            graph: The computational graph
            sequence_length: Sequence length

        Returns:
            Suggested batch size
        """
        # Start with batch size 1 and estimate
        batch_size = 1
        while True:
            estimated = self.estimate_peak_memory(graph, batch_size, sequence_length)
            if estimated > self.max_memory_mb * 0.8:  # Leave 20% headroom
                return max(1, batch_size - 1)
            batch_size *= 2

            # Safety limit
            if batch_size > 10000:
                return 10000
