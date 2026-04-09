"""
Unit tests for DomainContext dataclass.

Tests for:
- AC1: DomainContext serialization roundtrip (to_payload / from_payload)
- Wing/room/hall validation
- Tunnels list handling
- Enum enforcement
"""

from src.governance.memory.domain_context import (
    DomainContext,
    MemoryHall,
    MemoryWing,
)

import pytest


class TestMemoryWing:
    """Tests for MemoryWing enum."""

    def test_memory_wing_values(self):
        """MemoryWing should have expected values."""
        assert MemoryWing.CHISEAI.value == "chiseai"
        assert MemoryWing.CRAIG.value == "craig"
        assert MemoryWing.TRADING.value == "trading"
        assert MemoryWing.INFRA.value == "infra"

    def test_memory_wing_from_string(self):
        """MemoryWing should be constructible from string value."""
        assert MemoryWing("chiseai") == MemoryWing.CHISEAI
        assert MemoryWing("trading") == MemoryWing.TRADING

    def test_memory_wing_invalid_raises(self):
        """Invalid MemoryWing value should raise ValueError."""
        with pytest.raises(ValueError):
            MemoryWing("invalid")


class TestMemoryHall:
    """Tests for MemoryHall enum."""

    def test_memory_hall_values(self):
        """MemoryHall should have expected values."""
        assert MemoryHall.FACTS.value == "facts"
        assert MemoryHall.EVENTS.value == "events"
        assert MemoryHall.DISCOVERIES.value == "discoveries"
        assert MemoryHall.PREFERENCES.value == "preferences"
        assert MemoryHall.ADVICE.value == "advice"

    def test_memory_hall_from_string(self):
        """MemoryHall should be constructible from string value."""
        assert MemoryHall("facts") == MemoryHall.FACTS
        assert MemoryHall("events") == MemoryHall.EVENTS

    def test_memory_hall_invalid_raises(self):
        """Invalid MemoryHall value should raise ValueError."""
        with pytest.raises(ValueError):
            MemoryHall("invalid")


class TestDomainContext:
    """Tests for DomainContext dataclass."""

    def test_creation_with_required_fields(self):
        """DomainContext should be created with required wing/room/hall."""
        dc = DomainContext(
            wing="trading",
            room="risk-mgmt",
            hall="facts",
        )
        assert dc.wing == "trading"
        assert dc.room == "risk-mgmt"
        assert dc.hall == "facts"
        assert dc.tunnels == []

    def test_creation_with_tunnels(self):
        """DomainContext should be created with tunnels list."""
        dc = DomainContext(
            wing="trading",
            room="risk-mgmt",
            hall="facts",
            tunnels=["chiseai:strategy-dev", "infra:monitoring"],
        )
        assert len(dc.tunnels) == 2
        assert "chiseai:strategy-dev" in dc.tunnels
        assert "infra:monitoring" in dc.tunnels

    def test_creation_with_empty_tunnels(self):
        """DomainContext should default tunnels to empty list."""
        dc = DomainContext(
            wing="chiseai",
            room="iterations",
            hall="events",
            tunnels=[],
        )
        assert dc.tunnels == []

    def test_to_payload_basic(self):
        """to_payload should return Qdrant-compatible nested format."""
        dc = DomainContext(
            wing="trading",
            room="risk-mgmt",
            hall="facts",
        )
        payload = dc.to_payload()

        assert "domain_context" in payload
        assert payload["domain_context"]["wing"] == "trading"
        assert payload["domain_context"]["room"] == "risk-mgmt"
        assert payload["domain_context"]["hall"] == "facts"
        assert payload["domain_context"]["tunnels"] == []

    def test_to_payload_with_tunnels(self):
        """to_payload should include tunnels when non-empty."""
        dc = DomainContext(
            wing="infra",
            room="monitoring",
            hall="events",
            tunnels=["chiseai:iterations"],
        )
        payload = dc.to_payload()

        assert payload["domain_context"]["tunnels"] == ["chiseai:iterations"]

    def test_from_payload_basic(self):
        """from_payload should reconstruct DomainContext."""
        payload = {
            "domain_context": {
                "wing": "trading",
                "room": "risk-mgmt",
                "hall": "facts",
                "tunnels": [],
            }
        }
        dc = DomainContext.from_payload(payload)

        assert dc.wing == "trading"
        assert dc.room == "risk-mgmt"
        assert dc.hall == "facts"
        assert dc.tunnels == []

    def test_from_payload_with_tunnels(self):
        """from_payload should reconstruct tunnels correctly."""
        payload = {
            "domain_context": {
                "wing": "craig",
                "room": "preferences",
                "hall": "advice",
                "tunnels": ["chiseai:iterations", "trading:risk-mgmt"],
            }
        }
        dc = DomainContext.from_payload(payload)

        assert dc.wing == "craig"
        assert dc.room == "preferences"
        assert dc.hall == "advice"
        assert len(dc.tunnels) == 2

    def test_from_payload_missing_keys_uses_defaults(self):
        """from_payload should use defaults for missing keys."""
        payload = {"domain_context": {}}
        dc = DomainContext.from_payload(payload)

        assert dc.wing == "chiseai"  # default
        assert dc.room == "iterations"  # default
        assert dc.hall == "facts"  # default
        assert dc.tunnels == []

    def test_from_payload_no_domain_context_key(self):
        """from_payload should use defaults when domain_context key missing."""
        payload = {}
        dc = DomainContext.from_payload(payload)

        assert dc.wing == "chiseai"
        assert dc.room == "iterations"
        assert dc.hall == "facts"
        assert dc.tunnels == []

    def test_roundtrip_serialization(self):
        """to_payload -> from_payload should preserve all fields."""
        original = DomainContext(
            wing="trading",
            room="strategy-dev",
            hall="discoveries",
            tunnels=["chiseai:iterations", "craig:preferences"],
        )

        payload = original.to_payload()
        reconstructed = DomainContext.from_payload(payload)

        assert reconstructed.wing == original.wing
        assert reconstructed.room == original.room
        assert reconstructed.hall == original.hall
        assert reconstructed.tunnels == original.tunnels

    def test_is_valid_with_valid_enums(self):
        """is_valid should return True for valid wing/hall values."""
        dc = DomainContext(
            wing="trading",
            room="risk-mgmt",
            hall="facts",
        )
        assert dc.is_valid() is True

    def test_is_valid_with_invalid_wing(self):
        """is_valid should return False for invalid wing value."""
        dc = DomainContext(
            wing="invalid_wing",
            room="risk-mgmt",
            hall="facts",
        )
        assert dc.is_valid() is False

    def test_is_valid_with_invalid_hall(self):
        """is_valid should return False for invalid hall value."""
        dc = DomainContext(
            wing="trading",
            room="risk-mgmt",
            hall="invalid_hall",
        )
        assert dc.is_valid() is False

    def test_is_valid_with_both_invalid(self):
        """is_valid should return False when both wing and hall invalid."""
        dc = DomainContext(
            wing="invalid_wing",
            room="risk-mgmt",
            hall="invalid_hall",
        )
        assert dc.is_valid() is False

    def test_to_wing_room_hall_string(self):
        """to_wing_room_hall_string should format as dot-separated string."""
        dc = DomainContext(
            wing="trading",
            room="risk-mgmt",
            hall="facts",
        )
        assert dc.to_wing_room_hall_string() == "trading.risk-mgmt.facts"

    def test_to_wing_room_hall_string_with_complex_room(self):
        """to_wing_room_hall_string should handle complex room names."""
        dc = DomainContext(
            wing="chiseai",
            room="strategy-dev",
            hall="discoveries",
        )
        assert dc.to_wing_room_hall_string() == "chiseai.strategy-dev.discoveries"

    def test_memory_wing_is_str_enum(self):
        """MemoryWing should be a str enum for serialization compatibility."""
        assert isinstance(MemoryWing.CHISEAI, str)
        assert MemoryWing.CHISEAI == "chiseai"

    def test_memory_hall_is_str_enum(self):
        """MemoryHall should be a str enum for serialization compatibility."""
        assert isinstance(MemoryHall.FACTS, str)
        assert MemoryHall.FACTS == "facts"
