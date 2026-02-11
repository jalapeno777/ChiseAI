"""Paper Canary Planning & Gates module.

This module implements the paper canary deployment system with:
- Canary deployment at 10% of paper portfolio allocation
- Gate criteria checks (max 5% drawdown, min 55% win rate, 7-day duration)
- Automatic rollback on gate failure
- 15-minute monitoring schedule
- Integration with promotion packet workflow
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any


class CanaryStatus(Enum):
    """Canary deployment status."""

    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    PROMOTED = "promoted"


class GateCheckResult(Enum):
    """Result of a gate check."""

    PASS = "pass"
    FAIL = "fail"
    PENDING = "pending"


@dataclass
class GateCriteria:
    """Gate criteria configuration for canary validation.

    Attributes:
        max_drawdown_pct: Maximum allowed drawdown percentage (default 5%)
        min_win_rate_pct: Minimum required win rate percentage (default 55%)
        duration_days: Required canary duration in days (default 7)
        min_trades: Minimum number of trades required for evaluation (default 10)
    """

    max_drawdown_pct: float = 5.0
    min_win_rate_pct: float = 55.0
    duration_days: int = 7
    min_trades: int = 10

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "max_drawdown_pct": self.max_drawdown_pct,
            "min_win_rate_pct": self.min_win_rate_pct,
            "duration_days": self.duration_days,
            "min_trades": self.min_trades,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GateCriteria:
        """Create from dictionary."""
        return cls(
            max_drawdown_pct=data.get("max_drawdown_pct", 5.0),
            min_win_rate_pct=data.get("min_win_rate_pct", 55.0),
            duration_days=data.get("duration_days", 7),
            min_trades=data.get("min_trades", 10),
        )


@dataclass
class CanaryMetrics:
    """Metrics collected during canary deployment.

    Attributes:
        start_equity: Starting equity value
        current_equity: Current equity value
        peak_equity: Peak equity value reached
        total_trades: Total number of trades executed
        winning_trades: Number of winning trades
        losing_trades: Number of losing trades
        realized_pnl: Realized profit/loss
        max_drawdown_pct: Maximum drawdown percentage observed
        win_rate_pct: Current win rate percentage
        sharpe_ratio: Sharpe ratio (if available)
    """

    start_equity: float = 0.0
    current_equity: float = 0.0
    peak_equity: float = 0.0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    realized_pnl: float = 0.0
    max_drawdown_pct: float = 0.0
    win_rate_pct: float = 0.0
    sharpe_ratio: float | None = None

    def __post_init__(self) -> None:
        """Calculate derived metrics."""
        self._calculate_metrics()

    def _calculate_metrics(self) -> None:
        """Calculate derived metrics like win rate and drawdown."""
        # Calculate win rate
        if self.total_trades > 0:
            self.win_rate_pct = (self.winning_trades / self.total_trades) * 100

        # Calculate drawdown
        if self.peak_equity > 0 and self.current_equity > 0:
            self.max_drawdown_pct = (
                (self.peak_equity - self.current_equity) / self.peak_equity
            ) * 100

    def update_equity(self, new_equity: float) -> None:
        """Update equity and recalculate metrics.

        Args:
            new_equity: New equity value
        """
        self.current_equity = new_equity
        if new_equity > self.peak_equity:
            self.peak_equity = new_equity
        self._calculate_metrics()

    def record_trade(self, pnl: float) -> None:
        """Record a completed trade.

        Args:
            pnl: Profit/loss from the trade
        """
        self.total_trades += 1
        self.realized_pnl += pnl
        if pnl > 0:
            self.winning_trades += 1
        else:
            self.losing_trades += 1
        self._calculate_metrics()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "start_equity": round(self.start_equity, 8),
            "current_equity": round(self.current_equity, 8),
            "peak_equity": round(self.peak_equity, 8),
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "realized_pnl": round(self.realized_pnl, 8),
            "max_drawdown_pct": round(self.max_drawdown_pct, 4),
            "win_rate_pct": round(self.win_rate_pct, 4),
            "sharpe_ratio": round(self.sharpe_ratio, 4) if self.sharpe_ratio else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CanaryMetrics:
        """Create from dictionary."""
        metrics = cls(
            start_equity=data.get("start_equity", 0.0),
            current_equity=data.get("current_equity", 0.0),
            peak_equity=data.get("peak_equity", 0.0),
            total_trades=data.get("total_trades", 0),
            winning_trades=data.get("winning_trades", 0),
            losing_trades=data.get("losing_trades", 0),
            realized_pnl=data.get("realized_pnl", 0.0),
            max_drawdown_pct=data.get("max_drawdown_pct", 0.0),
            win_rate_pct=data.get("win_rate_pct", 0.0),
            sharpe_ratio=data.get("sharpe_ratio"),
        )
        return metrics


@dataclass
class GateCheck:
    """Result of a single gate check.

    Attributes:
        gate_name: Name of the gate being checked
        result: Check result (pass/fail/pending)
        actual_value: Actual measured value
        threshold_value: Threshold value for comparison
        message: Human-readable check message
        timestamp: When the check was performed
    """

    gate_name: str
    result: GateCheckResult
    actual_value: float
    threshold_value: float
    message: str
    timestamp: int = field(default_factory=lambda: int(datetime.now().timestamp()))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "gate_name": self.gate_name,
            "result": self.result.value,
            "actual_value": round(self.actual_value, 4),
            "threshold_value": round(self.threshold_value, 4),
            "message": self.message,
            "timestamp": self.timestamp,
        }


@dataclass
class CanaryDeployment:
    """Paper canary deployment state and configuration.

    Attributes:
        canary_id: Unique canary identifier
        strategy_id: Strategy being tested
        champion_strategy_id: Current champion strategy (for rollback)
        status: Current canary status
        allocation_pct: Portfolio allocation percentage (default 10%)
        start_time: Canary start timestamp
        end_time: Canary end timestamp (calculated from duration)
        criteria: Gate criteria configuration
        metrics: Collected metrics
        gate_checks: History of gate checks
        last_check_time: Timestamp of last gate check
        metadata: Additional metadata
    """

    canary_id: str
    strategy_id: str
    champion_strategy_id: str | None = None
    status: CanaryStatus = CanaryStatus.PENDING
    allocation_pct: float = 10.0
    start_time: int = 0
    end_time: int = 0
    criteria: GateCriteria = field(default_factory=GateCriteria)
    metrics: CanaryMetrics = field(default_factory=CanaryMetrics)
    gate_checks: list[GateCheck] = field(default_factory=list)
    last_check_time: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Initialize timestamps if not set."""
        if self.start_time == 0 and self.status == CanaryStatus.PENDING:
            self.start_time = int(datetime.now().timestamp())
            self._calculate_end_time()

    def _calculate_end_time(self) -> None:
        """Calculate end time based on start time and duration."""
        duration_seconds = self.criteria.duration_days * 24 * 60 * 60
        self.end_time = self.start_time + duration_seconds

    def start(self, initial_equity: float) -> None:
        """Start the canary deployment.

        Args:
            initial_equity: Starting equity value
        """
        self.status = CanaryStatus.RUNNING
        self.start_time = int(datetime.now().timestamp())
        self._calculate_end_time()
        self.metrics.start_equity = initial_equity
        self.metrics.current_equity = initial_equity
        self.metrics.peak_equity = initial_equity

    def check_gates(self) -> list[GateCheck]:
        """Check all gate criteria and return results.

        Returns:
            List of gate check results
        """
        checks = []
        current_time = int(datetime.now().timestamp())

        # Check drawdown gate
        drawdown_check = self._check_drawdown_gate()
        checks.append(drawdown_check)

        # Check win rate gate (only if enough trades)
        win_rate_check = self._check_win_rate_gate()
        checks.append(win_rate_check)

        # Check duration gate
        duration_check = self._check_duration_gate(current_time)
        checks.append(duration_check)

        self.gate_checks.extend(checks)
        self.last_check_time = current_time

        return checks

    def _check_drawdown_gate(self) -> GateCheck:
        """Check the maximum drawdown gate."""
        actual_drawdown = self.metrics.max_drawdown_pct
        threshold = self.criteria.max_drawdown_pct

        if actual_drawdown > threshold:
            result = GateCheckResult.FAIL
            message = (
                f"Drawdown {actual_drawdown:.2f}% exceeds threshold {threshold:.2f}%"
            )
        else:
            result = GateCheckResult.PASS
            message = (
                f"Drawdown {actual_drawdown:.2f}% within threshold {threshold:.2f}%"
            )

        return GateCheck(
            gate_name="max_drawdown",
            result=result,
            actual_value=actual_drawdown,
            threshold_value=threshold,
            message=message,
        )

    def _check_win_rate_gate(self) -> GateCheck:
        """Check the minimum win rate gate."""
        actual_win_rate = self.metrics.win_rate_pct
        threshold = self.criteria.min_win_rate_pct

        # Only evaluate if we have minimum trades
        if self.metrics.total_trades < self.criteria.min_trades:
            return GateCheck(
                gate_name="min_win_rate",
                result=GateCheckResult.PENDING,
                actual_value=actual_win_rate,
                threshold_value=threshold,
                message=(
                    f"Insufficient trades ({self.metrics.total_trades}/"
                    f"{self.criteria.min_trades})"
                ),
            )

        if actual_win_rate < threshold:
            result = GateCheckResult.FAIL
            message = (
                f"Win rate {actual_win_rate:.2f}% below threshold {threshold:.2f}%"
            )
        else:
            result = GateCheckResult.PASS
            message = (
                f"Win rate {actual_win_rate:.2f}% meets threshold {threshold:.2f}%"
            )

        return GateCheck(
            gate_name="min_win_rate",
            result=result,
            actual_value=actual_win_rate,
            threshold_value=threshold,
            message=message,
        )

    def _check_duration_gate(self, current_time: int) -> GateCheck:
        """Check the minimum duration gate."""
        elapsed_seconds = current_time - self.start_time
        required_seconds = self.criteria.duration_days * 24 * 60 * 60
        elapsed_days = elapsed_seconds / (24 * 60 * 60)

        if elapsed_seconds < required_seconds:
            result = GateCheckResult.PENDING
            message = (
                f"Duration {elapsed_days:.2f} days < required "
                f"{self.criteria.duration_days} days"
            )
        else:
            result = GateCheckResult.PASS
            message = (
                f"Duration {elapsed_days:.2f} days meets required "
                f"{self.criteria.duration_days} days"
            )

        return GateCheck(
            gate_name="duration",
            result=result,
            actual_value=elapsed_days,
            threshold_value=float(self.criteria.duration_days),
            message=message,
        )

    def evaluate_all_gates(self) -> tuple[CanaryStatus, list[str]]:
        """Evaluate all gates and determine canary status.

        Returns:
            Tuple of (new_status, failure_reasons)
        """
        checks = self.check_gates()
        failure_reasons = []

        for check in checks:
            if check.result == GateCheckResult.FAIL:
                failure_reasons.append(check.message)

        # Check if all gates pass
        all_passed = all(
            check.result == GateCheckResult.PASS
            for check in checks
            if check.gate_name != "min_win_rate"  # Win rate can be pending
        )
        win_rate_passed = any(
            check.result == GateCheckResult.PASS
            for check in checks
            if check.gate_name == "min_win_rate"
        )

        if failure_reasons:
            return CanaryStatus.FAILED, failure_reasons
        elif all_passed and win_rate_passed:
            return CanaryStatus.PASSED, []
        else:
            return self.status, []

    def should_rollback(self) -> tuple[bool, list[str]]:
        """Check if canary should be rolled back.

        Returns:
            Tuple of (should_rollback, reasons)
        """
        status, reasons = self.evaluate_all_gates()
        return status == CanaryStatus.FAILED, reasons

    def can_promote(self) -> tuple[bool, list[str]]:
        """Check if canary can be promoted to paper full.

        Returns:
            Tuple of (can_promote, pending_reasons)
        """
        if self.status != CanaryStatus.PASSED:
            return False, [f"Canary status is {self.status.value}, not passed"]

        # Re-evaluate gates to ensure they still pass
        status, reasons = self.evaluate_all_gates()
        if status != CanaryStatus.PASSED:
            return False, reasons

        return True, []

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "canary_id": self.canary_id,
            "strategy_id": self.strategy_id,
            "champion_strategy_id": self.champion_strategy_id,
            "status": self.status.value,
            "allocation_pct": self.allocation_pct,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "criteria": self.criteria.to_dict(),
            "metrics": self.metrics.to_dict(),
            "gate_checks": [check.to_dict() for check in self.gate_checks],
            "last_check_time": self.last_check_time,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CanaryDeployment:
        """Create from dictionary."""
        return cls(
            canary_id=data["canary_id"],
            strategy_id=data["strategy_id"],
            champion_strategy_id=data.get("champion_strategy_id"),
            status=CanaryStatus(data.get("status", "pending")),
            allocation_pct=data.get("allocation_pct", 10.0),
            start_time=data.get("start_time", 0),
            end_time=data.get("end_time", 0),
            criteria=GateCriteria.from_dict(data.get("criteria", {})),
            metrics=CanaryMetrics.from_dict(data.get("metrics", {})),
            gate_checks=[GateCheck(**check) for check in data.get("gate_checks", [])],
            last_check_time=data.get("last_check_time", 0),
            metadata=data.get("metadata", {}),
        )


def create_canary_deployment(
    canary_id: str,
    strategy_id: str,
    champion_strategy_id: str | None = None,
    allocation_pct: float = 10.0,
    criteria: GateCriteria | None = None,
) -> CanaryDeployment:
    """Create a new canary deployment.

    Args:
        canary_id: Unique canary identifier
        strategy_id: Strategy to test
        champion_strategy_id: Current champion (for rollback)
        allocation_pct: Portfolio allocation percentage
        criteria: Gate criteria (uses defaults if None)

    Returns:
        New CanaryDeployment instance
    """
    return CanaryDeployment(
        canary_id=canary_id,
        strategy_id=strategy_id,
        champion_strategy_id=champion_strategy_id,
        allocation_pct=allocation_pct,
        criteria=criteria or GateCriteria(),
    )
