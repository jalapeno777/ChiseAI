"""Batch processing for assessment data.

This module provides configurable batch processing for training data,
with support for shuffling, collation, and various data types.
"""

from __future__ import annotations

import logging
import random
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class Batch:
    """Container for a batch of data.

    Attributes:
        data: List of items in the batch
        indices: Original indices of items
        start_idx: Starting index in the dataset
        is_last: Whether this is the last batch
        metadata: Additional batch metadata
    """

    data: list[Any]
    indices: list[int]
    start_idx: int
    is_last: bool = False
    metadata: dict[str, Any] | None = None

    @property
    def size(self) -> int:
        """Get batch size."""
        return len(self.data)

    @property
    def is_empty(self) -> bool:
        """Check if batch is empty."""
        return len(self.data) == 0


class CollateFn(Protocol):
    """Protocol for collate functions."""

    def __call__(self, batch: list[Any]) -> Any:
        """Collate a list of items into a batch."""
        ...


def default_collate(batch: list[Any]) -> list[Any]:
    """Default collate function - returns list as-is.

    Args:
        batch: List of items

    Returns:
        The same list
    """
    return batch


def dict_collate(batch: list[dict[str, Any]]) -> dict[str, list[Any]]:
    """Collate dictionaries by key.

    Args:
        batch: List of dictionaries

    Returns:
        Dictionary with lists of values
    """
    if not batch:
        return {}
    keys = batch[0].keys()
    return {k: [item.get(k) for item in batch] for k in keys}


class BatchProcessor:
    """Processes data into configurable batches.

    Features:
    - Configurable batch sizes
    - Data shuffling
    - Custom collate functions
    - Support for various data types
    - Gradient accumulation support

    Example:
        processor = BatchProcessor(
            batch_size=32,
            shuffle=True,
            collate_fn=dict_collate,
        )

        for batch in processor.process(data):
            # Process batch
            ...
    """

    def __init__(
        self,
        batch_size: int = 32,
        shuffle: bool = True,
        collate_fn: CollateFn | None = None,
        drop_last: bool = False,
        gradient_accumulation_steps: int = 1,
        seed: int = 42,
    ):
        """Initialize batch processor.

        Args:
            batch_size: Number of items per batch
            shuffle: Whether to shuffle data before batching
            collate_fn: Function to collate items into batch format
            drop_last: Whether to drop the last incomplete batch
            gradient_accumulation_steps: Number of steps for gradient accumulation
            seed: Random seed for reproducibility
        """
        if batch_size <= 0:
            raise ValueError(f"batch_size must be positive, got {batch_size}")

        if gradient_accumulation_steps <= 0:
            raise ValueError(
                f"gradient_accumulation_steps must be positive, "
                f"got {gradient_accumulation_steps}"
            )

        self.batch_size = batch_size
        self.shuffle = shuffle
        self.collate_fn = collate_fn or default_collate
        self.drop_last = drop_last
        self.gradient_accumulation_steps = gradient_accumulation_steps
        self.seed = seed

        self._rng = random.Random(seed)

    def process(
        self,
        data: Sequence[T],
        indices: list[int] | None = None,
    ) -> list[Batch]:
        """Process data into batches.

        Args:
            data: Data to process
            indices: Optional indices for tracking

        Returns:
            List of Batch objects
        """
        if len(data) == 0:
            logger.warning("Empty data provided to BatchProcessor")
            return []

        # Create working copy and optionally shuffle
        working_data = list(data)
        working_indices = indices.copy() if indices else list(range(len(data)))

        if self.shuffle:
            zipped = list(zip(working_data, working_indices, strict=True))
            self._rng.shuffle(zipped)
            working_data, working_indices = (
                zip(*zipped, strict=True) if zipped else ([], [])
            )
            working_data, working_indices = list(working_data), list(working_indices)

        # Calculate number of batches
        total_size = len(working_data)
        num_batches = total_size // self.batch_size
        if not self.drop_last and total_size % self.batch_size != 0:
            num_batches += 1

        batches = []
        for i in range(num_batches):
            start_idx = i * self.batch_size
            end_idx = min(start_idx + self.batch_size, total_size)

            # Check if this is the last batch
            is_last = i == num_batches - 1

            batch_data = working_data[start_idx:end_idx]
            batch_indices = working_indices[start_idx:end_idx]

            # Apply collate function
            collated_data = self.collate_fn(batch_data)

            batch = Batch(
                data=collated_data,
                indices=batch_indices,
                start_idx=start_idx,
                is_last=is_last,
                metadata={"batch_num": i, "total_batches": num_batches},
            )
            batches.append(batch)

        logger.debug(
            f"Created {len(batches)} batches from {total_size} samples "
            f"(batch_size={self.batch_size}, drop_last={self.drop_last})"
        )

        return batches

    def process_with_accumulation(
        self,
        data: Sequence[T],
        indices: list[int] | None = None,
    ) -> list[Batch]:
        """Process data with gradient accumulation batching.

        Args:
            data: Data to process
            indices: Optional indices for tracking

        Returns:
            List of Batch objects with accumulation metadata
        """
        batches = self.process(data, indices)

        # Re-batch for gradient accumulation
        if self.gradient_accumulation_steps <= 1:
            return batches

        accumulated_batches = []
        for i in range(0, len(batches), self.gradient_accumulation_steps):
            chunk = batches[i : i + self.gradient_accumulation_steps]

            # Merge batches in chunk
            merged_data = []
            merged_indices = []
            total_size = 0

            for batch in chunk:
                if isinstance(batch.data, list):
                    merged_data.extend(batch.data)
                else:
                    merged_data.append(batch.data)
                merged_indices.extend(batch.indices)
                total_size += batch.size

            is_last = chunk[-1].is_last if chunk else False

            accumulated_batch = Batch(
                data=self.collate_fn(merged_data) if merged_data else merged_data,
                indices=merged_indices,
                start_idx=chunk[0].start_idx if chunk else 0,
                is_last=is_last,
                metadata={
                    "batch_num": i // self.gradient_accumulation_steps,
                    "total_batches": (
                        len(batches) + self.gradient_accumulation_steps - 1
                    )
                    // self.gradient_accumulation_steps,
                    "accumulated_steps": len(chunk),
                    "effective_batch_size": total_size,
                },
            )
            accumulated_batches.append(accumulated_batch)

        logger.debug(
            f"Created {len(accumulated_batches)} accumulated batches "
            f"from {len(batches)} base batches "
            f"(accumulation_steps={self.gradient_accumulation_steps})"
        )

        return accumulated_batches

    def get_num_batches(self, data_size: int) -> int:
        """Calculate number of batches for given data size.

        Args:
            data_size: Size of the data

        Returns:
            Number of batches that would be created
        """
        if data_size == 0:
            return 0

        num_batches = data_size // self.batch_size
        if not self.drop_last and data_size % self.batch_size != 0:
            num_batches += 1

        return num_batches

    def reset_seed(self) -> None:
        """Reset random seed for reproducibility."""
        self._rng = random.Random(self.seed)


def create_batch_processor(
    batch_size: int = 32,
    shuffle: bool = True,
    collate_fn_name: str | None = None,
    drop_last: bool = False,
    gradient_accumulation_steps: int = 1,
    seed: int = 42,
) -> BatchProcessor:
    """Factory function to create a BatchProcessor with common configurations.

    Args:
        batch_size: Number of items per batch
        shuffle: Whether to shuffle data
        collate_fn_name: Name of collate function ('default' or 'dict')
        drop_last: Whether to drop last incomplete batch
        gradient_accumulation_steps: Gradient accumulation steps
        seed: Random seed

    Returns:
        Configured BatchProcessor
    """
    collate_fn: CollateFn | None = None
    if collate_fn_name == "dict":
        collate_fn = dict_collate
    elif collate_fn_name == "default":
        collate_fn = default_collate

    return BatchProcessor(
        batch_size=batch_size,
        shuffle=shuffle,
        collate_fn=collate_fn,
        drop_last=drop_last,
        gradient_accumulation_steps=gradient_accumulation_steps,
        seed=seed,
    )
