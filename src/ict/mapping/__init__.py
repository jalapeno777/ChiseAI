"""
Zone-to-Signal Mapping for ICT Trading.

Maps ICT zones (Order Blocks, FVGs, CVD divergence zones) to trading signals
for the confluence pipeline.

Zone-to-Signal Mapping Rules:
    - Order Block zones → Entry signals (long for bullish OB, short for bearish OB)
    - FVG zones → Continuation signals (bullish FVG = long continuation, bearish = short)
    - CVD divergence zones → Momentum signals (bullish CVD = long momentum, bearish = short)

Zone Lifecycle Handling:
    - ACTIVE zones: Generate signals
    - TESTED zones: May still generate signals with reduced confidence
    - MITIGATED zones: Signal generation paused
    - INVALIDATED zones: No signal generation

Usage:
    from src.ict.mapping import ZoneSignalMapper, ZoneSignalType, SignalResolution

    mapper = ZoneSignalMapper(zone_manager, cvd_adapter, fvg_adapter, ob_adapter)
    signals = mapper.get_signals(token="BTC/USDT", timeframe="1H", current_price=50000.0)
"""

from src.ict.mapping.signal_models import (
    ContinuationSignal,
    EntrySignal,
    MomentumSignal,
    SignalDirection,
    SignalResolution,
    ZoneSignalType,
    ZoneToSignalResult,
)

__all__ = [
    "ZoneSignalType",
    "SignalDirection",
    "SignalResolution",
    "EntrySignal",
    "ContinuationSignal",
    "MomentumSignal",
    "ZoneToSignalResult",
]
