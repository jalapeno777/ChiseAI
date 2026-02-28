"""
Validation module for forensic evidence collection and gate validation.

This module provides collectors and validators for the ChiseAI
forensic validation harness. It includes collectors for:
- Discord messages (G5 validation)
- Redis deltas (G1-G4 validation)
- InfluxDB queries (G6-G7 validation)
- Recap validation (G5 source verification)

Example:
    from scripts.validation import (
        ForensicHarness,
        IntegratedForensicHarness,
        DiscordEvidenceCollector,
        RedisDeltaCollector,
        InfluxEvidenceCollector,
        RecapValidator,
    )

    # Use integrated harness with all collectors
    harness = IntegratedForensicHarness(duration_minutes=30)
    result = await harness.run_integrated_proof_loop()
"""

from scripts.validation.forensic_harness import (
    ForensicHarness,
    IntegratedForensicHarness,
)
from scripts.validation.discord_evidence import DiscordEvidenceCollector
from scripts.validation.redis_deltas import RedisDeltaCollector
from scripts.validation.influx_evidence import InfluxEvidenceCollector
from scripts.validation.recap_validator import RecapValidator

__all__ = [
    "ForensicHarness",
    "IntegratedForensicHarness",
    "DiscordEvidenceCollector",
    "RedisDeltaCollector",
    "InfluxEvidenceCollector",
    "RecapValidator",
]

__version__ = "1.0.0"
