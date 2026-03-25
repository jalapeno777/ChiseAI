"""
Unit tests for zone models.
"""

import pytest
from datetime import datetime
from uuid import UUID

from src.market_analysis.zones.zone_models import (
    MitigationEvent,
    PriceRange,
    Zone,
    ZoneStatus,
    ZoneType,
)


class TestPriceRange:
    """Tests for PriceRange dataclass."""

    def test_contains_within_range(self):
        """Test price within range returns True."""
        pr = PriceRange(high=100.0, low=90.0)
        assert pr.contains(95.0) is True

    def test_contains_at_boundaries(self):
        """Test price at exact boundaries returns True."""
        pr = PriceRange(high=100.0, low=90.0)
        assert pr.contains(100.0) is True
        assert pr.contains(90.0) is True

    def test_contains_outside_range(self):
        """Test price outside range returns False."""
        pr = PriceRange(high=100.0, low=90.0)
        assert pr.contains(89.9) is False
        assert pr.contains(100.1) is False

    def test_midpoint(self):
        """Test midpoint calculation."""
        pr = PriceRange(high=100.0, low=80.0)
        assert pr.midpoint == 90.0

    def test_to_dict(self):
        """Test serialization to dict."""
        pr = PriceRange(high=100.0, low=90.0)
        d = pr.to_dict()
        assert d == {"high": 100.0, "low": 90.0}

    def test_from_dict(self):
        """Test deserialization from dict."""
        d = {"high": 100.0, "low": 90.0}
        pr = PriceRange.from_dict(d)
        assert pr.high == 100.0
        assert pr.low == 90.0


class TestMitigationEvent:
    """Tests for MitigationEvent dataclass."""

    def test_to_dict(self):
        """Test serialization."""
        event = MitigationEvent(
            timestamp=datetime(2024, 1, 15, 10, 30),
            price=95.0,
            outcome="mitigated",
            notes="Test note",
        )
        d = event.to_dict()
        assert d["timestamp"] == "2024-01-15T10:30:00"
        assert d["price"] == 95.0
        assert d["outcome"] == "mitigated"
        assert d["notes"] == "Test note"

    def test_from_dict(self):
        """Test deserialization."""
        d = {
            "timestamp": "2024-01-15T10:30:00",
            "price": 95.0,
            "outcome": "mitigated",
            "notes": "Test note",
        }
        event = MitigationEvent.from_dict(d)
        assert event.timestamp == datetime(2024, 1, 15, 10, 30)
        assert event.price == 95.0
        assert event.outcome == "mitigated"


class TestZone:
    """Tests for Zone dataclass."""

    def test_create_zone(self):
        """Test zone creation with defaults."""
        zone = Zone(
            zone_type=ZoneType.OB,
            timeframe="1H",
            token="BTC/USDT",
            price_range=PriceRange(high=100.0, low=90.0),
        )
        assert zone.zone_type == ZoneType.OB
        assert zone.timeframe == "1H"
        assert zone.token == "BTC/USDT"
        assert zone.status == ZoneStatus.ACTIVE
        assert len(zone.mitigation_history) == 0
        assert isinstance(zone.uuid, UUID)

    def test_create_zone_with_notes(self):
        """Test zone creation with notes."""
        zone = Zone(
            zone_type=ZoneType.BRK,
            timeframe="4H",
            token="ETH/USDT",
            price_range=PriceRange(high=2000.0, low=1900.0),
            notes="Break of structure on daily close",
        )
        assert zone.notes == "Break of structure on daily close"

    def test_to_dict(self):
        """Test zone serialization."""
        zone = Zone(
            zone_type=ZoneType.FVG,
            timeframe="1H",
            token="BTC/USDT",
            price_range=PriceRange(high=100.0, low=95.0),
        )
        d = zone.to_dict()
        assert d["zone_type"] == "FVG"
        assert d["timeframe"] == "1H"
        assert d["token"] == "BTC/USDT"
        assert d["status"] == "ACTIVE"
        assert d["price_range"] == {"high": 100.0, "low": 95.0}

    def test_from_dict(self):
        """Test zone deserialization."""
        d = {
            "uuid": "12345678-1234-1234-1234-123456789abc",
            "zone_type": "OB",
            "timeframe": "1H",
            "token": "BTC/USDT",
            "price_range": {"high": 100.0, "low": 90.0},
            "creation_time": "2024-01-15T10:00:00",
            "status": "ACTIVE",
            "mitigation_history": [],
            "notes": None,
        }
        zone = Zone.from_dict(d)
        assert zone.zone_type == ZoneType.OB
        assert zone.timeframe == "1H"
        assert zone.status == ZoneStatus.ACTIVE

    def test_valid_transition_active_to_tested(self):
        """Test valid transition from ACTIVE to TESTED."""
        zone = Zone(
            zone_type=ZoneType.OB,
            timeframe="1H",
            token="BTC/USDT",
            price_range=PriceRange(high=100.0, low=90.0),
        )
        zone.transition_to(ZoneStatus.TESTED)
        assert zone.status == ZoneStatus.TESTED

    def test_valid_transition_tested_to_mitigated(self):
        """Test valid transition from TESTED to MITIGATED."""
        zone = Zone(
            zone_type=ZoneType.OB,
            timeframe="1H",
            token="BTC/USDT",
            price_range=PriceRange(high=100.0, low=90.0),
        )
        zone.transition_to(ZoneStatus.TESTED)
        zone.transition_to(ZoneStatus.MITIGATED)
        assert zone.status == ZoneStatus.MITIGATED

    def test_valid_transition_tested_to_invalidated(self):
        """Test valid transition from TESTED to INVALIDATED."""
        zone = Zone(
            zone_type=ZoneType.OB,
            timeframe="1H",
            token="BTC/USDT",
            price_range=PriceRange(high=100.0, low=90.0),
        )
        zone.transition_to(ZoneStatus.TESTED)
        zone.transition_to(ZoneStatus.INVALIDATED)
        assert zone.status == ZoneStatus.INVALIDATED

    def test_invalid_transition_active_to_mitigated(self):
        """Test invalid transition from ACTIVE directly to MITIGATED."""
        zone = Zone(
            zone_type=ZoneType.OB,
            timeframe="1H",
            token="BTC/USDT",
            price_range=PriceRange(high=100.0, low=90.0),
        )
        with pytest.raises(ValueError, match="Invalid transition"):
            zone.transition_to(ZoneStatus.MITIGATED)

    def test_invalid_transition_from_invalidated(self):
        """Test that INVALIDATED is terminal state."""
        zone = Zone(
            zone_type=ZoneType.OB,
            timeframe="1H",
            token="BTC/USDT",
            price_range=PriceRange(high=100.0, low=90.0),
        )
        zone.transition_to(ZoneStatus.TESTED)
        zone.transition_to(ZoneStatus.INVALIDATED)
        with pytest.raises(ValueError):
            zone.transition_to(ZoneStatus.ACTIVE)

    def test_add_mitigation(self):
        """Test adding mitigation event."""
        zone = Zone(
            zone_type=ZoneType.OB,
            timeframe="1H",
            token="BTC/USDT",
            price_range=PriceRange(high=100.0, low=90.0),
        )
        event = zone.add_mitigation(price=95.0, outcome="mitigated", notes="Test")
        assert len(zone.mitigation_history) == 1
        assert event.price == 95.0
        assert event.outcome == "mitigated"

    def test_is_active(self):
        """Test is_active helper."""
        zone = Zone(
            zone_type=ZoneType.OB,
            timeframe="1H",
            token="BTC/USDT",
            price_range=PriceRange(high=100.0, low=90.0),
        )
        assert zone.is_active() is True
        zone.transition_to(ZoneStatus.TESTED)
        assert zone.is_active() is False

    def test_is_invalidated(self):
        """Test is_invalidated helper."""
        zone = Zone(
            zone_type=ZoneType.OB,
            timeframe="1H",
            token="BTC/USDT",
            price_range=PriceRange(high=100.0, low=90.0),
        )
        assert zone.is_invalidated() is False
        zone.transition_to(ZoneStatus.TESTED)
        zone.transition_to(ZoneStatus.INVALIDATED)
        assert zone.is_invalidated() is True


class TestZoneType:
    """Tests for ZoneType enum."""

    def test_zone_types(self):
        """Test all zone types exist."""
        assert ZoneType.OB == "OB"
        assert ZoneType.BRK == "BRK"
        assert ZoneType.NG == "NG"
        assert ZoneType.FVG == "FVG"


class TestZoneStatus:
    """Tests for ZoneStatus enum."""

    def test_all_statuses(self):
        """Test all statuses exist."""
        assert ZoneStatus.ACTIVE == "ACTIVE"
        assert ZoneStatus.TESTED == "TESTED"
        assert ZoneStatus.MITIGATED == "MITIGATED"
        assert ZoneStatus.INVALIDATED == "INVALIDATED"
