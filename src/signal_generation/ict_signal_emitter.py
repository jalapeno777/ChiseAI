"""ICT Signal Emitter for signal generation pipeline.

This module provides the ICTSignalEmitter class that polls ICT detectors
(CVD, FVG, Order Block) and emits signals to the signal bus.

BOS/CHoCH signals are EXCLUDED per BL-BOS-CHOCH-001.

Usage:
    emitter = ICTSignalEmitter()
    await emitter.emit_signals(token="BTC/USDT", timeframe="1H")

Feature Flags (from ST-ICT-018):
    - enable_cvd_signals: Enable CVD signal emission
    - enable_fvg_signals: Enable FVG signal emission
    - enable_order_block_signals: Enable Order Block signal emission

Dependencies:
    - ST-ICT-014: TwoLayerScorer for confluence scoring
    - ST-ICT-015: ICTSignalRegistry for signal registration
    - ST-ICT-018: Feature flags for signal enablement
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from ict.liquidity.models import SweepSignal as LiquiditySweepSignal
from signal_generation.models import Signal, SignalDirection, SignalStatus
from signal_generation.registry.ict_signal_registry import (
    ICTSignalRegistry,
    get_ict_registry,
)
from validation.data_collection.signal_tracker import (
    SignalGroup,
    SignalTracker,
)

if TYPE_CHECKING:
    from market_analysis.confluence.two_layer_scorer import TwoLayerScorer
    from signal_generation.signal_emitter import SignalEmitter

logger = logging.getLogger(__name__)


@dataclass
class ICTEmissionConfig:
    """Configuration for ICT signal emission.

    Attributes:
        min_confidence: Minimum confidence threshold for emission (0.0-1.0)
        enable_cvd: Whether to enable CVD signals
        enable_fvg: Whether to enable FVG signals
        enable_order_block: Whether to enable Order Block signals
        enable_hl: Whether to enable H/L/H-OLD/L-OLD signals (S1A-2)
        enable_sweep: Whether to enable liquidity sweep (stop hunt) signals
        emission_interval_seconds: Interval between emission cycles
        max_signals_per_cycle: Maximum signals to emit per cycle
        bos_choch_warning: Whether to log warning if BOS/CHoCH detected
        signal_priority: Detection priority order. When multiple signals fire
            simultaneously, they are processed in this order (list of signal
            type strings). Lower index = higher priority. If None, uses the
            default from ICTSignalRegistry.SIGNAL_PRIORITY_ORDER.
    """

    min_confidence: float = 0.50
    enable_cvd: bool = True
    enable_fvg: bool = True
    enable_order_block: bool = True
    enable_hl: bool = True
    enable_sweep: bool = True
    emission_interval_seconds: float = 60.0
    max_signals_per_cycle: int = 10
    bos_choch_warning: bool = True
    signal_priority: list[str] | None = None  # Configurable priority override


@dataclass
class ICTSignalResult:
    """Result of ICT signal emission.

    Attributes:
        signal: The emitted signal
        signal_type: Type of ICT signal (cvd, fvg, order_block)
        emission_success: Whether emission succeeded
        emission_error: Error message if emission failed
        emission_latency_ms: Time taken to emit (ms)
        skipped: Whether signal was skipped (feature flag or confidence)
        skip_reason: Reason for skipping if applicable
    """

    signal: Signal | None = None
    signal_type: str = ""
    emission_success: bool = False
    emission_error: str | None = None
    emission_latency_ms: float = 0.0
    skipped: bool = False
    skip_reason: str | None = None


@dataclass
class ICTEmissionCycle:
    """Result of a complete ICT emission cycle.

    Attributes:
        cycle_id: Unique identifier for this cycle
        timestamp: When the cycle started
        duration_ms: Total cycle duration (ms)
        signals_processed: Number of signals processed
        signals_emitted: Number of signals emitted
        signals_skipped: Number of signals skipped
        results: Individual signal results
        excluded_signals: List of excluded signal types (BOS/CHoCH)
        errors: Any errors encountered during the cycle
    """

    cycle_id: str
    timestamp: datetime
    duration_ms: float = 0.0
    signals_processed: int = 0
    signals_emitted: int = 0
    signals_skipped: int = 0
    results: list[ICTSignalResult] = field(default_factory=list)
    excluded_signals: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "cycle_id": self.cycle_id,
            "timestamp": self.timestamp.isoformat(),
            "duration_ms": round(self.duration_ms, 3),
            "signals_processed": self.signals_processed,
            "signals_emitted": self.signals_emitted,
            "signals_skipped": self.signals_skipped,
            "results": [
                {
                    "signal_type": r.signal_type,
                    "emission_success": r.emission_success,
                    "emission_error": r.emission_error,
                    "emission_latency_ms": round(r.emission_latency_ms, 3),
                    "skipped": r.skipped,
                    "skip_reason": r.skip_reason,
                }
                for r in self.results
            ],
            "excluded_signals": self.excluded_signals,
            "errors": self.errors,
        }


class ICTSignalEmitter:
    """ICT Signal Emitter for signal generation pipeline.

    Polls ICT detectors (CVD, FVG, Order Block) and emits signals
    to the configured signal emitters (Discord, Dashboard, etc.).

    BOS/CHoCH signals are EXCLUDED per BL-BOS-CHOCH-001.

    This emitter:
    1. Checks feature flags for signal enablement
    2. Uses TwoLayerScorer for confluence scoring
    3. Respects minimum confidence thresholds
    4. Emits signals to the signal bus via registered emitters

    Attributes:
        config: Emission configuration
        registry: ICT signal registry for feature flags
        emitters: List of signal emitters for delivery
        two_layer_scorer: Two-layer scorer for ICT signals
        name: Emitter name identifier
    """

    name: str = "ict_signal_emitter"

    # BOS/CHoCH exclusion reference
    BOS_CHOCH_EXCLUSION_NOTICE = "BOS/CHoCH signals are EXCLUDED per BL-BOS-CHOCH-001"

    def __init__(
        self,
        config: ICTEmissionConfig | None = None,
        registry: ICTSignalRegistry | None = None,
        emitters: list[SignalEmitter] | None = None,
        two_layer_scorer: TwoLayerScorer | None = None,
        signal_tracker: SignalTracker | None = None,
    ):
        """Initialize ICT signal emitter.

        Args:
            config: Emission configuration (uses defaults if None)
            registry: ICT signal registry (uses global registry if None)
            emitters: List of signal emitters for delivery
            two_layer_scorer: Two-layer scorer instance (created if None)
            signal_tracker: SignalTracker for experiment telemetry (optional)
        """
        self.config = config or ICTEmissionConfig()
        self.registry = registry or get_ict_registry()
        self.emitters = emitters or []
        self._two_layer_scorer = two_layer_scorer
        self._signal_tracker = signal_tracker

        # Set initial feature flags from config
        self._sync_feature_flags()

        # Cycle tracking
        self._cycle_count = 0

        # Direction distribution tracking for bias detection
        self._direction_counts: dict[str, int] = {
            "long": 0,
            "short": 0,
            "neutral_skipped": 0,
        }
        self._direction_log_interval = 50  # Log every N signals

        logger.info(
            f"ICTSignalEmitter initialized: "
            f"min_confidence={self.config.min_confidence:.0%}, "
            f"cvd={self.config.enable_cvd}, fvg={self.config.enable_fvg}, "
            f"ob={self.config.enable_order_block}, "
            f"hl={self.config.enable_hl}, "
            f"telemetry={'enabled' if signal_tracker else 'disabled'}"
        )

    def _sync_feature_flags(self) -> None:
        """Sync feature flags from config to registry."""
        if self.config.enable_cvd:
            self.registry.set_feature_flag("enable_cvd_signals", True)
        if self.config.enable_fvg:
            self.registry.set_feature_flag("enable_fvg_signals", True)
        if self.config.enable_order_block:
            self.registry.set_feature_flag("enable_order_block_signals", True)
        if self.config.enable_hl:
            self.registry.set_feature_flag("enable_hl_signals", True)
        if self.config.enable_sweep:
            self.registry.set_feature_flag("enable_sweep_signals", True)

    def _get_two_layer_scorer(self) -> TwoLayerScorer:
        """Get or create TwoLayerScorer instance.

        Returns:
            TwoLayerScorer instance
        """
        if self._two_layer_scorer is None:
            from market_analysis.confluence.two_layer_scorer import TwoLayerScorer

            self._two_layer_scorer = TwoLayerScorer()
        return self._two_layer_scorer

    def _get_signal_tracker(self) -> SignalTracker | None:
        """Get or create SignalTracker instance.

        Returns:
            SignalTracker instance or None if not configured
        """
        if self._signal_tracker is None:
            # Try to create from environment/default Redis
            try:
                from validation.experiment_tracker import create_redis_tracker

                self._signal_tracker = create_redis_tracker()
            except Exception as e:
                logger.warning(f"Could not create SignalTracker: {e}")
                return None
        return self._signal_tracker

    async def _track_signal_for_experiment(
        self,
        signal: Signal,
        signal_type: str,
        confluence_score: float | None,
        direction: str,
    ) -> None:
        """Track signal for ICT experiment telemetry.

        Args:
            signal: The emitted Signal object
            signal_type: Type of signal (cvd, fvg, order_block)
            confluence_score: ICT confluence score (None for control, present for treatment)
            direction: Signal direction (bullish/bearish)
        """
        tracker = self._get_signal_tracker()
        if tracker is None:
            logger.debug("SignalTracker not configured, skipping telemetry tracking")
            return

        try:
            # Determine group based on confluence_score presence
            # TREATMENT: signal has ICT confluence scoring
            # CONTROL: signal without confluence scoring (baseline)
            if confluence_score is not None and confluence_score > 0:
                group = SignalGroup.TREATMENT
            else:
                group = SignalGroup.CONTROL

            # Extract entry price from signal metadata if available
            entry_price = 0.0
            if signal.metadata:
                entry_price = signal.metadata.get("entry_price", 0.0)

            # Track the signal
            tracked = tracker.track_signal(
                signal_type=signal_type,
                group=group,
                entry_price=entry_price,
                direction=direction,
                confluence_score=confluence_score,
                metadata={
                    "token": signal.token,
                    "timeframe": signal.timeframe,
                    "confidence": signal.confidence,
                    "source": "ict_signal_emitter",
                },
            )

            logger.info(
                f"Tracked {signal_type} signal for experiment: "
                f"id={tracked.signal_id}, group={group.value}, "
                f"confluence={confluence_score}"
            )

        except Exception as e:
            # Log but don't fail the emission if tracking fails
            logger.error(f"Failed to track signal for experiment: {e}")

    def _check_bos_choch_exclusion(self, signal_type: str) -> bool:
        """Check if signal type is BOS/CHoCH and should be excluded.

        Args:
            signal_type: The signal type to check

        Returns:
            True if signal should be excluded, False otherwise
        """
        # BOS/CHOCH re-enabled — no longer excluded
        return False

    def _log_bos_choch_warning(self, signal_type: str) -> None:
        """Log warning if BOS/CHoCH signal is detected.

        Args:
            signal_type: The BOS/CHoCH signal type detected
        """
        if self.config.bos_choch_warning:
            logger.warning(
                f"BOS/CHoCH signal detected: {signal_type}. "
                f"{self.BOS_CHOCH_EXCLUSION_NOTICE}"
            )

    def set_feature_flag(self, signal_type: str, enabled: bool) -> None:
        """Set feature flag for a signal type.

        Args:
            signal_type: The signal type (cvd, fvg, order_block, h, l, high_old, low_old)
            enabled: Whether the signal type is enabled
        """
        flag_map = {
            "cvd": "enable_cvd_signals",
            "fvg": "enable_fvg_signals",
            "order_block": "enable_order_block_signals",
            # H/L/H-OLD/L-OLD price structure signals (S1A-2)
            "h": "enable_hl_signals",
            "l": "enable_hl_signals",
            "high_old": "enable_hl_signals",
            "low_old": "enable_hl_signals",
            # Liquidity sweep (stop hunt) signals (ST-ICT-ST3)
            "liquidity_sweep": "enable_sweep_signals",
        }

        flag_name = flag_map.get(signal_type.lower())
        if flag_name:
            self.registry.set_feature_flag(flag_name, enabled)
            logger.info(f"Feature flag '{flag_name}' set to {enabled}")

            # Also update two-layer scorer
            scorer = self._get_two_layer_scorer()
            scorer.set_signal_enabled(signal_type.lower(), enabled)

    def is_signal_enabled(self, signal_type: str) -> bool:
        """Check if a signal type is enabled via feature flag.

        Args:
            signal_type: The signal type to check

        Returns:
            True if the signal type is enabled
        """
        # Check feature flag via registry
        flag_map = {
            "cvd": "enable_cvd_signals",
            "fvg": "enable_fvg_signals",
            "order_block": "enable_order_block_signals",
            # H/L/H-OLD/L-OLD price structure signals (S1A-2)
            "h": "enable_hl_signals",
            "l": "enable_hl_signals",
            "high_old": "enable_hl_signals",
            "low_old": "enable_hl_signals",
            # Liquidity sweep (stop hunt) signals (ST-ICT-ST3)
            "liquidity_sweep": "enable_sweep_signals",
        }

        flag_name = flag_map.get(signal_type.lower())
        if flag_name:
            return self.registry._feature_flags.is_enabled(flag_name)

        return True

    def _log_direction_distribution(self) -> None:
        """Log direction distribution and warn on extreme bias."""
        long_count = self._direction_counts["long"]
        short_count = self._direction_counts["short"]
        neutral_count = self._direction_counts["neutral_skipped"]
        total = long_count + short_count + neutral_count

        if total > 0 and total % self._direction_log_interval == 0:
            logger.info(
                f"ICT signal direction distribution: "
                f"LONG={long_count}, SHORT={short_count}, "
                f"NEUTRAL_SKIPPED={neutral_count}"
            )

        # Extreme bias warning: SHORT:LONG > 100:1
        if short_count > 100 * max(long_count, 1):
            logger.warning(
                f"Extreme SHORT bias detected: {short_count}:{long_count} "
                f"(neutral_skipped={neutral_count})"
            )

    def _create_signal_from_ict(
        self,
        signal_type: str,
        confluence_score: float,
        direction: SignalDirection,
        confidence: float,
        token: str,
        timeframe: str,
        metadata: dict[str, Any] | None = None,
    ) -> Signal | None:
        """Create a Signal from ICT scoring results.

        Args:
            signal_type: Type of ICT signal (cvd, fvg, order_block)
            confluence_score: Confluence score from two-layer scorer
            direction: Signal direction
            confidence: Confidence score
            token: Trading pair
            timeframe: Timeframe string
            metadata: Additional metadata

        Returns:
            Signal instance
        """
        # Map direction — explicit 3-way to avoid NEUTRAL→SHORT silent mapping
        from signal_generation.models import SignalDirection as SigDir

        if direction == SignalDirection.LONG or direction.value == "long":
            sig_direction = SigDir.LONG
            self._direction_counts["long"] += 1
        elif direction == SignalDirection.SHORT or direction.value == "short":
            sig_direction = SigDir.SHORT
            self._direction_counts["short"] += 1
        else:
            self._direction_counts["neutral_skipped"] += 1
            self._log_direction_distribution()
            logger.debug("Skipping signal with NEUTRAL direction from ICT scoring")
            return None

        self._log_direction_distribution()

        # Determine status based on confidence threshold
        # Use configurable threshold from TradingModeConfig via min_confidence
        actionable_threshold = getattr(self.config, "signal_confidence_threshold", 0.75)
        status = SignalStatus.LOGGED_ONLY
        if confidence >= actionable_threshold:
            status = SignalStatus.ACTIONABLE

        # Build metadata
        signal_metadata = metadata or {}
        signal_metadata.update(
            {
                "signal_type": signal_type,
                "source": "ict",
                "confluence_score": confluence_score,
            }
        )

        return Signal(
            token=token,
            direction=sig_direction,
            confidence=confidence,
            base_score=confluence_score * 100,
            timestamp=datetime.now(UTC),
            status=status,
            timeframe=timeframe,
            contributing_factors=[
                {
                    "factor": f"ict_{signal_type}",
                    "weight": 1.0,
                    "score": confluence_score,
                }
            ],
            metadata=signal_metadata,
        )

    async def emit_signal(
        self,
        signal_type: str,
        token: str,
        timeframe: str,
        signal_data: Any,
    ) -> ICTSignalResult:
        """Emit a single ICT signal.

        Args:
            signal_type: Type of ICT signal (cvd, fvg, order_block)
            token: Trading pair
            timeframe: Timeframe string
            signal_data: Signal-specific data (CVDResult, FVGDetectionResult, etc.)

        Returns:
            ICTSignalResult with emission status
        """
        start_time = time.perf_counter()

        # Check feature flag
        if not self.is_signal_enabled(signal_type):
            return ICTSignalResult(
                signal_type=signal_type,
                skipped=True,
                skip_reason=f"Feature flag disabled for {signal_type}",
            )

        try:
            # Score signal using two-layer scorer
            scorer = self._get_two_layer_scorer()

            if signal_type == "cvd":
                score_result = scorer.score(
                    cvd_result=signal_data,
                    timeframe=timeframe,
                )
            elif signal_type == "fvg":
                fvg_list = (
                    signal_data if isinstance(signal_data, list) else [signal_data]
                )
                score_result = scorer.score(
                    fvg_results=fvg_list,
                    timeframe=timeframe,
                )
            elif signal_type == "order_block":
                ob_list = (
                    signal_data if isinstance(signal_data, list) else [signal_data]
                )
                score_result = scorer.score(
                    order_blocks=ob_list,
                    timeframe=timeframe,
                )
            # H/L/H-OLD/L-OLD price structure signals (S1A-2)
            # These are direct price level signals with their own directionality
            elif signal_type in ("h", "l", "high_old", "low_old"):
                # signal_data for HL signals is expected to be a dict with:
                # {
                #     "price": float,          # The price level
                #     "direction": str,        # "long" or "short" based on context
                #     "confidence": float,     # Confidence score 0.0-1.0
                #     "timestamp": int,        # Unix timestamp ms
                #     "swing_high": float,     # For H-OLD/L-OLD, the swing high/low price
                #     "swing_low": float,      # For H-OLD/L-OLD, the swing high/low price
                # }
                if not isinstance(signal_data, dict):
                    return ICTSignalResult(
                        signal_type=signal_type,
                        skipped=True,
                        skip_reason=f"Invalid signal_data for {signal_type}: expected dict",
                    )

                price = signal_data.get("price", 0.0)
                direction_str = signal_data.get("direction", "long")
                confidence = signal_data.get("confidence", 0.60)

                # Create signal directly for HL signals
                from signal_generation.models import SignalDirection as SigDir

                # Explicit 3-way direction mapping (defensive)
                if direction_str == "long":
                    sig_direction = SigDir.LONG
                    self._direction_counts["long"] += 1
                elif direction_str == "short":
                    sig_direction = SigDir.SHORT
                    self._direction_counts["short"] += 1
                else:
                    self._direction_counts["neutral_skipped"] += 1
                    self._log_direction_distribution()
                    logger.debug(
                        f"Skipping HL signal with unexpected direction: "
                        f"'{direction_str}'"
                    )
                    return ICTSignalResult(
                        signal_type=signal_type,
                        skipped=True,
                        skip_reason=f"unexpected_direction:{direction_str}",
                    )

                actionable_threshold = getattr(
                    self.config, "signal_confidence_threshold", 0.75
                )
                status = SignalStatus.LOGGED_ONLY
                if confidence >= actionable_threshold:
                    status = SignalStatus.ACTIONABLE

                signal = Signal(
                    token=token,
                    direction=sig_direction,
                    confidence=confidence,
                    base_score=confidence * 100,
                    timestamp=datetime.now(UTC),
                    status=status,
                    timeframe=timeframe,
                    contributing_factors=[
                        {
                            "factor": f"ict_{signal_type}",
                            "weight": 1.0,
                            "score": confidence,
                        }
                    ],
                    metadata={
                        "signal_type": signal_type,
                        "source": "ict",
                        "price": price,
                        "swing_high": signal_data.get("swing_high"),
                        "swing_low": signal_data.get("swing_low"),
                    },
                )

                # Emit to all registered emitters
                emission_latency_ms = 0.0
                any_success = False
                last_error = None

                for emitter in self.emitters:
                    try:
                        result = await emitter.emit(signal)
                        emission_latency_ms += result.latency_ms
                        if result.success:
                            any_success = True
                        else:
                            last_error = result.error
                    except Exception as e:
                        last_error = str(e)
                        logger.error(f"Emitter {emitter.name} failed: {e}")

                latency_ms = (time.perf_counter() - start_time) * 1000

                return ICTSignalResult(
                    signal=signal,
                    signal_type=signal_type,
                    emission_success=any_success,
                    emission_error=last_error,
                    emission_latency_ms=latency_ms,
                )
            # Liquidity sweep (stop hunt) signals (ST-ICT-ST3)
            # signal_data is a LiquiditySweepSignal with confidence, direction, sweep info
            elif signal_type == "liquidity_sweep":
                if not isinstance(signal_data, LiquiditySweepSignal):
                    return ICTSignalResult(
                        signal_type=signal_type,
                        skipped=True,
                        skip_reason="Invalid signal_data for liquidity_sweep: expected SweepSignal",
                    )

                # Apply confidence threshold (reject < 0.75 per ST-ICT-ST3)
                actionable_threshold = getattr(
                    self.config, "signal_confidence_threshold", 0.75
                )
                if signal_data.confidence < actionable_threshold:
                    return ICTSignalResult(
                        signal_type=signal_type,
                        skipped=True,
                        skip_reason="confidence_below_threshold",
                    )

                from signal_generation.models import SignalDirection as SigDir

                # Explicit mapping for sweep direction (defensive —
                # SweepDirection only has BULLISH/BEARISH but be safe)
                sweep_val = signal_data.signal_direction.value
                if sweep_val == "bullish_sweep":
                    sig_direction = SigDir.LONG
                    self._direction_counts["long"] += 1
                elif sweep_val == "bearish_sweep":
                    sig_direction = SigDir.SHORT
                    self._direction_counts["short"] += 1
                else:
                    self._direction_counts["neutral_skipped"] += 1
                    self._log_direction_distribution()
                    logger.warning(
                        f"Unknown sweep direction '{sweep_val}', skipping "
                        f"liquidity sweep signal"
                    )
                    return ICTSignalResult(
                        signal_type=signal_type,
                        skipped=True,
                        skip_reason=f"unknown_sweep_direction:{sweep_val}",
                    )

                status = SignalStatus.LOGGED_ONLY
                if signal_data.confidence >= actionable_threshold:
                    status = SignalStatus.ACTIONABLE

                signal = Signal(
                    token=token,
                    direction=sig_direction,
                    confidence=signal_data.confidence,
                    base_score=signal_data.confidence * 100,
                    timestamp=datetime.now(UTC),
                    status=status,
                    timeframe=timeframe,
                    contributing_factors=[
                        {
                            "factor": "ict_liquidity_sweep",
                            "weight": 1.0,
                            "score": signal_data.confidence,
                        }
                    ],
                    metadata={
                        "signal_type": "liquidity_sweep",
                        "source": "ict",
                        "level_type": signal_data.metadata.get("level_type"),
                        "level_price": signal_data.metadata.get("level_price"),
                        "penetration_pct": signal_data.metadata.get("penetration_pct"),
                        "wick_ratio": signal_data.metadata.get("wick_ratio"),
                        "strength": signal_data.metadata.get("strength"),
                    },
                )

                # Emit to all registered emitters
                emission_latency_ms = 0.0
                any_success = False
                last_error = None

                for emitter in self.emitters:
                    try:
                        result = await emitter.emit(signal)
                        emission_latency_ms += result.latency_ms
                        if result.success:
                            any_success = True
                        else:
                            last_error = result.error
                    except Exception as e:
                        last_error = str(e)
                        logger.error(f"Emitter {emitter.name} failed: {e}")

                latency_ms = (time.perf_counter() - start_time) * 1000

                return ICTSignalResult(
                    signal=signal,
                    signal_type=signal_type,
                    emission_success=any_success,
                    emission_error=last_error,
                    emission_latency_ms=latency_ms,
                )
            # BOS/CHOCH signals (Break of Structure / Change of Character - re-enabled)
            elif signal_type in ("bos", "choch", "bos_choch"):
                # signal_data is expected to be a dict with:
                # {
                #     "price": float,
                #     "direction": str,
                #     "confidence": float,
                # }
                if not isinstance(signal_data, dict):
                    signal_data = {}

                price = signal_data.get("price", 0.0)
                direction_str = signal_data.get("direction", "long")
                confidence = signal_data.get("confidence", 0.65)

                from signal_generation.models import SignalDirection as SigDir

                # Explicit 3-way direction mapping (defensive)
                if direction_str == "long":
                    sig_direction = SigDir.LONG
                    self._direction_counts["long"] += 1
                elif direction_str == "short":
                    sig_direction = SigDir.SHORT
                    self._direction_counts["short"] += 1
                else:
                    self._direction_counts["neutral_skipped"] += 1
                    self._log_direction_distribution()
                    logger.debug(
                        f"Skipping BOS/CHoCH signal with unexpected direction: "
                        f"'{direction_str}'"
                    )
                    return ICTSignalResult(
                        signal_type=signal_type,
                        skipped=True,
                        skip_reason=f"unexpected_direction:{direction_str}",
                    )

                actionable_threshold = getattr(
                    self.config, "signal_confidence_threshold", 0.75
                )
                status = SignalStatus.LOGGED_ONLY
                if confidence >= actionable_threshold:
                    status = SignalStatus.ACTIONABLE

                signal = Signal(
                    token=token,
                    direction=sig_direction,
                    confidence=confidence,
                    base_score=confidence * 100,
                    timestamp=datetime.now(UTC),
                    status=status,
                    timeframe=timeframe,
                    contributing_factors=[
                        {
                            "factor": f"ict_{signal_type}",
                            "weight": 1.0,
                            "score": confidence,
                        }
                    ],
                    metadata={
                        "signal_type": signal_type,
                        "source": "ict",
                        "price": price,
                    },
                )

                # Emit to all registered emitters
                emission_latency_ms = 0.0
                any_success = False
                last_error = None

                for emitter in self.emitters:
                    try:
                        result = await emitter.emit(signal)
                        emission_latency_ms += result.latency_ms
                        if result.success:
                            any_success = True
                        else:
                            last_error = result.error
                    except Exception as e:
                        last_error = str(e)
                        logger.error(f"Emitter {emitter.name} failed: {e}")

                # Track signal for experiment telemetry if emission succeeded
                if any_success:
                    await self._track_signal_for_experiment(
                        signal=signal,
                        signal_type=signal_type,
                        confluence_score=confidence,
                        direction=sig_direction.value,
                    )

                latency_ms = (time.perf_counter() - start_time) * 1000

                return ICTSignalResult(
                    signal=signal,
                    signal_type=signal_type,
                    emission_success=any_success,
                    emission_error=last_error,
                    emission_latency_ms=latency_ms,
                )
            else:
                return ICTSignalResult(
                    signal_type=signal_type,
                    skipped=True,
                    skip_reason=f"Unsupported signal type: {signal_type}",
                )

            # Check confidence threshold (ST-ICT-S4: use signal_confidence_threshold for actionable gate)
            actionable_threshold = getattr(
                self.config, "signal_confidence_threshold", 0.75
            )
            if score_result.confidence < actionable_threshold:
                return ICTSignalResult(
                    signal_type=signal_type,
                    skipped=True,
                    skip_reason="confidence_below_threshold",
                )

            # Create signal
            signal = self._create_signal_from_ict(
                signal_type=signal_type,
                confluence_score=score_result.confluence_score,
                direction=score_result.direction,
                confidence=score_result.confidence,
                token=token,
                timeframe=timeframe,
                metadata=score_result.to_dict(),
            )

            # If direction was NEUTRAL, signal is None (skipped)
            if signal is None:
                return ICTSignalResult(
                    signal_type=signal_type,
                    skipped=True,
                    skip_reason="neutral_direction_skipped",
                )

            # Emit to all registered emitters
            emission_latency_ms = 0.0
            any_success = False
            last_error = None

            for emitter in self.emitters:
                try:
                    result = await emitter.emit(signal)
                    emission_latency_ms += result.latency_ms
                    if result.success:
                        any_success = True
                    else:
                        last_error = result.error
                except Exception as e:
                    last_error = str(e)
                    logger.error(f"Emitter {emitter.name} failed: {e}")

            # Track signal for experiment telemetry if emission succeeded
            if any_success:
                await self._track_signal_for_experiment(
                    signal=signal,
                    signal_type=signal_type,
                    confluence_score=score_result.confluence_score,
                    direction=signal.direction.value,
                )

            latency_ms = (time.perf_counter() - start_time) * 1000

            return ICTSignalResult(
                signal=signal,
                signal_type=signal_type,
                emission_success=any_success,
                emission_error=last_error,
                emission_latency_ms=latency_ms,
            )

        except Exception as e:
            latency_ms = (time.perf_counter() - start_time) * 1000
            logger.error(f"ICT signal emission failed for {signal_type}: {e}")
            return ICTSignalResult(
                signal_type=signal_type,
                emission_success=False,
                emission_error=str(e),
                emission_latency_ms=latency_ms,
            )

    def _get_emission_priority_order(self) -> list[str]:
        """Get the signal emission priority order.

        Returns the priority-ordered list of signal type strings.
        If config.signal_priority is set, it overrides the registry default.

        Priority rationale (ST-ICT-ST2):
            BOS/CHoCH > Order Blocks > FVG > Liquidity Sweep > CVD > Price Structure
            Lower index = higher priority = processed first.

        Returns:
            List of signal type strings in priority order
        """
        # Config override takes precedence
        if self.config.signal_priority is not None:
            return list(self.config.signal_priority)

        # Build priority order from registry's SIGNAL_PRIORITY_ORDER
        priority_map = self.registry.SIGNAL_PRIORITY_ORDER

        # Map ICTSignalType to string keys for emitter usage
        type_to_str: dict[str, str] = {}
        for sig_type, _priority_val in priority_map.items():
            type_to_str[sig_type.value] = sig_type.value

        # Sort by priority value (ascending = highest priority first)
        sorted_types = sorted(priority_map.items(), key=lambda x: x[1])
        result = [sig_type.value for sig_type, _ in sorted_types]

        # Add liquidity_sweep if not in registry (ST-ICT-ST3)
        # Default priority: after FVG (3) and before CVD (4)
        if "liquidity_sweep" not in result:
            # Insert at position 4 (after FVG at 3, before CVD at 4 which becomes 5)
            result.insert(3, "liquidity_sweep")

        return result

    async def emit_signals(
        self,
        token: str,
        timeframe: str,
        cvd_data: Any | None = None,
        fvg_data: list[Any] | None = None,
        order_block_data: list[Any] | None = None,
        hl_data: dict[str, Any] | None = None,
        sweep_data: list[LiquiditySweepSignal] | None = None,
    ) -> ICTEmissionCycle:
        """Emit all available ICT signals for a token/timeframe.

        Args:
            token: Trading pair
            timeframe: Timeframe string
            cvd_data: CVD calculation result
            fvg_data: List of FVG detection results
            order_block_data: List of Order Block detection results
            hl_data: H/L/H-OLD/L-OLD price structure signal data (S1A-2).
                Dict with keys: h, l, high_old, low_old, each containing:
                {
                    "price": float,
                    "direction": "long" | "short",
                    "confidence": float,
                    "timestamp": int,
                    "swing_high": float (optional),
                    "swing_low": float (optional),
                }
            sweep_data: List of LiquiditySweepSignal from LiquiditySweepDetector
                (ST-ICT-ST3). Each SweepSignal contains sweep direction,
                confidence score, and metadata about the swept level.

        Returns:
            ICTEmissionCycle with results for all signals
        """
        import uuid

        self._cycle_count += 1
        cycle_id = f"ict-cycle-{self._cycle_count}-{uuid.uuid4().hex[:8]}"
        start_time = time.perf_counter()

        cycle = ICTEmissionCycle(
            cycle_id=cycle_id,
            timestamp=datetime.now(UTC),
            excluded_signals=[],
        )

        logger.info(f"ICT emission cycle started: {cycle_id} for {token} {timeframe}")

        # Build the priority-ordered list of signal types to process.
        # Each entry is (signal_type_str, data, is_list) where is_list indicates
        # the data contains multiple items (FVG, Order Block) vs single (CVD, HL).
        priority_order = self._get_emission_priority_order()
        logger.debug(f"Emission priority order: {priority_order}")

        # Map signal types to their data and processing mode
        # Order Blocks (priority 2): institutional order flow zones
        # FVG (priority 3): imbalance / fair value zones
        # CVD (priority 4): volume delta
        # H/L/H-OLD/L-OLD (priority 5): price structure levels
        #
        # BOS/CHoCH (priority 1) is now re-enabled in the signal pipeline.

        # Process each signal type in priority order
        for signal_type_str in priority_order:
            if (
                signal_type_str == "order_block"
                and order_block_data
                and self.config.enable_order_block
            ):
                for i, ob in enumerate(
                    order_block_data[: self.config.max_signals_per_cycle]
                ):
                    cycle.signals_processed += 1
                    result = await self.emit_signal("order_block", token, timeframe, ob)
                    result.signal_type = f"order_block_{i}"
                    cycle.results.append(result)
                    if result.emission_success:
                        cycle.signals_emitted += 1
                    elif result.skipped:
                        cycle.signals_skipped += 1

            elif signal_type_str == "fvg" and fvg_data and self.config.enable_fvg:
                for i, fvg in enumerate(fvg_data[: self.config.max_signals_per_cycle]):
                    cycle.signals_processed += 1
                    result = await self.emit_signal("fvg", token, timeframe, fvg)
                    result.signal_type = f"fvg_{i}"
                    cycle.results.append(result)
                    if result.emission_success:
                        cycle.signals_emitted += 1
                    elif result.skipped:
                        cycle.signals_skipped += 1

            elif (
                signal_type_str == "cvd"
                and cvd_data is not None
                and self.config.enable_cvd
            ):
                cycle.signals_processed += 1
                result = await self.emit_signal("cvd", token, timeframe, cvd_data)
                cycle.results.append(result)
                if result.emission_success:
                    cycle.signals_emitted += 1
                elif result.skipped:
                    cycle.signals_skipped += 1

            elif (
                signal_type_str in ("h", "l", "high_old", "low_old")
                and hl_data
                and self.config.enable_hl
            ):
                if signal_type_str in hl_data:
                    cycle.signals_processed += 1
                    result = await self.emit_signal(
                        signal_type_str, token, timeframe, hl_data[signal_type_str]
                    )
                    cycle.results.append(result)
                    if result.emission_success:
                        cycle.signals_emitted += 1
                    elif result.skipped:
                        cycle.signals_skipped += 1

            # Liquidity sweep (stop hunt) signals (ST-ICT-ST3)
            elif (
                signal_type_str == "liquidity_sweep"
                and sweep_data
                and self.config.enable_sweep
            ):
                for i, sweep_signal in enumerate(
                    sweep_data[: self.config.max_signals_per_cycle]
                ):
                    cycle.signals_processed += 1
                    result = await self.emit_signal(
                        "liquidity_sweep", token, timeframe, sweep_signal
                    )
                    result.signal_type = f"liquidity_sweep_{i}"
                    cycle.results.append(result)
                    if result.emission_success:
                        cycle.signals_emitted += 1
                    elif result.skipped:
                        cycle.signals_skipped += 1

        cycle.duration_ms = (time.perf_counter() - start_time) * 1000

        logger.info(
            f"ICT emission cycle completed: {cycle_id} - "
            f"processed={cycle.signals_processed}, "
            f"emitted={cycle.signals_emitted}, "
            f"skipped={cycle.signals_skipped}, "
            f"duration={cycle.duration_ms:.1f}ms"
        )

        return cycle

    def get_status(self) -> dict[str, Any]:
        """Get emitter status including feature flag states.

        Returns:
            Dictionary with emitter status
        """
        return {
            "config": {
                "min_confidence": self.config.min_confidence,
                "enable_cvd": self.config.enable_cvd,
                "enable_fvg": self.config.enable_fvg,
                "enable_order_block": self.config.enable_order_block,
                "enable_hl": self.config.enable_hl,
                "enable_sweep": self.config.enable_sweep,
                "emission_interval_seconds": self.config.emission_interval_seconds,
                "max_signals_per_cycle": self.config.max_signals_per_cycle,
            },
            "feature_flags": {
                "enable_cvd_signals": self.registry._feature_flags.is_enabled(
                    "enable_cvd_signals"
                ),
                "enable_fvg_signals": self.registry._feature_flags.is_enabled(
                    "enable_fvg_signals"
                ),
                "enable_order_block_signals": self.registry._feature_flags.is_enabled(
                    "enable_order_block_signals"
                ),
                "enable_hl_signals": self.registry._feature_flags.is_enabled(
                    "enable_hl_signals"
                ),
                "enable_sweep_signals": self.registry._feature_flags.is_enabled(
                    "enable_sweep_signals"
                ),
            },
            "emitters": [e.name for e in self.emitters],
            "cycle_count": self._cycle_count,
            "bos_choch_excluded": False,
            "bos_choch_exclusion_reference": None,
        }


# Global emitter instance for convenience
_emitter_instance: ICTSignalEmitter | None = None


def get_ict_emitter() -> ICTSignalEmitter:
    """Get or create global ICT signal emitter instance.

    Returns:
        Global ICTSignalEmitter instance
    """
    global _emitter_instance
    if _emitter_instance is None:
        _emitter_instance = ICTSignalEmitter()
    return _emitter_instance
