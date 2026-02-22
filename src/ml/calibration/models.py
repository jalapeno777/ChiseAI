"""Data models for calibration data collection.

This module defines the data structures used for storing and managing
calibration records for ECE (Expected Calibration Error) analysis.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class SignalType(str, Enum):
    """Types of trading signals supported for calibration."""

    LONG = "LONG"
    SHORT = "SHORT"
    SCALP = "SCALP"


class CollectionWindow(str, Enum):
    """Predefined collection windows for querying calibration data."""

    ONE_HOUR = "1h"
    ONE_DAY = "24h"
    ONE_WEEK = "7d"
    ONE_MONTH = "30d"

    def to_hours(self) -> int:
        """Convert window to hours."""
        mapping = {
            CollectionWindow.ONE_HOUR: 1,
            CollectionWindow.ONE_DAY: 24,
            CollectionWindow.ONE_WEEK: 168,  # 7 * 24
            CollectionWindow.ONE_MONTH: 720,  # 30 * 24
        }
        return mapping[self]

    def to_seconds(self) -> int:
        """Convert window to seconds."""
        return self.to_hours() * 3600


@dataclass(frozen=True)
class CalibrationRecord:
    """Single calibration record representing a prediction-outcome pair.

    Attributes:
        timestamp: When the prediction was made (UTC)
        signal_id: Unique signal identifier
        predicted_prob: Predicted probability of success (0.0-1.0)
        actual_outcome: Actual outcome (1=win, 0=loss)
        signal_type: Type of signal (LONG, SHORT, SCALP)
        confidence_bin: Confidence bin index (0-9 for 10 bins)
        strategy_id: Optional strategy identifier
        metadata: Additional metadata for the record
    """

    timestamp: datetime
    signal_id: str
    predicted_prob: float
    actual_outcome: int
    signal_type: SignalType
    confidence_bin: int
    strategy_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validate the record after initialization."""
        # Validate predicted_prob is in valid range
        if not 0.0 <= self.predicted_prob <= 1.0:
            raise ValueError(
                f"predicted_prob must be between 0.0 and 1.0, got {self.predicted_prob}"
            )

        # Validate actual_outcome is binary
        if self.actual_outcome not in (0, 1):
            raise ValueError(
                f"actual_outcome must be 0 or 1, got {self.actual_outcome}"
            )

        # Validate confidence_bin is in valid range
        if not 0 <= self.confidence_bin <= 9:
            raise ValueError(
                f"confidence_bin must be between 0 and 9, got {self.confidence_bin}"
            )

        # Validate signal_type is valid
        if not isinstance(self.signal_type, SignalType):
            raise ValueError(
                f"signal_type must be a SignalType enum, got {type(self.signal_type)}"
            )

    @classmethod
    def calculate_confidence_bin(cls, predicted_prob: float, n_bins: int = 10) -> int:
        """Calculate the confidence bin for a given probability.

        Args:
            predicted_prob: Predicted probability (0.0-1.0)
            n_bins: Number of bins (default 10)

        Returns:
            Bin index (0 to n_bins-1)
        """
        if not 0.0 <= predicted_prob <= 1.0:
            raise ValueError(
                f"predicted_prob must be between 0.0 and 1.0, got {predicted_prob}"
            )

        # Calculate bin: floor(prob * n_bins), but cap at n_bins-1 for prob=1.0
        bin_idx = min(int(predicted_prob * n_bins), n_bins - 1)
        return bin_idx

    @property
    def bin_range(self) -> tuple[float, float]:
        """Get the confidence range for this record's bin.

        Returns:
            Tuple of (bin_start, bin_end)
        """
        bin_start = self.confidence_bin / 10.0
        bin_end = (self.confidence_bin + 1) / 10.0
        return (bin_start, bin_end)

    def to_dict(self) -> dict[str, Any]:
        """Convert record to dictionary for serialization.

        Returns:
            Dictionary representation of the record
        """
        return {
            "timestamp": self.timestamp.isoformat(),
            "signal_id": self.signal_id,
            "predicted_prob": round(self.predicted_prob, 6),
            "actual_outcome": self.actual_outcome,
            "signal_type": self.signal_type.value,
            "confidence_bin": self.confidence_bin,
            "strategy_id": self.strategy_id,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CalibrationRecord:
        """Create a CalibrationRecord from a dictionary.

        Args:
            data: Dictionary containing record data

        Returns:
            CalibrationRecord instance
        """
        timestamp_str = data.get("timestamp")
        if timestamp_str:
            timestamp = datetime.fromisoformat(timestamp_str)
        else:
            timestamp = datetime.now(UTC)

        return cls(
            timestamp=timestamp,
            signal_id=data["signal_id"],
            predicted_prob=data["predicted_prob"],
            actual_outcome=data["actual_outcome"],
            signal_type=SignalType(data["signal_type"]),
            confidence_bin=data["confidence_bin"],
            strategy_id=data.get("strategy_id"),
            metadata=data.get("metadata", {}),
        )

    def to_ece_format(self) -> dict[str, float | int]:
        """Convert to format expected by ECE calculation.

        Returns:
            Dictionary with 'confidence' and 'outcome' keys
        """
        return {
            "confidence": self.predicted_prob,
            "outcome": self.actual_outcome,
        }


@dataclass
class CalibrationConfig:
    """Configuration for calibration data collection.

    Attributes:
        n_bins: Number of confidence bins (default 10)
        retention_days: Data retention period in days (default 90)
        default_window: Default collection window for queries
        redis_host: Redis host for storage
        redis_port: Redis port for storage
        redis_db: Redis database number
        key_prefix: Prefix for Redis keys
        enable_compression: Whether to compress stored data
    """

    n_bins: int = 10
    retention_days: int = 90
    default_window: CollectionWindow = CollectionWindow.ONE_DAY
    redis_host: str = "host.docker.internal"
    redis_port: int = 6380
    redis_db: int = 0
    key_prefix: str = "calibration"
    enable_compression: bool = False

    def get_redis_key(self, signal_type: SignalType, date_str: str) -> str:
        """Generate Redis key for a specific signal type and date.

        Args:
            signal_type: Type of signal
            date_str: Date string in YYYY-MM-DD format

        Returns:
            Redis key string
        """
        return f"{self.key_prefix}:{signal_type.value}:{date_str}"

    def get_redis_pattern(self, signal_type: SignalType | None = None) -> str:
        """Generate Redis key pattern for querying.

        Args:
            signal_type: Optional signal type filter

        Returns:
            Redis key pattern
        """
        if signal_type:
            return f"{self.key_prefix}:{signal_type.value}:*"
        return f"{self.key_prefix}:*"

    def to_dict(self) -> dict[str, Any]:
        """Convert config to dictionary."""
        return {
            "n_bins": self.n_bins,
            "retention_days": self.retention_days,
            "default_window": self.default_window.value,
            "redis_host": self.redis_host,
            "redis_port": self.redis_port,
            "redis_db": self.redis_db,
            "key_prefix": self.key_prefix,
            "enable_compression": self.enable_compression,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CalibrationConfig:
        """Create config from dictionary."""
        window_str = data.get("default_window", "24h")
        default_window = CollectionWindow(window_str)

        return cls(
            n_bins=data.get("n_bins", 10),
            retention_days=data.get("retention_days", 90),
            default_window=default_window,
            redis_host=data.get("redis_host", "host.docker.internal"),
            redis_port=data.get("redis_port", 6380),
            redis_db=data.get("redis_db", 0),
            key_prefix=data.get("key_prefix", "calibration"),
            enable_compression=data.get("enable_compression", False),
        )
