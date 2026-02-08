from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RiskSizingResult:
    notional_usd: float
    risk_usd: float


def size_notional_for_stop_loss(
    *,
    portfolio_usd: float,
    entry_price: float,
    stop_loss_price: float,
    max_risk_fraction: float = 0.01,
) -> RiskSizingResult:
    """Return notional sizing so that a stop loss implies a max % portfolio loss.

    Assumptions:
    - Linear PnL approximation: loss ~= notional * (|entry - stop| / entry)
    - Notional is USD value of position at entry.
    - Caller decides long/short; sizing uses absolute distance.
    """
    if portfolio_usd <= 0:
        raise ValueError("portfolio_usd must be > 0")
    if entry_price <= 0:
        raise ValueError("entry_price must be > 0")
    if stop_loss_price <= 0:
        raise ValueError("stop_loss_price must be > 0")
    if not (0 < max_risk_fraction < 1):
        raise ValueError("max_risk_fraction must be between 0 and 1")

    sl_frac = abs(entry_price - stop_loss_price) / entry_price
    if sl_frac <= 0:
        raise ValueError("stop loss must differ from entry price")

    risk_usd = portfolio_usd * max_risk_fraction
    notional_usd = risk_usd / sl_frac
    return RiskSizingResult(notional_usd=notional_usd, risk_usd=risk_usd)
