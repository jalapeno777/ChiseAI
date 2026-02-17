"""Threshold optimizer for calibration analysis.

This module provides the ThresholdOptimizer class for finding optimal confidence
thresholds per signal type by analyzing ECE (Expected Calibration Error) curves.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import numpy as np
import yaml

if TYPE_CHECKING:
    from collections.abc import Sequence

    from ml.calibration.data_collector import CalibrationDataCollector
    from ml.calibration.models import CalibrationRecord

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OptimizationResult:
    """Result of threshold optimization.

    Attributes:
        signal_type: Type of signal (LONG, SHORT, SCALP)
        optimal_threshold: Optimal confidence threshold
        min_ece: Minimum ECE value achieved at optimal threshold
        confidence_bin: Confidence bin index for optimal threshold
        sample_size: Number of samples used in optimization
        threshold_range: Range of thresholds searched (start, end)
        step_size: Step size used in grid search
    """

    signal_type: str
    optimal_threshold: float
    min_ece: float
    confidence_bin: int
    sample_size: int
    threshold_range: tuple[float, float] = field(default=(0.4, 0.95))
    step_size: float = field(default=0.05)

    def to_dict(self) -> dict[str, Any]:
        """Convert result to dictionary."""
        return {
            "signal_type": self.signal_type,
            "optimal_threshold": round(self.optimal_threshold, 4),
            "min_ece": round(self.min_ece, 6),
            "confidence_bin": self.confidence_bin,
            "sample_size": self.sample_size,
            "threshold_range": list(self.threshold_range),
            "step_size": self.step_size,
        }


@dataclass(frozen=True)
class ECECurve:
    """ECE curve data for visualization.

    Attributes:
        thresholds: List of threshold values
        ece_values: List of ECE values corresponding to thresholds
        optimal_idx: Index of optimal threshold in the lists
        signal_type: Type of signal (LONG, SHORT, SCALP)
        sample_sizes: List of sample sizes for each threshold
    """

    thresholds: list[float]
    ece_values: list[float]
    optimal_idx: int
    signal_type: str
    sample_sizes: list[int] = field(default_factory=list)

    @property
    def optimal_threshold(self) -> float:
        """Get the optimal threshold value."""
        return self.thresholds[self.optimal_idx]

    @property
    def min_ece(self) -> float:
        """Get the minimum ECE value."""
        return self.ece_values[self.optimal_idx]

    def to_dict(self) -> dict[str, Any]:
        """Convert curve to dictionary for serialization."""
        return {
            "signal_type": self.signal_type,
            "thresholds": [round(t, 4) for t in self.thresholds],
            "ece_values": [round(e, 6) for e in self.ece_values],
            "optimal_idx": self.optimal_idx,
            "optimal_threshold": round(self.optimal_threshold, 4),
            "min_ece": round(self.min_ece, 6),
            "sample_sizes": self.sample_sizes,
        }


class ThresholdOptimizer:
    """Optimizer for finding optimal confidence thresholds per signal type.

    Analyzes ECE (Expected Calibration Error) vs threshold curves to find
    optimal confidence thresholds for each signal type (LONG, SHORT, SCALP).

    The optimization uses grid search over a threshold range, calculating ECE
    for records above each threshold. The threshold with minimum ECE is selected
    as optimal.

    Example:
        >>> from ml.calibration import CalibrationDataCollector
        >>> collector = CalibrationDataCollector()
        >>> # ... collect some data ...
        >>> optimizer = ThresholdOptimizer(collector)
        >>> result = optimizer.optimize_thresholds('LONG')
        >>> print(f"Optimal threshold: {result.optimal_threshold:.2f}")
        Optimal threshold: 0.70
    """

    def __init__(
        self,
        collector: CalibrationDataCollector,
        n_bins: int = 10,
    ):
        """Initialize the threshold optimizer.

        Args:
            collector: CalibrationDataCollector instance with data
            n_bins: Number of bins for ECE calculation (default 10)
        """
        self.collector = collector
        self.n_bins = n_bins

    def calculate_ece(
        self,
        records: Sequence[CalibrationRecord],
        n_bins: int | None = None,
    ) -> float:
        """Calculate Expected Calibration Error using equal-width binning.

        ECE = sum_{i=1}^{n} (|B_i|/N) * |acc(B_i) - conf(B_i)|

        Where:
        - B_i = bin i
        - |B_i| = number of samples in bin i
        - acc(B_i) = accuracy in bin i
        - conf(B_i) = average confidence in bin i

        Args:
            records: List of calibration records
            n_bins: Number of bins (uses instance default if None)

        Returns:
            ECE value (0.0-1.0)

        Raises:
            ValueError: If records list is empty
        """
        if not records:
            raise ValueError("Cannot calculate ECE: no records provided")

        n_bins = n_bins or self.n_bins
        total_samples = len(records)

        # Extract predictions and outcomes
        predictions = np.array([r.predicted_prob for r in records])
        outcomes = np.array([r.actual_outcome for r in records])

        # Create equal-width bins
        bin_edges = np.linspace(0.0, 1.0, n_bins + 1)

        # Assign records to bins
        # np.digitize returns indices starting at 1, so subtract 1
        bin_indices = np.digitize(predictions, bin_edges[1:-1])

        # Calculate ECE
        ece = 0.0
        for i in range(n_bins):
            mask = bin_indices == i
            bin_preds = predictions[mask]
            bin_outcomes = outcomes[mask]

            sample_count = len(bin_preds)
            if sample_count > 0:
                confidence = float(np.mean(bin_preds))
                accuracy = float(np.mean(bin_outcomes))
                weight = sample_count / total_samples
                ece += weight * abs(accuracy - confidence)

        return float(ece)

    def optimize_thresholds(
        self,
        signal_type: str,
        threshold_range: tuple[float, float] = (0.4, 0.95),
        step: float = 0.05,
        min_samples: int = 30,
    ) -> OptimizationResult:
        """Find optimal threshold for given signal type.

        Performs grid search over threshold range, calculating ECE for
        records above each threshold. Returns threshold with minimum ECE.

        Args:
            signal_type: Type of signal (LONG, SHORT, SCALP)
            threshold_range: Range of thresholds to search (start, end)
            step: Step size for grid search
            min_samples: Minimum samples required for valid optimization

        Returns:
            OptimizationResult with optimal threshold and metadata

        Raises:
            ValueError: If insufficient samples for optimization
        """
        # Get all records for this signal type
        records = self.collector.get_records(signal_type=signal_type)

        if len(records) < min_samples:
            raise ValueError(
                f"Insufficient samples for {signal_type}: "
                f"got {len(records)}, need at least {min_samples}"
            )

        # Generate threshold grid
        start, end = threshold_range
        thresholds = np.arange(start, end + step, step)

        best_threshold = start
        min_ece = float("inf")
        best_sample_size = 0
        best_idx = 0

        ece_values = []
        sample_sizes = []

        for idx, threshold in enumerate(thresholds):
            # Filter records above threshold
            filtered = [r for r in records if r.predicted_prob >= threshold]
            sample_size = len(filtered)
            sample_sizes.append(sample_size)

            if sample_size < min_samples:
                # Not enough samples, use high ECE to discourage selection
                ece = 1.0
            else:
                try:
                    ece = self.calculate_ece(filtered)
                except Exception as e:
                    logger.warning(
                        f"ECE calculation failed for threshold {threshold}: {e}"
                    )
                    ece = 1.0

            ece_values.append(ece)

            if ece < min_ece:
                min_ece = ece
                best_threshold = float(threshold)
                best_sample_size = sample_size
                best_idx = idx

        # Calculate confidence bin for optimal threshold
        from ml.calibration.models import CalibrationRecord

        confidence_bin = CalibrationRecord.calculate_confidence_bin(best_threshold)

        logger.info(
            f"Optimized threshold for {signal_type}: "
            f"{best_threshold:.2f} (ECE: {min_ece:.4f}, samples: {best_sample_size})"
        )

        return OptimizationResult(
            signal_type=signal_type,
            optimal_threshold=best_threshold,
            min_ece=min_ece,
            confidence_bin=confidence_bin,
            sample_size=best_sample_size,
            threshold_range=threshold_range,
            step_size=step,
        )

    def generate_ece_curve(
        self,
        signal_type: str,
        threshold_range: tuple[float, float] = (0.4, 0.95),
        step: float = 0.05,
        min_samples: int = 10,
    ) -> ECECurve:
        """Generate threshold vs ECE curve for visualization.

        Args:
            signal_type: Type of signal (LONG, SHORT, SCALP)
            threshold_range: Range of thresholds to evaluate
            step: Step size for threshold grid
            min_samples: Minimum samples for valid ECE calculation

        Returns:
            ECECurve with thresholds, ECE values, and optimal index

        Raises:
            ValueError: If no records found for signal type
        """
        # Get all records for this signal type
        records = self.collector.get_records(signal_type=signal_type)

        if not records:
            raise ValueError(f"No records found for signal type: {signal_type}")

        # Generate threshold grid
        start, end = threshold_range
        thresholds = np.arange(start, end + step, step)

        ece_values = []
        sample_sizes = []
        min_ece = float("inf")
        optimal_idx = 0

        for idx, threshold in enumerate(thresholds):
            # Filter records above threshold
            filtered = [r for r in records if r.predicted_prob >= threshold]
            sample_size = len(filtered)
            sample_sizes.append(sample_size)

            if sample_size < min_samples:
                ece = 1.0  # High ECE for insufficient samples
            else:
                try:
                    ece = self.calculate_ece(filtered)
                except Exception as e:
                    logger.warning(f"ECE calculation failed: {e}")
                    ece = 1.0

            ece_values.append(ece)

            if ece < min_ece:
                min_ece = ece
                optimal_idx = idx

        return ECECurve(
            thresholds=[float(t) for t in thresholds],
            ece_values=ece_values,
            optimal_idx=optimal_idx,
            signal_type=signal_type,
            sample_sizes=sample_sizes,
        )

    def optimize_all_signal_types(
        self,
        threshold_range: tuple[float, float] = (0.4, 0.95),
        step: float = 0.05,
        min_samples: int = 30,
    ) -> dict[str, OptimizationResult]:
        """Optimize thresholds for all signal types.

        Args:
            threshold_range: Range of thresholds to search
            step: Step size for grid search
            min_samples: Minimum samples required per signal type

        Returns:
            Dict mapping signal type to OptimizationResult
        """
        from ml.calibration.models import SignalType

        results = {}
        for signal_type in SignalType:
            try:
                result = self.optimize_thresholds(
                    signal_type=signal_type.value,
                    threshold_range=threshold_range,
                    step=step,
                    min_samples=min_samples,
                )
                results[signal_type.value] = result
            except ValueError as e:
                logger.warning(f"Could not optimize {signal_type.value}: {e}")
                # Create a result with default values
                results[signal_type.value] = OptimizationResult(
                    signal_type=signal_type.value,
                    optimal_threshold=threshold_range[0],
                    min_ece=1.0,
                    confidence_bin=0,
                    sample_size=0,
                    threshold_range=threshold_range,
                    step_size=step,
                )

        return results

    def generate_all_ece_curves(
        self,
        threshold_range: tuple[float, float] = (0.4, 0.95),
        step: float = 0.05,
        min_samples: int = 10,
    ) -> dict[str, ECECurve]:
        """Generate ECE curves for all signal types.

        Args:
            threshold_range: Range of thresholds to evaluate
            step: Step size for threshold grid
            min_samples: Minimum samples for valid ECE calculation

        Returns:
            Dict mapping signal type to ECECurve
        """
        from ml.calibration.models import SignalType

        curves = {}
        for signal_type in SignalType:
            try:
                curve = self.generate_ece_curve(
                    signal_type=signal_type.value,
                    threshold_range=threshold_range,
                    step=step,
                    min_samples=min_samples,
                )
                curves[signal_type.value] = curve
            except ValueError as e:
                logger.warning(f"Could not generate curve for {signal_type.value}: {e}")

        return curves

    def export_config(
        self,
        filepath: str,
        threshold_range: tuple[float, float] = (0.4, 0.95),
        step: float = 0.05,
        min_samples: int = 30,
    ) -> bool:
        """Export optimized thresholds to YAML configuration file.

        Args:
            filepath: Path to output YAML file
            threshold_range: Range of thresholds to search
            step: Step size for grid search
            min_samples: Minimum samples required per signal type

        Returns:
            True if export successful
        """
        try:
            # Optimize all signal types
            results = self.optimize_all_signal_types(
                threshold_range=threshold_range,
                step=step,
                min_samples=min_samples,
            )

            # Build configuration structure
            config = {
                "threshold_optimization": {
                    "version": "1.0",
                    "generated_at": str(np.datetime64("now")),
                    "parameters": {
                        "threshold_range": list(threshold_range),
                        "step": step,
                        "min_samples": min_samples,
                        "n_bins": self.n_bins,
                    },
                    "thresholds": {
                        signal_type: {
                            "optimal_threshold": round(result.optimal_threshold, 4),
                            "min_ece": round(result.min_ece, 6),
                            "sample_size": result.sample_size,
                            "confidence_bin": result.confidence_bin,
                        }
                        for signal_type, result in results.items()
                    },
                }
            }

            # Write to file
            with open(filepath, "w") as f:
                yaml.dump(config, f, default_flow_style=False, sort_keys=False)

            logger.info(f"Exported optimized thresholds to {filepath}")
            return True

        except Exception as e:
            logger.error(f"Failed to export config: {e}")
            return False

    def export_to_json(
        self,
        filepath: str,
        threshold_range: tuple[float, float] = (0.4, 0.95),
        step: float = 0.05,
        min_samples: int = 30,
    ) -> bool:
        """Export optimized thresholds to JSON configuration file.

        Args:
            filepath: Path to output JSON file
            threshold_range: Range of thresholds to search
            step: Step size for grid search
            min_samples: Minimum samples required per signal type

        Returns:
            True if export successful
        """
        import json

        try:
            # Optimize all signal types
            results = self.optimize_all_signal_types(
                threshold_range=threshold_range,
                step=step,
                min_samples=min_samples,
            )

            # Build configuration structure
            config = {
                "threshold_optimization": {
                    "version": "1.0",
                    "generated_at": str(np.datetime64("now")),
                    "parameters": {
                        "threshold_range": list(threshold_range),
                        "step": step,
                        "min_samples": min_samples,
                        "n_bins": self.n_bins,
                    },
                    "thresholds": {
                        signal_type: result.to_dict()
                        for signal_type, result in results.items()
                    },
                }
            }

            # Write to file
            with open(filepath, "w") as f:
                json.dump(config, f, indent=2)

            logger.info(f"Exported optimized thresholds to {filepath}")
            return True

        except Exception as e:
            logger.error(f"Failed to export config: {e}")
            return False
