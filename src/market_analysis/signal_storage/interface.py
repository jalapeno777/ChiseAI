"""Abstract storage interface for signal history.

Defines the contract that all signal storage implementations must follow.
Supports both InfluxDB and PostgreSQL backends.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from market_analysis.signal_storage.models import (
        OutcomeRecord,
        SignalRecord,
        SignalWithOutcome,
    )


class SignalStorageInterface(ABC):
    """Abstract interface for signal storage backends.

    All storage implementations (InfluxDB, PostgreSQL, etc.) must
    implement this interface to ensure consistent behavior.
    """

    @abstractmethod
    async def store_signal(self, signal: SignalRecord) -> bool:
        """Store a signal record.

        Args:
            signal: SignalRecord to store

        Returns:
            True if stored successfully, False otherwise
        """
        pass

    @abstractmethod
    async def store_outcome(self, outcome: OutcomeRecord) -> bool:
        """Store an outcome record.

        Args:
            outcome: OutcomeRecord to store

        Returns:
            True if stored successfully, False otherwise
        """
        pass

    @abstractmethod
    async def query_signals(
        self,
        token: str | None = None,
        direction: str | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
        indicators: list[str] | None = None,
        timeframes: list[str] | None = None,
        min_confidence: float | None = None,
        max_confidence: float | None = None,
        limit: int = 100,
    ) -> list[SignalRecord]:
        """Query signals with filters.

        Args:
            token: Filter by token (e.g., "BTC")
            direction: Filter by direction ("LONG", "SHORT", "NEUTRAL")
            start_time: Filter by timestamp >= (ms)
            end_time: Filter by timestamp <= (ms)
            indicators: Filter by indicators used (any match)
            timeframes: Filter by timeframes used (any match)
            min_confidence: Minimum confidence level (0.0-1.0)
            max_confidence: Maximum confidence level (0.0-1.0)
            limit: Maximum number of results

        Returns:
            List of SignalRecord matching filters
        """
        pass

    @abstractmethod
    async def get_signal_by_id(self, signal_id: str) -> SignalRecord | None:
        """Get a signal by its unique ID.

        Args:
            signal_id: UUID of the signal

        Returns:
            SignalRecord if found, None otherwise
        """
        pass

    @abstractmethod
    async def get_outcome_by_signal_id(self, signal_id: str) -> OutcomeRecord | None:
        """Get outcome for a signal by signal ID.

        Args:
            signal_id: UUID of the signal

        Returns:
            OutcomeRecord if found, None otherwise
        """
        pass

    @abstractmethod
    async def query_signals_with_outcomes(
        self,
        token: str | None = None,
        direction: str | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
        indicators: list[str] | None = None,
        timeframes: list[str] | None = None,
        min_confidence: float | None = None,
        max_confidence: float | None = None,
        resolved_only: bool = False,
        limit: int = 100,
    ) -> list[SignalWithOutcome]:
        """Query signals with their outcomes.

        Args:
            token: Filter by token
            direction: Filter by direction
            start_time: Filter by timestamp >= (ms)
            end_time: Filter by timestamp <= (ms)
            indicators: Filter by indicators used
            timeframes: Filter by timeframes used
            min_confidence: Minimum confidence level
            max_confidence: Maximum confidence level
            resolved_only: Only return signals with outcomes
            limit: Maximum number of results

        Returns:
            List of SignalWithOutcome
        """
        pass

    @abstractmethod
    async def calculate_prediction_accuracy(
        self,
        signal_type: str | None = None,
        confidence_bucket: str | None = None,
        token: str | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
        indicators: list[str] | None = None,
    ) -> dict[str, Any]:
        """Calculate prediction accuracy metrics.

        Args:
            signal_type: Filter by signal type (e.g., "LONG_rsi_macd")
            confidence_bucket: Filter by confidence bucket (e.g., "70-80")
            token: Filter by token
            start_time: Filter by timestamp >= (ms)
            end_time: Filter by timestamp <= (ms)
            indicators: Filter by indicators used

        Returns:
            Dictionary with accuracy metrics:
            - total_signals: Total number of signals
            - resolved_signals: Number with outcomes
            - wins: Number of winning outcomes
            - losses: Number of losing outcomes
            - accuracy: Win rate (0.0-1.0)
            - win_rate: Same as accuracy
            - avg_pnl: Average PnL
            - total_pnl: Total PnL
            - avg_duration_hours: Average trade duration
        """
        pass

    @abstractmethod
    async def get_unresolved_signals(
        self,
        before_timestamp: int | None = None,
        token: str | None = None,
        limit: int = 100,
    ) -> list[SignalRecord]:
        """Get signals that don't have outcomes yet.

        Args:
            before_timestamp: Only signals before this timestamp (ms)
            token: Filter by token
            limit: Maximum number of results

        Returns:
            List of unresolved SignalRecord
        """
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close the storage connection and cleanup resources."""
        pass

    async def __aenter__(self) -> SignalStorageInterface:
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.close()
