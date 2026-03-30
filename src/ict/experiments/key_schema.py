"""Experiment Key Schema.

Defines the structure and formatting for experiment keys used
in ICT experiment tracking.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class ExperimentKey:
    """Represents an experiment identifier with variant and timing.

    Attributes:
        experiment_id: Experiment identifier (e.g., "ICT-B1", "ICT-B2")
        variant: Experiment variant (e.g., "baseline", "enhanced", "risk_overlay")
        started_at: When the experiment was started

    Example:
        key = ExperimentKey(
            experiment_id="ICT-B1",
            variant="baseline",
            started_at=datetime.now()
        )
        print(key.key_format())
        # Output: "ict:exp:ICT-B1:baseline:20260329"
    """

    experiment_id: str
    variant: str
    started_at: datetime

    def key_format(self) -> str:
        """Generate Redis-compatible key string.

        Returns:
            Formatted key string: `ict:exp:{experiment_id}:{variant}:{YYYYMMDD}`
        """
        date_str = self.started_at.strftime("%Y%m%d")
        return f"ict:exp:{self.experiment_id}:{self.variant}:{date_str}"

    def prefix(self) -> str:
        """Generate key prefix for pattern matching.

        Returns:
            Key prefix for searching related keys
        """
        return f"ict:exp:{self.experiment_id}:{self.variant}"

    def __str__(self) -> str:
        """String representation of the experiment key.

        Returns:
            Human-readable string
        """
        return (
            f"{self.experiment_id}/{self.variant}@{self.started_at.strftime('%Y%m%d')}"
        )
