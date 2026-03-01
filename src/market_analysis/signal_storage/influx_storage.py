"""InfluxDB storage implementation for signal history.

Stores signals and outcomes in InfluxDB for efficient time-series queries.
Uses line protocol for high-throughput writes and Flux for queries.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from influxdb_client import InfluxDBClient
    from influxdb_client.client.write_api import WriteApi

from datetime import UTC

from market_analysis.signal_storage.interface import SignalStorageInterface
from market_analysis.signal_storage.models import (
    OutcomeRecord,
    OutcomeType,
    SignalDirection,
    SignalRecord,
    SignalWithOutcome,
)

logger = logging.getLogger(__name__)


class InfluxSignalStorage(SignalStorageInterface):
    """InfluxDB implementation of signal storage.

    Stores signals in 'trading_signals' measurement and outcomes in
    'trading_outcomes' measurement for efficient time-series queries.

    Schema:
        trading_signals:
            - measurement: trading_signals
            - tags: token, direction, signal_id, confidence_bucket
            - fields: confidence, entry_price, score, multiplier_applied,
                      indicators_used, timeframes_used
            - timestamp: signal timestamp

        trading_outcomes:
            - measurement: trading_outcomes
            - tags: signal_id, outcome_type
            - fields: is_win, pnl, exit_price, duration_hours, note
            - timestamp: exit timestamp
    """

    def __init__(
        self,
        client: InfluxDBClient | None = None,
        url: str = os.getenv("INFLUXDB_URL", "http://host.docker.internal:18087"),
        token: str = "",  # nosec B107 - empty default for optional param
        org: str = "chiseai",
        bucket: str = "signals",
    ):
        """Initialize InfluxDB storage.

        Args:
            client: Existing InfluxDB client (optional)
            url: InfluxDB URL (used if client not provided)
            token: InfluxDB token (used if client not provided)
            org: InfluxDB organization
            bucket: Bucket name for signals data
        """
        self.org = org
        self.bucket = bucket
        self._client = client
        self._url = url
        self._token = token
        self._write_api: WriteApi | None = None
        self._owned_client = client is None

    async def _get_client(self) -> InfluxDBClient:
        """Get or create InfluxDB client."""
        if self._client is None:
            from influxdb_client import InfluxDBClient

            self._client = InfluxDBClient(
                url=self._url,
                token=self._token,
                org=self.org,
            )
        return self._client

    async def _get_write_api(self) -> WriteApi:
        """Get or create write API."""
        if self._write_api is None:
            client = await self._get_client()
            self._write_api = client.write_api()
        return self._write_api

    async def store_signal(self, signal: SignalRecord) -> bool:
        """Store a signal record in InfluxDB.

        Args:
            signal: SignalRecord to store

        Returns:
            True if stored successfully
        """
        try:
            from influxdb_client import Point

            point = (
                Point("trading_signals")
                .tag("token", signal.token)
                .tag("direction", signal.direction.value)
                .tag("signal_id", signal.signal_id)
                .tag("confidence_bucket", signal.confidence_bucket)
                .field("confidence", signal.confidence)
                .field("entry_price", signal.entry_price)
                .field("score", signal.score)
                .field(
                    "multiplier_applied",
                    signal.multiplier_applied if signal.multiplier_applied else 0.0,
                )
                .field(
                    "indicators_used",
                    ",".join(signal.indicators_used) if signal.indicators_used else "",
                )
                .field(
                    "timeframes_used",
                    ",".join(signal.timeframes_used) if signal.timeframes_used else "",
                )
                .time(signal.timestamp)
            )

            write_api = await self._get_write_api()
            write_api.write(bucket=self.bucket, org=self.org, record=point)

            logger.debug(f"Stored signal {signal.signal_id} in InfluxDB")
            return True

        except Exception as e:
            logger.error(f"Failed to store signal: {e}")
            return False

    async def store_outcome(self, outcome: OutcomeRecord) -> bool:
        """Store an outcome record in InfluxDB.

        Args:
            outcome: OutcomeRecord to store

        Returns:
            True if stored successfully
        """
        try:
            from influxdb_client import Point

            point = (
                Point("trading_outcomes")
                .tag("signal_id", outcome.signal_id)
                .tag("outcome_type", outcome.outcome_type.value)
                .field("is_win", outcome.is_win)
                .field("pnl", outcome.pnl)
                .field("exit_price", outcome.exit_price)
                .field("duration_hours", outcome.duration_hours)
                .field("note", outcome.note or "")
                .time(outcome.exit_timestamp)
            )

            write_api = await self._get_write_api()
            write_api.write(bucket=self.bucket, org=self.org, record=point)

            logger.debug(f"Stored outcome for signal {outcome.signal_id} in InfluxDB")
            return True

        except Exception as e:
            logger.error(f"Failed to store outcome: {e}")
            return False

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
            token: Filter by token
            direction: Filter by direction
            start_time: Filter by timestamp >= (ms)
            end_time: Filter by timestamp <= (ms)
            indicators: Filter by indicators used
            timeframes: Filter by timeframes used
            min_confidence: Minimum confidence level
            max_confidence: Maximum confidence level
            limit: Maximum number of results

        Returns:
            List of SignalRecord
        """
        try:
            client = await self._get_client()
            query_api = client.query_api()

            # Build Flux query - let Flux use execution time when no end_time
            flux = f"""
                from(bucket: "{self.bucket}")
                    |> range(start: {
                self._ms_to_rfc3339(start_time) if start_time else -30
            })
                    |> filter(fn: (r) => r._measurement == "trading_signals")
            """

            if token:
                flux += f'    |> filter(fn: (r) => r.token == "{token}")\n'
            if direction:
                flux += f'    |> filter(fn: (r) => r.direction == "{direction}")\n'
            if min_confidence is not None:
                flux += f"    |> filter(fn: (r) => r.confidence >= {min_confidence})\n"
            if max_confidence is not None:
                flux += f"    |> filter(fn: (r) => r.confidence <= {max_confidence})\n"

            flux += f"    |> limit(n: {limit})\n"

            tables = query_api.query(flux, org=self.org)

            signals = []
            for table in tables:
                for record in table.records:
                    signal = self._record_to_signal(record)
                    if signal:
                        # Filter by indicators/timeframes in Python
                        if indicators and not any(
                            ind in signal.indicators_used for ind in indicators
                        ):
                            continue
                        if timeframes and not any(
                            tf in signal.timeframes_used for tf in timeframes
                        ):
                            continue
                        signals.append(signal)

            return signals

        except Exception as e:
            logger.error(f"Failed to query signals: {e}")
            return []

    async def get_signal_by_id(self, signal_id: str) -> SignalRecord | None:
        """Get a signal by its unique ID.

        Args:
            signal_id: UUID of the signal

        Returns:
            SignalRecord if found, None otherwise
        """
        try:
            client = await self._get_client()
            query_api = client.query_api()

            flux = f"""
                from(bucket: "{self.bucket}")
                    |> range(start: -365d)
                    |> filter(fn: (r) => r._measurement == "trading_signals")
                    |> filter(fn: (r) => r.signal_id == "{signal_id}")
                    |> limit(n: 1)
            """

            tables = query_api.query(flux, org=self.org)

            for table in tables:
                for record in table.records:
                    return self._record_to_signal(record)

            return None

        except Exception as e:
            logger.error(f"Failed to get signal by ID: {e}")
            return None

    async def get_outcome_by_signal_id(self, signal_id: str) -> OutcomeRecord | None:
        """Get outcome for a signal by signal ID.

        Args:
            signal_id: UUID of the signal

        Returns:
            OutcomeRecord if found, None otherwise
        """
        try:
            client = await self._get_client()
            query_api = client.query_api()

            flux = f"""
                from(bucket: "{self.bucket}")
                    |> range(start: -365d)
                    |> filter(fn: (r) => r._measurement == "trading_outcomes")
                    |> filter(fn: (r) => r.signal_id == "{signal_id}")
                    |> limit(n: 1)
            """

            tables = query_api.query(flux, org=self.org)

            for table in tables:
                for record in table.records:
                    return self._record_to_outcome(record)

            return None

        except Exception as e:
            logger.error(f"Failed to get outcome by signal ID: {e}")
            return None

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
        signals = await self.query_signals(
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

        result = []
        for signal in signals:
            outcome = await self.get_outcome_by_signal_id(signal.signal_id)
            if resolved_only and outcome is None:
                continue
            result.append(SignalWithOutcome(signal=signal, outcome=outcome))

        return result

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
            signal_type: Filter by signal type
            confidence_bucket: Filter by confidence bucket
            token: Filter by token
            start_time: Filter by timestamp >= (ms)
            end_time: Filter by timestamp <= (ms)
            indicators: Filter by indicators used

        Returns:
            Dictionary with accuracy metrics
        """
        signals_with_outcomes = await self.query_signals_with_outcomes(
            token=token,
            start_time=start_time,
            end_time=end_time,
            indicators=indicators,
            resolved_only=True,
            limit=10000,
        )

        # Filter by signal_type and confidence_bucket if specified
        filtered = []
        for swo in signals_with_outcomes:
            if signal_type and swo.signal.signal_type != signal_type:
                continue
            if confidence_bucket and swo.signal.confidence_bucket != confidence_bucket:
                continue
            filtered.append(swo)

        if not filtered:
            return {
                "total_signals": 0,
                "resolved_signals": 0,
                "wins": 0,
                "losses": 0,
                "accuracy": 0.0,
                "win_rate": 0.0,
                "avg_pnl": 0.0,
                "total_pnl": 0.0,
                "avg_duration_hours": 0.0,
            }

        wins = sum(1 for swo in filtered if swo.outcome and swo.outcome.is_win)
        losses = len(filtered) - wins
        total_pnl = sum(swo.outcome.pnl for swo in filtered if swo.outcome)
        avg_pnl = total_pnl / len(filtered) if filtered else 0.0
        avg_duration = (
            sum(swo.outcome.duration_hours for swo in filtered if swo.outcome)
            / len(filtered)
            if filtered
            else 0.0
        )

        accuracy = wins / len(filtered) if filtered else 0.0

        return {
            "total_signals": len(filtered),
            "resolved_signals": len(filtered),
            "wins": wins,
            "losses": losses,
            "accuracy": round(accuracy, 4),
            "win_rate": round(accuracy, 4),
            "avg_pnl": round(avg_pnl, 8),
            "total_pnl": round(total_pnl, 8),
            "avg_duration_hours": round(avg_duration, 2),
        }

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
        # Get all signals and filter out those with outcomes
        signals = await self.query_signals(
            token=token,
            end_time=before_timestamp,
            limit=limit * 2,  # Get more to account for filtering
        )

        unresolved = []
        for signal in signals:
            outcome = await self.get_outcome_by_signal_id(signal.signal_id)
            if outcome is None:
                unresolved.append(signal)
                if len(unresolved) >= limit:
                    break

        return unresolved[:limit]

    async def close(self) -> None:
        """Close the storage connection."""
        if self._write_api:
            self._write_api.close()
            self._write_api = None
        if self._owned_client and self._client:
            self._client.close()
            self._client = None

    def _ms_to_rfc3339(self, timestamp_ms: int) -> str:
        """Convert millisecond timestamp to RFC3339 string."""
        from datetime import datetime

        dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC)
        return dt.isoformat()

    def _record_to_signal(self, record: Any) -> SignalRecord | None:
        """Convert InfluxDB record to SignalRecord."""
        try:
            values = record.values
            return SignalRecord(
                signal_id=values.get("signal_id", ""),
                token=values.get("token", ""),
                timestamp=int(record.get_time().timestamp() * 1000),
                direction=SignalDirection(values.get("direction", "NEUTRAL")),
                confidence=values.get("confidence", 0.0),
                entry_price=values.get("entry_price", 0.0),
                score=values.get("score", 0.0),
                multiplier_applied=values.get("multiplier_applied") or None,
                indicators_used=(
                    values.get("indicators_used", "").split(",")
                    if values.get("indicators_used")
                    else []
                ),
                timeframes_used=(
                    values.get("timeframes_used", "").split(",")
                    if values.get("timeframes_used")
                    else []
                ),
            )
        except Exception as e:
            logger.error(f"Failed to convert record to signal: {e}")
            return None

    def _record_to_outcome(self, record: Any) -> OutcomeRecord | None:
        """Convert InfluxDB record to OutcomeRecord."""
        try:
            values = record.values
            outcome_type_str = values.get("outcome_type", "unknown")
            try:
                outcome_type = OutcomeType(outcome_type_str)
            except ValueError:
                outcome_type = OutcomeType.UNKNOWN

            return OutcomeRecord(
                signal_id=values.get("signal_id", ""),
                exit_timestamp=int(record.get_time().timestamp() * 1000),
                is_win=values.get("is_win", False),
                pnl=values.get("pnl", 0.0),
                exit_price=values.get("exit_price", 0.0),
                duration_hours=values.get("duration_hours", 0.0),
                outcome_type=outcome_type,
                note=values.get("note") or None,
            )
        except Exception as e:
            logger.error(f"Failed to convert record to outcome: {e}")
            return None
