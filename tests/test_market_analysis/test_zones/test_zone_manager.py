"""
Unit tests for ZoneManager.
"""

from uuid import uuid4

import pytest
from src.market_analysis.zones.redis_storage import ZoneRedisStorage
from src.market_analysis.zones.zone_manager import ZoneManager
from src.market_analysis.zones.zone_models import (
    ZoneStatus,
    ZoneType,
)


class MockRedis:
    """Mock Redis client for testing."""

    def __init__(self):
        self._data = {}  # key -> dict of field -> value
        self._sorted_sets = {}  # key -> {member: score}

    def hset(self, name: str, mapping=None, **kwargs):
        if name not in self._data:
            self._data[name] = {}
        if mapping:
            self._data[name].update(mapping)
        self._data[name].update(kwargs)

    def hgetall(self, name: str):
        # Return plain dict values (strings) to match what redis_storage.py expects
        # The storage layer only handles bytes for JSON-encoded complex fields
        return self._data.get(name, {})

    def delete(self, *names):
        deleted = 0
        for name in names:
            if name in self._data:
                del self._data[name]
                deleted += 1
            if name in self._sorted_sets:
                del self._sorted_sets[name]
                deleted += 1
        return deleted

    def zadd(self, name: str, mapping):
        if name not in self._sorted_sets:
            self._sorted_sets[name] = {}
        self._sorted_sets[name].update(mapping)
        return len(mapping)

    def zrevrange(self, name: str, start: int, end: int):
        if name not in self._sorted_sets:
            return []
        items = sorted(
            self._sorted_sets[name].items(),
            key=lambda x: x[1],
            reverse=True,
        )
        result = []
        for i in range(start, end + 1 if end != -1 else len(items)):
            if i < len(items):
                result.append(items[i][0])
        return result

    def zcard(self, name: str):
        return len(self._sorted_sets.get(name, {}))

    def zrem(self, name: str, *members):
        if name not in self._sorted_sets:
            return 0
        removed = 0
        for member in members:
            if member in self._sorted_sets[name]:
                del self._sorted_sets[name][member]
                removed += 1
        return removed

    def clear(self):
        """Clear all data for fresh test state."""
        self._data.clear()
        self._sorted_sets.clear()


@pytest.fixture
def mock_redis():
    """Provide a clean mock Redis instance."""
    return MockRedis()


@pytest.fixture
def storage(mock_redis):
    """Provide ZoneRedisStorage with mock Redis."""
    return ZoneRedisStorage(mock_redis)


@pytest.fixture
def manager(storage):
    """Provide ZoneManager with storage."""
    return ZoneManager(storage)


class TestZoneManagerCreate:
    """Tests for ZoneManager.create_zone."""

    def test_create_zone(self, manager):
        """Test creating a zone."""
        zone = manager.create_zone(
            zone_type=ZoneType.OB,
            timeframe="1H",
            token="BTC/USDT",
            high=100.0,
            low=90.0,
            notes="Test zone",
        )
        assert zone.zone_type == ZoneType.OB
        assert zone.timeframe == "1H"
        assert zone.token == "BTC/USDT"
        assert zone.price_range.high == 100.0
        assert zone.price_range.low == 90.0
        assert zone.notes == "Test zone"
        assert zone.status == ZoneStatus.ACTIVE

    def test_create_multiple_zones(self, manager):
        """Test creating multiple zones."""
        zone1 = manager.create_zone(
            zone_type=ZoneType.OB,
            timeframe="1H",
            token="BTC/USDT",
            high=100.0,
            low=90.0,
        )
        zone2 = manager.create_zone(
            zone_type=ZoneType.FVG,
            timeframe="4H",
            token="ETH/USDT",
            high=2000.0,
            low=1900.0,
        )
        assert zone1.uuid != zone2.uuid


class TestZoneManagerGet:
    """Tests for ZoneManager.get_zone and get_zones."""

    def test_get_zone(self, manager, mock_redis):
        """Test getting a zone by UUID."""
        created = manager.create_zone(
            zone_type=ZoneType.OB,
            timeframe="1H",
            token="BTC/USDT",
            high=100.0,
            low=90.0,
        )
        retrieved = manager.get_zone(created.uuid)
        assert retrieved is not None
        assert retrieved.uuid == created.uuid
        assert retrieved.zone_type == ZoneType.OB

    def test_get_zone_not_found(self, manager):
        """Test getting non-existent zone returns None."""
        result = manager.get_zone(uuid4())
        assert result is None

    def test_get_zones_by_token_timeframe(self, manager, mock_redis):
        """Test getting all zones for token/timeframe."""
        mock_redis.clear()
        manager.create_zone(
            zone_type=ZoneType.OB,
            timeframe="1H",
            token="BTC/USDT",
            high=100.0,
            low=90.0,
        )
        manager.create_zone(
            zone_type=ZoneType.BRK,
            timeframe="1H",
            token="BTC/USDT",
            high=200.0,
            low=180.0,
        )
        manager.create_zone(
            zone_type=ZoneType.FVG,
            timeframe="4H",
            token="BTC/USDT",
            high=300.0,
            low=280.0,
        )
        manager.create_zone(
            zone_type=ZoneType.OB,
            timeframe="1H",
            token="ETH/USDT",
            high=100.0,
            low=90.0,
        )

        zones = manager.get_zones("BTC/USDT", "1H")
        assert len(zones) == 2

    def test_get_zones_filtered_by_status(self, manager, mock_redis):
        """Test getting zones filtered by status."""
        mock_redis.clear()
        zone1 = manager.create_zone(
            zone_type=ZoneType.OB,
            timeframe="1H",
            token="BTC/USDT",
            high=100.0,
            low=90.0,
        )
        zone2 = manager.create_zone(
            zone_type=ZoneType.BRK,
            timeframe="1H",
            token="BTC/USDT",
            high=200.0,
            low=180.0,
        )

        # Transition zone2 to TESTED
        manager.mark_tested(zone2.uuid, 190.0)

        active = manager.get_zones("BTC/USDT", "1H", status=ZoneStatus.ACTIVE)
        assert len(active) == 1
        assert active[0].uuid == zone1.uuid

        tested = manager.get_zones("BTC/USDT", "1H", status=ZoneStatus.TESTED)
        assert len(tested) == 1
        assert tested[0].uuid == zone2.uuid

    def test_get_active_zones(self, manager, mock_redis):
        """Test getting only active zones."""
        mock_redis.clear()
        zone1 = manager.create_zone(
            zone_type=ZoneType.OB,
            timeframe="1H",
            token="BTC/USDT",
            high=100.0,
            low=90.0,
        )
        zone2 = manager.create_zone(
            zone_type=ZoneType.BRK,
            timeframe="1H",
            token="BTC/USDT",
            high=200.0,
            low=180.0,
        )

        manager.mark_tested(zone1.uuid, 95.0)

        active = manager.get_active_zones("BTC/USDT", "1H")
        assert len(active) == 1
        assert active[0].uuid == zone2.uuid


class TestZoneManagerUpdate:
    """Tests for ZoneManager.update_zone."""

    def test_update_zone(self, manager, mock_redis):
        """Test updating a zone."""
        zone = manager.create_zone(
            zone_type=ZoneType.OB,
            timeframe="1H",
            token="BTC/USDT",
            high=100.0,
            low=90.0,
        )
        zone.notes = "Updated notes"
        manager.update_zone(zone)

        retrieved = manager.get_zone(zone.uuid)
        assert retrieved.notes == "Updated notes"


class TestZoneManagerDelete:
    """Tests for ZoneManager.delete_zone."""

    def test_delete_zone(self, manager, mock_redis):
        """Test deleting a zone."""
        zone = manager.create_zone(
            zone_type=ZoneType.OB,
            timeframe="1H",
            token="BTC/USDT",
            high=100.0,
            low=90.0,
        )
        result = manager.delete_zone(zone.uuid)
        assert result is True

        retrieved = manager.get_zone(zone.uuid)
        assert retrieved is None

    def test_delete_zone_not_found(self, manager):
        """Test deleting non-existent zone returns False."""
        result = manager.delete_zone(uuid4())
        assert result is False


class TestZoneManagerLifecycle:
    """Tests for zone lifecycle transitions."""

    def test_mark_tested(self, manager, mock_redis):
        """Test marking zone as tested."""
        zone = manager.create_zone(
            zone_type=ZoneType.OB,
            timeframe="1H",
            token="BTC/USDT",
            high=100.0,
            low=90.0,
        )
        updated = manager.mark_tested(zone.uuid, 95.0)
        assert updated is not None
        assert updated.status == ZoneStatus.TESTED
        assert len(updated.mitigation_history) == 1

    def test_mark_mitigated(self, manager, mock_redis):
        """Test marking zone as mitigated."""
        zone = manager.create_zone(
            zone_type=ZoneType.OB,
            timeframe="1H",
            token="BTC/USDT",
            high=100.0,
            low=90.0,
        )
        manager.mark_tested(zone.uuid, 95.0)
        updated = manager.mark_mitigated(zone.uuid, 92.0)
        assert updated.status == ZoneStatus.MITIGATED
        assert len(updated.mitigation_history) == 2

    def test_mark_invalidated(self, manager, mock_redis):
        """Test marking zone as invalidated."""
        zone = manager.create_zone(
            zone_type=ZoneType.OB,
            timeframe="1H",
            token="BTC/USDT",
            high=100.0,
            low=90.0,
        )
        manager.mark_tested(zone.uuid, 95.0)
        updated = manager.mark_invalidated(zone.uuid, 85.0)
        assert updated.status == ZoneStatus.INVALIDATED
        assert len(updated.mitigation_history) == 2

    def test_invalid_transition_returns_none(self, manager, mock_redis):
        """Test that invalid transitions return None."""
        zone = manager.create_zone(
            zone_type=ZoneType.OB,
            timeframe="1H",
            token="BTC/USDT",
            high=100.0,
            low=90.0,
        )
        # ACTIVE -> MITIGATED is invalid
        updated = manager.transition_zone(zone.uuid, ZoneStatus.MITIGATED, 92.0)
        assert updated is None

    def test_transition_zone_not_found(self, manager):
        """Test transitioning non-existent zone returns None."""
        result = manager.transition_zone(uuid4(), ZoneStatus.TESTED, 95.0)
        assert result is None


class TestZoneManagerCapacity:
    """Tests for capacity management."""

    def test_get_capacity_info(self, manager, mock_redis):
        """Test getting capacity info."""
        mock_redis.clear()
        manager.create_zone(
            zone_type=ZoneType.OB,
            timeframe="1H",
            token="BTC/USDT",
            high=100.0,
            low=90.0,
        )
        manager.create_zone(
            zone_type=ZoneType.BRK,
            timeframe="1H",
            token="BTC/USDT",
            high=200.0,
            low=180.0,
        )

        info = manager.get_capacity_info("BTC/USDT", "1H")
        assert info["zone_count"] == 2
        assert info["estimated_size_bytes"] == 2 * 600
        assert "estimated_size_kb" in info
        assert info["capacity_check"] == "OK"

    def test_validate_capacity_within_limit(self, manager, mock_redis):
        """Test capacity validation when within limit."""
        mock_redis.clear()
        manager.create_zone(
            zone_type=ZoneType.OB,
            timeframe="1H",
            token="BTC/USDT",
            high=100.0,
            low=90.0,
        )
        assert manager.validate_capacity("BTC/USDT", "1H") is True

    def test_count_zones(self, manager, mock_redis):
        """Test zone counting."""
        mock_redis.clear()
        manager.create_zone(
            zone_type=ZoneType.OB,
            timeframe="1H",
            token="BTC/USDT",
            high=100.0,
            low=90.0,
        )
        manager.create_zone(
            zone_type=ZoneType.BRK,
            timeframe="1H",
            token="BTC/USDT",
            high=200.0,
            low=180.0,
        )
        manager.create_zone(
            zone_type=ZoneType.FVG,
            timeframe="4H",
            token="BTC/USDT",
            high=300.0,
            low=280.0,
        )

        assert manager.count_zones("BTC/USDT", "1H") == 2
        assert manager.count_zones("BTC/USDT", "4H") == 1

    def test_cleanup_old_zones(self, manager, mock_redis):
        """Test cleanup of old zones."""
        mock_redis.clear()
        # Create 5 zones
        for i in range(5):
            manager.create_zone(
                zone_type=ZoneType.OB,
                timeframe="1H",
                token="BTC/USDT",
                high=100.0 + i * 10,
                low=90.0 + i * 10,
            )

        deleted = manager.cleanup_old_zones("BTC/USDT", "1H", keep_count=3)
        assert deleted == 2
        assert manager.count_zones("BTC/USDT", "1H") == 3

    def test_cleanup_when_within_limit(self, manager, mock_redis):
        """Test cleanup when already within limit."""
        mock_redis.clear()
        manager.create_zone(
            zone_type=ZoneType.OB,
            timeframe="1H",
            token="BTC/USDT",
            high=100.0,
            low=90.0,
        )
        deleted = manager.cleanup_old_zones("BTC/USDT", "1H", keep_count=10)
        assert deleted == 0
