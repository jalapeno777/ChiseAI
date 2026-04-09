"""
Domain Context for Memory Scoping.

From memory-systems-evaluation-20260409.md Section 4:
"Palace wing/room/hall = Domain scoping (WHERE the memory lives)
 ChiseAI MemoryType = Semantic type (WHAT the memory IS)"

These can coexist. The palace concept adopted as DomainContext
overlay on ChiseAI's existing MemoryType enum.

HARDENING (Aria decision AD-PHASE4-20260409T000000Z-ctx001):
- DomainContext is optional metadata attached to memory records
- When present, enables cross-domain context assembly
- Tunnels field enables related domain discovery
"""

from dataclasses import dataclass, field
from typing import List, Optional
from enum import Enum


class MemoryWing(str, Enum):
    """Wing enum for domain scoping.

    Represents the primary domain/large division where the memory lives.
    """

    CHISEAI = "chiseai"
    CRAIG = "craig"
    TRADING = "trading"
    INFRA = "infra"


class MemoryHall(str, Enum):
    """Hall enum for memory categorization.

    Represents the semantic category of the memory content.
    """

    FACTS = "facts"
    EVENTS = "events"
    DISCOVERIES = "discoveries"
    PREFERENCES = "preferences"
    ADVICE = "advice"


@dataclass
class DomainContext:
    """
    Domain context for memory scoping.

    Provides palace-style hierarchical scoping (wing/room/hall) overlaid
    on ChiseAI's existing MemoryType system.

    Attributes:
        wing: Primary domain (chiseai | craig | trading | infra)
        room: Sub-domain (risk-mgmt | strategy-dev | preferences | iterations)
        hall: Memory category (facts | events | discoveries | preferences | advice)
        tunnels: List of related domains for cross-domain discovery

    Example:
        DomainContext(
            wing="trading",
            room="risk-mgmt",
            hall="facts",
            tunnels=["chiseai:strategy-dev", "infra:monitoring"]
        )
    """

    wing: str  # "chiseai" | "craig" | "trading" | "infra"
    room: str  # "risk-mgmt" | "strategy-dev" | "preferences" | "iterations"
    hall: str  # "facts" | "events" | "discoveries" | "preferences" | "advice"
    tunnels: List[str] = field(default_factory=list)  # related domains

    def to_payload(self) -> dict:
        """
        Convert to Qdrant nested payload format.

        Returns:
            Dict suitable for storage in Qdrant point payload.
        """
        return {
            "domain_context": {
                "wing": self.wing,
                "room": self.room,
                "hall": self.hall,
                "tunnels": self.tunnels,
            }
        }

    @classmethod
    def from_payload(cls, payload: dict) -> "DomainContext":
        """
        Reconstruct from Qdrant payload.

        Args:
            payload: Qdrant point payload dict containing domain_context.

        Returns:
            DomainContext instance reconstructed from payload.

        Raises:
            KeyError: If domain_context key is missing from payload.
        """
        domain_data = payload.get("domain_context", {})
        return cls(
            wing=domain_data.get("wing", "chiseai"),
            room=domain_data.get("room", "iterations"),
            hall=domain_data.get("hall", "facts"),
            tunnels=domain_data.get("tunnels", []),
        )

    def is_valid(self) -> bool:
        """
        Validate that wing and hall are recognized enum values.

        Note: room validation is intentionally flexible as it's
        user-defined/subjective.

        Returns:
            True if wing and hall are valid enum values.
        """
        try:
            MemoryWing(self.wing)
            MemoryHall(self.hall)
            return True
        except ValueError:
            return False

    def to_wing_room_hall_string(self) -> str:
        """
        Format as dot-separated string for logging/display.

        Returns:
            String like "trading.risk-mgmt.facts"
        """
        return f"{self.wing}.{self.room}.{self.hall}"
