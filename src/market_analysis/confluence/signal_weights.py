"""Signal weights for ICT signals based on EP-ICT-004 validation results.

This module defines signal reliability weights derived from EP-ICT-004 validation.
These weights are used by Layer 2 confluence aggregation to weight signals appropriately.

RE-ENABLED: BOS/CHoCH signals are now included in the signal pipeline (accuracy fix applied).

VALIDATED SIGNALS:
- CVD (Cumulative Volume Delta): 100% validation → weight 1.0
- FVG (Fair Value Gap): 100% validation → weight 1.0
- Order Block: 80.77% validation → weight 0.85
- BOS/CHoCH: Re-enabled — weight 0.65 (initial confidence base)
"""

from dataclasses import dataclass
from enum import Enum


class ICTSignalType(str, Enum):
    """ICT signal types available for confluence scoring.

    BOS/CHoCH signals are now re-enabled after accuracy fix.
    """

    CVD = "cvd"
    FVG = "fvg"
    ORDER_BLOCK = "order_block"
    BOS = "bos"  # Break of Structure - re-enabled
    CHOC = "choc"  # Change of Character - re-enabled

    @classmethod
    def is_valid_signal(cls, signal_type: str) -> bool:
        """Check if a signal type is valid for scoring.

        Args:
            signal_type: The signal type string to check

        Returns:
            True if the signal is valid (recognized enum member)
        """
        try:
            cls(signal_type)
            return True
        except ValueError:
            return False

    @classmethod
    def get_supported_signals(cls) -> list["ICTSignalType"]:
        """Get list of all supported signal types.

        Returns:
            List of all ICT signal types for scoring
        """
        return list(cls)


@dataclass(frozen=True)
class SignalWeight:
    """Weight configuration for a single ICT signal type.

    Attributes:
        signal_type: The type of ICT signal
        reliability_percent: Validation reliability percentage (0-100)
        weight: Computed weight value (0.0-1.0)
        description: Human-readable description of the signal
    """

    signal_type: ICTSignalType
    reliability_percent: float
    weight: float
    description: str


# Signal weights based on EP-ICT-004 validation results
# CVD: 100% validation → weight 1.0
# FVG: 100% validation → weight 1.0
# Order Block: 80.77% validation → weight 0.85

ICT_SIGNAL_WEIGHTS: dict[ICTSignalType, SignalWeight] = {
    ICTSignalType.CVD: SignalWeight(
        signal_type=ICTSignalType.CVD,
        reliability_percent=100.0,
        weight=1.0,
        description="Cumulative Volume Delta - 100% validated",
    ),
    ICTSignalType.FVG: SignalWeight(
        signal_type=ICTSignalType.FVG,
        reliability_percent=100.0,
        weight=1.0,
        description="Fair Value Gap - 100% validated",
    ),
    ICTSignalType.ORDER_BLOCK: SignalWeight(
        signal_type=ICTSignalType.ORDER_BLOCK,
        reliability_percent=80.77,
        weight=0.85,
        description="Order Block - 80.77% validated (BL-OB-003)",
    ),
    ICTSignalType.BOS: SignalWeight(
        signal_type=ICTSignalType.BOS,
        reliability_percent=65.0,
        weight=0.65,
        description="Break of Structure - re-enabled, initial confidence base",
    ),
    ICTSignalType.CHOC: SignalWeight(
        signal_type=ICTSignalType.CHOC,
        reliability_percent=65.0,
        weight=0.65,
        description="Change of Character - re-enabled, initial confidence base",
    ),
}


def get_signal_weight(signal_type: str) -> float:
    """Get the weight for a given signal type.

    Args:
        signal_type: The signal type string

    Returns:
        The signal weight (0.0-1.0), or 0.0 if unknown
    """
    try:
        signal_enum = ICTSignalType(signal_type)
        weight_info = ICT_SIGNAL_WEIGHTS.get(signal_enum)
        return weight_info.weight if weight_info else 0.0
    except ValueError:
        # Unknown signal type - return 0.0
        return 0.0


def get_all_weights() -> dict[str, float]:
    """Get all signal weights as a simple dictionary.

    Returns:
        Dictionary mapping signal type to weight
    """
    return {signal.value: info.weight for signal, info in ICT_SIGNAL_WEIGHTS.items()}


def get_signal_metadata(signal_type: str) -> dict:
    """Get full metadata for a signal type.

    Args:
        signal_type: The signal type string

    Returns:
        Dictionary with signal metadata or empty dict if not found
    """
    try:
        signal_enum = ICTSignalType(signal_type)
        weight_info = ICT_SIGNAL_WEIGHTS.get(signal_enum)
        if weight_info:
            return {
                "signal_type": weight_info.signal_type.value,
                "reliability_percent": weight_info.reliability_percent,
                "weight": weight_info.weight,
                "description": weight_info.description,
            }
    except ValueError:
        pass
    return {}
