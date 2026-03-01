"""Reconciliation data models for comparing telemetry vs persisted counts.

For ST-VENUE-002: Canonical reporting and venue enforcement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class ReconciliationStatus(Enum):
    """Status of reconciliation result."""

    OK = "OK"  # All counts match within tolerance
    WARN = "WARN"  # Delta exceeds warning threshold
    FAIL = "FAIL"  # Delta exceeds failure threshold or data unavailable


@dataclass
class CountDiscrepancy:
    """Specific count discrepancy detail.

    Attributes:
        category: Category of count (signals, orders, fills, outcomes)
        telemetry_count: Count from telemetry source (InfluxDB)
        persisted_count: Count from persisted source (Redis/PostgreSQL)
        delta: Difference (telemetry - persisted)
        delta_pct: Percentage difference
    """

    category: str
    telemetry_count: int
    persisted_count: int
    delta: int
    delta_pct: float

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "category": self.category,
            "telemetry_count": self.telemetry_count,
            "persisted_count": self.persisted_count,
            "delta": self.delta,
            "delta_pct": self.delta_pct,
        }


@dataclass
class ReconciliationResult:
    """Result of reconciliation between telemetry and persisted counts.

    Attributes:
        telemetry_count: Counts from telemetry source (InfluxDB)
        persisted_count: Counts from persisted source (Redis/PostgreSQL)
        delta_count: Differences (telemetry - persisted) for each category
        delta_pct: Percentage differences for each category
        status: Overall reconciliation status (OK/WARN/FAIL)
        timestamp: When reconciliation was performed
        discrepancies: List of specific mismatches exceeding thresholds
        environment: Trading environment (paper/live)
        portfolio_id: Portfolio identifier
    """

    telemetry_count: dict[str, int]
    persisted_count: dict[str, int]
    delta_count: dict[str, int]
    delta_pct: dict[str, float]
    status: ReconciliationStatus
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    discrepancies: list[CountDiscrepancy] = field(default_factory=list)
    environment: str = "paper"
    portfolio_id: str = "default"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "telemetry_count": self.telemetry_count,
            "persisted_count": self.persisted_count,
            "delta_count": self.delta_count,
            "delta_pct": self.delta_pct,
            "status": self.status.value,
            "timestamp": self.timestamp.isoformat(),
            "discrepancies": [d.to_dict() for d in self.discrepancies],
            "environment": self.environment,
            "portfolio_id": self.portfolio_id,
        }

    @property
    def is_healthy(self) -> bool:
        """Check if reconciliation is healthy (OK status)."""
        return self.status == ReconciliationStatus.OK

    @property
    def has_discrepancies(self) -> bool:
        """Check if there are any discrepancies."""
        return len(self.discrepancies) > 0

    def get_summary(self) -> str:
        """Get a human-readable summary."""
        lines = [
            f"Reconciliation Result [{self.status.value}]",
            f"  Environment: {self.environment}",
            f"  Portfolio: {self.portfolio_id}",
            f"  Timestamp: {self.timestamp.isoformat()}",
            "",
            "  Counts:",
        ]

        for category in sorted(
            set(self.telemetry_count.keys()) | set(self.persisted_count.keys())
        ):
            tel = self.telemetry_count.get(category, 0)
            per = self.persisted_count.get(category, 0)
            delta = self.delta_count.get(category, 0)
            pct = self.delta_pct.get(category, 0.0)
            lines.append(
                f"    {category}: telemetry={tel}, persisted={per}, delta={delta} ({pct:.2f}%)"
            )

        if self.discrepancies:
            lines.append("")
            lines.append("  Discrepancies:")
            for d in self.discrepancies:
                lines.append(f"    {d.category}: {d.delta_pct:.2f}% delta")

        return "\n".join(lines)
