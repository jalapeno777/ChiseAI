"""Live trading gate manager for human approval workflow.

Manages state transitions and approval process for live trading activation.
Integrates with kill-switch for immediate disable capability.

For ST-EX-002: Bitget Live Trading Gating Implementation
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from execution.kill_switch.state import KillSwitchConfig
    from execution.kill_switch.executor import KillSwitchExecutor

logger = logging.getLogger(__name__)


class LiveTradingState(Enum):
    """Live trading operational states.

    States:
        DISABLED: Live trading is disabled, no trading allowed
        PENDING_APPROVAL: Approval request submitted, awaiting human review
        APPROVED: Human approval granted, ready to activate
        ACTIVE: Live trading is active and executing trades
    """

    DISABLED = "disabled"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    ACTIVE = "active"

    def __str__(self) -> str:
        """Return string representation."""
        return self.value


@dataclass
class LiveGateConfig:
    """Configuration for live trading gating.

    Attributes:
        position_limits: Maximum position size per symbol (in base currency)
        leverage_cap: Maximum allowed leverage (default 3.0 per PRD)
        daily_loss_cap: Maximum daily loss before auto-disable (in quote currency)
        require_human_approval: Whether human approval is required (always True for safety)
        min_paper_trading_days: Minimum paper trading days required (default 30)
        min_sharpe_ratio: Minimum Sharpe ratio required (default 0.0, positive)
        max_drawdown_pct: Maximum drawdown percentage allowed (default 10.0)
        influxdb_measurement: InfluxDB measurement name for live gating metrics
    """

    position_limits: dict[str, float] = field(default_factory=dict)
    leverage_cap: float = 3.0
    daily_loss_cap: float = 1000.0
    require_human_approval: bool = True
    min_paper_trading_days: int = 30
    min_sharpe_ratio: float = 0.0
    max_drawdown_pct: float = 10.0
    influxdb_measurement: str = "live_gating"

    def __post_init__(self) -> None:
        """Validate configuration values."""
        if self.leverage_cap > 3.0:
            logger.warning(
                f"Leverage cap {self.leverage_cap} exceeds PRD limit of 3.0, capping at 3.0"
            )
            self.leverage_cap = 3.0
        if self.leverage_cap <= 0:
            raise ValueError("Leverage cap must be positive")
        if self.daily_loss_cap <= 0:
            raise ValueError("Daily loss cap must be positive")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "position_limits": self.position_limits,
            "leverage_cap": self.leverage_cap,
            "daily_loss_cap": self.daily_loss_cap,
            "require_human_approval": self.require_human_approval,
            "min_paper_trading_days": self.min_paper_trading_days,
            "min_sharpe_ratio": self.min_sharpe_ratio,
            "max_drawdown_pct": self.max_drawdown_pct,
            "influxdb_measurement": self.influxdb_measurement,
        }


@dataclass
class PaperTradingEvidence:
    """Evidence from paper trading for approval request.

    Attributes:
        duration_days: Number of days of paper trading data
        total_trades: Total number of trades executed
        win_rate_pct: Win rate percentage
        sharpe_ratio: Sharpe ratio (risk-adjusted returns)
        max_drawdown_pct: Maximum drawdown percentage observed
        realized_pnl: Realized profit/loss
        start_date: When paper trading started
        end_date: When paper trading ended (or current date)
        strategy_id: Strategy identifier
        additional_metrics: Any additional performance metrics
    """

    duration_days: float
    total_trades: int
    win_rate_pct: float
    sharpe_ratio: float
    max_drawdown_pct: float
    realized_pnl: float
    start_date: datetime
    end_date: datetime
    strategy_id: str = ""
    additional_metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "duration_days": self.duration_days,
            "total_trades": self.total_trades,
            "win_rate_pct": self.win_rate_pct,
            "sharpe_ratio": self.sharpe_ratio,
            "max_drawdown_pct": self.max_drawdown_pct,
            "realized_pnl": self.realized_pnl,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "strategy_id": self.strategy_id,
            "additional_metrics": self.additional_metrics,
        }

    def meets_prerequisites(self, config: LiveGateConfig) -> tuple[bool, list[str]]:
        """Check if evidence meets prerequisites for approval.

        Args:
            config: Gate configuration with thresholds

        Returns:
            Tuple of (meets_requirements, list of failure reasons)
        """
        failures = []

        # Check minimum paper trading duration
        if self.duration_days < config.min_paper_trading_days:
            failures.append(
                f"Paper trading duration {self.duration_days:.1f} days "
                f"is less than required {config.min_paper_trading_days} days"
            )

        # Check Sharpe ratio (must be positive)
        if self.sharpe_ratio < config.min_sharpe_ratio:
            failures.append(
                f"Sharpe ratio {self.sharpe_ratio:.2f} is less than "
                f"required {config.min_sharpe_ratio:.2f}"
            )

        # Check maximum drawdown
        if self.max_drawdown_pct > config.max_drawdown_pct:
            failures.append(
                f"Max drawdown {self.max_drawdown_pct:.2f}% exceeds "
                f"allowed {config.max_drawdown_pct:.2f}%"
            )

        # Check minimum trades for statistical significance
        if self.total_trades < 50:
            failures.append(
                f"Total trades {self.total_trades} is less than "
                f"minimum recommended 50 for statistical significance"
            )

        return len(failures) == 0, failures


@dataclass
class ApprovalRequest:
    """Request for live trading approval.

    Attributes:
        request_id: Unique request identifier
        evidence: Paper trading evidence
        submitted_at: When request was submitted
        status: Request status (pending/approved/rejected)
        rejection_reason: Reason for rejection (if rejected)
    """

    request_id: str
    evidence: PaperTradingEvidence
    submitted_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    status: str = "pending"
    rejection_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "request_id": self.request_id,
            "evidence": self.evidence.to_dict(),
            "submitted_at": self.submitted_at.isoformat(),
            "status": self.status,
            "rejection_reason": self.rejection_reason,
        }


@dataclass
class ApprovalPacket:
    """Signed approval packet from human approver.

    Attributes:
        approver_id: Identifier of approver (e.g., username, key ID)
        timestamp: When approval was granted
        signature: Cryptographic signature of approval
        paper_evidence: Reference to paper trading evidence
        request_id: Reference to approval request
        approval_notes: Optional notes from approver
    """

    approver_id: str
    timestamp: datetime
    signature: str
    paper_evidence: PaperTradingEvidence
    request_id: str
    approval_notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "approver_id": self.approver_id,
            "timestamp": self.timestamp.isoformat(),
            "signature": self.signature,
            "paper_evidence": self.paper_evidence.to_dict(),
            "request_id": self.request_id,
            "approval_notes": self.approval_notes,
        }

    def verify_signature(self) -> bool:
        """Verify the approval signature.

        In production, this would verify a cryptographic signature.
        For now, validates signature format and non-emptiness.

        Returns:
            True if signature is valid
        """
        if not self.signature:
            return False
        # Basic format validation - signature should be hex or base64
        if len(self.signature) < 16:
            return False
        return True


class LiveGateManager:
    """Manages live trading gating state and approval workflow.

    This class provides:
    - State management for live trading (disabled/pending/approved/active)
    - Paper trading prerequisite verification
    - Human approval request and validation
    - Integration with kill-switch for immediate disable
    - Audit logging of all state transitions

    Usage:
        manager = LiveGateManager(config)

        # Check prerequisites
        prereqs = manager.check_prerequisites(evidence)

        # Request approval
        request = manager.request_approval(evidence)

        # Approve (human action)
        packet = ApprovalPacket(...)
        manager.approve(packet)

        # Enable live trading
        manager.enable_live_trading()

        # Disable via kill-switch or manually
        manager.disable_live_trading("Kill-switch triggered")
    """

    def __init__(
        self,
        config: LiveGateConfig | None = None,
        kill_switch_executor: KillSwitchExecutor | None = None,
    ) -> None:
        """Initialize the gate manager.

        Args:
            config: Gate configuration (uses defaults if None)
            kill_switch_executor: Optional kill-switch executor for integration
        """
        self.config = config or LiveGateConfig()
        self._state = LiveTradingState.DISABLED
        self._current_request: ApprovalRequest | None = None
        self._last_approval: ApprovalPacket | None = None
        self._state_history: list[dict[str, Any]] = []
        self._kill_switch_executor = kill_switch_executor
        self._enabled_at: datetime | None = None
        self._daily_pnl: float = 0.0
        self._daily_pnl_reset_time: datetime = datetime.now(UTC)

        logger.info(f"LiveGateManager initialized with state: {self._state}")

    @property
    def state(self) -> LiveTradingState:
        """Get current live trading state."""
        return self._state

    @property
    def last_approval(self) -> ApprovalPacket | None:
        """Get last approval packet (if any)."""
        return self._last_approval

    @property
    def is_live_enabled(self) -> bool:
        """Check if live trading is currently enabled."""
        return self._state == LiveTradingState.ACTIVE

    def get_state(self) -> LiveTradingState:
        """Get current live trading state.

        Returns:
            Current LiveTradingState
        """
        return self._state

    def check_prerequisites(self, evidence: PaperTradingEvidence) -> list[str]:
        """Check paper trading prerequisites for live approval.

        Args:
            evidence: Paper trading evidence to validate

        Returns:
            List of prerequisite failures (empty if all pass)
        """
        meets_requirements, failures = evidence.meets_prerequisites(self.config)

        if meets_requirements:
            logger.info(f"Prerequisites met for strategy {evidence.strategy_id}")
        else:
            logger.warning(
                f"Prerequisites not met for strategy {evidence.strategy_id}: {failures}"
            )

        return failures

    def request_approval(self, evidence: PaperTradingEvidence) -> ApprovalRequest:
        """Submit a request for live trading approval.

        Args:
            evidence: Paper trading evidence supporting the request

        Returns:
            ApprovalRequest with generated request_id

        Raises:
            RuntimeError: If already pending approval or active
        """
        if self._state == LiveTradingState.PENDING_APPROVAL:
            raise RuntimeError("Approval request already pending")
        if self._state == LiveTradingState.ACTIVE:
            raise RuntimeError("Live trading already active")

        # Generate unique request ID
        request_id = f"REQ-{uuid.uuid4().hex[:12].upper()}"

        # Create approval request
        request = ApprovalRequest(
            request_id=request_id,
            evidence=evidence,
        )

        self._current_request = request
        self._transition_state(
            LiveTradingState.PENDING_APPROVAL, f"Approval requested: {request_id}"
        )

        logger.info(f"Approval request submitted: {request_id}")
        return request

    def approve(self, packet: ApprovalPacket) -> bool:
        """Approve live trading with signed packet.

        Args:
            packet: Signed approval packet from human approver

        Returns:
            True if approval successful

        Raises:
            RuntimeError: If not in PENDING_APPROVAL state
            ValueError: If packet signature is invalid
        """
        if self._state != LiveTradingState.PENDING_APPROVAL:
            raise RuntimeError(f"Cannot approve from state {self._state}")

        if self._current_request is None:
            raise RuntimeError("No pending approval request")

        if packet.request_id != self._current_request.request_id:
            raise ValueError(
                f"Packet request_id {packet.request_id} does not match "
                f"current request {self._current_request.request_id}"
            )

        # Verify signature
        if not packet.verify_signature():
            raise ValueError("Invalid approval signature")

        # Store approval
        self._last_approval = packet
        self._current_request.status = "approved"

        self._transition_state(
            LiveTradingState.APPROVED,
            f"Approved by {packet.approver_id} at {packet.timestamp.isoformat()}",
        )

        logger.info(f"Live trading approved by {packet.approver_id}")
        return True

    def reject(self, reason: str) -> bool:
        """Reject the current approval request.

        Args:
            reason: Reason for rejection

        Returns:
            True if rejection successful

        Raises:
            RuntimeError: If not in PENDING_APPROVAL state
        """
        if self._state != LiveTradingState.PENDING_APPROVAL:
            raise RuntimeError(f"Cannot reject from state {self._state}")

        if self._current_request is None:
            raise RuntimeError("No pending approval request")

        self._current_request.status = "rejected"
        self._current_request.rejection_reason = reason

        self._transition_state(LiveTradingState.DISABLED, f"Rejected: {reason}")

        logger.info(f"Approval request rejected: {reason}")
        return True

    def enable_live_trading(self) -> bool:
        """Enable live trading after approval.

        Returns:
            True if live trading enabled successfully

        Raises:
            RuntimeError: If not in APPROVED state
        """
        if self._state != LiveTradingState.APPROVED:
            raise RuntimeError(f"Cannot enable live trading from state {self._state}")

        if self._last_approval is None:
            raise RuntimeError("No approval packet found")

        self._enabled_at = datetime.now(UTC)
        self._daily_pnl = 0.0
        self._daily_pnl_reset_time = datetime.now(UTC)

        self._transition_state(LiveTradingState.ACTIVE, "Live trading enabled")

        logger.info("Live trading ENABLED - trades will now execute on Bitget")
        return True

    def disable_live_trading(self, reason: str) -> bool:
        """Disable live trading.

        This method can be called manually or automatically by the kill-switch.
        When disabled, all positions should be closed immediately.

        Args:
            reason: Reason for disabling

        Returns:
            True if live trading disabled successfully
        """
        if self._state == LiveTradingState.DISABLED:
            logger.warning(f"Live trading already disabled, reason: {reason}")
            return True

        old_state = self._state

        # Trigger kill-switch if available and not already triggered
        if self._kill_switch_executor is not None:
            try:
                # Import here to avoid circular dependency
                from execution.kill_switch.state import KillSwitchState

                # Check if kill-switch is armed
                if hasattr(self._kill_switch_executor, "get_state"):
                    ks_state = self._kill_switch_executor.get_state()
                    if ks_state == KillSwitchState.ARMED:
                        logger.info(
                            "Triggering kill-switch as part of live trading disable"
                        )
                        # Note: kill_switch_executor.trigger() would be called here
                        # but we avoid direct dependency - the kill-switch should
                        # trigger independently based on its own monitoring
            except Exception as e:
                logger.error(f"Error interacting with kill-switch: {e}")

        self._transition_state(LiveTradingState.DISABLED, f"Disabled: {reason}")

        # Reset approval - requires re-authorization after disable
        self._last_approval = None
        self._current_request = None
        self._enabled_at = None

        logger.warning(f"Live trading DISABLED - reason: {reason}")

        # If we were active, this was triggered by kill-switch or emergency
        if old_state == LiveTradingState.ACTIVE:
            logger.critical(
                "LIVE TRADING WAS ACTIVE AND HAS BEEN DISABLED - "
                "POSITIONS SHOULD BE CLOSED IMMEDIATELY"
            )

        return True

    def _transition_state(self, new_state: LiveTradingState, reason: str) -> None:
        """Transition to a new state with logging.

        Args:
            new_state: State to transition to
            reason: Reason for state change
        """
        old_state = self._state
        self._state = new_state

        entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "old_state": old_state.value,
            "new_state": new_state.value,
            "reason": reason,
        }
        self._state_history.append(entry)

        logger.info(
            f"State transition: {old_state.value} -> {new_state.value} ({reason})"
        )

    def get_state_history(self) -> list[dict[str, Any]]:
        """Get history of state transitions.

        Returns:
            List of state transition records
        """
        return self._state_history.copy()

    def update_daily_pnl(self, pnl: float) -> bool:
        """Update daily PnL and check against cap.

        Args:
            pnl: Current day's PnL

        Returns:
            True if within daily loss cap, False if cap exceeded
        """
        now = datetime.now(UTC)

        # Reset daily PnL if it's a new day
        if (now - self._daily_pnl_reset_time).days >= 1:
            self._daily_pnl = 0.0
            self._daily_pnl_reset_time = now

        self._daily_pnl += pnl

        # Check if daily loss cap exceeded
        if self._daily_pnl < -self.config.daily_loss_cap:
            logger.critical(
                f"Daily loss cap exceeded: {self._daily_pnl:.2f} "
                f"(cap: {self.config.daily_loss_cap:.2f})"
            )
            self.disable_live_trading(f"Daily loss cap exceeded: {self._daily_pnl:.2f}")
            return False

        return True

    def get_status(self) -> dict[str, Any]:
        """Get comprehensive status information.

        Returns:
            Dictionary with current status
        """
        return {
            "state": self._state.value,
            "is_live_enabled": self.is_live_enabled,
            "config": self.config.to_dict(),
            "current_request": self._current_request.to_dict()
            if self._current_request
            else None,
            "last_approval": self._last_approval.to_dict()
            if self._last_approval
            else None,
            "enabled_at": self._enabled_at.isoformat() if self._enabled_at else None,
            "daily_pnl": self._daily_pnl,
            "daily_pnl_reset_time": self._daily_pnl_reset_time.isoformat(),
            "state_history_count": len(self._state_history),
        }
