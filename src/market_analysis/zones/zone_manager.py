"""
ZoneManager - CRUD operations and lifecycle management for ICT trading zones.

Provides high-level API for zone persistence with Redis backend.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from src.market_analysis.zones.redis_storage import ZoneRedisStorage
from src.market_analysis.zones.zone_models import (
    PriceRange,
    Zone,
    ZoneCapacityError,
    ZoneStatus,
    ZoneType,
)


class ZoneManager:
    """
    Manages ICT trading zones with Redis persistence.

    Provides CRUD operations and lifecycle state transitions:
    ACTIVE → TESTED → MITIGATED → INVALIDATED
    """

    # Capacity threshold (600KB)
    CAPACITY_THRESHOLD_BYTES = 614400  # 600KB

    def __init__(self, storage: ZoneRedisStorage):
        """
        Initialize ZoneManager.

        Args:
            storage: ZoneRedisStorage instance
        """
        self._storage = storage

    def create_zone(
        self,
        zone_type: ZoneType,
        timeframe: str,
        token: str,
        high: float,
        low: float,
        notes: Optional[str] = None,
    ) -> Zone:
        """
        Create a new zone.

        Args:
            zone_type: Type of zone (OB, BRK, NG, FVG)
            timeframe: Trading timeframe (e.g., "1H", "4H")
            token: Trading pair symbol (e.g., "BTC/USDT")
            high: Upper price boundary
            low: Lower price boundary
            notes: Optional notes

        Returns:
            Created Zone

        Raises:
            ZoneCapacityError: If storage is at capacity
        """
        # Check capacity before saving
        if not self.validate_capacity(token, timeframe):
            # Try to free up space by cleaning old non-active zones
            self.cleanup_old_zones(token, timeframe)
            # If still over capacity, raise error
            if not self.validate_capacity(token, timeframe):
                raise ZoneCapacityError(
                    f"Zone storage at capacity for {token} {timeframe}. "
                    "Consider cleaning up old zones."
                )

        zone = Zone(
            zone_type=zone_type,
            timeframe=timeframe,
            token=token,
            price_range=PriceRange(high=high, low=low),
            notes=notes,
        )

        self._storage.save(zone)
        return zone

    def get_zone(self, uuid: UUID) -> Optional[Zone]:
        """
        Get zone by UUID.

        Args:
            uuid: Zone UUID

        Returns:
            Zone if found, None otherwise
        """
        return self._storage.get(uuid)

    def get_zones(
        self,
        token: str,
        timeframe: str,
        status: Optional[ZoneStatus] = None,
    ) -> list[Zone]:
        """
        Get all zones for token/timeframe.

        Args:
            token: Trading pair symbol
            timeframe: Trading timeframe
            status: Optional status filter

        Returns:
            List of zones (newest first)
        """
        return self._storage.get_by_token_timeframe(token, timeframe, status)

    def get_active_zones(self, token: str, timeframe: str) -> list[Zone]:
        """
        Get active zones for token/timeframe.

        Args:
            token: Trading pair symbol
            timeframe: Trading timeframe

        Returns:
            List of active zones
        """
        return self.get_zones(token, timeframe, status=ZoneStatus.ACTIVE)

    def update_zone(self, zone: Zone) -> None:
        """
        Update an existing zone.

        Args:
            zone: Zone to update
        """
        self._storage.update(zone)

    def delete_zone(self, uuid: UUID) -> bool:
        """
        Delete a zone.

        Args:
            uuid: Zone UUID

        Returns:
            True if deleted, False if not found
        """
        return self._storage.delete(uuid)

    def transition_zone(
        self,
        uuid: UUID,
        new_status: ZoneStatus,
        mitigation_price: Optional[float] = None,
    ) -> Optional[Zone]:
        """
        Transition zone to new status with optional mitigation event.

        Args:
            uuid: Zone UUID
            new_status: Target status
            mitigation_price: Price at which mitigation occurred (for TESTED/MITIGATED/INVALIDATED)

        Returns:
            Updated zone if found, None if not found
        """
        zone = self._storage.get(uuid)
        if not zone:
            return None

        # Validate transition first before adding any events
        try:
            zone.transition_to(new_status)
        except ValueError:
            return None

        # Add mitigation event for non-ACTIVE transitions only after successful validation
        if new_status != ZoneStatus.ACTIVE and mitigation_price is not None:
            zone.add_mitigation(
                price=mitigation_price,
                outcome=new_status.value.lower(),
            )

        self._storage.update(zone)
        return zone

    def mark_tested(self, uuid: UUID, test_price: float) -> Optional[Zone]:
        """
        Mark zone as TESTED after price touched it.

        Args:
            uuid: Zone UUID
            test_price: Price that tested the zone

        Returns:
            Updated zone if found, None if not found
        """
        return self.transition_zone(uuid, ZoneStatus.TESTED, test_price)

    def mark_mitigated(self, uuid: UUID, mitigation_price: float) -> Optional[Zone]:
        """
        Mark zone as MITIGATED.

        Args:
            uuid: Zone UUID
            mitigation_price: Price of mitigation

        Returns:
            Updated zone if found, None if not found
        """
        return self.transition_zone(uuid, ZoneStatus.MITIGATED, mitigation_price)

    def mark_invalidated(self, uuid: UUID, invalidate_price: float) -> Optional[Zone]:
        """
        Mark zone as INVALIDATED.

        Args:
            uuid: Zone UUID
            invalidate_price: Price that invalidated the zone

        Returns:
            Updated zone if found, None if not found
        """
        return self.transition_zone(uuid, ZoneStatus.INVALIDATED, invalidate_price)

    def get_capacity_info(self, token: str, timeframe: str) -> dict:
        """
        Get capacity information for token/timeframe.

        Args:
            token: Trading pair symbol
            timeframe: Trading timeframe

        Returns:
            Capacity info dict
        """
        info = self._storage.get_capacity_info(token, timeframe)
        info["threshold_bytes"] = self.CAPACITY_THRESHOLD_BYTES
        info["threshold_kb"] = self.CAPACITY_THRESHOLD_BYTES / 1024
        return info

    def validate_capacity(self, token: str, timeframe: str) -> bool:
        """
        Validate that storage is within capacity limits.

        Args:
            token: Trading pair symbol
            timeframe: Trading timeframe

        Returns:
            True if within capacity, False otherwise
        """
        info = self._storage.get_capacity_info(token, timeframe)
        return info["estimated_size_bytes"] < self.CAPACITY_THRESHOLD_BYTES

    def count_zones(self, token: str, timeframe: str) -> int:
        """
        Count zones for token/timeframe.

        Args:
            token: Trading pair symbol
            timeframe: Trading timeframe

        Returns:
            Number of zones
        """
        return self._storage.count_by_token_timeframe(token, timeframe)

    def cleanup_old_zones(
        self, token: str, timeframe: str, keep_count: int = 100
    ) -> int:
        """
        Remove oldest zones beyond keep_count.

        Prioritizes deletion of INVALIDATED and MITIGATED zones first.
        Only deletes ACTIVE/TESTED zones as last resort.

        Args:
            token: Trading pair symbol
            timeframe: Trading timeframe
            keep_count: Number of newest zones to keep

        Returns:
            Number of zones deleted
        """
        import logging

        logger = logging.getLogger(__name__)

        zones = self._storage.get_by_token_timeframe(token, timeframe)
        if len(zones) <= keep_count:
            return 0

        # Separate zones by priority (non-active first)
        terminal_zones = [
            z
            for z in zones
            if z.status in (ZoneStatus.INVALIDATED, ZoneStatus.MITIGATED)
        ]
        active_zones = [
            z for z in zones if z.status in (ZoneStatus.ACTIVE, ZoneStatus.TESTED)
        ]

        deleted = 0

        # First, delete terminal zones beyond keep_count (oldest first)
        if len(terminal_zones) > keep_count:
            zones_to_delete = terminal_zones[keep_count:]
            for zone in zones_to_delete:
                if self._storage.delete(zone.uuid):
                    deleted += 1

        # If we still need to free space, delete active zones (oldest first)
        remaining_needed = keep_count - (len(zones) - deleted - keep_count)
        if deleted < (len(zones) - keep_count):
            remaining = keep_count - (len(terminal_zones) - deleted)
            if remaining < 0:
                remaining = 0
            zones_to_delete = active_zones[remaining:]
            if zones_to_delete:
                logger.warning(
                    f"Cleaning up {len(zones_to_delete)} ACTIVE/TESTED zones for "
                    f"{token} {timeframe} - consider increasing keep_count"
                )
            for zone in zones_to_delete:
                if self._storage.delete(zone.uuid):
                    deleted += 1

        return deleted
