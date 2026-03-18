"""Anomaly Detection for ML Training Data.

This module provides statistical anomaly detection methods including:
- Data drift detection
- Concept drift detection
- Feature drift detection
- Outlier detection using Z-scores

Components:
- DriftReport: Dataclass for drift detection results
- AnomalyDetector: Class for detecting various types of drift/anomalies
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DriftReport
# ---------------------------------------------------------------------------


@dataclass
class DriftReport:
    """Report of drift/anomaly detection analysis.

    Attributes:
        drift_detected: Whether significant drift was detected
        drift_score: Numeric measure of drift severity (0-1)
        affected_features: List of feature names affected by drift
        severity: Severity level ('low', 'medium', 'high')
        recommendations: List of recommended actions
        details: Additional diagnostic information
    """

    drift_detected: bool
    drift_score: float
    affected_features: list[str] = field(default_factory=list)
    severity: str = "low"
    recommendations: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate severity levels."""
        if self.severity not in ("low", "medium", "high"):
            self.severity = "low"
        self.drift_score = max(0.0, min(1.0, self.drift_score))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "drift_detected": self.drift_detected,
            "drift_score": self.drift_score,
            "affected_features": self.affected_features,
            "severity": self.severity,
            "recommendations": self.recommendations,
            "details": self.details,
        }


# ---------------------------------------------------------------------------
# AnomalyDetector
# ---------------------------------------------------------------------------


class AnomalyDetector:
    """Detector for data drift, concept drift, and anomalies.

    Provides statistical methods for detecting various types of drift
    and anomalies in training data compared to baseline distributions.

    Usage:
        detector = AnomalyDetector()
        report = detector.detect_drift(current_data, baseline_data)
    """

    # PSI thresholds
    PSI_SIGNIFICANT = 0.2  # Significant drift
    PSI_MAJOR = 0.5  # Major drift

    # KS test threshold
    KS_THRESHOLD = 0.3  # Significant difference

    # Z-score threshold for outliers
    ZSCORE_THRESHOLD = 3.0

    def __init__(
        self,
        psi_threshold: float = 0.2,
        ks_threshold: float = 0.3,
        zscore_threshold: float = 3.0,
    ) -> None:
        """Initialize anomaly detector.

        Args:
            psi_threshold: PSI threshold for drift detection (default 0.2)
            ks_threshold: KS test threshold (default 0.3)
            zscore_threshold: Z-score threshold for outliers (default 3.0)
        """
        self.psi_threshold = psi_threshold
        self.ks_threshold = ks_threshold
        self.zscore_threshold = zscore_threshold

    def detect_drift(
        self,
        current: dict[str, Any] | list[dict[str, Any]],
        baseline: dict[str, Any] | list[dict[str, Any]],
    ) -> DriftReport:
        """Detect data drift between current and baseline datasets.

        Args:
            current: Current dataset (list of dicts or single dict)
            baseline: Baseline dataset for comparison

        Returns:
            DriftReport with drift analysis results
        """
        # Normalize to lists
        current_data = self._normalize_data(current)
        baseline_data = self._normalize_data(baseline)

        if not current_data or not baseline_data:
            return DriftReport(
                drift_detected=False,
                drift_score=0.0,
                recommendations=["Insufficient data for drift detection"],
            )

        # Identify common numeric features
        numeric_features = self._get_numeric_features(current_data, baseline_data)

        if not numeric_features:
            return DriftReport(
                drift_detected=False,
                drift_score=0.0,
                recommendations=["No numeric features found for drift detection"],
            )

        # Calculate drift for each feature
        feature_drift: dict[str, float] = {}
        affected_features: list[str] = []

        for feature in numeric_features:
            current_values = self._extract_feature(current_data, feature)
            baseline_values = self._extract_feature(baseline_data, feature)

            # Skip if not enough data
            if len(current_values) < 10 or len(baseline_values) < 10:
                continue

            # Calculate PSI
            psi = self._calculate_psi(baseline_values, current_values)
            feature_drift[feature] = psi

            # Check KS test
            ks_stat = self._calculate_ks(baseline_values, current_values)
            feature_drift[f"{feature}_ks"] = ks_stat

            # Flag as affected if drift is significant
            if psi > self.psi_threshold or ks_stat > self.ks_threshold:
                affected_features.append(feature)

        # Calculate overall drift score
        if feature_drift:
            # Average PSI across features
            psi_values = [v for k, v in feature_drift.items() if not k.endswith("_ks")]
            avg_psi = np.mean(psi_values) if psi_values else 0.0

            # Determine severity
            if avg_psi >= self.PSI_MAJOR:
                severity = "high"
            elif avg_psi >= self.psi_threshold:
                severity = "medium"
            else:
                severity = "low"

            drift_detected = len(affected_features) > 0
            drift_score = min(1.0, avg_psi)
        else:
            drift_detected = False
            drift_score = 0.0
            severity = "low"

        # Generate recommendations
        recommendations = self._generate_drift_recommendations(
            drift_detected, affected_features, feature_drift
        )

        return DriftReport(
            drift_detected=drift_detected,
            drift_score=drift_score,
            affected_features=affected_features,
            severity=severity,
            recommendations=recommendations,
            details={
                "feature_drift": feature_drift,
                "current_size": len(current_data),
                "baseline_size": len(baseline_data),
            },
        )

    def detect_outliers(
        self, data: dict[str, Any] | list[dict[str, Any]], feature: str
    ) -> list[dict[str, int]]:
        """Detect outliers in a numeric feature using Z-score.

        Args:
            data: Dataset to check for outliers
            feature: Feature name to analyze

        Returns:
            List of dicts with row index and z-score for outliers
        """
        data_list = self._normalize_data(data)
        values = self._extract_feature(data_list, feature)

        if len(values) < 3:
            return []

        # Calculate Z-scores
        mean = np.mean(values)
        std = np.std(values)

        if std == 0:
            return []

        zscores = [(v - mean) / std for v in values]

        # Find outliers
        outliers = []
        for idx, zscore in enumerate(zscores):
            if abs(zscore) > self.zscore_threshold:
                outliers.append({"row": idx, "zscore": round(zscore, 3)})

        return outliers

    def detect_concept_drift(
        self,
        current: dict[str, Any] | list[dict[str, Any]],
        baseline: dict[str, Any] | list[dict[str, Any]],
        label_field: str = "label",
    ) -> DriftReport:
        """Detect concept drift in label distribution.

        Concept drift occurs when the relationship between features and
        labels changes over time.

        Args:
            current: Current dataset
            baseline: Baseline dataset
            label_field: Name of the label field

        Returns:
            DriftReport with concept drift analysis
        """
        current_data = self._normalize_data(current)
        baseline_data = self._normalize_data(baseline)

        # Extract labels
        current_labels = self._extract_feature(current_data, label_field)
        baseline_labels = self._extract_feature(baseline_data, label_field)

        if not current_labels or not baseline_labels:
            return DriftReport(
                drift_detected=False,
                drift_score=0.0,
                recommendations=["Insufficient label data for concept drift detection"],
            )

        # Calculate label distribution drift using chi-square-like approach
        current_dist = self._calculate_distribution(current_labels)
        baseline_dist = self._calculate_distribution(baseline_labels)

        # Calculate distribution difference
        all_labels = set(current_dist.keys()) | set(baseline_dist.keys())
        total_diff = 0.0

        for label in all_labels:
            current_pct = current_dist.get(label, 0.0)
            baseline_pct = baseline_dist.get(label, 0.0)
            total_diff += abs(current_pct - baseline_pct)

        # Normalize to 0-1 score
        drift_score = min(1.0, total_diff / 2.0)

        # Determine severity
        if drift_score >= 0.5:
            severity = "high"
        elif drift_score >= 0.2:
            severity = "medium"
        else:
            severity = "low"

        drift_detected = drift_score > 0.2

        recommendations = []
        if drift_detected:
            recommendations.append(
                f"Concept drift detected: label distribution changed by {drift_score:.1%}"
            )
            recommendations.append("Consider retraining model with recent data")
            recommendations.append("Review if new patterns have emerged in the data")

        return DriftReport(
            drift_detected=drift_detected,
            drift_score=drift_score,
            affected_features=[label_field],
            severity=severity,
            recommendations=recommendations,
            details={
                "current_distribution": current_dist,
                "baseline_distribution": baseline_dist,
            },
        )

    # ---------------------------------------------------------------------------
    # Helper methods
    # ---------------------------------------------------------------------------

    def _normalize_data(
        self, data: dict[str, Any] | list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Normalize input to list of dicts."""
        if isinstance(data, dict):
            return [data]
        return list(data)

    def _get_numeric_features(
        self, current: list[dict[str, Any]], baseline: list[dict[str, Any]]
    ) -> list[str]:
        """Identify common numeric features."""
        current_features = set()
        for record in current:
            for key, value in record.items():
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    current_features.add(key)

        baseline_features = set()
        for record in baseline:
            for key, value in record.items():
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    baseline_features.add(key)

        return sorted(current_features & baseline_features)

    def _extract_feature(self, data: list[dict[str, Any]], feature: str) -> list[float]:
        """Extract numeric feature values from dataset."""
        values = []
        for record in data:
            value = record.get(feature)
            if value is not None and isinstance(value, (int, float)):
                values.append(float(value))
        return values

    def _calculate_psi(
        self, baseline: list[float], current: list[float], bins: int = 10
    ) -> float:
        """Calculate Population Stability Index (PSI).

        Args:
            baseline: Baseline distribution
            current: Current distribution
            bins: Number of bins for discretization

        Returns:
            PSI value (0 = no drift, higher = more drift)
        """
        if not baseline or not current:
            return 0.0

        # Create bins from combined data
        all_values = baseline + current
        min_val = min(all_values)
        max_val = max(all_values)

        if min_val == max_val:
            return 0.0

        bin_edges = np.linspace(min_val, max_val, bins + 1)

        # Calculate bin percentages
        baseline_hist, _ = np.histogram(baseline, bins=bin_edges)
        current_hist, _ = np.histogram(current, bins=bin_edges)

        # Convert to proportions
        baseline_pct = baseline_hist / len(baseline)
        current_pct = current_hist / len(current)

        # Add small epsilon to avoid log(0)
        epsilon = 1e-10
        baseline_pct = np.clip(baseline_pct, epsilon, 1.0)
        current_pct = np.clip(current_pct, epsilon, 1.0)

        # Calculate PSI
        psi = np.sum((current_pct - baseline_pct) * np.log(current_pct / baseline_pct))

        return max(0.0, psi)

    def _calculate_ks(self, baseline: list[float], current: list[float]) -> float:
        """Calculate Kolmogorov-Smirnov statistic.

        Args:
            baseline: Baseline distribution
            current: Current distribution

        Returns:
            KS statistic (0 = identical, 1 = completely different)
        """
        if not baseline or not current:
            return 0.0

        # Use scipy if available, otherwise use manual implementation
        try:
            from scipy import stats

            ks_stat, _ = stats.ks_2samp(baseline, current)
            return ks_stat
        except ImportError:
            # Manual KS calculation
            n1 = len(baseline)
            n2 = len(current)

            # Sort both arrays
            sorted_baseline = sorted(baseline)
            sorted_current = sorted(current)

            # Calculate empirical CDFs and find max difference
            max_diff = 0.0
            i = j = 0

            all_values = sorted(set(baseline + current))

            for value in all_values:
                cdf_baseline = sum(1 for x in baseline if x <= value) / n1
                cdf_current = sum(1 for x in current if x <= value) / n2
                max_diff = max(max_diff, abs(cdf_baseline - cdf_current))

            return max_diff

    def _calculate_distribution(self, values: list[Any]) -> dict[str, float]:
        """Calculate value distribution as percentages."""
        if not values:
            return {}

        from collections import Counter

        counts = Counter(values)
        total = len(values)
        return {str(k): v / total for k, v in counts.items()}

    def _generate_drift_recommendations(
        self,
        drift_detected: bool,
        affected_features: list[str],
        feature_drift: dict[str, float],
    ) -> list[str]:
        """Generate recommendations based on drift analysis."""
        recommendations: list[str] = []

        if not drift_detected:
            recommendations.append("No significant drift detected.")
            return recommendations

        recommendations.append(
            f"Data drift detected in {len(affected_features)} feature(s): "
            f"{', '.join(affected_features)}"
        )

        # Check for high drift features
        high_drift = [
            f
            for f, psi in feature_drift.items()
            if not f.endswith("_ks") and psi >= self.PSI_MAJOR
        ]

        if high_drift:
            recommendations.append(
                f"Severe drift in: {', '.join(high_drift)}. "
                "Consider immediate model retraining."
            )

        # General recommendations
        recommendations.append("Review data collection pipeline for issues")
        recommendations.append("Consider updating training data with recent samples")
        recommendations.append("Monitor drift trends over time")

        return recommendations
