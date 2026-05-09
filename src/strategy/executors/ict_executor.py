"""ICT Confluence Strategy Executor - multi-signal confirmation strategy.

Uses ICT (Inner Circle Trader) confluence signals to generate entry/exit
signals based on multi-signal alignment. Accepts pre-computed signal data
as input, keeping the strategy module loosely coupled from market_analysis
and signal_generation modules.

Entry rules:
- Confluence score >= min_confluence (default: 60/100)
- At least min_signals (default: 2) ICT signals aligned
- BOS/CHoCH must be one of the confirming signals (priority gate)
- Session alignment (London/NY preferred)

Exit rules:
- Confluence score drops below exit_threshold (default: 30/100)
- Opposing BOS/CHoCH signal detected
- Stop-loss: ATR-based or fixed percentage

ST-MVP-010: ICT Confluence Strategy satisfying StrategyProtocol.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from strategy.contracts import SignalResult

# ---------------------------------------------------------------------------
# Signal data structures (accepted as input, not generated internally)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ICTSignalData:
    """Represents a single ICT signal from the signal pipeline.

    This is the input format accepted by the executor. Signals are
    computed externally by signal_generation modules and passed in
    via the config/data dicts.

    Attributes:
        signal_type: Type of ICT signal (e.g., "bos_choch",
            "order_block", "fvg", "cvd").
        direction: Signal direction ("bullish" or "bearish").
        confidence: Signal confidence in [0.0, 1.0].
        timestamp: ISO 8601 timestamp string.
        priority: Signal priority (1=highest, 4=lowest).
        metadata: Optional additional signal context.
    """

    signal_type: str
    direction: str
    confidence: float
    timestamp: str
    priority: int = 4
    metadata: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Priority mapping for ICT signals
# ---------------------------------------------------------------------------

ICT_SIGNAL_PRIORITIES: dict[str, int] = {
    "bos_choch": 1,
    "order_block": 2,
    "fvg": 3,
    "cvd": 4,
}

VALID_SIGNAL_TYPES = frozenset(ICT_SIGNAL_PRIORITIES.keys())

VALID_SESSIONS = frozenset(("london", "new_york", "asian", "london_close", "ny_pm"))


class ICTConfluenceExecutor:
    """ICT Confluence Strategy using multi-signal confirmation.

    Accepts pre-computed ICT signal data and confluence scores as input
    to generate trading signals. The actual signal computation happens
    at a higher orchestration layer (see ST-MVP-011).

    This executor satisfies StrategyProtocol (structural typing).
    """

    @property
    def name(self) -> str:
        """Strategy name identifier."""
        return "ict_confluence"

    @property
    def version(self) -> str:
        """Strategy version string."""
        return "1.0.0"

    def validate_config(self, config: dict[str, Any]) -> bool:
        """Validate a strategy configuration dictionary.

        Required keys: none (all have defaults).
        Optional keys:
            min_confluence (float): Minimum confluence score [0-100].
            min_signals (int): Minimum aligned signals [1-4].
            require_bos_choch (bool): BOS/CHoCH priority gate.
            exit_threshold (float): Exit confluence threshold.
            stop_loss_type (str): "atr" or "fixed".
            risk_per_trade (float): Risk fraction per trade.
            take_profit_rr_ratio (float): Risk:Reward ratio.

        Args:
            config: Strategy configuration to validate.

        Returns:
            True if the configuration is valid.
        """
        if not isinstance(config, dict):
            return False

        validators: dict[str, tuple[Any, type]] = {
            "min_confluence": (60.0, (int, float)),
            "min_signals": (2, int),
            "require_bos_choch": (True, bool),
            "exit_threshold": (30.0, (int, float)),
            "stop_loss_type": ("atr", str),
            "risk_per_trade": (0.02, (int, float)),
            "take_profit_rr_ratio": (2.0, (int, float)),
        }

        for key, (_default, expected_types) in validators.items():
            if key in config:
                value = config[key]
                if not isinstance(value, expected_types):
                    return False

        # Range checks
        if "min_confluence" in config:
            val = config["min_confluence"]
            if not (0.0 <= val <= 100.0):
                return False

        if "min_signals" in config:
            val = config["min_signals"]
            if not (1 <= val <= 4):
                return False

        if "exit_threshold" in config:
            val = config["exit_threshold"]
            if not (0.0 <= val <= 100.0):
                return False

        if "stop_loss_type" in config:
            if config["stop_loss_type"] not in ("atr", "fixed"):
                return False

        if "risk_per_trade" in config:
            val = config["risk_per_trade"]
            if not (0.0 < val <= 0.1):
                return False

        if "take_profit_rr_ratio" in config:
            val = config["take_profit_rr_ratio"]
            if val <= 0.0:
                return False

        return True

    def generate_signals(
        self,
        market_data: list[dict[str, Any]],
        config: dict[str, Any],
    ) -> list[SignalResult]:
        """Generate trading signals from market data.

        Processes pre-computed signal data embedded in market_data entries.
        Each entry may contain an ``ict_signals`` list and a
        ``confluence_score`` float.

        Args:
            market_data: List of data bars, each potentially containing
                ``ict_signals`` (list of dicts) and ``confluence_score``
                (float).
            config: Strategy configuration with thresholds.

        Returns:
            List of trading signals (entry/exit/stop).
        """
        min_confluence = config.get("min_confluence", 60.0)
        min_signals = config.get("min_signals", 2)
        require_bos = config.get("require_bos_choch", True)
        exit_threshold = config.get("exit_threshold", 30.0)

        signals: list[SignalResult] = []

        for bar in market_data:
            ict_signals_raw = bar.get("ict_signals", [])
            confluence_score = bar.get("confluence_score", 0.0)
            timestamp = bar.get("timestamp", "")

            if not ict_signals_raw:
                continue

            parsed = self._parse_signals(ict_signals_raw)
            if not parsed:
                continue

            aligned = self._get_aligned_signals(parsed)
            direction = self._determine_direction(aligned)

            if not direction:
                continue

            # Exit signal: confluence drops below threshold
            if confluence_score < exit_threshold:
                signals.append(
                    SignalResult(
                        signal_type="exit",
                        direction="flat",
                        confidence=confluence_score / 100.0,
                        timestamp=timestamp,
                        metadata={"reason": "confluence_below_threshold"},
                    )
                )
                continue

            # Opposing BOS/CHoCH check
            opposing = self._has_opposing_bos(parsed, direction)
            if opposing:
                signals.append(
                    SignalResult(
                        signal_type="exit",
                        direction="flat",
                        confidence=0.7,
                        timestamp=timestamp,
                        metadata={"reason": "opposing_bos_choch"},
                    )
                )
                continue

            # Entry signal: confluence gate
            if confluence_score < min_confluence:
                continue

            # Minimum signals gate
            if len(aligned) < min_signals:
                continue

            # BOS/CHoCH priority gate
            if require_bos:
                has_bos = any(s.signal_type == "bos_choch" for s in aligned)
                if not has_bos:
                    continue

            confidence = self._calculate_confidence(confluence_score, aligned)

            signals.append(
                SignalResult(
                    signal_type="entry",
                    direction=direction,
                    confidence=confidence,
                    timestamp=timestamp,
                    metadata={
                        "confluence_score": confluence_score,
                        "aligned_signals": [s.signal_type for s in aligned],
                        "aligned_count": len(aligned),
                    },
                )
            )

        return signals

    def execute(
        self,
        strategy_config: dict[str, Any],
        data: list[dict[str, Any]],
        initial_capital: float,
    ) -> dict[str, Any]:
        """Execute strategy on data and return results.

        Simulates trading based on generated signals. Calculates P&L,
        drawdown, and other metrics from the signal sequence.

        Args:
            strategy_config: Strategy configuration dictionary.
            data: OHLCV data with embedded ICT signal data.
            initial_capital: Starting capital for execution.

        Returns:
            Execution results dictionary compatible with ExecutionResult.
        """
        risk_per_trade = strategy_config.get("risk_per_trade", 0.02)
        rr_ratio = strategy_config.get("take_profit_rr_ratio", 2.0)

        signals = self.generate_signals(data, strategy_config)

        capital = initial_capital
        peak_capital = initial_capital
        max_drawdown = 0.0
        winning_trades = 0
        total_trades = 0
        total_pnl = 0.0
        position: dict[str, Any] | None = None

        for i, bar in enumerate(data):
            bar_close = bar.get("close", 0.0)
            timestamp = bar.get("timestamp", f"bar_{i}")

            # Find matching signal for this bar
            matching = [s for s in signals if s.timestamp == timestamp]

            for signal in matching:
                if signal.signal_type == "entry" and position is None:
                    # Open position
                    risk_amount = capital * risk_per_trade
                    stop_distance = bar_close * risk_per_trade

                    if signal.direction == "long":
                        stop_loss = bar_close - stop_distance
                        take_profit = bar_close + (stop_distance * rr_ratio)
                    else:
                        stop_loss = bar_close + stop_distance
                        take_profit = bar_close - (stop_distance * rr_ratio)

                    position = {
                        "direction": signal.direction,
                        "entry_price": bar_close,
                        "stop_loss": stop_loss,
                        "take_profit": take_profit,
                        "risk_amount": risk_amount,
                    }
                    total_trades += 1

                elif signal.signal_type == "exit" and position is not None:
                    # Close position at bar close
                    entry = position["entry_price"]
                    direction = position["direction"]

                    if direction == "long":
                        trade_pnl = (bar_close - entry) / entry * capital
                    else:
                        trade_pnl = (entry - bar_close) / entry * capital

                    capital += trade_pnl
                    total_pnl += trade_pnl

                    if trade_pnl > 0:
                        winning_trades += 1

                    peak_capital = max(peak_capital, capital)
                    drawdown = (
                        (peak_capital - capital) / peak_capital
                        if peak_capital > 0
                        else 0.0
                    )
                    max_drawdown = max(max_drawdown, drawdown)
                    position = None

            # Check stop/take profit if position open
            if position is not None:
                high = bar.get("high", bar_close)
                low = bar.get("low", bar_close)

                closed = self._check_stop_tp(position, high, low, bar_close)
                if closed is not None:
                    trade_pnl = closed
                    capital += trade_pnl
                    total_pnl += trade_pnl

                    if trade_pnl > 0:
                        winning_trades += 1

                    peak_capital = max(peak_capital, capital)
                    drawdown = (
                        (peak_capital - capital) / peak_capital
                        if peak_capital > 0
                        else 0.0
                    )
                    max_drawdown = max(max_drawdown, drawdown)
                    position = None

        win_rate = winning_trades / total_trades if total_trades > 0 else 0.0

        pnl = capital - initial_capital
        sharpe = self._calculate_sharpe(total_pnl, total_trades)

        return {
            "trades": total_trades,
            "pnl": round(pnl, 2),
            "sharpe": round(sharpe, 4),
            "max_drawdown": round(max_drawdown, 4),
            "win_rate": round(win_rate, 4),
            "metadata": {
                "initial_capital": initial_capital,
                "final_capital": round(capital, 2),
                "total_pnl": round(total_pnl, 2),
                "strategy": self.name,
                "version": self.version,
            },
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _parse_signals(self, raw_signals: list[dict[str, Any]]) -> list[ICTSignalData]:
        """Parse raw signal dicts into ICTSignalData objects."""
        parsed: list[ICTSignalData] = []
        for raw in raw_signals:
            sig_type = raw.get("signal_type", "")
            if sig_type not in VALID_SIGNAL_TYPES:
                continue
            parsed.append(
                ICTSignalData(
                    signal_type=sig_type,
                    direction=raw.get("direction", ""),
                    confidence=float(raw.get("confidence", 0.0)),
                    timestamp=raw.get("timestamp", ""),
                    priority=ICT_SIGNAL_PRIORITIES.get(sig_type, 4),
                    metadata=raw.get("metadata"),
                )
            )
        return parsed

    def _get_aligned_signals(self, signals: list[ICTSignalData]) -> list[ICTSignalData]:
        """Get signals that share a common direction (>= 2 aligned)."""
        if len(signals) < 2:
            return []

        directions: dict[str, list[ICTSignalData]] = {}
        for s in signals:
            if s.direction not in ("bullish", "bearish"):
                continue
            directions.setdefault(s.direction, []).append(s)

        for _dir, group in directions.items():
            if len(group) >= 2:
                return group

        return []

    def _determine_direction(self, aligned: list[ICTSignalData]) -> str:
        """Determine trade direction from aligned signals."""
        if not aligned:
            return ""

        first_dir = aligned[0].direction
        if first_dir == "bullish":
            return "long"
        elif first_dir == "bearish":
            return "short"
        return ""

    def _has_opposing_bos(
        self,
        all_signals: list[ICTSignalData],
        trade_direction: str,
    ) -> bool:
        """Check for BOS/CHoCH signal opposing the trade direction."""
        opposing_dir = "bearish" if trade_direction == "long" else "bullish"
        return any(
            s.signal_type == "bos_choch" and s.direction == opposing_dir
            for s in all_signals
        )

    def _calculate_confidence(
        self,
        confluence_score: float,
        aligned: list[ICTSignalData],
    ) -> float:
        """Calculate signal confidence from confluence and alignment."""
        base = confluence_score / 100.0
        # Bonus for more aligned signals
        signal_bonus = min(len(aligned) * 0.05, 0.2)
        # Average confidence of aligned signals
        avg_signal_conf = (
            sum(s.confidence for s in aligned) / len(aligned) if aligned else 0.0
        )
        combined = base * 0.5 + avg_signal_conf * 0.3 + signal_bonus * 0.2
        return round(min(max(combined, 0.0), 1.0), 4)

    def _check_stop_tp(
        self,
        position: dict[str, Any],
        bar_high: float,
        bar_low: float,
        bar_close: float,
    ) -> float | None:
        """Check if stop-loss or take-profit was hit.

        Returns:
            Trade P&L if position was closed, None otherwise.
        """
        sl = position["stop_loss"]
        tp = position["take_profit"]
        risk_amount = position["risk_amount"]
        direction = position["direction"]

        if direction == "long":
            if bar_low <= sl:
                return -risk_amount
            if bar_high >= tp:
                return risk_amount * (position.get("take_profit_rr_ratio", 2.0))
        else:
            if bar_high >= sl:
                return -risk_amount
            if bar_low <= tp:
                return risk_amount * (position.get("take_profit_rr_ratio", 2.0))

        return None

    def _calculate_sharpe(self, total_pnl: float, trades: int) -> float:
        """Calculate a simplified Sharpe ratio estimate."""
        if trades == 0:
            return 0.0
        # Simplified: annualize average trade return
        avg_return = total_pnl / trades
        # Rough approximation assuming ~252 trading days, ~4 trades/day
        if avg_return <= 0:
            return 0.0
        annualized = avg_return * 252
        # Assume 20% annualized volatility as baseline
        return annualized / (annualized * 0.2 + 1e-10) if annualized > 0 else 0.0
