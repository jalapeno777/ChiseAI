# Strategy DSL Specification

**Version:** 1.0.0  
**Status:** Draft  
**Story:** ST-SIG-001  
**Last Updated:** 2026-02-12

## Overview

This document defines the Strategy Domain-Specific Language (DSL) for ChiseAI. The DSL provides a constrained, declarative format for defining trading strategies that supports safe parameter and structure evolution while maintaining full auditability and reproducibility.

## Design Goals

- **Constrained Evolution**: Changes are limited to approved modules and mutation operators
- **Readable Diffs**: Strategy changes appear as config diffs, not arbitrary code changes
- **Reproducibility**: Every strategy configuration can be exactly reproduced
- **Testability**: All DSL-defined strategies can be backtested and validated
- **Safety**: Risk caps and guardrails are enforced outside the DSL

---

## DSL Structure

A complete strategy definition consists of the following sections:

```yaml
# Required sections
metadata:        # Strategy identification and versioning
universe:        # Trading universe (symbols, sessions)
signals:         # Entry signal definitions
exits:           # Exit rules (stop, take profit, trailing, time-based)
sizing:          # Position sizing rules
execution_policy: # Order execution parameters
risk_rules:      # Risk limits and caps

# Optional sections
filters:         # Market regime and volatility filters
telemetry_tags:  # Audit logging tags
```

---

## 1. Metadata Section

Defines strategy identification, versioning, and classification.

### Schema

```yaml
metadata:
  name: string                    # Unique strategy name (required)
  version: string                 # Semantic version (required)
  description: string             # Human-readable description
  author: string                  # Strategy author/owner
  created_at: ISO8601             # Creation timestamp
  updated_at: ISO8601             # Last update timestamp
  tags:                           # Classification tags
    - string
  category: enum                  # Strategy category
    # [momentum, mean_reversion, trend_following, breakout, grid, arbitrage]
  timeframes:                     # Supported timeframes
    - enum                        # [1m, 5m, 15m, 1h, 4h, 1d]
  status: enum                    # Strategy lifecycle status
    # [development, backtesting, paper, live, deprecated, archived]
```

### Example

```yaml
metadata:
  name: "BTC_Grid_Momentum_v1"
  version: "1.2.0"
  description: "BTC/USDT grid strategy with momentum confirmation"
  author: "chise-ai-system"
  created_at: "2026-01-15T10:00:00Z"
  updated_at: "2026-02-10T14:30:00Z"
  tags:
    - "btc"
    - "grid"
    - "momentum"
    - "perpetual"
  category: "grid"
  timeframes:
    - "15m"
    - "1h"
  status: "backtesting"
```

---

## 2. Universe Section

Defines the trading universe including symbols, sessions, and market filters.

### Schema

```yaml
universe:
  symbols:                        # List of trading pairs
    - symbol: string              # Trading pair (e.g., "BTCUSDT")
      exchange: string            # Exchange identifier
      market_type: enum           # [spot, perpetual, margin]
      
  sessions:                       # Trading sessions (optional)
    - name: string                # Session name
      timezone: string            # IANA timezone
      start_time: "HH:MM"         # Session start
      end_time: "HH:MM"           # Session end
      days:                       # Active days
        - enum                    # [mon, tue, wed, thu, fri, sat, sun]
      
  filters:                        # Universe filters
    min_24h_volume_usd: number    # Minimum daily volume
    max_spread_bps: number        # Maximum spread in basis points
    min_liquidity_depth_usd: number # Minimum orderbook depth
```

### Example

```yaml
universe:
  symbols:
    - symbol: "BTCUSDT"
      exchange: "bybit"
      market_type: "perpetual"
    - symbol: "ETHUSDT"
      exchange: "bybit"
      market_type: "perpetual"
      
  sessions:
    - name: "london_ny_overlap"
      timezone: "UTC"
      start_time: "13:00"
      end_time: "17:00"
      days:
        - "mon"
        - "tue"
        - "wed"
        - "thu"
        - "fri"
        
  filters:
    min_24h_volume_usd: 10000000
    max_spread_bps: 10
    min_liquidity_depth_usd: 500000
```

---

## 3. Signals Section

Defines entry signal triggers and their parameters.

### Schema

```yaml
signals:
  entry_logic: enum               # Entry logic type
    # [single_indicator, confluence, ensemble, pattern]
    
  indicators:                     # Indicator configurations
    - name: string                # Indicator name
      type: enum                  # Indicator type
        # [rsi, macd, ema, sma, bollinger, atr, volume, custom]
      parameters:                 # Indicator-specific parameters
        period: integer
        # ... additional params
      conditions:                 # Entry conditions
        - operator: enum          # [gt, lt, eq, cross_above, cross_below, in_range]
          threshold: number       # Threshold value
          direction: enum         # [long, short, both]
          
  confluence:                     # Confluence scoring (optional)
    enabled: boolean
    min_score: number             # 0.0-1.0 minimum confluence score
    min_confidence: number        # 0.0-1.0 minimum confidence
    require_alignment: boolean    # Require all indicators align
    
  cooldown:                       # Signal cooldown
    bars: integer                 # Bars to wait between signals
    timeframe: enum               # Cooldown timeframe
```

### Example

```yaml
signals:
  entry_logic: "confluence"
  
  indicators:
    - name: "rsi"
      type: "rsi"
      parameters:
        period: 14
        oversold: 30
        overbought: 70
      conditions:
        - operator: "lt"
          threshold: 30
          direction: "long"
        - operator: "gt"
          threshold: 70
          direction: "short"
          
    - name: "ema_cross"
      type: "ema"
      parameters:
        fast_period: 9
        slow_period: 21
      conditions:
        - operator: "cross_above"
          direction: "long"
        - operator: "cross_below"
          direction: "short"
          
  confluence:
    enabled: true
    min_score: 0.65
    min_confidence: 0.75
    require_alignment: false
    
  cooldown:
    bars: 3
    timeframe: "1h"
```

---

## 4. Filters Section

Defines market regime, volatility, and other filters to prevent trading in unfavorable conditions.

### Schema

```yaml
filters:
  regime:                         # Market regime filter
    enabled: boolean
    allowed_regimes:              # Allowed market regimes
      - enum                      # [trending, ranging, volatile, calm]
    detection_method: enum        # [adx, volatility, ml_classifier]
    adx_threshold: number         # ADX threshold for trending (default: 25)
    
  volatility:                     # Volatility filter
    enabled: boolean
    method: enum                  # [atr, bollinger, historical]
    atr_period: integer
    min_atr_percent: number       # Minimum ATR as % of price
    max_atr_percent: number       # Maximum ATR as % of price
    
  time_based:                     # Time-based filters
    - name: string
      type: enum                  # [session, news_event, weekend]
      action: enum                # [block, reduce_size, require_confirmation]
      parameters:                 # Type-specific parameters
        
  correlation:                    # Correlation filter
    enabled: boolean
    max_correlation: number       # Maximum correlation between positions
    lookback_days: integer
```

### Example

```yaml
filters:
  regime:
    enabled: true
    allowed_regimes:
      - "trending"
      - "ranging"
    detection_method: "adx"
    adx_threshold: 20
    
  volatility:
    enabled: true
    method: "atr"
    atr_period: 14
    min_atr_percent: 0.5
    max_atr_percent: 5.0
    
  time_based:
    - name: "high_impact_news"
      type: "news_event"
      action: "block"
      parameters:
        impact_level: "high"
        buffer_minutes: 30
        
  correlation:
    enabled: true
    max_correlation: 0.8
    lookback_days: 30
```

---

## 5. Exits Section

Defines exit rules including stop-loss, take-profit, trailing stops, and time-based exits.

### Schema

```yaml
exits:
  stop_loss:                      # Stop-loss configuration
    enabled: boolean
    type: enum                    # [fixed, atr_based, support_resistance, volatility]
    fixed_percent: number         # For fixed type
    atr_multiplier: number        # For atr_based type
    max_loss_percent: number      # Maximum loss per trade
    
  take_profit:                    # Take-profit configuration
    enabled: boolean
    type: enum                    # [fixed, r_based, fibonacci, trailing]
    fixed_percent: number         # For fixed type
    r_multiple: number            # Risk multiple for R-based TP
    levels:                       # Multiple TP levels
      - percent: number
        close_percent: number     # % of position to close
        
  trailing_stop:                  # Trailing stop configuration
    enabled: boolean
    activation: enum              # [immediate, profit_based]
    activation_percent: number    # Profit % to activate (if profit_based)
    distance_type: enum           # [fixed, atr_based, percent]
    distance_value: number        # Distance value
    atr_multiplier: number        # For atr_based distance
    
  time_based:                     # Time-based exits
    enabled: boolean
    max_bars: integer             # Max bars to hold position
    max_hours: number             # Max hours to hold position
    exit_at_session_end: boolean  # Exit when session ends
    
  breakeven:                      # Breakeven stop
    enabled: boolean
    activation_percent: number    # Profit % to move to BE
    buffer_percent: number        # Buffer above/below entry
```

### Example

```yaml
exits:
  stop_loss:
    enabled: true
    type: "atr_based"
    atr_multiplier: 1.5
    max_loss_percent: 2.0
    
  take_profit:
    enabled: true
    type: "r_based"
    r_multiple: 2.0
    levels:
      - percent: 1.0
        close_percent: 50
      - percent: 2.0
        close_percent: 50
        
  trailing_stop:
    enabled: true
    activation: "profit_based"
    activation_percent: 1.0
    distance_type: "atr_based"
    atr_multiplier: 1.0
    
  time_based:
    enabled: true
    max_bars: 48
    max_hours: 24
    exit_at_session_end: false
    
  breakeven:
    enabled: true
    activation_percent: 0.5
    buffer_percent: 0.1
```

---

## 6. Sizing Section

Defines position sizing rules including risk-per-trade and volatility targeting.

### Schema

```yaml
sizing:
  method: enum                    # Sizing method
    # [fixed, risk_percent, kelly, volatility_target, fixed_usd]
    
  fixed_size: number              # For fixed method (contracts/coins)
  fixed_usd: number               # For fixed_usd method
  
  risk_percent:                   # Risk-based sizing
    enabled: boolean
    percent: number               # % of equity to risk per trade
    max_position_percent: number  # Max position as % of equity
    
  volatility_target:              # Volatility targeting
    enabled: boolean
    target_volatility: number     # Target annualized volatility %
    lookback_days: integer
    max_position_multiplier: number
    
  drawdown_scaling:               # Scale down during drawdowns
    enabled: boolean
    start_drawdown: number        # DD % to start scaling
    max_drawdown: number          # DD % to stop trading
    min_size_multiplier: number   # Minimum size multiplier
    
  pyramiding:                     # Add to winning positions
    enabled: boolean
    max_entries: integer          # Max number of entries
    size_reduction: number        # Size reduction per entry (0-1)
    trigger: enum                 # [profit_percent, atr_distance]
    trigger_value: number
```

### Example

```yaml
sizing:
  method: "risk_percent"
  
  risk_percent:
    enabled: true
    percent: 1.0
    max_position_percent: 10.0
    
  volatility_target:
    enabled: true
    target_volatility: 20.0
    lookback_days: 30
    max_position_multiplier: 2.0
    
  drawdown_scaling:
    enabled: true
    start_drawdown: 5.0
    max_drawdown: 15.0
    min_size_multiplier: 0.25
    
  pyramiding:
    enabled: false
    max_entries: 3
    size_reduction: 0.5
    trigger: "profit_percent"
    trigger_value: 1.0
```

---

## 7. Execution Policy Section

Defines order execution parameters including order types, retries, and slippage handling.

### Schema

```yaml
execution_policy:
  order_types:                    # Order type preferences
    entry: enum                   # [market, limit, stop_limit]
    exit: enum                    # [market, limit]
    
  limit_orders:                   # Limit order settings
    enabled: boolean
    entry_offset_bps: number      # Offset from signal price (basis points)
    exit_offset_bps: number
    timeout_seconds: integer      # Timeout before market order
    
  slippage:                       # Slippage handling
    max_entry_slippage_bps: number
    max_exit_slippage_bps: number
    cancel_on_excessive_slippage: boolean
    
  partial_fills:                  # Partial fill handling
    allow_partial: boolean
    min_fill_percent: number      # Minimum acceptable fill %
    
  retries:                        # Retry configuration
    max_retries: integer
    retry_delay_ms: integer
    backoff_multiplier: number
    
  liquidity:                      # Liquidity requirements
    min_orderbook_depth_usd: number
    max_spread_bps: number
    
  timing:                         # Execution timing
    immediate_or_cancel: boolean
    good_till_time_seconds: integer
```

### Example

```yaml
execution_policy:
  order_types:
    entry: "limit"
    exit: "market"
    
  limit_orders:
    enabled: true
    entry_offset_bps: 5
    exit_offset_bps: 0
    timeout_seconds: 30
    
  slippage:
    max_entry_slippage_bps: 20
    max_exit_slippage_bps: 50
    cancel_on_excessive_slippage: true
    
  partial_fills:
    allow_partial: true
    min_fill_percent: 80
    
  retries:
    max_retries: 3
    retry_delay_ms: 500
    backoff_multiplier: 2.0
    
  liquidity:
    min_orderbook_depth_usd: 100000
    max_spread_bps: 10
    
  timing:
    immediate_or_cancel: false
    good_till_time_seconds: 60
```

---

## 8. Risk Rules Section

Defines risk limits, caps, and circuit breakers.

### Schema

```yaml
risk_rules:
  position_limits:                # Position-level limits
    max_position_size_usd: number
    max_position_percent: number  # % of portfolio
    max_leverage: number          # Max leverage (safety: 3x max)
    
  portfolio_limits:               # Portfolio-level limits
    max_open_positions: integer
    max_correlated_positions: integer
    max_sector_exposure_percent: number
    
  daily_limits:                   # Daily loss limits
    max_daily_loss_usd: number
    max_daily_loss_percent: number
    max_daily_trades: integer
    
  circuit_breakers:               # Trading halt triggers
    - trigger: enum               # [daily_loss, drawdown, volatility_spike]
      threshold: number
      action: enum                # [halt, reduce_size, require_approval]
      duration_minutes: integer
      
  correlation_limits:             # Cross-position limits
    max_pair_correlation: number
    max_portfolio_correlation: number
```

### Example

```yaml
risk_rules:
  position_limits:
    max_position_size_usd: 50000
    max_position_percent: 10.0
    max_leverage: 3.0
    
  portfolio_limits:
    max_open_positions: 5
    max_correlated_positions: 2
    max_sector_exposure_percent: 50.0
    
  daily_limits:
    max_daily_loss_usd: 1000
    max_daily_loss_percent: 2.0
    max_daily_trades: 20
    
  circuit_breakers:
    - trigger: "daily_loss"
      threshold: 2.0
      action: "halt"
      duration_minutes: 60
    - trigger: "drawdown"
      threshold: 10.0
      action: "reduce_size"
      duration_minutes: 0
      
  correlation_limits:
    max_pair_correlation: 0.8
    max_portfolio_correlation: 0.7
```

---

## 9. Telemetry Tags Section

Defines tags for audit logging and observability.

### Schema

```yaml
telemetry_tags:
  strategy_family: string         # Strategy family identifier
  experiment_id: string           # A/B test or experiment ID
  risk_tier: enum                 # [conservative, moderate, aggressive]
  approval_status: enum           # [auto, manual, experimental]
  
  custom_tags:                    # Additional custom tags
    key: value
```

### Example

```yaml
telemetry_tags:
  strategy_family: "grid_momentum"
  experiment_id: "exp_2026_02_grid_v2"
  risk_tier: "moderate"
  approval_status: "auto"
  
  custom_tags:
    backtest_id: "bt_20260210_001"
    optimization_run: "run_42"
```

---

## Complete Example Strategy

```yaml
# Complete BTC Grid Strategy DSL

metadata:
  name: "BTC_Grid_Momentum_v1"
  version: "1.2.0"
  description: "BTC/USDT grid strategy with momentum confirmation"
  author: "chise-ai-system"
  created_at: "2026-01-15T10:00:00Z"
  updated_at: "2026-02-10T14:30:00Z"
  tags:
    - "btc"
    - "grid"
    - "momentum"
  category: "grid"
  timeframes:
    - "15m"
    - "1h"
  status: "backtesting"

universe:
  symbols:
    - symbol: "BTCUSDT"
      exchange: "bybit"
      market_type: "perpetual"
  filters:
    min_24h_volume_usd: 10000000
    max_spread_bps: 10

signals:
  entry_logic: "confluence"
  indicators:
    - name: "rsi"
      type: "rsi"
      parameters:
        period: 14
      conditions:
        - operator: "lt"
          threshold: 30
          direction: "long"
        - operator: "gt"
          threshold: 70
          direction: "short"
  confluence:
    enabled: true
    min_score: 0.65
    min_confidence: 0.75
  cooldown:
    bars: 3
    timeframe: "1h"

filters:
  regime:
    enabled: true
    allowed_regimes:
      - "trending"
      - "ranging"
    detection_method: "adx"
    adx_threshold: 20
  volatility:
    enabled: true
    method: "atr"
    atr_period: 14
    min_atr_percent: 0.5
    max_atr_percent: 5.0

exits:
  stop_loss:
    enabled: true
    type: "atr_based"
    atr_multiplier: 1.5
    max_loss_percent: 2.0
  take_profit:
    enabled: true
    type: "r_based"
    r_multiple: 2.0
  trailing_stop:
    enabled: true
    activation: "profit_based"
    activation_percent: 1.0
    distance_type: "atr_based"
    atr_multiplier: 1.0
  time_based:
    enabled: true
    max_bars: 48
    max_hours: 24

sizing:
  method: "risk_percent"
  risk_percent:
    enabled: true
    percent: 1.0
    max_position_percent: 10.0
  drawdown_scaling:
    enabled: true
    start_drawdown: 5.0
    max_drawdown: 15.0
    min_size_multiplier: 0.25

execution_policy:
  order_types:
    entry: "limit"
    exit: "market"
  limit_orders:
    enabled: true
    entry_offset_bps: 5
    timeout_seconds: 30
  slippage:
    max_entry_slippage_bps: 20
    max_exit_slippage_bps: 50

risk_rules:
  position_limits:
    max_position_size_usd: 50000
    max_position_percent: 10.0
    max_leverage: 3.0
  portfolio_limits:
    max_open_positions: 5
  daily_limits:
    max_daily_loss_percent: 2.0
    max_daily_trades: 20
  circuit_breakers:
    - trigger: "daily_loss"
      threshold: 2.0
      action: "halt"
      duration_minutes: 60

telemetry_tags:
  strategy_family: "grid_momentum"
  risk_tier: "moderate"
  approval_status: "auto"
```

---

## Mutation Operators

Mutation operators define approved changes that can be made to strategies during optimization and evolution.

### Parameter Mutations

| Operator | Description | Example |
|----------|-------------|---------|
| `adjust_threshold` | Modify indicator thresholds | RSI oversold: 30 → 25 |
| `change_lookback` | Modify lookback periods | EMA period: 21 → 14 |
| `adjust_cooldown` | Modify signal cooldown | Bars: 3 → 5 |
| `resize_risk` | Modify risk per trade | Risk %: 1.0 → 0.5 |
| `adjust_multiplier` | Modify ATR/exit multipliers | SL multiplier: 1.5 → 2.0 |
| `shift_offset` | Modify limit order offsets | Entry offset: 5 → 10 bps |

### Structural Mutations

| Operator | Description | Constraints |
|----------|-------------|-------------|
| `add_filter` | Add a new filter | Must be from approved filter library |
| `remove_filter` | Remove an existing filter | Cannot remove required filters |
| `swap_entry` | Change entry indicator family | Must pass backtest validation |
| `swap_exit` | Change exit logic family | Must pass backtest validation |
| `add_ensemble` | Wrap with ensemble logic | Requires min 2 base strategies |
| `toggle_module` | Enable/disable optional module | Cannot disable required modules |

### Mutation Safety Rules

1. **Schema Compliance**: All mutations must produce valid DSL according to this specification
2. **Risk Cap Preservation**: Mutations cannot increase max_leverage above 3x
3. **Validation Required**: Structural mutations require backtest validation
4. **Audit Trail**: All mutations are logged with before/after state
5. **Rollback Support**: Mutations must be reversible

---

## Validation Rules

### Schema Validation

All strategy configurations must pass JSON Schema validation against the DSL schema.

### Semantic Validation

| Rule | Description | Severity |
|------|-------------|----------|
| `risk_cap_check` | max_leverage ≤ 3.0 | ERROR |
| `position_limit_check` | max_position_percent ≤ 100% | ERROR |
| `stop_loss_required` | Stop-loss must be enabled | WARNING |
| `daily_loss_cap` | max_daily_loss_percent ≤ 5% | WARNING |
| `cooldown_check` | Cooldown must be ≥ 1 bar | WARNING |
| `confluence_min_score` | min_score must be 0.5-1.0 | ERROR |
| `timeframe_supported` | Timeframe must be in supported list | ERROR |

### Backtest Validation

Before promotion to paper/live, strategies must pass:

1. **Minimum Metrics**:
   - Sharpe Ratio ≥ 0.5
   - Max Drawdown < 20%
   - Win Rate ≥ 45%
   - Profit Factor ≥ 1.0

2. **Walk-Forward Validation**:
   - Pass at least 3 walk-forward windows
   - Out-of-sample performance within 20% of in-sample

3. **Stress Tests**:
   - High volatility regime performance
   - Low liquidity simulation
   - Flash crash scenario

---

## Safety Constraints

### Hard Limits (Enforced by Guardrails)

| Constraint | Value | Enforcement |
|------------|-------|-------------|
| Max Leverage | 3.0x | Position sizing engine |
| Max Position Size | Configurable | Risk management layer |
| Max Daily Loss | 2% of equity | Circuit breaker |
| Max Drawdown | 15% | Trading halt |
| Min Stop Distance | 0.5% | Order validation |

### Soft Limits (Warnings)

| Constraint | Value | Action |
|------------|-------|--------|
| Position Concentration | >50% in single asset | Alert + require approval |
| Correlation Exposure | >0.8 between positions | Warning |
| Trade Frequency | >20 trades/day | Review for overtrading |
| Slippage | >20 bps entry, >50 bps exit | Alert |

---

## Integration with Pipeline

The DSL integrates with the candidate backtesting pipeline:

```python
# From src/backtesting/candidate/pipeline.py
class CandidateBacktestPipeline:
    def run_backtest(self, candidate_config: dict, ...) -> CandidateResult:
        # candidate_config is a DSL-compliant strategy definition
        # ...
```

### Candidate Result Mapping

DSL sections map to `CandidateResult` fields:

| DSL Section | CandidateResult Field |
|-------------|----------------------|
| `metadata` | `strategy_id`, `version` |
| `signals` + `filters` | Used in backtest calculation |
| `exits` + `sizing` | Used in P&L calculation |
| All sections | `metrics` (derived) |

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2026-02-12 | Initial specification |

---

## References

- **SKILL.md**: `docs/_archive/tempdocs-pack/.opencode/skills/strategy-dsl-design/SKILL.md`
- **Candidate Models**: `src/backtesting/candidate/models.py`
- **Pipeline**: `src/backtesting/candidate/pipeline.py`
- **Signal Generation**: `src/signal_generation/signal_generator.py`
