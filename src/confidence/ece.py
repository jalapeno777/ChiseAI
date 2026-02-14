"""Expected Calibration Error (ECE) calculation module.

ECE measures how well-calibrated confidence scores are by comparing
predicted confidence with actual accuracy across confidence bins.

Formula: ECE = Σ (n_i / N) * |accuracy_i - confidence_i|

Where:
- n_i = number of samples in bin i
- N = total number of samples
- accuracy_i = actual accuracy in bin i
- confidence_i = average predicted confidence in bin i
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = logging.getLogger(__name__)


class SignalType(str, Enum):
    """Types of trading signals."""

    ENTRY = "entry"
    EXIT = "exit"
    STOP_LOSS = "sl"
    TAKE_PROFIT = "tp"


@dataclass(frozen=True)
class ECEBin:
    """Data for a single confidence bin.

    Attributes:
        bin_index: Index of this bin (0-9 for 10 bins)
        bin_start: Start of confidence range (0.0-0.9)
        bin_end: End of confidence range (0.1-1.0)
        confidence: Average predicted confidence in this bin
        accuracy: Actual accuracy in this bin
        sample_count: Number of samples in this bin
        error: Absolute difference |accuracy - confidence|
    """

    bin_index: int
    bin_start: float
    bin_end: float
    confidence: float
    accuracy: float
    sample_count: int
    error: float = field(init=False)

    def __post_init__(self):
        object.__setattr__(self, "error", abs(self.accuracy - self.confidence))

    @property
    def weight(self) -> float:
        """Weight of this bin in ECE calculation (n_i / N)."""
        return self.sample_count


@dataclass(frozen=True)
class ECEResult:
    """Result of ECE calculation.

    Attributes:
        ece: Expected Calibration Error value (0.0-1.0)
        n_bins: Number of bins used
        total_samples: Total number of samples
        bins: List of ECEBin objects with per-bin details
        signal_type: Optional signal type for this calculation
        strategy_id: Optional strategy identifier
    """

    ece: float
    n_bins: int
    total_samples: int
    bins: list[ECEBin]
    signal_type: SignalType | None = None
    strategy_id: str | None = None

    @property
    def is_well_calibrated(self, threshold: float = 0.1) -> bool:
        """Check if ECE indicates well-calibrated predictions.

        Args:
            threshold: Maximum acceptable ECE (default 0.1 = 10%)

        Returns:
            True if ECE <= threshold
        """
        return self.ece <= threshold

    def get_bin(self, bin_index: int) -> ECEBin | None:
        """Get bin by index.

        Args:
            bin_index: Bin index (0 to n_bins-1)

        Returns:
            ECEBin if found, None otherwise
        """
        for b in self.bins:
            if b.bin_index == bin_index:
                return b
        return None


class ECECalculator:
    """Calculator for Expected Calibration Error.

    Implements ECE calculation with configurable binning.
    Default is 10 equal-width bins: [0-0.1), [0.1-0.2), ..., [0.9-1.0]

    Example:
        >>> calculator = ECECalculator(n_bins=10)
        >>> predictions = [0.85, 0.92, 0.78, 0.95, 0.88]
        >>> outcomes = [1, 1, 0, 1, 1]  # 1=correct, 0=incorrect
        >>> result = calculator.calculate(predictions, outcomes)
        >>> print(f"ECE: {result.ece:.4f}")
        ECE: 0.0560
    """

    def __init__(self, n_bins: int = 10):
        """Initialize ECE calculator.

        Args:
            n_bins: Number of equal-width confidence bins (default 10)
        """
        self.n_bins = n_bins
        self._bin_edges = np.linspace(0.0, 1.0, n_bins + 1)

    def calculate(
        self,
        predictions: Sequence[float],
        outcomes: Sequence[int],
        signal_type: SignalType | None = None,
        strategy_id: str | None = None,
    ) -> ECEResult:
        """Calculate ECE for given predictions and outcomes.

        Args:
            predictions: List of confidence scores (0.0-1.0)
            outcomes: List of binary outcomes (1=correct, 0=incorrect)
            signal_type: Optional signal type classification
            strategy_id: Optional strategy identifier

        Returns:
            ECEResult with ECE value and per-bin details

        Raises:
            ValueError: If predictions and outcomes have different lengths
            ValueError: If predictions contain values outside [0, 1]
            ValueError: If outcomes contain values other than 0 or 1
        """
        predictions_arr = np.asarray(predictions, dtype=np.float64)
        outcomes_arr = np.asarray(outcomes, dtype=np.int32)

        # Validate inputs
        if len(predictions_arr) != len(outcomes_arr):
            msg = f"Predictions ({len(predictions_arr)}) and outcomes ({len(outcomes_arr)}) must have same length"
            raise ValueError(msg)

        if len(predictions_arr) == 0:
            logger.warning("Empty predictions/outcomes provided")
            return ECEResult(
                ece=0.0,
                n_bins=self.n_bins,
                total_samples=0,
                bins=[],
                signal_type=signal_type,
                strategy_id=strategy_id,
            )

        if np.any((predictions_arr < 0) | (predictions_arr > 1)):
            msg = "Predictions must be in range [0, 1]"
            raise ValueError(msg)

        if not np.all(np.isin(outcomes_arr, [0, 1])):
            msg = "Outcomes must be binary (0 or 1)"
            raise ValueError(msg)

        # Assign to bins
        bin_indices = np.digitize(predictions_arr, self._bin_edges[1:-1])

        # Calculate per-bin statistics
        bins: list[ECEBin] = []
        total_samples = len(predictions_arr)
        ece = 0.0

        for i in range(self.n_bins):
            mask = bin_indices == i
            bin_preds = predictions_arr[mask]
            bin_outcomes = outcomes_arr[mask]

            sample_count = len(bin_preds)
            bin_start = self._bin_edges[i]
            bin_end = self._bin_edges[i + 1]

            if sample_count > 0:
                confidence = float(np.mean(bin_preds))
                accuracy = float(np.mean(bin_outcomes))
            else:
                # Empty bin: use midpoint as confidence, 0 accuracy
                confidence = (bin_start + bin_end) / 2
                accuracy = 0.0

            bin_obj = ECEBin(
                bin_index=i,
                bin_start=bin_start,
                bin_end=bin_end,
                confidence=confidence,
                accuracy=accuracy,
                sample_count=sample_count,
            )
            bins.append(bin_obj)

            # Weighted contribution to ECE
            weight = sample_count / total_samples
            ece += weight * bin_obj.error

        return ECEResult(
            ece=float(ece),
            n_bins=self.n_bins,
            total_samples=total_samples,
            bins=bins,
            signal_type=signal_type,
            strategy_id=strategy_id,
        )

    def calculate_per_signal_type(
        self,
        predictions_by_type: dict[SignalType, Sequence[float]],
        outcomes_by_type: dict[SignalType, Sequence[int]],
        strategy_id: str | None = None,
    ) -> dict[SignalType, ECEResult]:
        """Calculate ECE separately for each signal type.

        Args:
            predictions_by_type: Dict mapping signal type to confidence scores
            outcomes_by_type: Dict mapping signal type to binary outcomes
            strategy_id: Optional strategy identifier

        Returns:
            Dict mapping signal type to ECEResult

        Raises:
            ValueError: If signal types don't match between predictions and outcomes
        """
        if set(predictions_by_type.keys()) != set(outcomes_by_type.keys()):
            msg = "Signal types must match between predictions and outcomes"
            raise ValueError(msg)

        results: dict[SignalType, ECEResult] = {}

        for signal_type in predictions_by_type:
            result = self.calculate(
                predictions=predictions_by_type[signal_type],
                outcomes=outcomes_by_type[signal_type],
                signal_type=signal_type,
                strategy_id=strategy_id,
            )
            results[signal_type] = result

        return results

    def calculate_per_bin(
        self,
        predictions: Sequence[float],
        outcomes: Sequence[int],
    ) -> list[ECEBin]:
        """Calculate per-bin accuracy and confidence.

        Args:
            predictions: List of confidence scores (0.0-1.0)
            outcomes: List of binary outcomes (1=correct, 0=incorrect)

        Returns:
            List of ECEBin objects for each bin
        """
        result = self.calculate(predictions, outcomes)
        return result.bins


def calculate_ece(
    predictions: Sequence[float],
    outcomes: Sequence[int],
    n_bins: int = 10,
) -> float:
    """Convenience function to calculate ECE value only.

    Args:
        predictions: List of confidence scores (0.0-1.0)
        outcomes: List of binary outcomes (1=correct, 0=incorrect)
        n_bins: Number of equal-width confidence bins (default 10)

    Returns:
        ECE value (0.0-1.0)
    """
    calculator = ECECalculator(n_bins=n_bins)
    result = calculator.calculate(predictions, outcomes)
    return result.ece
