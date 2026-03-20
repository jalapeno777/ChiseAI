"""Base indicator interface and shared types for the indicator plugin system."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Generic, TypeVar

from data_ingestion.ohlcv_fetcher import OHLCVData


class SignalDirection(Enum):
    """Direction of trading signal."""

    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


@dataclass
class Signal:
    """Standardized signal output from any indicator.

    Attributes:
        direction: BUY, SELL, or HOLD
        confidence: 0.0 to 1.0 confidence score
        timestamp: When signal was generated
        metadata: Additional indicator-specific data
    """

    direction: SignalDirection
    confidence: float
    timestamp: datetime
    metadata: dict[str, Any]

    def __post_init__(self) -> None:
        """Validate signal values."""
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"Confidence must be in [0, 1], got {self.confidence}")


T = TypeVar("T")


class BaseIndicator(ABC, Generic[T]):
    """Abstract base class for all technical indicators.

    All indicators must implement this interface for plugin compatibility.
    """

    def __init__(self, name: str | None = None):
        """Initialize indicator.

        Args:
            name: Optional custom name (defaults to class name)
        """
        self._name = name or self.__class__.__name__

    @property
    def name(self) -> str:
        """Get indicator name."""
        return self._name

    @property
    @abstractmethod
    def description(self) -> str:
        """Get human-readable description of the indicator."""
        pass

    @property
    @abstractmethod
    def parameters(self) -> dict[str, Any]:
        """Get current parameter configuration."""
        pass

    @abstractmethod
    def compute(self, data: list[OHLCVData]) -> T:
        """Compute indicator values from OHLCV data.

        Args:
            data: List of OHLCV data points

        Returns:
            Indicator-specific result type
        """
        pass

    @abstractmethod
    def validate(self, data: list[OHLCVData]) -> bool:
        """Validate that data is sufficient for calculation.

        Args:
            data: List of OHLCV data points

        Returns:
            True if data is valid for computation
        """
        pass

    @abstractmethod
    def get_metadata(self) -> dict[str, Any]:
        """Get indicator metadata for serialization.

        Returns:
            Dictionary with name, description, parameters
        """
        pass

    def to_signal(self, result: T) -> Signal:
        """Convert indicator result to standardized signal.

        Args:
            result: Indicator computation result

        Returns:
            Standardized Signal object
        """
        # Default implementation - subclasses should override
        return Signal(
            direction=SignalDirection.HOLD,
            confidence=0.5,
            timestamp=datetime.utcnow(),
            metadata={"indicator": self.name},
        )
