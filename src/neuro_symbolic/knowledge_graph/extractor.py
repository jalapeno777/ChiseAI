"""
RelationshipExtractor - Extracts relationships from market data.

This module provides functionality for extracting various types of
relationships from market data including correlations, causalities,
and temporal patterns.
"""

import math
from datetime import datetime
from typing import Any

from src.neuro_symbolic.knowledge_graph.models import (
    Edge,
    EdgeType,
    ExtractionResult,
    Node,
    NodeType,
    RelationshipStrength,
)


class RelationshipExtractor:
    """
    Extracts relationships from market data.

    This class provides methods for:
    - Correlation detection between assets
    - Causality inference using Granger causality
    - Temporal pattern extraction
    - Lead-lag relationship identification
    """

    def __init__(
        self,
        correlation_threshold: float = 0.3,
        causality_threshold: float = 0.05,
        min_samples: int = 30,
    ):
        """
        Initialize the relationship extractor.

        Args:
            correlation_threshold: Minimum correlation to consider significant
            causality_threshold: P-value threshold for causality tests
            min_samples: Minimum samples required for extraction
        """
        self.correlation_threshold = correlation_threshold
        self.causality_threshold = causality_threshold
        self.min_samples = min_samples
        self._extraction_count = 0

    def extract_correlation(
        self,
        source_id: str,
        target_id: str,
        source_data: list[float],
        target_data: list[float],
        metadata: dict[str, Any] | None = None,
    ) -> ExtractionResult | None:
        """
        Extract correlation relationship between two assets.

        Args:
            source_id: Source asset identifier
            target_id: Target asset identifier
            source_data: Price/return data for source
            target_data: Price/return data for target
            metadata: Additional metadata

        Returns:
            ExtractionResult if correlation is significant, None otherwise
        """
        if len(source_data) < self.min_samples or len(target_data) < self.min_samples:
            return None

        # Compute Pearson correlation
        correlation = self._pearson_correlation(source_data, target_data)

        if abs(correlation) < self.correlation_threshold:
            return None

        # Determine edge type based on correlation sign
        edge_type = (
            EdgeType.CORRELATED_WITH
            if correlation > 0
            else EdgeType.NEGATIVELY_CORRELATED
        )

        # Create nodes
        source_node = Node(
            id=source_id,
            node_type=NodeType.ASSET,
            properties={"symbol": source_id},
            source="correlation_extraction",
        )
        target_node = Node(
            id=target_id,
            node_type=NodeType.ASSET,
            properties={"symbol": target_id},
            source="correlation_extraction",
        )

        # Create edge
        strength = RelationshipStrength.from_correlation(correlation)
        edge = Edge(
            source_id=source_id,
            target_id=target_id,
            edge_type=edge_type,
            weight=abs(correlation),
            confidence=self._correlation_to_confidence(correlation),
            properties={
                "correlation": correlation,
                "strength": strength.value,
                "sample_size": min(len(source_data), len(target_data)),
            },
            evidence=[f"pearson_correlation={correlation:.4f}"],
        )

        self._extraction_count += 1

        return ExtractionResult(
            source_node=source_node,
            target_node=target_node,
            edge=edge,
            extraction_method="pearson_correlation",
            extraction_confidence=edge.confidence,
            supporting_data=metadata or {},
        )

    def extract_causality(
        self,
        source_id: str,
        target_id: str,
        source_data: list[float],
        target_data: list[float],
        max_lag: int = 5,
        metadata: dict[str, Any] | None = None,
    ) -> ExtractionResult | None:
        """
        Extract causal relationship using Granger causality test.

        Args:
            source_id: Source asset identifier (potential cause)
            target_id: Target asset identifier (potential effect)
            source_data: Time series data for source
            target_data: Time series data for target
            max_lag: Maximum lag to test
            metadata: Additional metadata

        Returns:
            ExtractionResult if causality is detected, None otherwise
        """
        if len(source_data) < self.min_samples or len(target_data) < self.min_samples:
            return None

        # Simplified Granger causality test
        result = self._granger_causality_test(source_data, target_data, max_lag)

        if result["p_value"] > self.causality_threshold:
            return None

        # Create nodes
        source_node = Node(
            id=source_id,
            node_type=NodeType.ASSET,
            properties={"symbol": source_id},
            source="causality_extraction",
        )
        target_node = Node(
            id=target_id,
            node_type=NodeType.ASSET,
            properties={"symbol": target_id},
            source="causality_extraction",
        )

        # Create edge
        edge = Edge(
            source_id=source_id,
            target_id=target_id,
            edge_type=EdgeType.CAUSES,
            weight=result["f_statistic"],
            confidence=1 - result["p_value"],
            properties={
                "p_value": result["p_value"],
                "f_statistic": result["f_statistic"],
                "optimal_lag": result["optimal_lag"],
            },
            evidence=[f"granger_p_value={result['p_value']:.4f}"],
        )

        self._extraction_count += 1

        return ExtractionResult(
            source_node=source_node,
            target_node=target_node,
            edge=edge,
            extraction_method="granger_causality",
            extraction_confidence=edge.confidence,
            supporting_data=metadata or {},
        )

    def extract_lead_lag(
        self,
        source_id: str,
        target_id: str,
        source_data: list[float],
        target_data: list[float],
        max_lag: int = 10,
        metadata: dict[str, Any] | None = None,
    ) -> ExtractionResult | None:
        """
        Extract lead-lag relationship between two assets.

        Args:
            source_id: Potential leader asset
            target_id: Potential lagger asset
            source_data: Time series data for source
            target_data: Time series data for target
            max_lag: Maximum lag to test
            metadata: Additional metadata

        Returns:
            ExtractionResult if lead-lag is detected, None otherwise
        """
        if len(source_data) < self.min_samples or len(target_data) < self.min_samples:
            return None

        # Find optimal lag with maximum cross-correlation
        best_lag = 0
        best_correlation = 0.0

        for lag in range(1, min(max_lag + 1, len(source_data) // 2)):
            # Correlation of source at t with target at t+lag
            if lag < len(source_data) and lag < len(target_data):
                corr = self._pearson_correlation(source_data[:-lag], target_data[lag:])
                if abs(corr) > abs(best_correlation):
                    best_correlation = corr
                    best_lag = lag

        if abs(best_correlation) < self.correlation_threshold:
            return None

        # Create nodes
        source_node = Node(
            id=source_id,
            node_type=NodeType.ASSET,
            properties={"symbol": source_id},
            source="lead_lag_extraction",
        )
        target_node = Node(
            id=target_id,
            node_type=NodeType.ASSET,
            properties={"symbol": target_id},
            source="lead_lag_extraction",
        )

        # Create edge
        edge = Edge(
            source_id=source_id,
            target_id=target_id,
            edge_type=EdgeType.LEADS,
            weight=abs(best_correlation),
            confidence=self._correlation_to_confidence(best_correlation),
            properties={
                "lag": best_lag,
                "cross_correlation": best_correlation,
                "direction": "positive" if best_correlation > 0 else "negative",
            },
            evidence=[f"lead_lag={best_lag}, corr={best_correlation:.4f}"],
        )

        self._extraction_count += 1

        return ExtractionResult(
            source_node=source_node,
            target_node=target_node,
            edge=edge,
            extraction_method="lead_lag_analysis",
            extraction_confidence=edge.confidence,
            supporting_data=metadata or {},
        )

    def extract_co_occurrence(
        self,
        events: list[dict[str, Any]],
        time_window_seconds: float = 300.0,
        min_co_occurrences: int = 3,
    ) -> list[ExtractionResult]:
        """
        Extract co-occurrence relationships from event data.

        Args:
            events: List of events with 'id', 'type', 'timestamp' keys
            time_window_seconds: Time window for co-occurrence
            min_co_occurrences: Minimum co-occurrences to consider

        Returns:
            List of ExtractionResults for co-occurring events
        """
        results = []
        co_occurrence_count: dict[tuple[str, str], int] = {}

        # Count co-occurrences
        for i, event1 in enumerate(events):
            for event2 in events[i + 1 :]:
                time_diff = abs(
                    (
                        event1.get("timestamp", datetime.utcnow())
                        - event2.get("timestamp", datetime.utcnow())
                    ).total_seconds()
                )
                if time_diff <= time_window_seconds:
                    pair = (event1["id"], event2["id"])
                    co_occurrence_count[pair] = co_occurrence_count.get(pair, 0) + 1

        # Create extraction results for significant co-occurrences
        for (source_id, target_id), count in co_occurrence_count.items():
            if count >= min_co_occurrences:
                source_node = Node(
                    id=source_id,
                    node_type=NodeType.EVENT,
                    source="co_occurrence_extraction",
                )
                target_node = Node(
                    id=target_id,
                    node_type=NodeType.EVENT,
                    source="co_occurrence_extraction",
                )

                edge = Edge(
                    source_id=source_id,
                    target_id=target_id,
                    edge_type=EdgeType.CO_OCCURS_WITH,
                    weight=count / len(events),
                    confidence=min(count / min_co_occurrences, 1.0),
                    properties={
                        "co_occurrence_count": count,
                        "time_window_seconds": time_window_seconds,
                    },
                    evidence=[f"co_occurred_{count}_times"],
                )

                self._extraction_count += 1

                results.append(
                    ExtractionResult(
                        source_node=source_node,
                        target_node=target_node,
                        edge=edge,
                        extraction_method="co_occurrence_analysis",
                        extraction_confidence=edge.confidence,
                    )
                )

        return results

    def extract_influence(
        self,
        influencer_id: str,
        influenced_id: str,
        influencer_events: list[dict[str, Any]],
        influenced_events: list[dict[str, Any]],
        time_window_seconds: float = 600.0,
    ) -> ExtractionResult | None:
        """
        Extract influence relationship between event types.

        Args:
            influencer_id: ID of the influencing event/source
            influenced_id: ID of the influenced event/target
            influencer_events: Events from the influencer
            influenced_events: Events from the influenced
            time_window_seconds: Time window for influence detection

        Returns:
            ExtractionResult if influence is detected, None otherwise
        """
        if not influencer_events or not influenced_events:
            return None

        # Count how often influencer events are followed by influenced events
        influence_count = 0
        for inf_event in influencer_events:
            inf_time = inf_event.get("timestamp", datetime.utcnow())
            for infd_event in influenced_events:
                infd_time = infd_event.get("timestamp", datetime.utcnow())
                time_diff = (infd_time - inf_time).total_seconds()
                if 0 < time_diff <= time_window_seconds:
                    influence_count += 1
                    break  # Count at most once per influencer event

        influence_ratio = influence_count / len(influencer_events)

        if influence_ratio < 0.3:  # At least 30% of events show influence
            return None

        source_node = Node(
            id=influencer_id,
            node_type=NodeType.EVENT,
            source="influence_extraction",
        )
        target_node = Node(
            id=influenced_id,
            node_type=NodeType.EVENT,
            source="influence_extraction",
        )

        edge = Edge(
            source_id=influencer_id,
            target_id=influenced_id,
            edge_type=EdgeType.INFLUENCES,
            weight=influence_ratio,
            confidence=influence_ratio,
            properties={
                "influence_count": influence_count,
                "total_influencer_events": len(influencer_events),
                "time_window_seconds": time_window_seconds,
            },
            evidence=[f"influence_ratio={influence_ratio:.2f}"],
        )

        self._extraction_count += 1

        return ExtractionResult(
            source_node=source_node,
            target_node=target_node,
            edge=edge,
            extraction_method="influence_analysis",
            extraction_confidence=edge.confidence,
        )

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _pearson_correlation(self, x: list[float], y: list[float]) -> float:
        """
        Compute Pearson correlation coefficient.

        Args:
            x: First data series
            y: Second data series

        Returns:
            Correlation coefficient (-1 to 1)
        """
        n = min(len(x), len(y))
        if n < 2:
            return 0.0

        x = x[:n]
        y = y[:n]

        mean_x = sum(x) / n
        mean_y = sum(y) / n

        # Compute covariance and standard deviations
        covariance = sum(
            (xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y, strict=False)
        )
        std_x = math.sqrt(sum((xi - mean_x) ** 2 for xi in x))
        std_y = math.sqrt(sum((yi - mean_y) ** 2 for yi in y))

        if std_x == 0 or std_y == 0:
            return 0.0

        return covariance / (std_x * std_y)

    def _granger_causality_test(
        self, cause: list[float], effect: list[float], max_lag: int
    ) -> dict[str, Any]:
        """
        Simplified Granger causality test.

        This is a simplified implementation that checks if past values
        of 'cause' help predict 'effect' beyond past values of 'effect'.

        Args:
            cause: Potential causal time series
            effect: Potential effect time series
            max_lag: Maximum lag to test

        Returns:
            Dictionary with test results
        """
        n = min(len(cause), len(effect))
        if n < max_lag + 2:
            return {"p_value": 1.0, "f_statistic": 0.0, "optimal_lag": 0}

        # Simple approach: test correlation at different lags
        best_f = 0.0
        best_lag = 1
        best_p = 1.0

        for lag in range(1, min(max_lag + 1, n // 2)):
            # Correlation between cause[t-lag] and effect[t]
            corr = self._pearson_correlation(cause[: n - lag], effect[lag:n])

            # Approximate F-statistic from correlation
            if abs(corr) > 0 and abs(corr) < 0.9999:  # Avoid division by zero
                f_stat = (corr**2) / (1 - corr**2) * (n - lag - 2)
                # Approximate p-value (simplified)
                p_value = max(0.001, 1 - abs(corr) ** 2)

                if f_stat > best_f:
                    best_f = f_stat
                    best_lag = lag
                    best_p = p_value

        return {
            "p_value": best_p,
            "f_statistic": best_f,
            "optimal_lag": best_lag,
        }

    def _correlation_to_confidence(self, correlation: float) -> float:
        """
        Convert correlation to confidence score.

        Args:
            correlation: Correlation coefficient

        Returns:
            Confidence score (0-1)
        """
        # Map absolute correlation to confidence
        abs_corr = abs(correlation)
        if abs_corr >= 0.9:
            return 0.95
        elif abs_corr >= 0.7:
            return 0.85
        elif abs_corr >= 0.5:
            return 0.75
        elif abs_corr >= 0.3:
            return 0.65
        else:
            return 0.5

    @property
    def extraction_count(self) -> int:
        """Number of extractions performed."""
        return self._extraction_count

    def reset_count(self) -> None:
        """Reset the extraction counter."""
        self._extraction_count = 0
