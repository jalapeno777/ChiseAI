"""ICT Confluence Strategy default configuration.

ST-MVP-010: Default configuration dataclass for the ICT Confluence Strategy.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ICTConfluenceConfig:
    """Default ICT Confluence Strategy configuration.

    All parameters have sensible defaults. The strategy uses these
    thresholds to determine entry/exit conditions based on ICT
    confluence signal alignment.

    Attributes:
        min_confluence: Minimum confluence score (0-100) for entry.
        min_signals: Minimum number of aligned ICT signals required.
        require_bos_choch: BOS/CHoCH must be among confirming signals.
        stop_loss_type: Stop-loss calculation method ("atr" or "fixed").
        stop_loss_atr_multiplier: ATR multiplier for ATR-based stops.
        stop_loss_fixed_pct: Fixed percentage for fixed stop-losses.
        risk_per_trade: Maximum risk fraction per trade (0.0-0.1).
        take_profit_rr_ratio: Risk:Reward ratio for take-profit.
        preferred_sessions: Trading sessions preferred for entries.
        timeframe: Primary candle timeframe for analysis.
    """

    min_confluence: float = 60.0
    min_signals: int = 2
    require_bos_choch: bool = True
    stop_loss_type: str = "atr"
    stop_loss_atr_multiplier: float = 1.5
    stop_loss_fixed_pct: float = 0.01
    risk_per_trade: float = 0.02
    take_profit_rr_ratio: float = 2.0
    preferred_sessions: tuple[str, ...] = (
        "london",
        "new_york",
    )
    timeframe: str = "15m"

    def to_dict(self) -> dict[str, object]:
        """Convert config to a dictionary for StrategyProtocol methods."""
        return {
            "min_confluence": self.min_confluence,
            "min_signals": self.min_signals,
            "require_bos_choch": self.require_bos_choch,
            "stop_loss_type": self.stop_loss_type,
            "stop_loss_atr_multiplier": self.stop_loss_atr_multiplier,
            "stop_loss_fixed_pct": self.stop_loss_fixed_pct,
            "risk_per_trade": self.risk_per_trade,
            "take_profit_rr_ratio": self.take_profit_rr_ratio,
            "preferred_sessions": self.preferred_sessions,
            "timeframe": self.timeframe,
            "exit_threshold": self.min_confluence * 0.5,
        }


DEFAULT_CONFIG = ICTConfluenceConfig()
