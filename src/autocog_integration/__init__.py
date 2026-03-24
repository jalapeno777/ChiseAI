"""Cross-system learning bridge between AUTOCOG and STRONG systems."""

from .adapters import AutocogAdapter, StrongAdapter
from .bridge import BridgeMetrics, BridgeStatus, LearningBridge
from .converters import (
    AutocogToStrongConverter,
    DataFormatConverter,
    StrongToAutocogConverter,
)
from .protocols import KnowledgeTransferProtocol, TransferEvent, TransferStatus

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
