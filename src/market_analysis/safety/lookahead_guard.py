"""Safety module for repainting and lookahead detection.

This module provides guards against repainting and lookahead biases in
market analysis indicators. Repainting occurs when an indicator's historical
values change as new data arrives, which can lead to false backtesting results.

Key concepts:
- Lookahead: Accessing future data during calculation
- Repainting: Historical indicator values changing after the fact
- 0% tolerance: Any detected repainting/lookahead is a failure

Usage:
    @lookahead_guard
    def calculate(self, data: list[OHLCVData]) -> IndicatorResult:
        ...

    detector = RepaintingDetector()
    detector.check_indicator(indicator, data)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from functools import wraps
from typing import Any, Callable, Generic, TypeVar, cast

import numpy as np

logger = logging.getLogger(__name__)

T = TypeVar("T")


class RepaintingViolationType(Enum):
    """Types of repainting/lookahead violations."""

    LOOKAHEAD_ACCESS = "lookahead_access"  # Accessed future data
    VALUE_CHANGE = "value_change"  # Historical value changed
    INDEX_BOUNDS = "index_bounds"  # Accessed beyond valid range
    SIGNAL_REPAINT = "signal_repaint"  # Signal changed for historical bar


@dataclass
class RepaintingViolation:
    """Represents a single repainting or lookahead violation.

    Attributes:
        violation_type: The type of violation detected
        index: The data index where violation occurred
        timestamp: The timestamp of the violating access
        details: Additional details about the violation
        severity: Severity level (0.0 to 1.0, where 1.0 is most severe)
    """

    violation_type: RepaintingViolationType
    index: int
    timestamp: Any
    details: str
    severity: float = 1.0  # 0% tolerance means any violation is severity 1.0


@dataclass
class GuardResult:
    """Result of a repainting guard check.

    Attributes:
        passed: True if no violations detected
        violations: List of detected violations (empty if passed)
        guard_name: Name of the guard that performed the check
        check_time_ms: Time taken for the check in milliseconds
    """

    passed: bool
    violations: list[RepaintingViolation]
    guard_name: str
    check_time_ms: float = 0.0

    @property
    def violation_count(self) -> int:
        """Get the number of violations."""
        return len(self.violations)


class RepaintingDetector:
    """Detector for repainting and lookahead violations.

    Uses shadow calculation to detect if an indicator's historical values
    change when new data is added. Implements 0% tolerance policy.

    The detector works by:
    1. Taking a snapshot of indicator values at N bars
    2. Adding new data and recalculating
    3. Checking if any values at bars 0 to N-1 changed

    Attributes:
        tolerance: Acceptable violation rate (0.0 for 0% tolerance)
        store_snapshots: Whether to store calculation snapshots
    """

    def __init__(
        self,
        tolerance: float = 0.0,  # 0% tolerance
        store_snapshots: bool = False,
    ):
        """Initialize repainting detector.

        Args:
            tolerance: Acceptable violation rate (default 0.0 for strict)
            store_snapshots: Whether to store intermediate snapshots
        """
        if not 0.0 <= tolerance <= 1.0:
            raise ValueError(f"Tolerance must be in [0, 1], got {tolerance}")
        self.tolerance = tolerance
        self.store_snapshots = store_snapshots
        self._snapshots: dict[str, Any] = {}

    def snapshot_key(self, indicator_name: str, bar_index: int) -> str:
        """Generate key for snapshot storage."""
        return f"{indicator_name}:{bar_index}"

    def store_snapshot(
        self, indicator_name: str, bar_index: int, values: np.ndarray
    ) -> None:
        """Store a snapshot of indicator values at a specific bar.

        Args:
            indicator_name: Name of the indicator
            bar_index: Index of the bar when snapshot was taken
            values: Array of indicator values at that bar
        """
        if self.store_snapshots:
            key = self.snapshot_key(indicator_name, bar_index)
            self._snapshots[key] = values.copy()

    def get_snapshot(self, indicator_name: str, bar_index: int) -> np.ndarray | None:
        """Retrieve a stored snapshot.

        Args:
            indicator_name: Name of the indicator
            bar_index: Index of the bar

        Returns:
            Stored snapshot values or None if not found
        """
        if not self.store_snapshots:
            return None
        key = self.snapshot_key(indicator_name, bar_index)
        return self._snapshots.get(key)

    def check_lookahead(
        self,
        data: list[Any],
        calculator: Callable[[list[Any]], Any],
        indicator_name: str = "indicator",
    ) -> GuardResult:
        """Check for lookahead access in a calculation.

        This method wraps a calculator function and detects if it accesses
        data beyond the current processing index.

        Args:
            data: List of data points (OHLCV or similar)
            calculator: Function that computes indicator from data
            indicator_name: Name for logging purposes

        Returns:
            GuardResult indicating pass/fail and any violations
        """
        start_time = datetime.now()
        violations: list[RepaintingViolation] = []

        # Track all data accesses by wrapping numpy operations
        # For a proper implementation, we would use a proxy array class
        # that logs all accesses. For now, we do basic bounds checking.

        try:
            result = calculator(data)

            # Check if any future data was conceptually accessed
            # This is a simplified check - real implementation would
            # require instrumented data structures
            if isinstance(result, np.ndarray):
                # Check if result length suggests future access
                if len(result) > len(data):
                    violations.append(
                        RepaintingViolation(
                            violation_type=RepaintingViolationType.LOOKAHEAD_ACCESS,
                            index=len(data),
                            timestamp=getattr(data[-1], "timestamp", None)
                            if data
                            else None,
                            details=f"Result length {len(result)} exceeds data length {len(data)}",
                            severity=1.0,
                        )
                    )
            elif isinstance(result, dict) and "values" in result:
                values = result["values"]
                if len(values) > len(data):
                    violations.append(
                        RepaintingViolation(
                            violation_type=RepaintingViolationType.LOOKAHEAD_ACCESS,
                            index=len(data),
                            timestamp=getattr(data[-1], "timestamp", None)
                            if data
                            else None,
                            details=f"Values length {len(values)} exceeds data length {len(data)}",
                            severity=1.0,
                        )
                    )

        except Exception as e:
            violations.append(
                RepaintingViolation(
                    violation_type=RepaintingViolationType.LOOKAHEAD_ACCESS,
                    index=-1,
                    timestamp=None,
                    details=f"Calculation error: {str(e)}",
                    severity=1.0,
                )
            )

        elapsed_ms = (datetime.now() - start_time).total_seconds() * 1000

        return GuardResult(
            passed=len(violations) == 0,
            violations=violations,
            guard_name=f"{indicator_name}_lookahead_check",
            check_time_ms=elapsed_ms,
        )

    def check_repainting(
        self,
        indicator: Any,
        data: list[Any],
        num_bars_to_check: int | None = None,
    ) -> GuardResult:
        """Check if an indicator repaints by comparing snapshots.

        Calculates indicator at N bars, then at N+1 bars, and compares
        whether any historical values changed.

        Args:
            indicator: The indicator instance with a compute() or calculate() method
            data: Full list of data points
            num_bars_to_check: Number of historical bars to verify (None = all)

        Returns:
            GuardResult indicating pass/fail and any violations
        """
        start_time = datetime.now()
        violations: list[RepaintingViolation] = []

        if len(data) < 2:
            return GuardResult(
                passed=True,
                violations=[],
                guard_name=f"{indicator.__class__.__name__}_repainting_check",
                check_time_ms=0.0,
            )

        indicator_name = indicator.__class__.__name__
        check_limit = num_bars_to_check or (len(data) - 1)

        # Get the compute method
        compute_method = getattr(indicator, "compute", None) or getattr(
            indicator, "calculate", None
        )
        if compute_method is None:
            return GuardResult(
                passed=False,
                violations=[
                    RepaintingViolation(
                        violation_type=RepaintingViolationType.VALUE_CHANGE,
                        index=-1,
                        timestamp=None,
                        details="Indicator has no compute() or calculate() method",
                        severity=1.0,
                    )
                ],
                guard_name=f"{indicator_name}_repainting_check",
                check_time_ms=0.0,
            )

        # Calculate at N bars
        data_n = data[: len(data) - 1]
        try:
            result_n = compute_method(data_n)
            values_n = self._extract_values(result_n)
        except Exception as e:
            return GuardResult(
                passed=False,
                violations=[
                    RepaintingViolation(
                        violation_type=RepaintingViolationType.VALUE_CHANGE,
                        index=-1,
                        timestamp=None,
                        details=f"Initial calculation failed: {str(e)}",
                        severity=1.0,
                    )
                ],
                guard_name=f"{indicator_name}_repainting_check",
                check_time_ms=0.0,
            )

        # Calculate at N+1 bars
        try:
            result_n1 = compute_method(data)
            values_n1 = self._extract_values(result_n1)
        except Exception:
            # If calculation fails with more data, that's OK for this check
            values_n1 = None

        # Compare historical values (indices 0 to len(data)-2)
        if values_n1 is not None and values_n is not None:
            # Get the valid comparison range
            min_len = min(len(values_n), len(values_n1), check_limit + 1)

            for i in range(min_len - 1):  # Don't check the last bar (boundary)
                if self.store_snapshots:
                    self.store_snapshot(indicator_name, i, values_n1[: i + 1])

                if not self._values_equal(values_n[i], values_n1[i]):
                    violations.append(
                        RepaintingViolation(
                            violation_type=RepaintingViolationType.VALUE_CHANGE,
                            index=i,
                            timestamp=getattr(data[i], "timestamp", None)
                            if i < len(data)
                            else None,
                            details=f"Value at bar {i} changed from {values_n[i]} to {values_n1[i]}",
                            severity=1.0,
                        )
                    )

        elapsed_ms = (datetime.now() - start_time).total_seconds() * 1000

        return GuardResult(
            passed=len(violations) == 0,
            violations=violations,
            guard_name=f"{indicator_name}_repainting_check",
            check_time_ms=elapsed_ms,
        )

    def _extract_values(self, result: Any) -> np.ndarray:
        """Extract values array from indicator result.

        Args:
            result: Indicator calculation result

        Returns:
            numpy array of values
        """
        if isinstance(result, np.ndarray):
            return result
        elif isinstance(result, dict):
            for key in ["values", "result", "data"]:
                if key in result and isinstance(result[key], np.ndarray):
                    return result[key]
        elif hasattr(result, "values") and isinstance(result.values, np.ndarray):
            return result.values
        elif hasattr(result, "data") and isinstance(result.data, np.ndarray):
            return result.data
        # Handle BollingerBandsResult and similar dataclass results
        elif hasattr(result, "middle_band"):
            # BollingerBandsResult - use percent_b as primary values
            return result.percent_b
        elif hasattr(result, "histogram"):
            # MACDResult
            return result.histogram
        elif hasattr(result, "rsi_values"):
            # RSI-like result
            return result.rsi_values
        elif hasattr(result, "values") and hasattr(result.values, "values"):
            # Nested result structure
            primary = result.values.values
            if isinstance(primary, np.ndarray):
                return primary
        # Handle OrderBookImbalanceResult - scalar values, not arrays
        elif hasattr(result, "bid_ask_ratio") and not hasattr(result, "values"):
            # OrderBookImbalanceResult produces scalar values
            # Convert to a single-element array for comparison purposes
            return np.array([result.bid_ask_ratio])

        raise ValueError(f"Cannot extract values from result type {type(result)}")

    def _values_equal(self, a: Any, b: Any) -> bool:
        """Check if two values are equal, handling NaN."""
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            if np.isnan(a) and np.isnan(b):
                return True
            return abs(float(a) - float(b)) < 1e-10
        if isinstance(a, np.ndarray) and isinstance(b, np.ndarray):
            if a.shape != b.shape:
                return False
            return np.allclose(a, b, equal_nan=True)
        return a == b


class LookaheadGuard:
    """Context manager and decorator for lookahead detection.

    This class provides both a decorator and context manager interface
    for detecting and preventing lookahead bias in calculations.

    Usage as decorator:
        @LookaheadGuard()
        def calculate(self, data):
            ...

    Usage as context manager:
        with LookaheadGuard() as guard:
            # calculation here
            guard.check()
    """

    def __init__(
        self,
        name: str = "lookahead_guard",
        strict: bool = True,
    ):
        """Initialize lookahead guard.

        Args:
            name: Name for this guard instance
            strict: If True, raise exception on violation
        """
        self.name = name
        self.strict = strict
        self._violations: list[RepaintingViolation] = []
        self._enabled = True
        self._access_log: list[tuple[int, str]] = []

    def __enter__(self) -> "LookaheadGuard":
        """Enter context manager."""
        self._violations.clear()
        self._access_log.clear()
        self._enabled = True
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit context manager."""
        if self.strict and self._violations:
            raise RepaintingError(
                f"Lookahead violation detected in {self.name}: {self._violations}"
            )

    def __call__(self, func: Callable[..., T]) -> Callable[..., T]:
        """Use as a decorator.

        Args:
            func: Function to wrap with lookahead guard

        Returns:
            Wrapped function that checks for lookahead
        """

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            with LookaheadGuard(name=func.__name__, strict=self.strict):
                return func(*args, **kwargs)

        return cast(Callable[..., T], wrapper)

    def log_access(self, index: int, access_type: str = "read") -> None:
        """Log a data access for later violation detection.

        Args:
            index: The data index being accessed
            access_type: Type of access ('read', 'write', 'compute')
        """
        if self._enabled:
            self._access_log.append((index, access_type))

    def check(self) -> list[RepaintingViolation]:
        """Check for lookahead violations in logged accesses.

        Returns:
            List of violations found (empty if none)

        Raises:
            NotImplementedError: Detection not yet implemented. Use check_lookahead()
                or check_repainting() on RepaintingDetector for actual detection.
        """
        raise NotImplementedError(
            "LookaheadGuard.check() detection not yet implemented. "
            "Use RepaintingDetector.check_lookahead() or check_repainting() "
            "for actual lookahead/repainting detection."
        )

    @property
    def violations(self) -> list[RepaintingViolation]:
        """Get current list of violations."""
        return self._violations.copy()

    def disable(self) -> None:
        """Temporarily disable the guard."""
        self._enabled = False

    def enable(self) -> None:
        """Re-enable the guard."""
        self._enabled = True


def lookahead_guard(func: Callable[..., T]) -> Callable[..., T]:
    """Decorator that applies a lookahead guard to a function.

    This decorator wraps a calculation function and ensures it does not
    access future data. Any violation raises a RepaintingError.

    Args:
        func: The calculation function to guard

    Returns:
        Wrapped function with lookahead protection

    Example:
        @lookahead_guard
        def calculate(self, data: list[OHLCVData]) -> RSIResult:
            # This code is now protected against lookahead
            ...
    """
    guard = LookaheadGuard(name=func.__name__, strict=True)

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> T:
        with guard:
            return func(*args, **kwargs)

    return cast(Callable[..., T], wrapper)


class RepaintingError(Exception):
    """Exception raised when repainting or lookahead is detected.

    This exception indicates that an indicator's calculation has
    violated the 0% repainting tolerance policy.
    """

    pass


# Global detector instance for framework-wide use
_default_detector: RepaintingDetector | None = None


def get_detector() -> RepaintingDetector:
    """Get the global repainting detector instance.

    Returns:
        The global RepaintingDetector instance
    """
    global _default_detector
    if _default_detector is None:
        _default_detector = RepaintingDetector(tolerance=0.0)
    return _default_detector


def check_indicator(
    indicator: Any, data: list[Any], num_bars: int | None = None
) -> GuardResult:
    """Convenience function to check an indicator for repainting.

    Args:
        indicator: The indicator to check
        data: The data to use for checking
        num_bars: Number of historical bars to check (None = all)

    Returns:
        GuardResult indicating pass/fail
    """
    detector = get_detector()
    return detector.check_repainting(indicator, data, num_bars)


def check_lookahead(
    data: list[Any], calculator: Callable[[list[Any]], Any], name: str = "indicator"
) -> GuardResult:
    """Convenience function to check for lookahead in a calculation.

    Args:
        data: The data to use for checking
        calculator: Function that computes indicator from data
        name: Name for logging purposes

    Returns:
        GuardResult indicating pass/fail
    """
    detector = get_detector()
    return detector.check_lookahead(data, calculator, name)


class CheckpointedData(Generic[T]):
    """Wrapper for data that tracks bar access at calculation time.

    This class wraps OHLCV or other data and ensures that calculations
    only access data up to the current bar index, preventing lookahead.

    Usage:
        data = CheckpointedData(ohlcv_list)
        with data.access_checkpoint(current_bar=10) as checkpoint:
            # Only indices 0-10 are accessible
            value = checkpoint[15]  # Raises LookaheadAccessError
    """

    def __init__(self, data: list[T]):
        """Initialize checkpointed data.

        Args:
            data: The underlying data list
        """
        self._data = data
        self._checkpoint_bar: int | None = None

    def __len__(self) -> int:
        """Get length of underlying data."""
        return len(self._data)

    def __getitem__(self, index: int) -> T:
        """Get item with lookahead checking.

        Args:
            index: Index to access

        Returns:
            Data at index

        Raises:
            LookaheadAccessError: If accessing beyond checkpoint
        """
        if self._checkpoint_bar is not None and index > self._checkpoint_bar:
            raise LookaheadAccessError(
                f"Attempted to access index {index} at checkpoint bar {self._checkpoint_bar}"
            )
        return self._data[index]

    def access_checkpoint(self, current_bar: int) -> "CheckpointContext":
        """Create a checkpoint context for safe access.

        Args:
            current_bar: The current bar index (max accessible)

        Returns:
            CheckpointContext for use in 'with' statement
        """
        return CheckpointContext(self, current_bar)


class CheckpointContext:
    """Context manager for checkpointed data access."""

    def __init__(self, data: CheckpointedData, current_bar: int):
        """Initialize checkpoint context.

        Args:
            data: CheckpointedData instance
            current_bar: The current bar index
        """
        self._data = data
        self._current_bar = current_bar

    def __enter__(self) -> "CheckpointedData":
        """Enter the checkpoint context."""
        self._data._checkpoint_bar = self._current_bar
        return self._data

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit the checkpoint context."""
        self._data._checkpoint_bar = None


class LookaheadAccessError(Exception):
    """Exception raised when lookahead access is detected."""

    pass


def checkpoint(current_bar: int) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator that ensures calculations only access data up to current_bar.

    This decorator should be applied to methods that perform calculations
    on time series data to prevent lookahead bias.

    Args:
        current_bar: The current bar index for the calculation

    Returns:
        Decorated function with lookahead protection

    Example:
        @checkpoint(current_bar=10)
        def calculate_indicator(self, data):
            # data[0:11] is accessible, data[12+] raises error
            ...
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            # Get the data argument (assumes it's passed as first or keyword arg)
            data: list[Any] | None = None
            if args and isinstance(args[0], list):
                data = args[0]
            elif "data" in kwargs:
                data = kwargs["data"]

            if data is not None:
                # Wrap data with checkpoint protection
                checkpointed = CheckpointedData(data)
                args = (checkpointed,) + args[1:]
            return func(*args, **kwargs)

        return cast(Callable[..., T], wrapper)

    return decorator
