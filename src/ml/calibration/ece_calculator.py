"""Outcome-based ECE Calculator module.

This module provides ECE (Expected Calibration Error) calculation from actual
trade outcomes. It integrates with the outcome capture service from ST-LAUNCH-006
to fetch prediction-outcome pairs and calculate calibration metrics.

Formula: ECE = Σ (n_i / N) * |accuracy_i - confidence_i|

Where:
- n_i = number of samples in bin i
- N = total number of samples
- accuracy_i = actual accuracy in bin i
- confidence_i = average predicted confidence in bin i

Acceptance Criteria:
- 10-bin calibration (0-10%, 10-20%, ..., 90-100%)
- Per-signal-type ECE (entry, exit, SL, TP)
- Daily updates within 5 minutes
- Historical tracking with degradation >0.15 triggers alert
- API endpoint <200ms response

Example:
    >>> from ml.calibration.ece_calculator import OutcomeBasedECECalculator
    >>> from confidence.ece import SignalType
    >>>
    >>> calculator = OutcomeBasedECECalculator()
    >>> result = await calculator.calculate_from_outcomes(
    ...     strategy_id="grid_btc_1h",
    ...     signal_type=SignalType.ENTRY,
    ...     days=30
    ... )
    >>> print(f"ECE: {result.ece:.4f}")
    ECE: 0.0850
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Protocol

from confidence.ece import ECECalculator, ECEResult, SignalType

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PredictionOutcomeRecord:
    """A prediction-outcome pair from the database.

    Attributes:
        prediction_id: Unique identifier for the prediction
        confidence: Predicted confidence score (0.0-1.0)
        outcome: Binary outcome (1=correct, 0=incorrect)
        signal_type: Type of signal (entry, exit, sl, tp)
        strategy_id: Strategy identifier
        timestamp: When the prediction was made
        matched_outcome_id: ID of the matched outcome record
    """

    prediction_id: str
    confidence: float
    outcome: int
    signal_type: SignalType
    strategy_id: str
    timestamp: datetime
    matched_outcome_id: str | None = None


@dataclass(frozen=True)
class ECECalculationRequest:
    """Request parameters for ECE calculation.

    Attributes:
        strategy_id: Strategy identifier (optional for all strategies)
        signal_type: Signal type filter (optional for all types)
        days: Number of days to look back
        min_samples: Minimum samples required for calculation
    """

    strategy_id: str | None = None
    signal_type: SignalType | None = None
    days: int = 30
    min_samples: int = 10


@dataclass(frozen=True)
class ECECalculationResponse:
    """Response from ECE calculation.

    Attributes:
        success: Whether calculation succeeded
        ece_result: ECEResult with ECE value and bin details
        request: Original request parameters
        error_message: Error message if failed
        calculation_time_ms: Time taken for calculation in milliseconds
        sample_count: Number of samples used
    """

    success: bool
    ece_result: ECEResult | None
    request: ECECalculationRequest
    error_message: str | None = None
    calculation_time_ms: float = 0.0
    sample_count: int = 0


class OutcomeDataStore(Protocol):
    """Protocol for outcome data stores.

    Implementations must provide methods to fetch prediction-outcome
    pairs for ECE calculation.
    """

    async def fetch_prediction_outcomes(
        self,
        strategy_id: str | None = None,
        signal_type: SignalType | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> Sequence[PredictionOutcomeRecord]:
        """Fetch prediction-outcome pairs from the store.

        Args:
            strategy_id: Filter by strategy ID
            signal_type: Filter by signal type
            since: Only fetch pairs after this time
            until: Only fetch pairs before this time

        Returns:
            Sequence of prediction-outcome records
        """
        ...

    async def get_sample_count(
        self,
        strategy_id: str | None = None,
        signal_type: SignalType | None = None,
        since: datetime | None = None,
    ) -> int:
        """Get count of available samples without fetching all data.

        Args:
            strategy_id: Filter by strategy ID
            signal_type: Filter by signal type
            since: Only count pairs after this time

        Returns:
            Number of matching samples
        """
        ...


class OutcomeBasedECECalculator:
    """Calculator for ECE from actual trade outcomes.

    This calculator integrates with the outcome capture service to fetch
    prediction-outcome pairs and compute ECE metrics. It supports:
    - 10-bin calibration (0-10%, 10-20%, ..., 90-100%)
    - Per-signal-type breakdown (entry, exit, SL, TP)
    - Multiple strategies

    Example:
        >>> calculator = OutcomeBasedECECalculator(store=outcome_store)
        >>> request = ECECalculationRequest(
        ...     strategy_id="grid_btc_1h",
        ...     signal_type=SignalType.ENTRY,
        ...     days=30
        ... )
        >>> response = await calculator.calculate(request)
        >>> if response.success:
        ...     print(f"ECE: {response.ece_result.ece:.4f}")
    """

    def __init__(
        self,
        store: OutcomeDataStore | None = None,
        n_bins: int = 10,
    ):
        """Initialize the outcome-based ECE calculator.

        Args:
            store: Outcome data store (optional, can be set later)
            n_bins: Number of equal-width confidence bins (default 10)
        """
        self.store = store
        self.n_bins = n_bins
        self._calculator = ECECalculator(n_bins=n_bins)

    def set_store(self, store: OutcomeDataStore) -> None:
        """Set or update the outcome data store.

        Args:
            store: New outcome data store
        """
        self.store = store

    async def calculate(
        self,
        request: ECECalculationRequest,
    ) -> ECECalculationResponse:
        """Calculate ECE from outcomes based on request parameters.

        Args:
            request: ECE calculation request with filters

        Returns:
            ECECalculationResponse with results or error
        """
        start_time = datetime.now(UTC)

        if self.store is None:
            return ECECalculationResponse(
                success=False,
                ece_result=None,
                request=request,
                error_message="Outcome data store not initialized",
                calculation_time_ms=0.0,
            )

        try:
            # Calculate time range
            since = datetime.now(UTC) - timedelta(days=request.days)

            # Fetch prediction-outcome pairs
            records = await self.store.fetch_prediction_outcomes(
                strategy_id=request.strategy_id,
                signal_type=request.signal_type,
                since=since,
            )

            # Validate sample count
            if len(records) < request.min_samples:
                error_msg = (
                    f"Insufficient samples for ECE calculation: "
                    f"{len(records)} < {request.min_samples}"
                )
                return ECECalculationResponse(
                    success=False,
                    ece_result=None,
                    request=request,
                    error_message=error_msg,
                    calculation_time_ms=self._elapsed_ms(start_time),
                    sample_count=len(records),
                )

            # Extract predictions and outcomes
            predictions = [r.confidence for r in records]
            outcomes = [r.outcome for r in records]

            # Calculate ECE
            ece_result = self._calculator.calculate(
                predictions=predictions,
                outcomes=outcomes,
                signal_type=request.signal_type,
                strategy_id=request.strategy_id,
            )

            calculation_time_ms = self._elapsed_ms(start_time)

            logger.info(
                f"ECE calculation completed: ECE={ece_result.ece:.4f}, "
                f"samples={len(records)}, time={calculation_time_ms:.2f}ms, "
                f"strategy={request.strategy_id}, signal_type={request.signal_type}"
            )

            return ECECalculationResponse(
                success=True,
                ece_result=ece_result,
                request=request,
                calculation_time_ms=calculation_time_ms,
                sample_count=len(records),
            )

        except Exception as e:
            logger.exception("ECE calculation failed")
            return ECECalculationResponse(
                success=False,
                ece_result=None,
                request=request,
                error_message=str(e),
                calculation_time_ms=self._elapsed_ms(start_time),
            )

    async def calculate_from_outcomes(
        self,
        strategy_id: str,
        signal_type: SignalType | None = None,
        days: int = 30,
        min_samples: int = 10,
    ) -> ECEResult:
        """Convenience method to calculate ECE with simple parameters.

        Args:
            strategy_id: Strategy identifier
            signal_type: Optional signal type filter
            days: Number of days to look back
            min_samples: Minimum samples required

        Returns:
            ECEResult with ECE value and bin details

        Raises:
            ValueError: If store not initialized or insufficient samples
        """
        request = ECECalculationRequest(
            strategy_id=strategy_id,
            signal_type=signal_type,
            days=days,
            min_samples=min_samples,
        )

        response = await self.calculate(request)

        if not response.success:
            raise ValueError(response.error_message or "ECE calculation failed")

        if response.ece_result is None:
            raise ValueError("ECE calculation returned no result")

        return response.ece_result

    async def calculate_per_signal_type(
        self,
        strategy_id: str,
        days: int = 30,
        min_samples: int = 10,
    ) -> dict[SignalType, ECECalculationResponse]:
        """Calculate ECE separately for each signal type.

        Args:
            strategy_id: Strategy identifier
            days: Number of days to look back
            min_samples: Minimum samples per signal type

        Returns:
            Dict mapping signal type to ECECalculationResponse
        """
        results: dict[SignalType, ECECalculationResponse] = {}

        for signal_type in SignalType:
            request = ECECalculationRequest(
                strategy_id=strategy_id,
                signal_type=signal_type,
                days=days,
                min_samples=min_samples,
            )

            response = await self.calculate(request)
            results[signal_type] = response

        return results

    async def calculate_all_strategies(
        self,
        days: int = 30,
        min_samples: int = 10,
    ) -> dict[str, ECECalculationResponse]:
        """Calculate ECE for all available strategies.

        Note: This requires the store to support listing strategies.

        Args:
            days: Number of days to look back
            min_samples: Minimum samples per strategy

        Returns:
            Dict mapping strategy_id to ECECalculationResponse
        """
        results: dict[str, ECECalculationResponse] = {}

        # Get all unique strategy IDs from records
        since = datetime.now(UTC) - timedelta(days=days)

        if self.store is None:
            return results

        # Fetch all records and group by strategy
        records = await self.store.fetch_prediction_outcomes(since=since)

        strategy_ids = {r.strategy_id for r in records}

        for strategy_id in strategy_ids:
            request = ECECalculationRequest(
                strategy_id=strategy_id,
                days=days,
                min_samples=min_samples,
            )

            response = await self.calculate(request)
            results[strategy_id] = response

        return results

    def _elapsed_ms(self, start_time: datetime) -> float:
        """Calculate elapsed time in milliseconds.

        Args:
            start_time: Start timestamp

        Returns:
            Elapsed time in milliseconds
        """
        return (datetime.now(UTC) - start_time).total_seconds() * 1000


class InMemoryOutcomeDataStore:
    """In-memory implementation of OutcomeDataStore for testing.

    Stores prediction-outcome records in memory. Suitable for testing
    and development, not for production use.

    Example:
        >>> store = InMemoryOutcomeDataStore()
        >>> record = PredictionOutcomeRecord(
        ...     prediction_id="pred-001",
        ...     confidence=0.85,
        ...     outcome=1,
        ...     signal_type=SignalType.ENTRY,
        ...     strategy_id="grid_btc_1h",
        ...     timestamp=datetime.now(UTC)
        ... )
        >>> await store.add_record(record)
        >>> records = await store.fetch_prediction_outcomes()
    """

    def __init__(self):
        """Initialize empty in-memory store."""
        self._records: list[PredictionOutcomeRecord] = []

    async def add_record(self, record: PredictionOutcomeRecord) -> None:
        """Add a prediction-outcome record to the store.

        Args:
            record: Record to add
        """
        self._records.append(record)

    async def add_records(self, records: Sequence[PredictionOutcomeRecord]) -> int:
        """Add multiple records to the store.

        Args:
            records: Records to add

        Returns:
            Number of records added
        """
        self._records.extend(records)
        return len(records)

    async def clear(self) -> None:
        """Clear all records from the store."""
        self._records.clear()

    async def fetch_prediction_outcomes(
        self,
        strategy_id: str | None = None,
        signal_type: SignalType | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> Sequence[PredictionOutcomeRecord]:
        """Fetch prediction-outcome records from the store.

        Args:
            strategy_id: Filter by strategy ID
            signal_type: Filter by signal type
            since: Only fetch records after this time
            until: Only fetch records before this time

        Returns:
            Sequence of matching records
        """
        result = self._records.copy()

        if strategy_id:
            result = [r for r in result if r.strategy_id == strategy_id]
        if signal_type:
            result = [r for r in result if r.signal_type == signal_type]
        if since:
            result = [r for r in result if r.timestamp >= since]
        if until:
            result = [r for r in result if r.timestamp <= until]

        return result

    async def get_sample_count(
        self,
        strategy_id: str | None = None,
        signal_type: SignalType | None = None,
        since: datetime | None = None,
    ) -> int:
        """Get count of available samples.

        Args:
            strategy_id: Filter by strategy ID
            signal_type: Filter by signal type
            since: Only count records after this time

        Returns:
            Number of matching samples
        """
        records = await self.fetch_prediction_outcomes(
            strategy_id=strategy_id,
            signal_type=signal_type,
            since=since,
        )
        return len(records)


async def calculate_ece_from_outcomes(
    store: OutcomeDataStore,
    strategy_id: str,
    signal_type: SignalType | None = None,
    days: int = 30,
    n_bins: int = 10,
) -> ECEResult:
    """Convenience function to calculate ECE from outcomes.

    Args:
        store: Outcome data store
        strategy_id: Strategy identifier
        signal_type: Optional signal type filter
        days: Number of days to look back
        n_bins: Number of bins for ECE calculation

    Returns:
        ECEResult with ECE value

    Raises:
        ValueError: If insufficient samples or calculation fails
    """
    calculator = OutcomeBasedECECalculator(store=store, n_bins=n_bins)
    return await calculator.calculate_from_outcomes(
        strategy_id=strategy_id,
        signal_type=signal_type,
        days=days,
    )
