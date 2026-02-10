"""Signal storage package.

Provides storage backends for signal history tracking:
- InfluxDB: High-throughput time-series storage
- PostgreSQL: Fallback/audit storage with strong consistency

Exports:
    SignalStorageInterface: Abstract storage interface
    InfluxSignalStorage: InfluxDB implementation
    PostgresSignalStorage: PostgreSQL implementation
    SignalRecord: Signal data model
    OutcomeRecord: Outcome data model
    SignalWithOutcome: Combined signal and outcome
    SignalDirection: Signal direction enum
    OutcomeType: Outcome type enum
"""

from market_analysis.signal_storage.influx_storage import InfluxSignalStorage
from market_analysis.signal_storage.interface import SignalStorageInterface
from market_analysis.signal_storage.models import (
    OutcomeRecord,
    OutcomeType,
    SignalDirection,
    SignalRecord,
    SignalWithOutcome,
)
from market_analysis.signal_storage.postgres_storage import PostgresSignalStorage

__all__ = [
    # Storage interfaces and implementations
    "SignalStorageInterface",
    "InfluxSignalStorage",
    "PostgresSignalStorage",
    # Data models
    "SignalRecord",
    "OutcomeRecord",
    "SignalWithOutcome",
    # Enums
    "SignalDirection",
    "OutcomeType",
]
