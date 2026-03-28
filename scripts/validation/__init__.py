"""Validation module for forensic evidence collection and gate validation.

This module provides collectors and validators for the ChiseAI
forensic validation harness. It includes collectors for:
- Discord messages (G5 validation)
- Redis deltas (G1-G4 validation)
- InfluxDB queries (G6-G7 validation)
- Bybit-Journal reconciliation

Example:
    from scripts.validation import (
        ForensicHarness,
        IntegratedForensicHarness,
        DiscordEvidenceCollector,
        RedisDeltaCollector,
        InfluxEvidenceCollector,
        BybitJournalReconciler,
    )

    # Use integrated harness with all collectors
    harness = IntegratedForensicHarness(duration_minutes=30)
    result = await harness.run_integrated_proof_loop()
"""

from .discord_evidence import DiscordEvidenceCollector
from .forensic_harness import (
    ForensicHarness,
    IntegratedForensicHarness,
)
from .influx_evidence import InfluxEvidenceCollector
from .recap_validator import (
    DiscordMessageEvidence,
    GateResult,
    GateStatus,
    OutcomeSourceProof,
    RecapValidationEvidence,
    RecapValidator,
)
from .reconcile_bybit_journal import (
    BybitJournalReconciler,
    ReconciliationReport,
)
from .redis_deltas import RedisDeltaCollector

__all__ = [
    "ForensicHarness",
    "IntegratedForensicHarness",
    "DiscordEvidenceCollector",
    "RedisDeltaCollector",
    "InfluxEvidenceCollector",
    "BybitJournalReconciler",
    "ReconciliationReport",
    "RecapValidator",
    "RecapValidationEvidence",
    "DiscordMessageEvidence",
    "OutcomeSourceProof",
    "GateResult",
    "GateStatus",
]

__version__ = "1.1.0"
