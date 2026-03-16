"""Belief Embedding Pipeline Module for Strong AI System.

Provides the BeliefPipeline class for end-to-end belief processing
with configurable stages, batch processing, and metrics collection.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

import numpy as np

from .cache import BeliefCache
from .search import BeliefSearchIndex, SearchResult
from .vector import BeliefVector, ValidationError


class PipelineStage(Enum):
    """Pipeline processing stages."""

    EMBED = auto()
    INDEX = auto()
    SEARCH = auto()
    CACHE = auto()


@dataclass
class PipelineMetrics:
    """Metrics for pipeline performance monitoring.

    Attributes:
        total_processed: Total number of beliefs processed
        batch_count: Number of batches processed
        total_latency_ms: Total latency in milliseconds
        cache_hits: Number of cache hits
        cache_misses: Number of cache misses
        errors: Number of processing errors
    """

    total_processed: int = 0
    batch_count: int = 0
    total_latency_ms: float = 0.0
    cache_hits: int = 0
    cache_misses: int = 0
    errors: int = 0

    @property
    def avg_latency_ms(self) -> float:
        """Calculate average latency per belief in milliseconds."""
        if self.total_processed == 0:
            return 0.0
        return self.total_latency_ms / self.total_processed

    @property
    def throughput(self) -> float:
        """Calculate throughput (beliefs per second)."""
        if self.total_latency_ms == 0:
            return 0.0
        return (self.total_processed / self.total_latency_ms) * 1000

    @property
    def cache_hit_rate(self) -> float:
        """Calculate cache hit rate."""
        total_cache_ops = self.cache_hits + self.cache_misses
        if total_cache_ops == 0:
            return 0.0
        return self.cache_hits / total_cache_ops

    @property
    def error_rate(self) -> float:
        """Calculate error rate."""
        if self.total_processed == 0:
            return 0.0
        return self.errors / self.total_processed

    def record_processing(self, count: int, latency_ms: float, errors: int = 0) -> None:
        """Record a batch processing event.

        Args:
            count: Number of beliefs processed
            latency_ms: Processing latency in milliseconds
            errors: Number of errors encountered
        """
        self.total_processed += count
        self.batch_count += 1
        self.total_latency_ms += latency_ms
        self.errors += errors

    def record_cache_hit(self) -> None:
        """Record a cache hit."""
        self.cache_hits += 1

    def record_cache_miss(self) -> None:
        """Record a cache miss."""
        self.cache_misses += 1

    def to_dict(self) -> dict[str, Any]:
        """Convert metrics to dictionary."""
        return {
            "total_processed": self.total_processed,
            "batch_count": self.batch_count,
            "avg_latency_ms": self.avg_latency_ms,
            "throughput": self.throughput,
            "cache_hit_rate": self.cache_hit_rate,
            "error_rate": self.error_rate,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "errors": self.errors,
        }


@dataclass
class PipelineConfig:
    """Configuration for BeliefPipeline.

    Attributes:
        enable_cache: Whether to enable caching
        cache_size: Maximum cache size
        cache_ttl: Default cache TTL in seconds
        batch_size: Default batch size for batch operations
        enable_metrics: Whether to collect metrics
        stages: List of enabled pipeline stages
    """

    enable_cache: bool = True
    cache_size: int = 1000
    cache_ttl: float | None = 300.0  # 5 minutes default
    batch_size: int = 100
    enable_metrics: bool = True
    stages: list[PipelineStage] = field(
        default_factory=lambda: [
            PipelineStage.EMBED,
            PipelineStage.INDEX,
            PipelineStage.SEARCH,
        ]
    )

    def is_stage_enabled(self, stage: PipelineStage) -> bool:
        """Check if a stage is enabled."""
        return stage in self.stages


@dataclass
class ProcessingResult:
    """Result of a belief processing operation.

    Attributes:
        belief: The processed belief vector
        search_results: Search results if search stage was enabled
        cached: Whether result was retrieved from cache
        processing_time_ms: Processing time in milliseconds
        error: Error message if processing failed
    """

    belief: BeliefVector | None = None
    search_results: list[SearchResult] | None = None
    cached: bool = False
    processing_time_ms: float = 0.0
    error: str | None = None

    @property
    def success(self) -> bool:
        """Check if processing was successful."""
        return self.error is None and self.belief is not None


class BeliefPipeline:
    """End-to-end belief processing pipeline.

    Provides configurable stages for belief embedding, indexing, and search
    with intelligent caching and comprehensive metrics.

    Attributes:
        config: Pipeline configuration
        search_index: BeliefSearchIndex for vector search
        cache: BeliefCache for result caching
        metrics: Pipeline performance metrics
    """

    def __init__(
        self,
        config: PipelineConfig | None = None,
        search_index: BeliefSearchIndex | None = None,
    ):
        """Initialize the belief pipeline.

        Args:
            config: Pipeline configuration (uses defaults if None)
            search_index: BeliefSearchIndex for vector search (creates default if None)
        """
        self.config = config if config is not None else PipelineConfig()
        self.search_index = (
            search_index
            if search_index is not None
            else BeliefSearchIndex.create_with_fallback()
        )
        self.cache = (
            BeliefCache(
                max_size=self.config.cache_size,
                default_ttl=self.config.cache_ttl,
            )
            if self.config.enable_cache
            else None
        )
        self.metrics = PipelineMetrics() if self.config.enable_metrics else None

        # Stage handlers
        self._stage_handlers: dict[PipelineStage, Callable[..., Any]] = {
            PipelineStage.EMBED: self._handle_embed,
            PipelineStage.INDEX: self._handle_index,
            PipelineStage.SEARCH: self._handle_search,
            PipelineStage.CACHE: self._handle_cache,
        }

    def _handle_embed(self, belief: BeliefVector, **kwargs: Any) -> BeliefVector:
        """Handle embed stage (pass-through by default)."""
        return belief

    def _handle_index(self, belief: BeliefVector, **kwargs: Any) -> BeliefVector:
        """Handle index stage - add belief to search index."""
        self.search_index.add_belief(belief)
        return belief

    def _handle_search(
        self, belief: BeliefVector, k: int = 5, **kwargs: Any
    ) -> list[SearchResult]:
        """Handle search stage - search for similar beliefs."""
        return self.search_index.search_by_similarity(belief, k=k)

    def _handle_cache(self, belief: BeliefVector, **kwargs: Any) -> BeliefVector:
        """Handle cache stage - cache the belief."""
        if self.cache is not None:
            self.cache.set_belief(belief)
        return belief

    def process(
        self,
        belief: BeliefVector,
        enable_search: bool = True,
        search_k: int = 5,
        use_cache: bool = True,
    ) -> ProcessingResult:
        """Process a single belief through the pipeline.

        Args:
            belief: BeliefVector to process
            enable_search: Whether to perform search stage
            search_k: Number of search results to return
            use_cache: Whether to use cache for this operation

        Returns:
            ProcessingResult with the processed belief and metadata
        """
        start_time = time.perf_counter()

        try:
            # Check cache first
            if (
                use_cache
                and self.cache is not None
                and PipelineStage.CACHE in self.config.stages
            ):
                cached_belief = self.cache.get_belief(belief.belief_id)
                if cached_belief is not None:
                    if self.metrics:
                        self.metrics.record_cache_hit()
                    elapsed_ms = (time.perf_counter() - start_time) * 1000
                    return ProcessingResult(
                        belief=cached_belief,
                        cached=True,
                        processing_time_ms=elapsed_ms,
                    )

                if self.metrics:
                    self.metrics.record_cache_miss()

            # Process through enabled stages
            current_belief = belief
            search_results: list[SearchResult] | None = None

            for stage in self.config.stages:
                handler = self._stage_handlers.get(stage)
                if handler is None:
                    continue

                if stage == PipelineStage.SEARCH and not enable_search:
                    continue

                if stage == PipelineStage.SEARCH:
                    search_results = handler(current_belief, k=search_k)
                else:
                    current_belief = handler(current_belief)

            elapsed_ms = (time.perf_counter() - start_time) * 1000

            if self.metrics:
                self.metrics.record_processing(1, elapsed_ms)

            return ProcessingResult(
                belief=current_belief,
                search_results=search_results,
                cached=False,
                processing_time_ms=elapsed_ms,
            )

        except Exception as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            if self.metrics:
                self.metrics.record_processing(1, elapsed_ms, errors=1)

            return ProcessingResult(
                belief=None,
                error=str(e),
                processing_time_ms=elapsed_ms,
            )

    def process_batch(
        self,
        beliefs: list[BeliefVector],
        enable_search: bool = False,
        search_k: int = 5,
        use_cache: bool = True,
    ) -> list[ProcessingResult]:
        """Process a batch of beliefs through the pipeline.

        Batch processing provides significantly better throughput than
        individual processing by amortizing overhead across many beliefs.

        Args:
            beliefs: List of BeliefVector objects to process
            enable_search: Whether to perform search stage (default: False for performance)
            search_k: Number of search results to return
            use_cache: Whether to use cache for this operation

        Returns:
            List of ProcessingResult objects
        """
        if not beliefs:
            return []

        start_time = time.perf_counter()
        results: list[ProcessingResult] = []
        errors = 0

        # Process in batches for efficiency
        batch_size = self.config.batch_size
        for i in range(0, len(beliefs), batch_size):
            batch = beliefs[i : i + batch_size]

            for belief in batch:
                result = self.process(
                    belief,
                    enable_search=enable_search,
                    search_k=search_k,
                    use_cache=use_cache,
                )
                results.append(result)
                if not result.success:
                    errors += 1

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        if self.metrics:
            self.metrics.record_processing(len(beliefs), elapsed_ms, errors)

        return results

    def embed_and_index(
        self,
        vectors: list[np.ndarray],
        metadata_list: list[dict[str, Any]] | None = None,
    ) -> list[ProcessingResult]:
        """Embed vectors and add them to the index.

        Convenience method for bulk embedding and indexing operations.

        Args:
            vectors: List of numpy arrays to embed
            metadata_list: Optional list of metadata dicts for each vector

        Returns:
            List of ProcessingResult objects
        """
        if metadata_list is None:
            metadata_list = [{} for _ in vectors]

        if len(vectors) != len(metadata_list):
            raise ValueError("vectors and metadata_list must have same length")

        beliefs: list[BeliefVector] = []
        for vec, meta in zip(vectors, metadata_list):
            belief = BeliefVector(vector=vec, metadata=meta)
            beliefs.append(belief)

        return self.process_batch(beliefs, enable_search=False, use_cache=True)

    def search(
        self,
        query_vector: np.ndarray,
        k: int = 5,
        use_cache: bool = True,
    ) -> list[SearchResult]:
        """Search for beliefs similar to a query vector.

        Args:
            query_vector: Query vector to search for
            k: Number of results to return
            use_cache: Whether to use cache for this operation

        Returns:
            List of SearchResult objects
        """
        # Check cache first
        if use_cache and self.cache is not None:
            cached_results = self.cache.get_search_results(query_vector)
            if cached_results is not None:
                if self.metrics:
                    self.metrics.record_cache_hit()
                return cached_results

            if self.metrics:
                self.metrics.record_cache_miss()

        # Perform search
        results = self.search_index.search(query_vector, k=k)

        # Cache results
        if use_cache and self.cache is not None:
            self.cache.set_search_results(query_vector, results)

        return results

    def search_belief(
        self,
        belief: BeliefVector,
        k: int = 5,
        exclude_self: bool = True,
    ) -> list[SearchResult]:
        """Search for beliefs similar to an existing belief.

        Args:
            belief: BeliefVector to search by
            k: Number of results to return
            exclude_self: Whether to exclude the belief itself from results

        Returns:
            List of SearchResult objects
        """
        results = self.search_index.search_by_similarity(belief, k=k + 1)

        if exclude_self:
            results = [r for r in results if r.belief_id != belief.belief_id]

        return results[:k]

    def get_metrics(self) -> dict[str, Any]:
        """Get current pipeline metrics.

        Returns:
            Dictionary with pipeline metrics
        """
        if self.metrics is None:
            return {"enabled": False}

        metrics_dict = self.metrics.to_dict()
        metrics_dict["enabled"] = True

        # Add cache metrics if available
        if self.cache is not None:
            metrics_dict["cache"] = self.cache.get_stats()

        return metrics_dict

    def reset_metrics(self) -> None:
        """Reset pipeline metrics."""
        if self.metrics is not None:
            self.metrics = PipelineMetrics()

    def clear_cache(self) -> None:
        """Clear the pipeline cache."""
        if self.cache is not None:
            self.cache.clear()

    def get_cache_stats(self) -> dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dictionary with cache statistics
        """
        if self.cache is None:
            return {"enabled": False}
        stats = self.cache.get_stats()
        stats["enabled"] = True
        return stats

    def warmup_cache(self, beliefs: list[BeliefVector]) -> None:
        """Pre-populate cache with beliefs.

        Args:
            beliefs: List of beliefs to cache
        """
        if self.cache is None:
            return

        for belief in beliefs:
            self.cache.set_belief(belief)

    def __enter__(self) -> BeliefPipeline:
        """Context manager entry."""
        return self

    def __exit__(self, *args: Any) -> None:
        """Context manager exit."""
        pass
