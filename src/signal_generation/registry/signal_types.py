"""Signal types for the signal generation registry.

This module defines signal type enums and related constants used
throughout the signal generation system.

EXCLUDED: BOS/CHoCH signals are explicitly excluded per BL-BOS-CHOCH-001.
These signals should not be registered in the ICT signal registry.
"""

from enum import Enum


class SignalType(Enum):
    """Base signal types for the signal generation system."""

    # Technical analysis signals
    CVD = "cvd"  # Cumulative Volume Delta
    FVG = "fvg"  # Fair Value Gap
    ORDER_BLOCK = "order_block"  # Order Block
    BOS = "bos"  # Break of Structure
    CHOCH = "choch"  # Change of Character

    # Indicator-based signals
    RSI = "rsi"
    MACD = "macd"
    BOLLINGER = "bollinger_bands"

    # Other signals
    REGIME = "regime"
    ZONE = "zone"
    CONFLUENCE = "confluence"


class ICTSignalType(Enum):
    """ICT-specific signal types.

    Note: BOS/CHoCH signals are EXCLUDED per BL-BOS-CHOCH-001.
    These signal types should not be used or registered.

    EXCLUDED_SIGNALS:
        - BOS_CHOCH: "bos_choch" - Break of Structure / Change of Character

    Price Structure Signals (S1A-2):
        H: Current period high
        L: Current period low
        HIGH_OLD: Previous significant high
        LOW_OLD: Previous significant low
    """

    CVD = "cvd"
    FVG = "fvg"
    ORDER_BLOCK = "order_block"
    # BOS_CHOCH = "bos_choch"  # EXCLUDED per BL-BOS-CHOCH-001

    # Price structure signals (H/L/H-OLD/L-OLD)
    H = "h"  # Current period high
    L = "l"  # Current period low
    HIGH_OLD = "high_old"  # Previous significant high
    LOW_OLD = "low_old"  # Previous significant low

    @classmethod
    def is_excluded(cls, signal_type: "ICTSignalType") -> bool:
        """Check if a signal type is excluded.

        Args:
            signal_type: The ICT signal type to check

        Returns:
            True if the signal type is excluded, False otherwise
        """
        # Currently all ICTSignalType members are valid (not excluded)
        # This method exists for future expansion if needed
        return False

    @classmethod
    def get_excluded_signals(cls) -> list[str]:
        """Get list of excluded signal names.

        Returns:
            List of signal names that are excluded per BL-BOS-CHOCH-001
        """
        return ["bos_choch"]


class SignalSource(Enum):
    """Source of the signal generation."""

    ICT = "ict"
    TECHNICAL = "technical"
    REGIME = "regime"
    CONFLUENCE = "confluence"
    LLM = "llm"
