"""Signal tracking and outcome matching logic.

Provides the SignalTracker class for storing signals, recording outcomes,
and matching signals with their outcomes for performance analysis.
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from market_analysis.signal_storage.interface import SignalStorageInterface
    from market_analysis.signal_storage.models import SignalDirection

from market_analysis.confluence.scorer import ConfluenceScore
from market_analysis.signal_storage.models import (
    OutcomeRecord,
    OutcomeType,
    SignalRecord,
    SignalWithOutcome,
)

logger = logging.getLogger(__name__)


class SignalTracker:
    """Tracks signals and matches them with outcomes for performance analysis.

    The SignalTracker provides a high-level interface for:
    - Storing signals with unique UUIDs
    - Recording outcomes linked to signals
    - Querying signal history with various filters
    - Finding unresolved signals that need outcome tracking

    Attributes:
        storage: Backend storage implementation (InfluxDB or PostgreSQL)
        outcome_matching_window_hours: Default window for matching outcomes to signals
    """

    def __init__(
        self,
        storage: SignalStorageInterface,
        outcome_matching_window_hours: float = 24.0,
    ):
        """Initialize signal tracker.

        Args:
            storage: Storage backend implementation
            outcome_matching_window_hours: Default matching window in hours
        """
        self.storage = storage
        self.outcome_matching_window_hours = outcome_matching_window_hours

    async def store_signal(
        self,
        token: str,
        timestamp: int,
        direction: SignalDirection,
        confidence: float,
        entry_price: float,
        score: float,
        indicators_used: list[str],
        timeframes_used: list[str],
        multiplier_applied: float | None = None,
        metadata: dict[str, Any] | None = None,
        signal_id: str | None = None,
    ) -> SignalRecord:
        """Store a new signal.

        Args:
            token: Trading pair token (e.g., "BTC")
            timestamp: Unix timestamp in milliseconds
            direction: Signal direction (LONG/SHORT/NEUTRAL)
            confidence: Confidence level (0.0-1.0)
            entry_price: Entry price at signal time
            score: Confluence score (0-100)
            indicators_used: List of indicator types used
            timeframes_used: List of timeframes used
            multiplier_applied: Confidence multiplier applied (if any)
            metadata: Additional metadata
            signal_id: Optional custom signal ID (UUID generated if not provided)

        Returns:
            The stored SignalRecord
        """
        signal = SignalRecord(
            signal_id=signal_id or str(uuid.uuid4()),
            token=token,
            timestamp=timestamp,
            direction=direction,
            confidence=confidence,
            entry_price=entry_price,
            score=score,
            indicators_used=indicators_used,
            timeframes_used=timeframes_used,
            multiplier_applied=multiplier_applied,
            metadata=metadata or {},
        )

        success = await self.storage.store_signal(signal)
        if success:
            logger.info(
                f"Stored signal {signal.signal_id} for {token} "
                f"[{direction.value}] confidence={confidence:.2%}"
            )
        else:
            logger.error(f"Failed to store signal for {token}")

        return signal

    async def store_signal_from_confluence(
        self,
        token: str,
        timestamp: int,
        entry_price: float,
        confluence_score: "ConfluenceScore",
        indicators_used: list[str] | None = None,
        timeframes_used: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SignalRecord:
        """Store a signal from a ConfluenceScore result.

        Convenience method that extracts signal data from a ConfluenceScore.

        Args:
            token: Trading pair token
            timestamp: Unix timestamp in milliseconds
            entry_price: Entry price at signal time
            confluence_score: ConfluenceScore result
            indicators_used: Override indicators (auto-detected if None)
            timeframes_used: Override timeframes (auto-detected if None)
            metadata: Additional metadata

        Returns:
            The stored SignalRecord
        """
        from market_analysis.signal_storage.models import SignalDirection

        # Extract indicators and timeframes from signal breakdown if not provided
        if indicators_used is None:
            indicators_used = list(
                confluence_score.signal_breakdown.get("by_indicator", {}).keys()
            )

        if timeframes_used is None:
            timeframes_used = list(
                confluence_score.signal_breakdown.get("by_timeframe", {}).keys()
            )

        # Map ConfluenceScore direction to SignalDirection (models)
        direction = confluence_score.direction
        if isinstance(direction, str):
            direction = SignalDirection(direction)
        elif direction is not None:
            # Convert from signal_aggregator.SignalDirection to models.SignalDirection
            direction = SignalDirection(direction.value)

        return await self.store_signal(
            token=token,
            timestamp=timestamp,
            direction=direction,
            confidence=confluence_score.confidence,
            entry_price=entry_price,
            score=confluence_score.score,
            indicators_used=indicators_used,
            timeframes_used=timeframes_used,
            multiplier_applied=confluence_score.multiplier_applied,
            metadata={
                "confluence_score": confluence_score.to_dict(),
                **(metadata or {}),
            },
        )

    async def record_outcome(
        self,
        signal_id: str,
        exit_timestamp: int,
        is_win: bool,
        pnl: float,
        exit_price: float,
        duration_hours: float,
        outcome_type: OutcomeType = OutcomeType.UNKNOWN,
        note: str | None = None,
    ) -> OutcomeRecord:
        """Record an outcome for a signal.

        Args:
            signal_id: UUID of the signal this outcome belongs to
            exit_timestamp: Unix timestamp in milliseconds when position closed
            is_win: True if the outcome was profitable
            pnl: Profit/loss amount
            exit_price: Exit price when position closed
            duration_hours: Duration of the trade in hours
            outcome_type: Type of outcome (tp_hit, sl_hit, etc.)
            note: Optional notes

        Returns:
            The stored OutcomeRecord
        """
        outcome = OutcomeRecord(
            signal_id=signal_id,
            exit_timestamp=exit_timestamp,
            is_win=is_win,
            pnl=pnl,
            exit_price=exit_price,
            duration_hours=duration_hours,
            outcome_type=outcome_type,
            note=note,
        )

        success = await self.storage.store_outcome(outcome)
        if success:
            logger.info(
                f"Recorded outcome for signal {signal_id}: win={is_win}, pnl={pnl:.4f}"
            )
        else:
            logger.error(f"Failed to record outcome for signal {signal_id}")

        return outcome

    async def get_signal_history(
        self,
        token: str | None = None,
        direction: str | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
        indicators: list[str] | None = None,
        timeframes: list[str] | None = None,
        min_confidence: float | None = None,
        max_confidence: float | None = None,
        include_outcomes: bool = True,
        limit: int = 100,
    ) -> list[SignalWithOutcome]:
        """Query signal history with filters.

        Args:
            token: Filter by token
            direction: Filter by direction ("LONG", "SHORT", "NEUTRAL")
            start_time: Filter by timestamp >= (ms)
            end_time: Filter by timestamp <= (ms)
            indicators: Filter by indicators used
            timeframes: Filter by timeframes used
            min_confidence: Minimum confidence level
            max_confidence: Maximum confidence level
            include_outcomes: Include outcome data if available
            limit: Maximum number of results

        Returns:
            List of SignalWithOutcome
        """
        if include_outcomes:
            return await self.storage.query_signals_with_outcomes(
                token=token,
                direction=direction,
                start_time=start_time,
                end_time=end_time,
                indicators=indicators,
                timeframes=timeframes,
                min_confidence=min_confidence,
                max_confidence=max_confidence,
                limit=limit,
            )
        else:
            signals = await self.storage.query_signals(
                token=token,
                direction=direction,
                start_time=start_time,
                end_time=end_time,
                indicators=indicators,
                timeframes=timeframes,
                min_confidence=min_confidence,
                max_confidence=max_confidence,
                limit=limit,
            )
            return [SignalWithOutcome(signal=s, outcome=None) for s in signals]

    async def get_signal_by_id(self, signal_id: str) -> SignalWithOutcome | None:
        """Get a signal and its outcome by ID.

        Args:
            signal_id: UUID of the signal

        Returns:
            SignalWithOutcome if found, None otherwise
        """
        signal = await self.storage.get_signal_by_id(signal_id)
        if signal is None:
            return None

        outcome = await self.storage.get_outcome_by_signal_id(signal_id)
        return SignalWithOutcome(signal=signal, outcome=outcome)

    async def get_unresolved_signals(
        self,
        before_timestamp: int | None = None,
        token: str | None = None,
        limit: int = 100,
    ) -> list[SignalRecord]:
        """Get signals that don't have outcomes yet.

        Useful for finding signals that need outcome tracking.

        Args:
            before_timestamp: Only signals before this timestamp (ms)
            token: Filter by token
            limit: Maximum number of results

        Returns:
            List of unresolved SignalRecord
        """
        return await self.storage.get_unresolved_signals(
            before_timestamp=before_timestamp,
            token=token,
            limit=limit,
        )

    async def find_signals_needing_outcomes(
        self,
        token: str | None = None,
        limit: int = 100,
    ) -> list[SignalRecord]:
        """Find signals that likely need outcomes recorded.

        Returns signals that:
        1. Don't have outcomes yet
        2. Were generated before the outcome matching window

        Args:
            token: Filter by token
            limit: Maximum number of results

        Returns:
            List of SignalRecord needing outcomes
        """
        import time

        # Calculate cutoff time (signals older than matching window)
        window_ms = int(self.outcome_matching_window_hours * 3600 * 1000)
        cutoff_timestamp = int(time.time() * 1000) - window_ms

        return await self.get_unresolved_signals(
            before_timestamp=cutoff_timestamp,
            token=token,
            limit=limit,
        )

    async def close(self) -> None:
        """Close the storage connection."""
        await self.storage.close()

    async def __aenter__(self) -> SignalTracker:
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.close()
