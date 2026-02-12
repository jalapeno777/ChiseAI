# ST-OPS-002: Paper/Live Trading Dashboards

## Story Metadata

| Field | Value |
|-------|-------|
| **Story ID** | ST-OPS-002 |
| **Title** | Paper/Live Trading Dashboards |
| **Story Points** | 4 |
| **Epic ID** | EP-OPS-001 |
| **Sprint ID** | p0-7 |
| **Status** | Planned |

## Description

Create specialized Grafana dashboards for monitoring paper trading and live trading operations. These dashboards provide real-time visibility into trading performance, position status, order execution, and risk metrics for both simulation and production environments.

## Features Delivered

1. **Paper Trading Dashboard**
   - Real-time P&L tracking for paper trades
   - Open positions and order status
   - Strategy performance comparison
   - Virtual balance and equity curve

2. **Live Trading Dashboard**
   - Real account balance and margin monitoring
   - Active positions with unrealized P&L
   - Order execution history and fill rates
   - Exchange connectivity status

3. **Trading Performance Metrics**
   - Win rate, profit factor, Sharpe ratio
   - Drawdown monitoring and alerts
   - Trade duration analysis
   - Symbol/sector performance breakdown

4. **Risk Monitoring Panels**
   - Position size vs account balance
   - Exposure concentration alerts
   - Daily loss limit tracking
   - Leverage utilization metrics

## Dependencies

- ST-OPS-001: Grafana Dashboards (completed - base Grafana infrastructure)
- ST-DATA-003: Continuous Backtest Runner (completed - performance metrics patterns)
- CH-BG-001: Bitget Integration (in progress - live trading data source)

## Acceptance Criteria

- [ ] AC1: Paper trading dashboard JSON created and provisioned
- [ ] AC2: Live trading dashboard JSON created and provisioned
- [ ] AC3: Dashboards display real-time data from trading operations
- [ ] AC4: Risk metrics panels show accurate position sizing
- [ ] AC5: Exchange connectivity status visible on live dashboard
- [ ] AC6: Dashboard refresh rate appropriate for trading (5-10 seconds)
- [ ] AC7: Mobile-friendly layout for on-the-go monitoring

## Scope Globs

```yaml
implementation:
  - infrastructure/terraform/grafana/dashboards/paper-trading.json
  - infrastructure/terraform/grafana/dashboards/live-trading.json
documentation:
  - docs/operations/trading-dashboards.md
tests:
  - tests/grafana/test_trading_dashboards.py
```

## Verification Steps

1. Provision dashboards via Terraform: `terraform apply`
2. Verify dashboards appear in Grafana "Trading" folder
3. Check paper trading dashboard shows simulated data
4. Verify live trading dashboard connects to exchange API
5. Test real-time updates with active trades
6. Confirm risk metrics calculate correctly
7. Test mobile responsiveness of dashboards

## Notes

- Paper trading uses simulated data with realistic delays
- Live trading requires secure API credential management
- Consider implementing view-only mode for shared access
- Trading dashboards may require higher refresh rates than monitoring dashboards
