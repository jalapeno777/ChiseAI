"""Dynamic Threshold Controller for ChiseAI Calibration System.

This module provides the ThresholdController class for automatically applying
optimized thresholds and adjusting them based on ongoing performance. Supports
both dynamic and fixed modes with audit logging.

Components:
- controller.py: Main controller class for threshold management
- dynamic.py: Dynamic adjustment logic based on ECE monitoring
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

import yaml

if TYPE_CHECKING:

    from ml.calibration.optimizer import ThresholdOptimizer

logger = logging.getLogger(__name__)


class ThresholdMode(str, Enum):
    """Operating modes for threshold controller.

    DYNAMIC: Auto-adjust thresholds based on ECE degradation
    FIXED: Manual fixed thresholds, no auto-adjustment
    """

    DYNAMIC = "dynamic"
    FIXED = "fixed"


@dataclass
class ThresholdChange:
    """Record of a threshold change event.

    Attributes:
        timestamp: When the change occurred
        signal_type: Type of signal (LONG, SHORT, SCALP)
        old_threshold: Previous threshold value
        new_threshold: New threshold value
        reason: Reason for the change
        mode: Current threshold mode at time of change
        ece_before: ECE before the change
        ece_after: ECE after the change (None if not calculated)
    """

    timestamp: datetime
    signal_type: str
    old_threshold: float
    new_threshold: float
    reason: str
    mode: ThresholdMode
    ece_before: float
    ece_after: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "signal_type": self.signal_type,
            "old_threshold": round(self.old_threshold, 4),
            "new_threshold": round(self.new_threshold, 4),
            "reason": self.reason,
            "mode": self.mode.value,
            "ece_before": round(self.ece_before, 6) if self.ece_before else None,
            "ece_after": round(self.ece_after, 6) if self.ece_after else None,
        }


class ThresholdController:
    """Controls application of confidence thresholds for signal filtering.

    The controller manages threshold application for signal filtering, supporting
    both dynamic (auto-adjusting based on ECE) and fixed modes. All threshold
    changes are logged for audit purposes.

    Example:
        >>> from ml.calibration import ThresholdController, ThresholdMode
        >>> controller = ThresholdController(optimizer, mode=ThresholdMode.DYNAMIC)
        >>>
        >>> # Check if signal meets threshold
        >>> signal = {'type': 'LONG', 'confidence': 0.75}
        >>> should_emit = controller.should_emit_signal(signal)
        >>> print(f'Should emit: {should_emit}')
    """

    DEFAULT_THRESHOLDS: dict[str, float] = {
        "LONG": 0.60,
        "SHORT": 0.60,
        "SCALP": 0.65,
    }

    MIN_THRESHOLD: float = 0.40
    MAX_THRESHOLD: float = 0.95

    def __init__(
        self,
        optimizer: ThresholdOptimizer,
        mode: ThresholdMode = ThresholdMode.DYNAMIC,
        redis_host: str = "host.docker.internal",
        redis_port: int = 6380,
        redis_db: int = 0,
        audit_retention_days: int = 90,
    ):
        """Initialize the threshold controller.

        Args:
            optimizer: ThresholdOptimizer instance for threshold optimization
            mode: Operating mode (DYNAMIC or FIXED)
            redis_host: Redis host for audit logging
            redis_port: Redis port
            redis_db: Redis database number
            audit_retention_days: Days to retain audit logs
        """
        self.optimizer = optimizer
        self.mode = mode
        self._audit_log: list[ThresholdChange] = []
        self._redis_host = redis_host
        self._redis_port = redis_port
        self._redis_db = redis_db
        self._audit_retention_days = audit_retention_days

        # Current thresholds (initialized from defaults)
        self._current_thresholds: dict[str, float] = self.DEFAULT_THRESHOLDS.copy()

        # Last known ECE values per signal type
        self._last_ece: dict[str, float] = {}

        # Import dynamic adjuster if in dynamic mode
        if self.mode == ThresholdMode.DYNAMIC:
            try:
                from ml.calibration.dynamic import DynamicThresholdAdjuster

                self._adjuster: DynamicThresholdAdjuster | None = (
                    DynamicThresholdAdjuster(self, ece_threshold=0.15)
                )
            except ImportError:
                logger.warning(
                    "DynamicThresholdAdjuster not available, falling back to fixed mode"
                )
                self._adjuster = None
                self.mode = ThresholdMode.FIXED
        else:
            self._adjuster = None

        logger.info(f"ThresholdController initialized in {self.mode.value} mode")

    @property
    def mode(self) -> ThresholdMode:
        """Get current operating mode."""
        return self._mode

    @mode.setter
    def mode(self, value: ThresholdMode):
        """Set operating mode."""
        self._mode = value

    @property
    def current_thresholds(self) -> dict[str, float]:
        """Get current threshold values."""
        return self._current_thresholds.copy()

    def should_emit_signal(self, signal: dict[str, Any]) -> bool:
        """Check if signal meets current threshold for emission.

        Args:
            signal: Signal dictionary with 'type' and 'confidence' keys

        Returns:
            True if signal confidence exceeds threshold for its type
        """
        signal_type = signal.get("type", "LONG")
        confidence = signal.get("confidence", 0.0)

        threshold = self.get_current_threshold(signal_type)
        return confidence >= threshold

    def get_current_threshold(self, signal_type: str) -> float:
        """Get active threshold for signal type.

        Args:
            signal_type: Type of signal (LONG, SHORT, SCALP)

        Returns:
            Current threshold value for the signal type
        """
        return self._current_thresholds.get(
            signal_type, self.DEFAULT_THRESHOLDS.get(signal_type, 0.60)
        )

    def set_threshold(
        self,
        signal_type: str,
        value: float,
        reason: str = "manual",
        log_change: bool = True,
    ) -> bool:
        """Set threshold for a specific signal type.

        Args:
            signal_type: Type of signal
            value: New threshold value (clamped to valid range)
            reason: Reason for the change
            log_change: Whether to log this change to audit trail

        Returns:
            True if threshold was updated
        """
        # Clamp to valid range
        clamped_value = max(self.MIN_THRESHOLD, min(self.MAX_THRESHOLD, value))

        old_value = self._current_thresholds.get(
            signal_type, self.DEFAULT_THRESHOLDS.get(signal_type, 0.60)
        )

        if abs(old_value - clamped_value) < 0.001:
            return False  # No significant change

        self._current_thresholds[signal_type] = clamped_value

        if log_change:
            self._log_threshold_change(
                signal_type=signal_type,
                old_threshold=old_value,
                new_threshold=clamped_value,
                reason=reason,
                ece_before=self._last_ece.get(signal_type),
                ece_after=None,
            )

        logger.info(
            f"Threshold updated for {signal_type}: {old_value:.2f} -> {clamped_value:.2f} ({reason})"
        )
        return True

    def update_thresholds(self, force: bool = False) -> bool:
        """Update thresholds based on latest optimization.

        Args:
            force: Force update even if not in dynamic mode

        Returns:
            True if thresholds were updated
        """
        if not force and self.mode != ThresholdMode.DYNAMIC:
            logger.debug("Skipping threshold update in fixed mode")
            return False

        updated = False
        for signal_type in ["LONG", "SHORT", "SCALP"]:
            try:
                result = self.optimizer.optimize_thresholds(signal_type)
                old_threshold = self.get_current_threshold(signal_type)

                # Only update if significantly different
                if abs(old_threshold - result.optimal_threshold) > 0.01:
                    self._last_ece[signal_type] = result.min_ece

                    self.set_threshold(
                        signal_type=signal_type,
                        value=result.optimal_threshold,
                        reason=f"optimization: ECE={result.min_ece:.4f}",
                        log_change=True,
                    )
                    updated = True

            except ValueError as e:
                logger.warning(f"Could not optimize {signal_type}: {e}")
                continue

        return updated

    def switch_mode(self, mode: ThresholdMode, reason: str) -> bool:
        """Switch between dynamic and fixed mode.

        Args:
            mode: New operating mode
            reason: Reason for mode switch

        Returns:
            True if mode was switched
        """
        if self._mode == mode:
            return False

        old_mode = self._mode
        self._mode = mode

        # Initialize adjuster if switching to dynamic
        if mode == ThresholdMode.DYNAMIC:
            try:
                from ml.calibration.dynamic import DynamicThresholdAdjuster

                self._adjuster = DynamicThresholdAdjuster(self, ece_threshold=0.15)
            except ImportError:
                logger.warning("DynamicThresholdAdjuster not available")
                self._adjuster = None
                self._mode = ThresholdMode.FIXED
        else:
            self._adjuster = None

        # Log mode change as a threshold change event
        for signal_type, threshold in self._current_thresholds.items():
            self._log_threshold_change(
                signal_type=signal_type,
                old_threshold=threshold,
                new_threshold=threshold,
                reason=f"mode_switch: {old_mode.value} -> {mode.value}: {reason}",
                ece_before=self._last_ece.get(signal_type),
                ece_after=None,
            )

        logger.info(f"Mode switched: {old_mode.value} -> {mode.value} ({reason})")
        return True

    def monitor_and_adjust(self) -> list[dict[str, Any]]:
        """Monitor ECE and adjust thresholds if needed (dynamic mode only).

        Returns:
            List of adjustments made (empty if no adjustments needed)
        """
        if self.mode != ThresholdMode.DYNAMIC or self._adjuster is None:
            return []

        adjustments = self._adjuster.monitor_and_adjust()
        if adjustments:
            return [adjustments] if not isinstance(adjustments, list) else adjustments
        return []

    def check_ece_degradation(self, signal_type: str, threshold: float = 0.15) -> bool:
        """Check if ECE has degraded beyond threshold.

        Args:
            signal_type: Type of signal
            threshold: ECE threshold for degradation

        Returns:
            True if ECE exceeds threshold (poor calibration)
        """
        try:
            records = self.optimizer.collector.get_records(signal_type=signal_type)
            if len(records) < 10:
                return False

            current_ece = self.optimizer.calculate_ece(records)
            self._last_ece[signal_type] = current_ece

            return current_ece > threshold

        except Exception as e:
            logger.warning(f"ECE degradation check failed for {signal_type}: {e}")
            return False

    def get_audit_log(
        self,
        since: datetime | None = None,
        signal_type: str | None = None,
    ) -> list[ThresholdChange]:
        """Get audit log of threshold changes.

        Args:
            since: Only return changes after this time
            signal_type: Only return changes for this signal type

        Returns:
            List of threshold change records
        """
        log = self._audit_log.copy()

        if since:
            log = [c for c in log if c.timestamp >= since]

        if signal_type:
            log = [c for c in log if c.signal_type == signal_type]

        return log

    def _log_threshold_change(
        self,
        signal_type: str,
        old_threshold: float,
        new_threshold: float,
        reason: str,
        ece_before: float | None,
        ece_after: float | None,
    ) -> None:
        """Log a threshold change to audit trail.

        Args:
            signal_type: Type of signal
            old_threshold: Previous threshold
            new_threshold: New threshold
            reason: Reason for change
            ece_before: ECE before change
            ece_after: ECE after change
        """
        change = ThresholdChange(
            timestamp=datetime.now(UTC),
            signal_type=signal_type,
            old_threshold=old_threshold,
            new_threshold=new_threshold,
            reason=reason,
            mode=self._mode,
            ece_before=ece_before if ece_before is not None else -1.0,
            ece_after=ece_after,
        )

        self._audit_log.append(change)

        # Also log to Redis if available
        self._log_to_redis(change)

    def _log_to_redis(self, change: ThresholdChange) -> None:
        """Log threshold change to Redis for persistence.

        Args:
            change: Threshold change to log
        """
        try:
            import redis

            r = redis.Redis(
                host=self._redis_host,
                port=self._redis_port,
                db=self._redis_db,
                decode_responses=True,
            )

            key = f"threshold:changes:{change.signal_type}"
            data = json.dumps(change.to_dict())

            # Add to sorted set with timestamp as score
            r.zadd(key, {data: change.timestamp.timestamp()})

            # Set expiration
            r.expire(key, self._audit_retention_days * 86400)

        except Exception as e:
            logger.debug(f"Could not log to Redis: {e}")

    def export_audit_log(self, filepath: str) -> bool:
        """Export audit log to JSON file.

        Args:
            filepath: Path to output file

        Returns:
            True if export successful
        """
        try:
            with open(filepath, "w") as f:
                json.dump(
                    [c.to_dict() for c in self._audit_log],
                    f,
                    indent=2,
                )
            logger.info(f"Exported audit log to {filepath}")
            return True
        except Exception as e:
            logger.error(f"Failed to export audit log: {e}")
            return False

    def get_status(self) -> dict[str, Any]:
        """Get current controller status.

        Returns:
            Dictionary with status information
        """
        return {
            "mode": self.mode.value,
            "thresholds": {k: round(v, 4) for k, v in self._current_thresholds.items()},
            "last_ece": {k: round(v, 6) for k, v in self._last_ece.items()},
            "audit_log_entries": len(self._audit_log),
            "dynamic_enabled": self._adjuster is not None,
        }

    @classmethod
    def from_config(
        cls,
        config_path: str,
        optimizer: ThresholdOptimizer,
    ) -> ThresholdController:
        """Create controller from YAML configuration.

        Args:
            config_path: Path to calibration.yaml
            optimizer: ThresholdOptimizer instance

        Returns:
            Configured ThresholdController instance
        """
        try:
            with open(config_path) as f:
                config = yaml.safe_load(f)
        except Exception as e:
            logger.warning(f"Could not load config: {e}, using defaults")
            config = {}

        controller_config = config.get("controller", {})

        mode_str = controller_config.get("mode", "dynamic")
        mode = ThresholdMode(mode_str)

        audit_config = controller_config.get("audit", {})
        redis_config = config.get("redis", {})

        return cls(
            optimizer=optimizer,
            mode=mode,
            redis_host=redis_config.get("host", "host.docker.internal"),
            redis_port=redis_config.get("port", 6380),
            redis_db=redis_config.get("db", 0),
            audit_retention_days=audit_config.get("retention_days", 90),
        )


__all__ = [
    "ThresholdController",
    "ThresholdMode",
    "ThresholdChange",
]
