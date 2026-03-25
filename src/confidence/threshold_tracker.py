"""Threshold history tracking module.

Tracks historical threshold adjustments and mode switches with
persistent storage support for audit trails and analysis.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

from confidence.threshold import (
    ModeSwitchRecord,
    ThresholdAdjustment,
    ThresholdConfig,
    ThresholdMode,
)

logger = logging.getLogger(__name__)


class ThresholdHistoryTracker(ABC):
    """Abstract base class for threshold history tracking.

    Implementations must provide persistent storage for threshold
    adjustments and mode switches with full audit trail capabilities.
    """

    @abstractmethod
    async def record_adjustment(self, adjustment: ThresholdAdjustment) -> bool:
        """Record a threshold adjustment.

        Args:
            adjustment: The adjustment to record

        Returns:
            True if successfully recorded
        """
        ...

    @abstractmethod
    async def record_mode_switch(self, mode_switch: ModeSwitchRecord) -> bool:
        """Record a mode switch.

        Args:
            mode_switch: The mode switch to record

        Returns:
            True if successfully recorded
        """
        ...

    @abstractmethod
    async def record_config_change(
        self, config: ThresholdConfig, change_type: str
    ) -> bool:
        """Record a configuration change.

        Args:
            config: The configuration
            change_type: Type of change ("create", "update", "delete")

        Returns:
            True if successfully recorded
        """
        ...

    @abstractmethod
    async def get_adjustment_history(
        self,
        strategy_id: str | None = None,
        days: int = 30,
        adjustment_type: str | None = None,
    ) -> list[ThresholdAdjustment]:
        """Get adjustment history.

        Args:
            strategy_id: Optional strategy filter
            days: Number of days to look back
            adjustment_type: Optional filter by adjustment type

        Returns:
            List of threshold adjustments
        """
        ...

    @abstractmethod
    async def get_mode_switch_history(
        self,
        strategy_id: str | None = None,
        days: int = 30,
    ) -> list[ModeSwitchRecord]:
        """Get mode switch history.

        Args:
            strategy_id: Optional strategy filter
            days: Number of days to look back

        Returns:
            List of mode switch records
        """
        ...

    @abstractmethod
    async def get_latest_adjustment(
        self, strategy_id: str
    ) -> ThresholdAdjustment | None:
        """Get the most recent adjustment for a strategy.

        Args:
            strategy_id: Strategy identifier

        Returns:
            Most recent adjustment or None
        """
        ...

    @abstractmethod
    async def get_adjustment_count(
        self,
        strategy_id: str | None = None,
        days: int = 30,
    ) -> int:
        """Get count of adjustments.

        Args:
            strategy_id: Optional strategy filter
            days: Number of days to look back

        Returns:
            Number of adjustments
        """
        ...

    @abstractmethod
    async def get_strategies_with_adjustments(self, days: int = 30) -> list[str]:
        """Get list of strategies that have had adjustments.

        Args:
            days: Number of days to look back

        Returns:
            List of strategy IDs
        """
        ...


@dataclass
class InMemoryThresholdTracker(ThresholdHistoryTracker):
    """In-memory implementation of threshold history tracker.

    Stores all history in memory. Suitable for testing and short-lived
    applications. Data is lost when the process exits.

    Example:
        >>> tracker = InMemoryThresholdTracker()
        >>> await tracker.record_adjustment(adjustment)
        >>> history = await tracker.get_adjustment_history("grid_btc_1h")
    """

    _adjustments: list[ThresholdAdjustment] = field(default_factory=list)
    _mode_switches: list[ModeSwitchRecord] = field(default_factory=list)
    _config_changes: list[dict[str, Any]] = field(default_factory=list)

    async def record_adjustment(self, adjustment: ThresholdAdjustment) -> bool:
        """Record a threshold adjustment in memory.

        Args:
            adjustment: The adjustment to record

        Returns:
            True (always succeeds for in-memory storage)
        """
        self._adjustments.append(adjustment)
        logger.debug(
            f"Recorded adjustment for {adjustment.strategy_id}: "
            f"{adjustment.old_value:.2%} -> {adjustment.new_value:.2%}"
        )
        return True

    async def record_mode_switch(self, mode_switch: ModeSwitchRecord) -> bool:
        """Record a mode switch in memory.

        Args:
            mode_switch: The mode switch to record

        Returns:
            True (always succeeds for in-memory storage)
        """
        self._mode_switches.append(mode_switch)
        logger.debug(
            f"Recorded mode switch for {mode_switch.strategy_id}: "
            f"{mode_switch.old_mode.value} -> {mode_switch.new_mode.value}"
        )
        return True

    async def record_config_change(
        self, config: ThresholdConfig, change_type: str
    ) -> bool:
        """Record a configuration change in memory.

        Args:
            config: The configuration
            change_type: Type of change

        Returns:
            True (always succeeds for in-memory storage)
        """
        self._config_changes.append(
            {
                "config": config,
                "change_type": change_type,
                "recorded_at": datetime.now(UTC),
            }
        )
        logger.debug(f"Recorded config change for {config.strategy_id}: {change_type}")
        return True

    async def get_adjustment_history(
        self,
        strategy_id: str | None = None,
        days: int = 30,
        adjustment_type: str | None = None,
    ) -> list[ThresholdAdjustment]:
        """Get adjustment history from memory.

        Args:
            strategy_id: Optional strategy filter
            days: Number of days to look back
            adjustment_type: Optional filter by adjustment type

        Returns:
            List of threshold adjustments
        """
        cutoff = datetime.now(UTC) - timedelta(days=days)

        filtered = [
            adj
            for adj in self._adjustments
            if adj.timestamp >= cutoff
            and (strategy_id is None or adj.strategy_id == strategy_id)
            and (adjustment_type is None or adj.adjustment_type == adjustment_type)
        ]

        return sorted(filtered, key=lambda x: x.timestamp)

    async def get_mode_switch_history(
        self,
        strategy_id: str | None = None,
        days: int = 30,
    ) -> list[ModeSwitchRecord]:
        """Get mode switch history from memory.

        Args:
            strategy_id: Optional strategy filter
            days: Number of days to look back

        Returns:
            List of mode switch records
        """
        cutoff = datetime.now(UTC) - timedelta(days=days)

        filtered = [
            switch
            for switch in self._mode_switches
            if switch.timestamp >= cutoff
            and (strategy_id is None or switch.strategy_id == strategy_id)
        ]

        return sorted(filtered, key=lambda x: x.timestamp)

    async def get_latest_adjustment(
        self, strategy_id: str
    ) -> ThresholdAdjustment | None:
        """Get the most recent adjustment for a strategy.

        Args:
            strategy_id: Strategy identifier

        Returns:
            Most recent adjustment or None
        """
        strategy_adjustments = [
            adj for adj in self._adjustments if adj.strategy_id == strategy_id
        ]

        if not strategy_adjustments:
            return None

        return max(strategy_adjustments, key=lambda x: x.timestamp)

    async def get_adjustment_count(
        self,
        strategy_id: str | None = None,
        days: int = 30,
    ) -> int:
        """Get count of adjustments.

        Args:
            strategy_id: Optional strategy filter
            days: Number of days to look back

        Returns:
            Number of adjustments
        """
        cutoff = datetime.now(UTC) - timedelta(days=days)

        return sum(
            1
            for adj in self._adjustments
            if adj.timestamp >= cutoff
            and (strategy_id is None or adj.strategy_id == strategy_id)
        )

    async def get_strategies_with_adjustments(self, days: int = 30) -> list[str]:
        """Get list of strategies that have had adjustments.

        Args:
            days: Number of days to look back

        Returns:
            List of strategy IDs
        """
        cutoff = datetime.now(UTC) - timedelta(days=days)

        strategies = {
            adj.strategy_id for adj in self._adjustments if adj.timestamp >= cutoff
        }

        return sorted(strategies)

    def clear(self) -> None:
        """Clear all in-memory history."""
        self._adjustments.clear()
        self._mode_switches.clear()
        self._config_changes.clear()
        logger.debug("Cleared all in-memory threshold history")

    def get_stats(self) -> dict[str, int]:
        """Get statistics about stored history.

        Returns:
            Dictionary with counts of adjustments, mode switches, and config changes
        """
        return {
            "adjustments": len(self._adjustments),
            "mode_switches": len(self._mode_switches),
            "config_changes": len(self._config_changes),
        }


class InfluxDBThresholdTracker(ThresholdHistoryTracker):
    """InfluxDB-backed threshold history tracker.

    Stores threshold adjustments and mode switches in InfluxDB for
    persistent, time-series storage with efficient querying.

    Schema:
        measurement: threshold_adjustments
        tags: strategy_id, adjustment_type, triggered_by
        fields: old_value, new_value, reason, ece_before, ece_after
        timestamp: adjustment time

        measurement: mode_switches
        tags: strategy_id, old_mode, new_mode
        fields: old_threshold, new_threshold, reason
        timestamp: switch time

    Example:
        >>> tracker = InfluxDBThresholdTracker(
        ...     url="http://localhost:8086",
        ...     token="my-token",
        ...     org="chiseai",
        ...     bucket="thresholds"
        ... )
        >>> await tracker.record_adjustment(adjustment)
        >>> history = await tracker.get_adjustment_history("grid_btc_1h", days=7)
    """

    def __init__(
        self,
        client: Any | None = None,
        url: str | None = None,
        token: str = "",  # nosec B107
        org: str = "chiseai",
        bucket: str = "thresholds",
    ):
        """Initialize InfluxDB threshold tracker.

        Args:
            client: Existing InfluxDB client (optional)
            url: InfluxDB URL (used if client not provided)
            token: InfluxDB token (used if client not provided)
            org: InfluxDB organization
            bucket: Bucket name for threshold data
        """
        self.org = org
        self.bucket = bucket
        self._client = client
        self._url = url
        self._token = token
        self._write_api: Any | None = None
        self._owned_client = client is None

    async def _get_client(self) -> Any:
        """Get or create InfluxDB client."""
        if self._client is None:
            from influxdb_client import InfluxDBClient

            self._client = InfluxDBClient(
                url=self._url,
                token=self._token,
                org=self.org,
            )
        return self._client

    async def _get_write_api(self) -> Any:
        """Get or create write API."""
        if self._write_api is None:
            client = await self._get_client()
            self._write_api = client.write_api()
        return self._write_api

    async def record_adjustment(self, adjustment: ThresholdAdjustment) -> bool:
        """Record a threshold adjustment to InfluxDB.

        Args:
            adjustment: The adjustment to record

        Returns:
            True if successfully recorded
        """
        try:
            from influxdb_client.client.write.point import Point

            write_api = await self._get_write_api()

            point = (
                Point("threshold_adjustments")
                .tag("strategy_id", adjustment.strategy_id)
                .tag("adjustment_type", adjustment.adjustment_type)
                .tag("triggered_by", adjustment.triggered_by)
                .field("old_value", adjustment.old_value)
                .field("new_value", adjustment.new_value)
                .field("reason", adjustment.reason)
            )

            if adjustment.ece_before is not None:
                point = point.field("ece_before", adjustment.ece_before)
            if adjustment.ece_after is not None:
                point = point.field("ece_after", adjustment.ece_after)

            point = point.time(adjustment.timestamp)

            write_api.write(bucket=self.bucket, org=self.org, record=point)

            logger.debug(
                f"Recorded adjustment to InfluxDB for {adjustment.strategy_id}"
            )
            return True

        except Exception:
            logger.exception("Failed to record adjustment to InfluxDB")
            return False

    async def record_mode_switch(self, mode_switch: ModeSwitchRecord) -> bool:
        """Record a mode switch to InfluxDB.

        Args:
            mode_switch: The mode switch to record

        Returns:
            True if successfully recorded
        """
        try:
            from influxdb_client.client.write.point import Point

            write_api = await self._get_write_api()

            point = (
                Point("mode_switches")
                .tag("strategy_id", mode_switch.strategy_id)
                .tag("old_mode", mode_switch.old_mode.value)
                .tag("new_mode", mode_switch.new_mode.value)
                .field("old_threshold", mode_switch.old_threshold)
                .field("new_threshold", mode_switch.new_threshold)
                .field("reason", mode_switch.reason)
                .time(mode_switch.timestamp)
            )

            write_api.write(bucket=self.bucket, org=self.org, record=point)

            logger.debug(
                f"Recorded mode switch to InfluxDB for {mode_switch.strategy_id}"
            )
            return True

        except Exception:
            logger.exception("Failed to record mode switch to InfluxDB")
            return False

    async def record_config_change(
        self, config: ThresholdConfig, change_type: str
    ) -> bool:
        """Record a configuration change to InfluxDB.

        Args:
            config: The configuration
            change_type: Type of change

        Returns:
            True if successfully recorded
        """
        try:
            from influxdb_client.client.write.point import Point

            write_api = await self._get_write_api()

            point = (
                Point("config_changes")
                .tag("strategy_id", config.strategy_id)
                .tag("mode", config.mode.value)
                .tag("change_type", change_type)
                .field("current_threshold", config.current_threshold)
                .field("min_threshold", config.min_threshold)
                .field("max_threshold", config.max_threshold)
                .field("adjustment_step_up", config.adjustment_step_up)
                .field("adjustment_step_down", config.adjustment_step_down)
                .field("ece_high_threshold", config.ece_high_threshold)
                .field("ece_low_threshold", config.ece_low_threshold)
                .time(datetime.now(UTC))
            )

            write_api.write(bucket=self.bucket, org=self.org, record=point)

            logger.debug(f"Recorded config change to InfluxDB for {config.strategy_id}")
            return True

        except Exception:
            logger.exception("Failed to record config change to InfluxDB")
            return False

    async def get_adjustment_history(
        self,
        strategy_id: str | None = None,
        days: int = 30,
        adjustment_type: str | None = None,
    ) -> list[ThresholdAdjustment]:
        """Get adjustment history from InfluxDB.

        Args:
            strategy_id: Optional strategy filter
            days: Number of days to look back
            adjustment_type: Optional filter by adjustment type

        Returns:
            List of threshold adjustments
        """
        try:
            client = await self._get_client()
            query_api = client.query_api()

            start_time = datetime.now(UTC) - timedelta(days=days)

            # Build query filters
            filters = ['r._measurement == "threshold_adjustments"']
            if strategy_id:
                filters.append(f'r.strategy_id == "{strategy_id}"')
            if adjustment_type:
                filters.append(f'r.adjustment_type == "{adjustment_type}"')

            filter_str = " and ".join(filters)

            query = f"""
            from(bucket: "{self.bucket}")
                |> range(start: {start_time.isoformat()})
                |> filter(fn: (r) => {filter_str})
                |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
                |> sort(columns: ["_time"], desc: false)
            """

            tables = query_api.query(query, org=self.org)

            adjustments: list[ThresholdAdjustment] = []
            for table in tables:
                for record in table.records:
                    adjustment = ThresholdAdjustment(
                        timestamp=record.get_time(),
                        strategy_id=record.values.get("strategy_id", ""),
                        old_value=float(record.values.get("old_value", 0)),
                        new_value=float(record.values.get("new_value", 0)),
                        reason=str(record.values.get("reason", "")),
                        ece_before=(
                            float(record.values.get("ece_before"))
                            if "ece_before" in record.values
                            else None
                        ),
                        ece_after=(
                            float(record.values.get("ece_after"))
                            if "ece_after" in record.values
                            else None
                        ),
                        adjustment_type=record.values.get("adjustment_type", "auto"),
                        triggered_by=record.values.get("triggered_by", "unknown"),
                    )
                    adjustments.append(adjustment)

            return adjustments

        except Exception:
            logger.exception("Failed to query adjustment history from InfluxDB")
            return []

    async def get_mode_switch_history(
        self,
        strategy_id: str | None = None,
        days: int = 30,
    ) -> list[ModeSwitchRecord]:
        """Get mode switch history from InfluxDB.

        Args:
            strategy_id: Optional strategy filter
            days: Number of days to look back

        Returns:
            List of mode switch records
        """
        try:
            client = await self._get_client()
            query_api = client.query_api()

            start_time = datetime.now(UTC) - timedelta(days=days)

            # Build query filters
            filters = ['r._measurement == "mode_switches"']
            if strategy_id:
                filters.append(f'r.strategy_id == "{strategy_id}"')

            filter_str = " and ".join(filters)

            query = f"""
            from(bucket: "{self.bucket}")
                |> range(start: {start_time.isoformat()})
                |> filter(fn: (r) => {filter_str})
                |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
                |> sort(columns: ["_time"], desc: false)
            """

            tables = query_api.query(query, org=self.org)

            switches: list[ModeSwitchRecord] = []
            for table in tables:
                for record in table.records:
                    mode_switch = ModeSwitchRecord(
                        timestamp=record.get_time(),
                        strategy_id=record.values.get("strategy_id", ""),
                        old_mode=ThresholdMode(
                            record.values.get("old_mode", "dynamic")
                        ),
                        new_mode=ThresholdMode(
                            record.values.get("new_mode", "dynamic")
                        ),
                        reason=str(record.values.get("reason", "")),
                        old_threshold=float(record.values.get("old_threshold", 0)),
                        new_threshold=float(record.values.get("new_threshold", 0)),
                    )
                    switches.append(mode_switch)

            return switches

        except Exception:
            logger.exception("Failed to query mode switch history from InfluxDB")
            return []

    async def get_latest_adjustment(
        self, strategy_id: str
    ) -> ThresholdAdjustment | None:
        """Get the most recent adjustment for a strategy.

        Args:
            strategy_id: Strategy identifier

        Returns:
            Most recent adjustment or None
        """
        try:
            client = await self._get_client()
            query_api = client.query_api()

            query = f"""
            from(bucket: "{self.bucket}")
                |> range(start: -365d)
                |> filter(fn: (r) => r._measurement == "threshold_adjustments")
                |> filter(fn: (r) => r.strategy_id == "{strategy_id}")
                |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
                |> sort(columns: ["_time"], desc: true)
                |> limit(n: 1)
            """

            tables = query_api.query(query, org=self.org)

            for table in tables:
                for record in table.records:
                    return ThresholdAdjustment(
                        timestamp=record.get_time(),
                        strategy_id=record.values.get("strategy_id", ""),
                        old_value=float(record.values.get("old_value", 0)),
                        new_value=float(record.values.get("new_value", 0)),
                        reason=str(record.values.get("reason", "")),
                        ece_before=(
                            float(record.values.get("ece_before"))
                            if "ece_before" in record.values
                            else None
                        ),
                        ece_after=(
                            float(record.values.get("ece_after"))
                            if "ece_after" in record.values
                            else None
                        ),
                        adjustment_type=record.values.get("adjustment_type", "auto"),
                        triggered_by=record.values.get("triggered_by", "unknown"),
                    )

            return None

        except Exception:
            logger.exception("Failed to query latest adjustment from InfluxDB")
            return None

    async def get_adjustment_count(
        self,
        strategy_id: str | None = None,
        days: int = 30,
    ) -> int:
        """Get count of adjustments.

        Args:
            strategy_id: Optional strategy filter
            days: Number of days to look back

        Returns:
            Number of adjustments
        """
        try:
            client = await self._get_client()
            query_api = client.query_api()

            start_time = datetime.now(UTC) - timedelta(days=days)

            filters = ['r._measurement == "threshold_adjustments"']
            if strategy_id:
                filters.append(f'r.strategy_id == "{strategy_id}"')

            filter_str = " and ".join(filters)

            query = f"""
            from(bucket: "{self.bucket}")
                |> range(start: {start_time.isoformat()})
                |> filter(fn: (r) => {filter_str})
                |> count()
            """

            tables = query_api.query(query, org=self.org)

            for table in tables:
                for record in table.records:
                    return int(record.get_value())

            return 0

        except Exception:
            logger.exception("Failed to query adjustment count from InfluxDB")
            return 0

    async def get_strategies_with_adjustments(self, days: int = 30) -> list[str]:
        """Get list of strategies that have had adjustments.

        Args:
            days: Number of days to look back

        Returns:
            List of strategy IDs
        """
        try:
            client = await self._get_client()
            query_api = client.query_api()

            start_time = datetime.now(UTC) - timedelta(days=days)

            query = f"""
            from(bucket: "{self.bucket}")
                |> range(start: {start_time.isoformat()})
                |> filter(fn: (r) => r._measurement == "threshold_adjustments")
                |> keep(columns: ["strategy_id"])
                |> distinct(column: "strategy_id")
            """

            tables = query_api.query(query, org=self.org)

            strategies: set[str] = set()
            for table in tables:
                for record in table.records:
                    if record.values.get("strategy_id"):
                        strategies.add(record.values["strategy_id"])

            return sorted(strategies)

        except Exception:
            logger.exception("Failed to query strategies from InfluxDB")
            return []

    async def close(self) -> None:
        """Close InfluxDB connections."""
        if self._write_api:
            self._write_api.close()
            self._write_api = None

        if self._client:
            if self._owned_client:
                self._client.close()
            self._client = None
