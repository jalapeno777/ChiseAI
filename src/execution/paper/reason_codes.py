"""Unified reason code contract for paper trading.

Provides standardized enums and mapping utilities for:
- Trade exit reasons (CloseReason)
- Signal rejection reasons (RejectReason)
- Bidirectional mapping between string codes and enum values

This module serves as the single source of truth for all reason codes
in the paper trading system, ensuring consistency across:
- Trade journal entries
- Signal provenance tracking
- Orchestrator decision logging

For REASON-CODE-001: Unified Reason Code Contract
"""

from __future__ import annotations

from enum import Enum


class ExitReason(Enum):
    """Reason for trade exit.

    Reasons:
        STOP_LOSS_HIT: Position closed due to stop loss trigger
        TAKE_PROFIT_HIT: Position closed due to take profit trigger
        SIGNAL_REVERSE: Position closed due to opposing signal
        TIME_LIMIT: Position closed due to time limit expiration
        MANUAL_CLOSE: Position manually closed by operator
        KILL_SWITCH: Position closed due to kill switch activation
        RISK_REDUCTION: Position closed as part of risk reduction
    """

    STOP_LOSS_HIT = "stop_loss_hit"
    TAKE_PROFIT_HIT = "take_profit_hit"
    SIGNAL_REVERSE = "signal_reverse"
    TIME_LIMIT = "time_limit"
    MANUAL_CLOSE = "manual_close"
    KILL_SWITCH = "kill_switch"
    RISK_REDUCTION = "risk_reduction"


class DecisionReason(Enum):
    """Reason codes for execution decisions.

    All accept/reject/skip decisions must have a reason code for
    auditability and debugging. These codes are normalized across
    the provenance tracking system.

    Reasons:
        SIGNAL_ACCEPTED: Signal passed all validation and was accepted
        RISK_REJECTED: Signal rejected due to risk constraints
        LOW_CONFIDENCE: Signal confidence below threshold
        SYMBOL_OCCUPIED: Symbol already has an active position
        KILL_SWITCH_ACTIVE: Kill switch is active, blocking all signals
        MAX_POSITION_LIMIT: Maximum position limit reached
        INVALID_SIGNAL: Signal validation failed (malformed data)
        SYSTEM_ERROR: Internal system error during processing
    """

    SIGNAL_ACCEPTED = "signal_accepted"
    RISK_REJECTED = "risk_rejected"
    LOW_CONFIDENCE = "low_confidence"
    SYMBOL_OCCUPIED = "symbol_occupied"
    KILL_SWITCH_ACTIVE = "kill_switch_active"
    MAX_POSITION_LIMIT = "max_position_limit"
    INVALID_SIGNAL = "invalid_signal"
    SYSTEM_ERROR = "system_error"


class CloseReason(Enum):
    """Reason for trade exit/close.

    Standardized exit reasons for trade journal entries and position closures.
    These codes are used consistently across the orchestrator, trade journal,
    and reporting surfaces.

    Reasons:
        STOP_LOSS_HIT: Position closed due to stop loss trigger
        TAKE_PROFIT_HIT: Position closed due to take profit trigger
        SIGNAL_REVERSE: Position closed due to opposing signal
        TIME_LIMIT: Position closed due to time limit expiration
        MANUAL_CLOSE: Position manually closed by operator
        KILL_SWITCH: Position closed due to kill switch activation
        RISK_REDUCTION: Position closed as part of risk reduction
        POSITION_CLOSE: Generic position close (legacy alias)
    """

    STOP_LOSS_HIT = "stop_loss_hit"
    TAKE_PROFIT_HIT = "take_profit_hit"
    SIGNAL_REVERSE = "signal_reverse"
    TIME_LIMIT = "time_limit"
    MANUAL_CLOSE = "manual_close"
    KILL_SWITCH = "kill_switch"
    RISK_REDUCTION = "risk_reduction"
    POSITION_CLOSE = "position_close"


class RejectReason(Enum):
    """Reason for signal/order rejection.

    Standardized rejection reasons for tracking why signals were not
    executed. Used in provenance tracking and decision logging.

    Reasons:
        KILL_SWITCH_ACTIVE: Kill switch is active, blocking all signals
        NO_MARKET_PRICE: No market price available for symbol
        LLM_REJECTION: LLM enhancer rejected the signal
        RISK_VIOLATION: Risk constraint violation
        ORDER_FAILED: Order placement failed
        SYSTEM_ERROR: Internal system error
        SYMBOL_OCCUPIED: Symbol already has an active position
        MAX_POSITION_LIMIT: Maximum position limit reached
        LOW_CONFIDENCE: Signal confidence below threshold
        INVALID_SIGNAL: Signal validation failed
    """

    KILL_SWITCH_ACTIVE = "kill_switch_active"
    NO_MARKET_PRICE = "no_market_price"
    LLM_REJECTION = "llm_rejection"
    RISK_VIOLATION = "risk_violation"
    ORDER_FAILED = "order_failed"
    SYSTEM_ERROR = "system_error"
    SYMBOL_OCCUPIED = "symbol_occupied"
    MAX_POSITION_LIMIT = "max_position_limit"
    LOW_CONFIDENCE = "low_confidence"
    INVALID_SIGNAL = "invalid_signal"


class ReasonCodeMapper:
    """Maps between string reason codes and enum values.

    Provides centralized mapping logic to ensure consistency when
    converting between string representations (from external sources,
    configuration, or legacy code) and typed enum values.

    All mappings are case-insensitive for the input strings.
    """

    # Mapping from close reason strings to CloseReason enum values
    _CLOSE_REASON_MAP: dict[str, CloseReason] = {
        # Standard reasons
        "stop_loss_hit": CloseReason.STOP_LOSS_HIT,
        "take_profit_hit": CloseReason.TAKE_PROFIT_HIT,
        "signal_reverse": CloseReason.SIGNAL_REVERSE,
        "time_limit": CloseReason.TIME_LIMIT,
        "manual_close": CloseReason.MANUAL_CLOSE,
        "kill_switch": CloseReason.KILL_SWITCH,
        "risk_reduction": CloseReason.RISK_REDUCTION,
        "position_close": CloseReason.POSITION_CLOSE,
        # Legacy aliases (for backward compatibility)
        "manual": CloseReason.MANUAL_CLOSE,
        "opposite_signal": CloseReason.SIGNAL_REVERSE,
        "stop_loss": CloseReason.STOP_LOSS_HIT,
        "take_profit": CloseReason.TAKE_PROFIT_HIT,
    }

    # Mapping from CloseReason enum to ExitReason enum (for trade journal compatibility)
    _CLOSE_TO_EXIT_MAP: dict[CloseReason, ExitReason] = {
        CloseReason.STOP_LOSS_HIT: ExitReason.STOP_LOSS_HIT,
        CloseReason.TAKE_PROFIT_HIT: ExitReason.TAKE_PROFIT_HIT,
        CloseReason.SIGNAL_REVERSE: ExitReason.SIGNAL_REVERSE,
        CloseReason.TIME_LIMIT: ExitReason.TIME_LIMIT,
        CloseReason.MANUAL_CLOSE: ExitReason.MANUAL_CLOSE,
        CloseReason.KILL_SWITCH: ExitReason.KILL_SWITCH,
        CloseReason.RISK_REDUCTION: ExitReason.RISK_REDUCTION,
        CloseReason.POSITION_CLOSE: ExitReason.MANUAL_CLOSE,  # Default fallback
    }

    @classmethod
    def map_close_reason_string_to_enum(cls, reason: str) -> ExitReason:
        """Map a close reason string to an ExitReason enum value.

        Handles standard reason strings and legacy aliases for backward
        compatibility. Returns ExitReason.MANUAL_CLOSE as the default
        if the reason string is unknown.

        Args:
            reason: The reason string to map (e.g., "time_limit", "manual")

        Returns:
            ExitReason enum value corresponding to the string

        Examples:
            >>> ReasonCodeMapper.map_close_reason_string_to_enum("time_limit")
            ExitReason.TIME_LIMIT
            >>> ReasonCodeMapper.map_close_reason_string_to_enum("manual")
            ExitReason.MANUAL_CLOSE
            >>> ReasonCodeMapper.map_close_reason_string_to_enum("opposite_signal")
            ExitReason.SIGNAL_REVERSE
        """
        if not reason:
            return ExitReason.MANUAL_CLOSE

        # Normalize to lowercase for case-insensitive matching
        normalized = reason.lower()

        # First map to CloseReason, then to ExitReason
        close_reason = cls._CLOSE_REASON_MAP.get(normalized, CloseReason.MANUAL_CLOSE)
        return cls._CLOSE_TO_EXIT_MAP.get(close_reason, ExitReason.MANUAL_CLOSE)

    @classmethod
    def map_string_to_close_reason(cls, reason: str) -> CloseReason:
        """Map a string to CloseReason enum.

        Args:
            reason: The reason string to map

        Returns:
            CloseReason enum value, defaults to MANUAL_CLOSE
        """
        if not reason:
            return CloseReason.MANUAL_CLOSE

        return cls._CLOSE_REASON_MAP.get(reason.lower(), CloseReason.MANUAL_CLOSE)

    @classmethod
    def map_close_reason_to_exit_reason(cls, close_reason: CloseReason) -> ExitReason:
        """Map CloseReason to ExitReason.

        Args:
            close_reason: CloseReason enum value

        Returns:
            Corresponding ExitReason enum value
        """
        return cls._CLOSE_TO_EXIT_MAP.get(close_reason, ExitReason.MANUAL_CLOSE)

    @classmethod
    def get_all_close_reason_strings(cls) -> list[str]:
        """Get all valid close reason strings.

        Returns:
            List of all recognized close reason strings including aliases
        """
        return list(cls._CLOSE_REASON_MAP.keys())

    @classmethod
    def is_valid_close_reason(cls, reason: str) -> bool:
        """Check if a string is a valid close reason.

        Args:
            reason: The reason string to check

        Returns:
            True if the string maps to a known close reason
        """
        if not reason:
            return False
        return reason.lower() in cls._CLOSE_REASON_MAP
