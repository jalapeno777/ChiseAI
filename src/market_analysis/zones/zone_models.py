"""
Zone data models for ICT trading zones.

Zone Types: OB (Order Block), BRK (Break of Structure), NG (Next Generation), FVG (Fair Value Gap)
Zone Status: ACTIVE → TESTED → MITIGATED → INVALIDATED
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4


class ZoneType(str, Enum):
    """Types of ICT trading zones."""

    OB = "OB"  # Order Block
    BRK = "BRK"  # Break of Structure
    NG = "NG"  # Next Generation
    FVG = "FVG"  # Fair Value Gap


class ZoneStatus(str, Enum):
    """Zone lifecycle status."""

    ACTIVE = "ACTIVE"
    TESTED = "TESTED"
    MITIGATED = "MITIGATED"
    INVALIDATED = "INVALIDATED"


@dataclass
class MitigationEvent:
    """Record of a zone mitigation event."""

    timestamp: datetime
    price: float
    outcome: str  # e.g., "mitigated", "invalidated", "partially_mitigated"
    notes: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "price": self.price,
            "outcome": self.outcome,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MitigationEvent":
        """Create from dictionary."""
        return cls(
            timestamp=datetime.fromisoformat(data["timestamp"]),
            price=data["price"],
            outcome=data["outcome"],
            notes=data.get("notes"),
        )


@dataclass
class PriceRange:
    """High/low price range for a zone."""

    high: float
    low: float

    @property
    def midpoint(self) -> float:
        """Calculate midpoint of the range."""
        return (self.high + self.low) / 2

    def contains(self, price: float) -> bool:
        """Check if price is within the range (inclusive)."""
        return self.low <= price <= self.high

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return {"high": self.high, "low": self.low}

    @classmethod
    def from_dict(cls, data: dict) -> "PriceRange":
        """Create from dictionary."""
        return cls(high=data["high"], low=data["low"])


@dataclass
class Zone:
    """
    ICT Trading Zone data model.

    Attributes:
        uuid: Unique identifier for the zone
        zone_type: Type of zone (OB, BRK, NG, FVG)
        timeframe: Trading timeframe (e.g., "1H", "4H", "1D")
        token: Trading pair symbol (e.g., "BTC/USDT")
        price_range: High/low price boundaries
        creation_time: When the zone was created
        status: Current lifecycle status
        mitigation_history: List of mitigation events
        notes: Optional notes about the zone
    """

    zone_type: ZoneType
    timeframe: str
    token: str
    price_range: PriceRange
    uuid: UUID = field(default_factory=uuid4)
    creation_time: datetime = field(default_factory=datetime.now)
    status: ZoneStatus = ZoneStatus.ACTIVE
    mitigation_history: list[MitigationEvent] = field(default_factory=list)
    notes: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert zone to dictionary for storage."""
        return {
            "uuid": str(self.uuid),
            "zone_type": self.zone_type.value,
            "timeframe": self.timeframe,
            "token": self.token,
            "price_range": self.price_range.to_dict(),
            "creation_time": self.creation_time.isoformat(),
            "status": self.status.value,
            "mitigation_history": [e.to_dict() for e in self.mitigation_history],
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Zone":
        """Create zone from dictionary."""
        return cls(
            uuid=UUID(data["uuid"]),
            zone_type=ZoneType(data["zone_type"]),
            timeframe=data["timeframe"],
            token=data["token"],
            price_range=PriceRange.from_dict(data["price_range"]),
            creation_time=datetime.fromisoformat(data["creation_time"]),
            status=ZoneStatus(data["status"]),
            mitigation_history=[
                MitigationEvent.from_dict(e) for e in data.get("mitigation_history", [])
            ],
            notes=data.get("notes"),
        )

    def transition_to(self, new_status: ZoneStatus) -> None:
        """
        Transition zone to new status with validation.

        Valid transitions:
            ACTIVE → TESTED
            TESTED → MITIGATED
            TESTED → INVALIDATED
            MITIGATED → INVALIDATED

        Args:
            new_status: The target status

        Raises:
            ValueError: If the transition is not valid
        """
        valid_transitions = {
            ZoneStatus.ACTIVE: [ZoneStatus.TESTED],
            ZoneStatus.TESTED: [ZoneStatus.MITIGATED, ZoneStatus.INVALIDATED],
            ZoneStatus.MITIGATED: [ZoneStatus.INVALIDATED],
            ZoneStatus.INVALIDATED: [],  # Terminal state
        }

        if new_status not in valid_transitions[self.status]:
            raise ValueError(
                f"Invalid transition: {self.status.value} → {new_status.value}"
            )

        self.status = new_status

    def add_mitigation(
        self, price: float, outcome: str, notes: Optional[str] = None
    ) -> MitigationEvent:
        """
        Add a mitigation event to the zone.

        Args:
            price: Price at which mitigation occurred
            outcome: Outcome description
            notes: Optional notes

        Returns:
            The created MitigationEvent
        """
        event = MitigationEvent(
            timestamp=datetime.now(),
            price=price,
            outcome=outcome,
            notes=notes,
        )
        self.mitigation_history.append(event)
        return event

    def is_active(self) -> bool:
        """Check if zone is in active state."""
        return self.status == ZoneStatus.ACTIVE

    def is_invalidated(self) -> bool:
        """Check if zone is invalidated (terminal state)."""
        return self.status == ZoneStatus.INVALIDATED
