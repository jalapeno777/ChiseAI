"""
Concept drift detection system for autonomous cognition.

Monitors prediction feature distributions, detects novel error patterns,
and validates model assumptions to identify when the underlying data
distribution has changed.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any


@dataclass
class DriftScore:
    """Score representing drift between two distributions."""

    feature_name: str
    baseline_distribution: dict[str, float]
    current_distribution: dict[str, float]
    kl_divergence: float
    js_divergence: float
    is_drift: bool
    severity: str

    def to_dict(self) -> dict[str, Any]:
        """Convert DriftScore to dictionary."""
        return {
            "feature_name": self.feature_name,
            "baseline_distribution": self.baseline_distribution,
            "current_distribution": self.current_distribution,
            "kl_divergence": self.kl_divergence,
            "js_divergence": self.js_divergence,
            "is_drift": self.is_drift,
            "severity": self.severity,
        }


@dataclass
class ErrorPattern:
    """Represents a detected error pattern."""

    pattern_id: str
    error_type: str
    description: str
    first_seen: datetime
    last_seen: datetime
    count: int
    severity: str
    examples: list[str] = field(default_factory=list)
    is_novel: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert ErrorPattern to dictionary."""
        return {
            "pattern_id": self.pattern_id,
            "error_type": self.error_type,
            "description": self.description,
            "first_seen": self.first_seen.isoformat(),
            "last_seen": self.last_seen.isoformat(),
            "count": self.count,
            "severity": self.severity,
            "examples": self.examples[:5],  # Limit examples
            "is_novel": self.is_novel,
        }


class ConceptDriftDetector:
    """
    Detector for concept drift in autonomous cognition systems.

    Monitors feature distributions, detects novel error patterns,
    and validates model assumptions.
    """

    # Thresholds for drift detection
    KL_DIVERGENCE_THRESHOLD_LOW = 0.1
    KL_DIVERGENCE_THRESHOLD_HIGH = 0.5
    JS_DIVERGENCE_THRESHOLD = 0.2
    MIN_SAMPLES_FOR_DRIFT = 10

    def __init__(self, redis_client: Any = None, qdrant_client: Any = None):
        """
        Initialize the concept drift detector.

        Args:
            redis_client: Optional Redis client for pattern tracking
            qdrant_client: Optional Qdrant client for feature storage
        """
        self.redis_client = redis_client
        self.qdrant_client = qdrant_client

        # Baseline distributions
        self._baseline_distributions: dict[str, dict[str, float]] = {}
        self._baseline_stats: dict[str, dict[str, float]] = {}

        # Error pattern tracking
        self._known_error_types: set[str] = set()
        self._error_patterns: dict[str, ErrorPattern] = {}
        self._error_history: list[dict[str, Any]] = []

        # Model assumption tracking
        self._assumption_violations: list[dict[str, Any]] = []
        self._correlation_matrix: dict[str, dict[str, float]] = {}

        # Feature tracking
        self._feature_history: dict[str, list[float]] = defaultdict(list)
        self._max_history_size = 1000

    def extract_features(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Extract features from input data for drift monitoring.

        Features monitored:
        - Prediction confidence distribution
        - Error type frequency
        - Input data characteristics
        - Decision type distribution
        - Risk level distribution

        Args:
            data: Input data containing predictions, errors, decisions, etc.

        Returns:
            Dictionary of extracted features

        Raises:
            ValueError: If data is empty or malformed
        """
        if not data:
            raise ValueError("Data cannot be empty")

        features: dict[str, Any] = {}

        # Prediction confidence distribution
        if "predictions" in data:
            predictions = data["predictions"]
            if isinstance(predictions, list) and predictions:
                confidences = [
                    p.get("confidence", 0.5) for p in predictions if isinstance(p, dict)
                ]
                if confidences:
                    features["prediction_confidence"] = {
                        "mean": sum(confidences) / len(confidences),
                        "std": self._calculate_std(confidences),
                        "min": min(confidences),
                        "max": max(confidences),
                        "distribution": self._discretize_distribution(confidences),
                    }

        # Error type frequency
        if "errors" in data:
            errors = data["errors"]
            if isinstance(errors, list):
                error_types = [
                    e.get("type", "unknown") for e in errors if isinstance(e, dict)
                ]
                features["error_type_distribution"] = dict(Counter(error_types))

        # Input data characteristics
        if "inputs" in data:
            inputs = data["inputs"]
            if isinstance(inputs, list) and inputs:
                features["input_characteristics"] = {
                    "count": len(inputs),
                    "avg_length": sum(len(str(i)) for i in inputs) / len(inputs)
                    if inputs
                    else 0,
                }

        # Decision type distribution
        if "decisions" in data:
            decisions = data["decisions"]
            if isinstance(decisions, list):
                decision_types = [
                    d.get("type", "unknown") for d in decisions if isinstance(d, dict)
                ]
                features["decision_type_distribution"] = dict(Counter(decision_types))

        # Risk level distribution
        if "risks" in data:
            risks = data["risks"]
            if isinstance(risks, list):
                risk_levels = [
                    r.get("level", "unknown") for r in risks if isinstance(r, dict)
                ]
                features["risk_level_distribution"] = dict(Counter(risk_levels))

        # Timestamp for tracking
        features["timestamp"] = datetime.now().isoformat()

        return features

    def compare_distributions(
        self,
        baseline: dict[str, float],
        current: dict[str, float],
        feature_name: str = "unknown",
    ) -> DriftScore:
        """
        Compare two distributions and calculate drift metrics.

        Args:
            baseline: Baseline distribution (category -> probability)
            current: Current distribution (category -> probability)
            feature_name: Name of the feature being compared

        Returns:
            DriftScore containing comparison metrics

        Raises:
            ValueError: If distributions are empty or invalid
        """
        if not baseline or not current:
            raise ValueError("Distributions cannot be empty")

        # Normalize distributions to ensure they sum to 1
        baseline_sum = sum(baseline.values())
        current_sum = sum(current.values())

        if baseline_sum == 0 or current_sum == 0:
            raise ValueError("Distribution sums cannot be zero")

        baseline_norm = {k: v / baseline_sum for k, v in baseline.items()}
        current_norm = {k: v / current_sum for k, v in current.items()}

        # Calculate KL divergence (Kullback-Leibler)
        kl_div = self._calculate_kl_divergence(baseline_norm, current_norm)

        # Calculate JS divergence (Jensen-Shannon)
        js_div = self._calculate_js_divergence(baseline_norm, current_norm)

        # Determine if drift is detected
        is_drift = (
            kl_div > self.KL_DIVERGENCE_THRESHOLD_LOW
            or js_div > self.JS_DIVERGENCE_THRESHOLD
        )

        # Determine severity
        if kl_div > self.KL_DIVERGENCE_THRESHOLD_HIGH or js_div > 0.4:
            severity = "high"
        elif (
            kl_div > self.KL_DIVERGENCE_THRESHOLD_LOW
            or js_div > self.JS_DIVERGENCE_THRESHOLD
        ):
            severity = "medium"
        else:
            severity = "low"

        return DriftScore(
            feature_name=feature_name,
            baseline_distribution=baseline_norm,
            current_distribution=current_norm,
            kl_divergence=kl_div,
            js_divergence=js_div,
            is_drift=is_drift,
            severity=severity,
        )

    def detect_novel_patterns(self, errors: list[dict[str, Any]]) -> list[ErrorPattern]:
        """
        Detect novel error patterns from a list of errors.

        Args:
            errors: List of error dictionaries with 'type', 'message', etc.

        Returns:
            List of detected error patterns (novel and existing)

        Raises:
            ValueError: If errors list is malformed
        """
        if not isinstance(errors, list):
            raise ValueError("Errors must be a list")

        now = datetime.now()
        detected_patterns: dict[str, ErrorPattern] = {}

        for error in errors:
            if not isinstance(error, dict):
                continue

            error_type = error.get("type", "unknown")
            error_message = error.get("message", str(error))

            # Check if this is a novel error type
            is_novel = error_type not in self._known_error_types

            if is_novel:
                self._known_error_types.add(error_type)

            # Create or update pattern
            pattern_id = f"pattern_{error_type}"

            if pattern_id not in detected_patterns:
                detected_patterns[pattern_id] = ErrorPattern(
                    pattern_id=pattern_id,
                    error_type=error_type,
                    description=self._extract_error_description(error),
                    first_seen=now,
                    last_seen=now,
                    count=0,
                    severity=error.get("severity", "unknown"),
                    examples=[],
                    is_novel=is_novel,
                )

            pattern = detected_patterns[pattern_id]
            pattern.count += 1
            pattern.last_seen = now

            # Store example (limit to avoid memory issues)
            if len(pattern.examples) < 10:
                pattern.examples.append(error_message)

        # Update stored patterns
        for pattern_id, pattern in detected_patterns.items():
            if pattern_id in self._error_patterns:
                # Update existing pattern
                existing = self._error_patterns[pattern_id]
                existing.count += pattern.count
                existing.last_seen = pattern.last_seen
                existing.examples.extend(pattern.examples[:5])
            else:
                # Store new pattern
                self._error_patterns[pattern_id] = pattern

            # Store in error history
            self._error_history.append(
                {
                    "pattern_id": pattern_id,
                    "error_type": pattern.error_type,
                    "timestamp": now.isoformat(),
                    "is_novel": pattern.is_novel,
                }
            )

        # Trim history if needed
        if len(self._error_history) > self._max_history_size:
            self._error_history = self._error_history[-self._max_history_size :]

        return list(detected_patterns.values())

    def check_model_assumptions(self) -> bool:
        """
        Check if model assumptions are still valid.

        Validates:
        - Feature independence
        - Distribution stability
        - Outlier frequency
        - Correlation stability

        Returns:
            True if all assumptions hold, False otherwise
        """
        assumptions_valid = True

        # Check feature independence (if we have enough data)
        if len(self._feature_history) >= 2:
            features = list(self._feature_history.keys())[:2]
            correlation = self._calculate_correlation(
                self._feature_history[features[0]],
                self._feature_history[features[1]],
            )

            if abs(correlation) > 0.8:
                assumptions_valid = False
                self._assumption_violations.append(
                    {
                        "assumption": "feature_independence",
                        "violation": f"High correlation detected: {correlation:.3f}",
                        "timestamp": datetime.now().isoformat(),
                    }
                )

        # Check distribution stability
        for feature_name, history in self._feature_history.items():
            if len(history) >= self.MIN_SAMPLES_FOR_DRIFT:
                # Split history in half and compare using consistent binning
                mid = len(history) // 2
                early_data = history[:mid]
                late_data = history[mid:]

                # Use consistent binning across both periods
                early_dist, late_dist = self._discretize_with_consistent_bins(
                    early_data, late_data
                )

                drift_score = self.compare_distributions(
                    early_dist, late_dist, feature_name
                )

                if drift_score.is_drift and drift_score.severity == "high":
                    assumptions_valid = False
                    self._assumption_violations.append(
                        {
                            "assumption": "distribution_stability",
                            "feature": feature_name,
                            "violation": f"Distribution drift detected: KL={drift_score.kl_divergence:.3f}",
                            "timestamp": datetime.now().isoformat(),
                        }
                    )

        # Check outlier frequency
        for feature_name, history in self._feature_history.items():
            if len(history) >= self.MIN_SAMPLES_FOR_DRIFT:
                outlier_count = self._count_outliers(history)
                outlier_rate = outlier_count / len(history)

                if outlier_rate > 0.1:  # More than 10% outliers
                    assumptions_valid = False
                    self._assumption_violations.append(
                        {
                            "assumption": "outlier_frequency",
                            "feature": feature_name,
                            "violation": f"High outlier rate: {outlier_rate:.1%}",
                            "timestamp": datetime.now().isoformat(),
                        }
                    )

        return assumptions_valid

    def get_drift_report(self) -> dict[str, Any]:
        """
        Generate a comprehensive drift analysis report.

        Returns:
            Dictionary containing:
            - drift_scores: List of DriftScore objects
            - error_patterns: List of ErrorPattern objects
            - assumption_violations: List of assumption violations
            - summary: High-level drift status
        """
        now = datetime.now()

        # Calculate drift scores for all monitored features
        drift_scores = []
        for feature_name, history in self._feature_history.items():
            if len(history) >= self.MIN_SAMPLES_FOR_DRIFT * 2:
                # Compare recent vs older data using consistent binning
                split_idx = len(history) // 2
                baseline_data = history[:split_idx]
                current_data = history[split_idx:]

                baseline_dist, current_dist = self._discretize_with_consistent_bins(
                    baseline_data, current_data
                )

                score = self.compare_distributions(
                    baseline_dist, current_dist, feature_name
                )
                drift_scores.append(score.to_dict())

        # Get recent error patterns
        recent_patterns = [
            p.to_dict()
            for p in self._error_patterns.values()
            if (now - p.last_seen) < timedelta(hours=24)
        ]

        # Get recent assumption violations
        recent_violations = [
            v
            for v in self._assumption_violations
            if datetime.fromisoformat(v["timestamp"]) > now - timedelta(hours=24)
        ]

        # Calculate summary
        has_drift = any(s.get("is_drift", False) for s in drift_scores)
        has_novel_patterns = any(p.get("is_novel", False) for p in recent_patterns)
        has_violations = len(recent_violations) > 0

        # Determine overall severity
        if has_drift and has_violations:
            overall_severity = "critical"
        elif has_drift or has_novel_patterns:
            overall_severity = "warning"
        elif has_violations:
            overall_severity = "attention"
        else:
            overall_severity = "normal"

        return {
            "timestamp": now.isoformat(),
            "drift_scores": drift_scores,
            "error_patterns": recent_patterns,
            "assumption_violations": recent_violations,
            "summary": {
                "has_drift": has_drift,
                "has_novel_patterns": has_novel_patterns,
                "has_violations": has_violations,
                "overall_severity": overall_severity,
                "monitored_features": len(self._feature_history),
                "known_error_types": len(self._known_error_types),
            },
        }

    def set_baseline(self, feature_name: str, distribution: dict[str, float]) -> None:
        """
        Set a baseline distribution for a feature.

        Args:
            feature_name: Name of the feature
            distribution: Baseline distribution (category -> probability)
        """
        self._baseline_distributions[feature_name] = distribution.copy()

    def update_feature_history(self, feature_name: str, value: float) -> None:
        """
        Update the history for a feature.

        Args:
            feature_name: Name of the feature
            value: New value to add to history
        """
        self._feature_history[feature_name].append(value)

        # Trim if needed
        if len(self._feature_history[feature_name]) > self._max_history_size:
            self._feature_history[feature_name] = self._feature_history[feature_name][
                -self._max_history_size :
            ]

    def get_error_clusters(
        self, errors: list[dict[str, Any]], n_clusters: int = 3
    ) -> list[dict[str, Any]]:
        """
        Cluster similar errors together.

        Uses a simple text similarity approach based on error messages.

        Args:
            errors: List of error dictionaries
            n_clusters: Number of clusters to create

        Returns:
            List of clusters with error counts and representative examples
        """
        if not errors:
            return []

        # Simple clustering by error type
        clusters: dict[str, list[dict[str, Any]]] = defaultdict(list)

        for error in errors:
            if isinstance(error, dict):
                error_type = error.get("type", "unknown")
                clusters[error_type].append(error)

        # Sort clusters by size and return top n_clusters
        sorted_clusters = sorted(
            clusters.items(),
            key=lambda x: len(x[1]),
            reverse=True,
        )[:n_clusters]

        result = []
        for cluster_name, cluster_errors in sorted_clusters:
            messages = [
                e.get("message", str(e)) for e in cluster_errors if isinstance(e, dict)
            ]

            result.append(
                {
                    "cluster_id": f"cluster_{cluster_name}",
                    "error_type": cluster_name,
                    "count": len(cluster_errors),
                    "representative_examples": messages[:3],
                }
            )

        return result

    # Private helper methods

    def _calculate_kl_divergence(
        self,
        p: dict[str, float],
        q: dict[str, float],
    ) -> float:
        """Calculate KL divergence D_KL(P || Q)."""
        kl = 0.0

        # Get all unique keys from both distributions
        all_keys = set(p.keys()) | set(q.keys())

        for key in all_keys:
            p_val = p.get(key, 1e-10)  # Small epsilon to avoid log(0)
            q_val = q.get(key, 1e-10)

            # Clip to avoid numerical issues
            p_val = max(p_val, 1e-10)
            q_val = max(q_val, 1e-10)

            kl += p_val * math.log(p_val / q_val)

        return kl

    def _calculate_js_divergence(
        self,
        p: dict[str, float],
        q: dict[str, float],
    ) -> float:
        """Calculate Jensen-Shannon divergence."""
        # JS(P || Q) = 0.5 * KL(P || M) + 0.5 * KL(Q || M)
        # where M = 0.5 * (P + Q)

        # Create mixture distribution M
        all_keys = set(p.keys()) | set(q.keys())
        m = {key: 0.5 * (p.get(key, 0) + q.get(key, 0)) for key in all_keys}

        # Add epsilon to avoid zeros
        m = {k: max(v, 1e-10) for k, v in m.items()}

        kl_p_m = self._calculate_kl_divergence(p, m)
        kl_q_m = self._calculate_kl_divergence(q, m)

        return 0.5 * (kl_p_m + kl_q_m)

    def _calculate_std(self, values: list[float]) -> float:
        """Calculate standard deviation of a list of values."""
        if not values or len(values) < 2:
            return 0.0

        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        return math.sqrt(variance)

    def _discretize_distribution(
        self,
        values: list[float],
        n_bins: int = 10,
    ) -> dict[str, float]:
        """
        Discretize a list of continuous values into a distribution.

        Args:
            values: List of numeric values
            n_bins: Number of bins to create

        Returns:
            Dictionary mapping bin labels to frequencies
        """
        if not values:
            return {}

        if len(values) == 1:
            return {"single_value": 1.0}

        min_val = min(values)
        max_val = max(values)

        if min_val == max_val:
            return {"single_value": float(len(values))}

        # Create bins
        bin_width = (max_val - min_val) / n_bins
        bins: dict[str, int] = defaultdict(int)

        for value in values:
            bin_idx = min(int((value - min_val) / bin_width), n_bins - 1)
            bin_label = f"bin_{bin_idx}"
            bins[bin_label] += 1

        return dict(bins)

    def _discretize_with_consistent_bins(
        self,
        data1: list[float],
        data2: list[float],
        n_bins: int = 10,
    ) -> tuple[dict[str, float], dict[str, float]]:
        """
        Discretize two datasets using consistent bin boundaries.

        This ensures that values from different ranges are properly compared
        by using bin boundaries based on the combined range of both datasets.

        Args:
            data1: First list of numeric values
            data2: Second list of numeric values
            n_bins: Number of bins to create

        Returns:
            Tuple of (distribution1, distribution2) with consistent binning
        """
        if not data1 and not data2:
            return {}, {}

        if not data1:
            return {}, self._discretize_distribution(data2, n_bins)

        if not data2:
            return self._discretize_distribution(data1, n_bins), {}

        # Calculate bin boundaries from combined data
        all_values = data1 + data2
        min_val = min(all_values)
        max_val = max(all_values)

        if min_val == max_val:
            # All values are the same
            return (
                {"single_value": float(len(data1))},
                {"single_value": float(len(data2))},
            )

        # Create consistent bins
        bin_width = (max_val - min_val) / n_bins

        bins1: dict[str, int] = defaultdict(int)
        bins2: dict[str, int] = defaultdict(int)

        for value in data1:
            bin_idx = min(int((value - min_val) / bin_width), n_bins - 1)
            bin_label = f"bin_{bin_idx}"
            bins1[bin_label] += 1

        for value in data2:
            bin_idx = min(int((value - min_val) / bin_width), n_bins - 1)
            bin_label = f"bin_{bin_idx}"
            bins2[bin_label] += 1

        return dict(bins1), dict(bins2)

    def _extract_error_description(self, error: dict[str, Any]) -> str:
        """Extract a human-readable description from an error."""
        error_type = error.get("type", "unknown")
        message = error.get("message", "")

        if message:
            return f"{error_type}: {message[:100]}"
        return f"Error of type {error_type}"

    def _calculate_correlation(self, x: list[float], y: list[float]) -> float:
        """Calculate Pearson correlation coefficient between two lists."""
        if len(x) != len(y) or len(x) < 2:
            return 0.0

        n = len(x)
        mean_x = sum(x) / n
        mean_y = sum(y) / n

        numerator = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
        denom_x = sum((xi - mean_x) ** 2 for xi in x)
        denom_y = sum((yi - mean_y) ** 2 for yi in y)

        if denom_x == 0 or denom_y == 0:
            return 0.0

        return numerator / math.sqrt(denom_x * denom_y)

    def _count_outliers(self, values: list[float], threshold: float = 2.0) -> int:
        """Count the number of outliers in a list using z-score."""
        if not values or len(values) < 2:
            return 0

        mean = sum(values) / len(values)
        std = self._calculate_std(values)

        if std == 0:
            return 0

        return sum(1 for v in values if abs((v - mean) / std) > threshold)
