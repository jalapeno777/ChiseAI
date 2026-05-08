"""Signal types for the signal generation registry.

This module defines signal type enums and related constants used
throughout the signal generation system.

RE-ENABLED: BOS/CHoCH signals are now included in the signal pipeline (accuracy fix applied).
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
    BOS_CHOCH = "bos_choch"

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
            List of signal names that are excluded (currently none).
        """
        return []


class SignalPriority(Enum):
    """Detection priority for ICT signals.

    When multiple ICT signals fire simultaneously, the system acts on
    the highest-priority signal first. Lower numeric value = higher priority.

    Priority rationale (ICT Smart Money Concepts):
        1. BOS/CHoCH (priority 1): Structural break signals indicate a
           fundamental shift in market bias. They are the most important
           confirmation of trend change or continuation. Currently excluded
           per BL-BOS-CHOCH-001 but priority preserved for re-enablement.
        2. Order Blocks (priority 2): Institutional order flow zones where
           large market participants placed orders before a strong move.
           These represent the highest-probability entry zones in the ICT
           framework.
        3. FVG (priority 3): Fair Value Gaps represent price imbalance zones
           where price may revisit to fill the gap. Lower priority than Order
           Blocks because FVGs are more frequent and less precise.
        4. Liquidity Sweeps (priority 4): Stop hunts and liquidity grabs
           are common but less actionable on their own. They provide context
           but typically require confluence with higher-priority signals.
        5. Price Structure (priority 5): H/L/H-OLD/L-OLD levels provide
           structural context and support/resistance reference points.
           Lowest priority as they are informational rather than actionable.

    This priority is configurable via ICTSignalRegistry.SIGNAL_PRIORITY_ORDER.
    """

    BOS_CHOCH = 1  # Break of Structure / Change of Character
    ORDER_BLOCK = 2  # Institutional order flow zones
    FVG = 3  # Fair Value Gap (imbalance zones)
    LIQUIDITY_SWEEP = 4  # Stops and liquidity grabs
    PRICE_STRUCTURE = 5  # H/L/H-OLD/L-OLD levels


class SignalSource(Enum):
    """Source of the signal generation."""

    ICT = "ict"
    TECHNICAL = "technical"
    REGIME = "regime"
    CONFLUENCE = "confluence"
    LLM = "llm"
