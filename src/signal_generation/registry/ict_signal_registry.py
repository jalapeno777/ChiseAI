"""ICT Signal Registry.

This module provides the ICTSignalRegistry class for registering and managing
ICT trading signals (CVD, FVG, Order Block) with the signal generation system.

BOS/CHoCH signals are EXCLUDED per BL-BOS-CHOCH-001.

Usage:
    registry = ICTSignalRegistry()

    # Register CVD signal
    registry.register_signal(
        signal_type=ICTSignalType.CVD,
        feature_flag="enable_cvd_signals",
        metadata={"description": "Cumulative Volume Delta"}
    )

    # Get all registered signals
    signals = registry.get_registered_signals()
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from signal_generation.registry.signal_types import (
    ICTSignalType,
    SignalPriority,
    SignalSource,
)

logger = logging.getLogger(__name__)


@dataclass
class SignalMetadata:
    """Metadata for a registered signal.

    Attributes:
        name: Human-readable signal name
        description: Description of the signal
        confidence_base: Base confidence score (0.0-1.0)
        timeframe_default: Default timeframe for the signal
        source: Signal source (ICT, technical, etc.)
        tags: Additional tags for categorization
    """

    name: str
    description: str
    confidence_base: float = 0.5
    timeframe_default: str = "1H"
    source: SignalSource = SignalSource.ICT
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert metadata to dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "confidence_base": self.confidence_base,
            "timeframe_default": self.timeframe_default,
            "source": self.source.value,
            "tags": self.tags,
        }


@dataclass
class RegisteredSignal:
    """A registered signal in the registry.

    Attributes:
        signal_type: The ICT signal type
        metadata: Signal metadata
        feature_flag: Feature flag name for enabling/disabling the signal
        enabled: Whether the signal is currently enabled
        registered_at: When the signal was registered
        last_updated: When the signal was last updated
        priority: Detection priority (lower = higher priority)
    """

    signal_type: ICTSignalType
    metadata: SignalMetadata
    feature_flag: str | None = None
    enabled: bool = True
    registered_at: datetime = field(default_factory=datetime.utcnow)
    last_updated: datetime = field(default_factory=datetime.utcnow)
    priority: int = 10  # Default low priority; set explicitly per signal

    def to_dict(self) -> dict[str, Any]:
        """Convert registered signal to dictionary."""
        return {
            "signal_type": self.signal_type.value,
            "metadata": self.metadata.to_dict(),
            "feature_flag": self.feature_flag,
            "enabled": self.enabled,
            "registered_at": self.registered_at.isoformat(),
            "last_updated": self.last_updated.isoformat(),
        }


class FeatureFlagManager:
    """Manages feature flags for signal enabling/disabling.

    This is a simple implementation that can be replaced with a more
    sophisticated feature flag system (e.g., using a config service).
    """

    def __init__(self) -> None:
        """Initialize feature flag manager."""
        self._flags: dict[str, bool] = {}

    def set_flag(self, name: str, enabled: bool) -> None:
        """Set a feature flag value.

        Args:
            name: Flag name
            enabled: Whether the flag is enabled
        """
        self._flags[name] = enabled
        logger.debug(f"Feature flag '{name}' set to {enabled}")

    def is_enabled(self, name: str | None) -> bool:
        """Check if a feature flag is enabled.

        Args:
            name: Flag name (None means always enabled)

        Returns:
            True if flag is enabled or if name is None
        """
        if name is None:
            return True
        return self._flags.get(name, True)  # Default to True if not set

    def get_flag(self, name: str) -> bool | None:
        """Get a feature flag value.

        Args:
            name: Flag name

        Returns:
            Flag value or None if not set
        """
        return self._flags.get(name)


class ICTSignalRegistry:
    """Registry for ICT trading signals.

    This registry manages ICT-specific signals (CVD, FVG, Order Block)
    and provides feature flag support for enabling/disabling signals.

    BOS/CHoCH signals are EXCLUDED per BL-BOS-CHOCH-001.

    Attributes:
        DEFAULT_SIGNALS: Default ICT signals that are always registered
    """

    # Default ICT signals to register
    DEFAULT_SIGNALS: list[tuple[ICTSignalType, SignalMetadata, str | None]] = [
        (
            ICTSignalType.CVD,
            SignalMetadata(
                name="Cumulative Volume Delta",
                description=(
                    "CVD tracks net volume flow by accumulating tick-level "
                    "buy/sell volume deltas to identify institutional "
                    "buying/selling pressure."
                ),
                confidence_base=0.65,
                timeframe_default="1H",
                tags=["volume", "institutional", "cvd"],
            ),
            "enable_cvd_signals",
        ),
        (
            ICTSignalType.FVG,
            SignalMetadata(
                name="Fair Value Gap",
                description=(
                    "FVG detects bullish and bearish gaps in price action "
                    "using 3-candle patterns, indicating potential fair value "
                    "zones where price may revisit."
                ),
                confidence_base=0.70,
                timeframe_default="1H",
                tags=["price_action", "fvg", "gap"],
            ),
            "enable_fvg_signals",
        ),
        (
            ICTSignalType.ORDER_BLOCK,
            SignalMetadata(
                name="Order Block",
                description=(
                    "Order blocks detect consolidation zones where institutional "
                    "traders positioned themselves before a strong directional move."
                ),
                confidence_base=0.68,
                timeframe_default="1H",
                tags=["zone", "order_block", "institutional"],
            ),
            "enable_order_block_signals",
        ),
        # Price structure signals (H/L/H-OLD/L-OLD) - S1A-2
        (
            ICTSignalType.H,
            SignalMetadata(
                name="High",
                description=(
                    "Current period high - the highest price reached during "
                    "the measurement period. Key resistance level for potential "
                    "reversal or continuation signals."
                ),
                confidence_base=0.60,
                timeframe_default="1H",
                tags=["price_structure", "high", "resistance"],
            ),
            "enable_hl_signals",
        ),
        (
            ICTSignalType.L,
            SignalMetadata(
                name="Low",
                description=(
                    "Current period low - the lowest price reached during "
                    "the measurement period. Key support level for potential "
                    "reversal or continuation signals."
                ),
                confidence_base=0.60,
                timeframe_default="1H",
                tags=["price_structure", "low", "support"],
            ),
            "enable_hl_signals",
        ),
        (
            ICTSignalType.HIGH_OLD,
            SignalMetadata(
                name="Old High",
                description=(
                    "Previous significant high - the most recent swing high "
                    "that preceded the current period. Used to identify "
                    "potential breakouts or rejection at resistance."
                ),
                confidence_base=0.65,
                timeframe_default="1H",
                tags=["price_structure", "high", "swing", "resistance"],
            ),
            "enable_hl_signals",
        ),
        (
            ICTSignalType.LOW_OLD,
            SignalMetadata(
                name="Old Low",
                description=(
                    "Previous significant low - the most recent swing low "
                    "that preceded the current period. Used to identify "
                    "potential breakdowns or rejection at support."
                ),
                confidence_base=0.65,
                timeframe_default="1H",
                tags=["price_structure", "low", "swing", "support"],
            ),
            "enable_hl_signals",
        ),
        # BOS/CHoCH - Break of Structure / Change of Character
        # Re-enabled after accuracy fix (was excluded via BL-BOS-CHOCH-001)
        (
            ICTSignalType.BOS_CHOCH,
            SignalMetadata(
                name="Break of Structure / Change of Character",
                description=(
                    "BOS/CHoCH identifies structural market shifts by detecting "
                    "breaks of significant swing points (BOS) or character changes "
                    "where the market transitions from bullish to bearish structure "
                    "or vice versa (CHoCH)."
                ),
                confidence_base=0.65,
                timeframe_default="1H",
                tags=["structure", "bos", "choch", "institutional"],
            ),
            "enable_bos_choch_signals",
        ),
    ]

    # --- Detection priority configuration (ST-ICT-ST2) ---
    # Maps each ICTSignalType to its SignalPriority value.
    # This mapping is the single source of truth for priority ordering.
    # To reconfigure priority, update this dictionary.
    #
    # Priority rationale:
    #   BOS/CHoCH > Order Blocks > FVG > Liquidity Sweeps > Price Structure
    #   (lower numeric value = higher priority)
    #
    # Note: BOS/CHOCH priority ordering (re-enabled).
    SIGNAL_PRIORITY_ORDER: dict[ICTSignalType, int] = {
        # Priority 1: BOS/CHoCH
        ICTSignalType.BOS_CHOCH: SignalPriority.BOS_CHOCH.value,
        # Priority 2: Order Blocks - institutional order flow zones
        ICTSignalType.ORDER_BLOCK: SignalPriority.ORDER_BLOCK.value,
        # Priority 3: FVG - imbalance / fair value zones
        ICTSignalType.FVG: SignalPriority.FVG.value,
        # Priority 4: CVD - volume delta (treated as liquidity-sensitive)
        ICTSignalType.CVD: SignalPriority.LIQUIDITY_SWEEP.value,
        # Priority 5: Price structure (H/L/H-OLD/L-OLD)
        ICTSignalType.H: SignalPriority.PRICE_STRUCTURE.value,
        ICTSignalType.L: SignalPriority.PRICE_STRUCTURE.value,
        ICTSignalType.HIGH_OLD: SignalPriority.PRICE_STRUCTURE.value,
        ICTSignalType.LOW_OLD: SignalPriority.PRICE_STRUCTURE.value,
    }

    def _get_priority(self, signal_type: ICTSignalType) -> int:
        """Get detection priority for a signal type.

        Args:
            signal_type: The ICT signal type

        Returns:
            Priority value (lower = higher priority). Defaults to 99
            (lowest priority) for unknown signal types.
        """
        return self.SIGNAL_PRIORITY_ORDER.get(signal_type, 99)

    def __init__(self) -> None:
        """Initialize ICT signal registry."""
        self._signals: dict[ICTSignalType, RegisteredSignal] = {}
        self._feature_flags = FeatureFlagManager()
        self._initialize_default_signals()

    def _initialize_default_signals(self) -> None:
        """Register default ICT signals with detection priority."""
        for signal_type, metadata, feature_flag in self.DEFAULT_SIGNALS:
            self._signals[signal_type] = RegisteredSignal(
                signal_type=signal_type,
                metadata=metadata,
                feature_flag=feature_flag,
                enabled=True,
                priority=self._get_priority(signal_type),
            )
            logger.debug(
                f"Registered default signal: {signal_type.value} "
                f"(priority={self._get_priority(signal_type)})"
            )

    def register_signal(
        self,
        signal_type: ICTSignalType,
        metadata: SignalMetadata,
        feature_flag: str | None = None,
        enabled: bool = True,
        priority: int | None = None,
    ) -> RegisteredSignal:
        """Register a new ICT signal.

        Args:
            signal_type: The ICT signal type to register
            metadata: Signal metadata
            feature_flag: Optional feature flag name
            enabled: Whether the signal is enabled
            priority: Detection priority (lower = higher priority).
                If None, uses the default from SIGNAL_PRIORITY_ORDER.

        Returns:
            The registered signal

        Raises:
            ValueError: If signal type is already registered
        """
        if signal_type in self._signals:
            raise ValueError(f"Signal type '{signal_type.value}' is already registered")

        # Set initial feature flag state
        if feature_flag:
            self._feature_flags.set_flag(feature_flag, enabled)

        resolved_priority = (
            priority if priority is not None else self._get_priority(signal_type)
        )

        registered = RegisteredSignal(
            signal_type=signal_type,
            metadata=metadata,
            feature_flag=feature_flag,
            enabled=enabled,
            priority=resolved_priority,
        )
        self._signals[signal_type] = registered
        logger.info(
            f"Registered ICT signal: {signal_type.value} (priority={resolved_priority})"
        )

        return registered

    def unregister_signal(self, signal_type: ICTSignalType) -> bool:
        """Unregister an ICT signal.

        Args:
            signal_type: The signal type to unregister

        Returns:
            True if unregistered, False if not found
        """
        if signal_type in self._signals:
            del self._signals[signal_type]
            logger.info(f"Unregistered ICT signal: {signal_type.value}")
            return True
        return False

    def get_signal(self, signal_type: ICTSignalType) -> RegisteredSignal | None:
        """Get a registered signal by type.

        Args:
            signal_type: The signal type to retrieve

        Returns:
            The registered signal or None if not found
        """
        return self._signals.get(signal_type)

    def get_registered_signals(
        self,
        enabled_only: bool = False,
    ) -> list[RegisteredSignal]:
        """Get all registered signals.

        Args:
            enabled_only: If True, only return enabled signals

        Returns:
            List of registered signals
        """
        signals = list(self._signals.values())

        if enabled_only:
            signals = [s for s in signals if self.is_signal_enabled(s.signal_type)]

        return signals

    def get_registered_signals_sorted_by_priority(
        self,
        enabled_only: bool = False,
    ) -> list[RegisteredSignal]:
        """Get registered signals sorted by detection priority.

        Signals are returned in priority order (lower priority value first =
        higher priority). This determines the order in which signals are
        processed when multiple fire simultaneously.

        Args:
            enabled_only: If True, only return enabled signals

        Returns:
            List of registered signals sorted by priority (ascending)
        """
        signals = self.get_registered_signals(enabled_only=enabled_only)
        return sorted(signals, key=lambda s: s.priority)

    def is_signal_enabled(self, signal_type: ICTSignalType) -> bool:
        """Check if a signal is enabled.

        Checks both the enabled flag and the feature flag state.

        Args:
            signal_type: The signal type to check

        Returns:
            True if the signal is enabled
        """
        registered = self._signals.get(signal_type)
        if not registered:
            return False

        # Check registered enabled flag
        if not registered.enabled:
            return False

        # Check feature flag
        if registered.feature_flag:
            return self._feature_flags.is_enabled(registered.feature_flag)

        return True

    def set_signal_enabled(
        self,
        signal_type: ICTSignalType,
        enabled: bool,
    ) -> bool:
        """Enable or disable a signal.

        Args:
            signal_type: The signal type to enable/disable
            enabled: Whether to enable the signal

        Returns:
            True if updated, False if signal not found
        """
        registered = self._signals.get(signal_type)
        if not registered:
            return False

        registered.enabled = enabled
        registered.last_updated = datetime.utcnow()

        if registered.feature_flag:
            self._feature_flags.set_flag(registered.feature_flag, enabled)

        logger.info(
            f"Signal '{signal_type.value}' {'enabled' if enabled else 'disabled'}"
        )
        return True

    def set_feature_flag(self, name: str, enabled: bool) -> None:
        """Set a feature flag value.

        Args:
            name: Flag name
            enabled: Whether the flag is enabled
        """
        self._feature_flags.set_flag(name, enabled)

        # Update all signals with this feature flag
        for signal in self._signals.values():
            if signal.feature_flag == name:
                signal.last_updated = datetime.utcnow()

    def get_signal_metadata(
        self,
        signal_type: ICTSignalType,
    ) -> SignalMetadata | None:
        """Get metadata for a signal type.

        Args:
            signal_type: The signal type

        Returns:
            Signal metadata or None if not found
        """
        registered = self._signals.get(signal_type)
        return registered.metadata if registered else None

    def list_signal_types(
        self,
        enabled_only: bool = False,
    ) -> list[ICTSignalType]:
        """List all registered signal types.

        Args:
            enabled_only: If True, only return enabled signal types

        Returns:
            List of registered signal types
        """
        signals = self.get_registered_signals(enabled_only=enabled_only)
        return [s.signal_type for s in signals]

    def get_excluded_signals(self) -> list[str]:
        """Get list of excluded signal names.

        Returns:
            List of signal names excluded per BL-BOS-CHOCH-001
        """
        return ICTSignalType.get_excluded_signals()

    def to_dict(self) -> dict[str, Any]:
        """Convert registry to dictionary.

        Returns:
            Dictionary representation of the registry
        """
        return {
            "signals": {st.value: reg.to_dict() for st, reg in self._signals.items()},
            "excluded_signals": self.get_excluded_signals(),
            "feature_flags": {
                name: flag for name, flag in self._feature_flags._flags.items()
            },
        }


# Global registry instance
_registry: ICTSignalRegistry | None = None


def get_ict_registry() -> ICTSignalRegistry:
    """Get or create global ICT signal registry instance.

    Returns:
        The global ICT signal registry
    """
    global _registry
    if _registry is None:
        _registry = ICTSignalRegistry()
    return _registry
