"""Cross-system learning bridge between AUTOCOG and STRONG systems."""

from .bridge import LearningBridge, BridgeMetrics, BridgeStatus
from .protocols import KnowledgeTransferProtocol, TransferEvent, TransferStatus
from .converters import (
    DataFormatConverter,
    AutocogToStrongConverter,
    StrongToAutocogConverter,
)
from .adapters import AutocogAdapter, StrongAdapter

__all__ = [
    "LearningBridge",
    "BridgeMetrics",
    "BridgeStatus",
    "KnowledgeTransferProtocol",
    "TransferEvent",
    "TransferStatus",
    "DataFormatConverter",
    "AutocogToStrongConverter",
    "StrongToAutocogConverter",
    "AutocogAdapter",
    "StrongAdapter",
]
