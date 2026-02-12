---
title: Order Rejects Runbook
category: alerting
severity: critical
estimated_time_to_resolve: 5-20 minutes
last_updated: 2026-02-11
maintainers: risk-team
---

# Order Rejects Runbook

## Problem Description

Trading orders submitted to exchanges (Bybit, Bitget) are being rejected, preventing trade execution. Order rejects can indicate:
- Risk management intervention
- Exchange-side issues
- API configuration problems
- Insufficient funds or margin

## Symptoms and Indicators

### Primary Symptoms
1. **Order Rejection Logs** in application logs:
   ```
   ERROR: OrderRejected: INSUFFICIENT_FUNDS
   ERROR: OrderRejected: RISK_CHECK_FAILED
   ERROR: OrderRejected: BELOW_MIN_ORDER_SIZE
   ```

2. **Execution Dashboard Shows Rejected Orders**
   - Order status shows "rejected" or "failed"
   - Rejection reason displayed
   - No fill confirmation received

3. **Trade Volume Drop** - Expected trades not appearing
4. **P&L Impact** - Missed trading opportunities

### Secondary Indicators
- Position size calculations failing
- Margin utilization spikes
- Risk metric violations in logs
- API error rate increases

## Root Cause Analysis

### Common Causes (in order of frequency)

1. **Risk Management Rejections**
   - Position size exceeds limits (1% per trade risk)
   - Portfolio exposure exceeds limits (10% per token)
   - Leverage exceeds 3x limit
   - Correlation limits breached (>40%)

2. **Insufficient Funds/Margin**
   - Available balance check failed
   - Margin requirements not met
   - Order size below minimum exchange threshold
   - Outstanding orders consuming margin

3. **Order Validation Failures**
   - Invalid price format (negative, zero)
   - Invalid quantity (negative, zero, decimal precision)
   - Symbol not found or delisted
   - Trading pair suspended

4. **Exchange-Side Rejections**
   - Exchange risk management intervention
   - Symbol maintenance
   - Liquidity constraints
   - Market circuit breakers triggered

5. **API/Integration Issues**
   - Incorrect order parameters
   - Timestamp drift causing signature failure
   - Rate limiting affecting order submission
   - Authentication token expired

## Step-by-Step Resolution Procedures

### Phase 1: Initial Assessment (2-5 minutes)

1. **Identify Rejected Orders**
   ```bash
   # View recent order rejections
   docker logs chiseai-api --since 1h | grep -iE "(OrderRejected|rejected|rejection)"

   # Query order history
   curl -s "http://localhost:8000/api/v1/orders?status=rejected" | jq '.'
   ```

2. **Check Execution Dashboard**
   - Navigate to Grafana Execution Dashboard
   - Filter for rejected orders in last hour
   - Note rejection reasons distribution

3. **Gather Order Details**
   - Order ID
   - Symbol/pair
   - Order type (market/limit)
   - Rejection reason
   - Timestamp

### Phase 2: Immediate Analysis (5-10 minutes)

1. **Categorize Rejection Reason**
   ```bash
   # Check for specific error patterns
   docker logs chiseai-api --since 1h | grep -iE "(INSUFFICIENT|RISK|INVALID|BELOW)" | \
     sort | uniq -c | sort -rn
   ```

2. **Check Risk System Status**
   ```bash
   # Verify risk system is functioning
   curl -s "http://localhost:8000/api/v1/risk/status" | jq '.'

   # Check current exposure metrics
   curl -s "http://localhost:8000/api/v1/portfolio/exposure" | jq '.'
   ```

3. **Verify Account Status**
   ```bash
   # Check exchange account balance
   curl -s "http://localhost:8000/api/v1/exchange/bybit/balance" | jq '.'

   # Check open positions
   curl -s "http://localhost:8000/api/v1/positions" | jq '.'
   ```

### Phase 3: Resolution Actions (5-15 minutes)

#### For Risk Management Rejections

1. **Review Risk Limits**
   ```bash
   # Check current risk metrics
   curl -s "http://localhost:8000/api/v1/risk/metrics" | jq '.'

   # Verify per-trade risk limits
   # 1% per trade at stop-loss
   # 10% max per token
   # 3x max leverage
   ```

2. **Adjust Position Sizing**
   ```bash
   # Calculate compliant position size
   python3 scripts/risk/calculate_position.py \
     --symbol btcusdt \
     --entry_price 50000 \
     --stop_loss 49000 \
     --max_risk_pct 1.0

   # Retry order with compliant parameters
   ```

#### For Insufficient Funds

1. **Check Available Balance**
   ```bash
   # Verify account balance
   curl -s "http://localhost:8000/api/v1/exchange/bybit/wallet" | jq '.'
   ```

2. **Cancel Unfilled Orders**
   ```bash
   # Identify and cancel stale orders
   curl -s "http://localhost:8000/api/v1/orders?status=open" | jq '.[] | select(.age > 3600)'

   # Cancel specific order
   curl -X DELETE "http://localhost:8000/api/v1/orders/{order_id}"
   ```

3. **Run Retry Script**
   ```bash
   # Retry rejected orders with exponential backoff
   ./scripts/ops/retry_rejected_orders.sh --max_attempts 3 --backoff 60
   ```

#### For Order Validation Failures

1. **Validate Order Parameters**
   ```bash
   # Check order parameters against exchange requirements
   ./scripts/ops/validate_order_params.sh \
     --symbol btcusdt \
     --quantity 0.001 \
     --price 50000

   # Verify symbol is trading
   curl -s "http://localhost:8000/api/v1/exchange/bybit/symbols" | jq '.[] | select(.symbol == "BTCUSDT")'
   ```

2. **Correct and Retry**
   ```bash
   # Retry with corrected parameters
   ./scripts/ops/submit_order.sh \
     --symbol btcusdt \
     --side buy \
     --type limit \
     --quantity 0.001 \
     --price 49950.50  # Corrected price
   ```

#### For Exchange-Side Issues

1. **Check Exchange Status**
   ```bash
   # Check exchange health endpoints
   curl -s https://api.bybit.com/v5/market/time
   curl -s https://api.bybit.com/v5/market/tickers?category=linear

   # Verify trading status
   ```

2. **Wait and Retry**
   ```bash
   # Monitor exchange status
   ./scripts/ops/monitor_exchange.sh --exchange bybit --duration 300

   # Retry after stability confirmed
   ./scripts/ops/retry_rejected_orders.sh --delay 120
   ```

### Phase 4: Validation (2-5 minutes)

1. **Verify Order Execution**
   ```bash
   # Check order status after retry
   curl -s "http://localhost:8000/api/v1/orders/{order_id}" | jq '.'

   # Verify position updated
   curl -s "http://localhost:8000/api/v1/positions" | jq '.[] | select(.symbol == "BTCUSDT")'
   ```

2. **Monitor for Recurrence**
   ```bash
   # Watch for new rejections
   docker logs -f chiseai-api 2>&1 | grep -iE "(OrderRejected|rejected)"

   # Set up alert for continued issues
   ```

3. **Document Incident**
   - Record order details and rejection reason
   - Note any patterns or systemic issues
   - Update prevention measures

## Estimated Time to Resolve

| Scenario | Estimated Time |
|----------|---------------|
| Risk limit adjustment | 2-5 minutes |
| Insufficient funds (balance check) | 5-10 minutes |
| Order validation fix | 5-10 minutes |
| Exchange-side issue (wait) | 10-20 minutes |
| API/integration issue | 10-15 minutes |

## Prevention Measures

### Proactive Monitoring

1. **Pre-Trade Risk Checks**
   - Validate all orders against risk limits before submission
   - Reject orders that would exceed limits
   - Provide clear feedback on rejection reasons

2. **Balance Monitoring**
   - Track available balance in real-time
   - Alert on low balance scenarios
   - Maintain buffer for margin requirements

3. **Order Validation**
   - Strict parameter validation before submission
   - Sanity checks on all order fields
   - Symbol status verification

### Preventive Maintenance

1. **Regular Balance Reviews**
   - Daily balance checks
   - Alert on unusual balance changes
   - Maintain minimum operating balance

2. **Symbol Health Checks**
   - Monitor symbol trading status
   - Track delisting announcements
   - Pre-validate symbols before trading

3. **Testing Environment**
   - Test orders in paper mode first
   - Validate risk calculations in test environment
   - Chaos test order submission pipeline

## Related Alerts and Dashboards

### Grafana Dashboards
- [Execution Dashboard](../infrastructure/grafana/dashboards/execution.json)
- [Risk Management Dashboard](../infrastructure/grafana/dashboards/risk.json)
- [Position Tracking Dashboard](../infrastructure/grafana/dashboards/positions.json)

### Related Runbooks
- [API Disconnect](api-disconnect.md) - May cause order failures
- [Data Gaps](data-gaps.md) - Can affect order sizing

### Alert Rules
- `Alert: OrderRejectedHighRate` - Triggered when rejection rate > 5%
- `Alert: RiskCheckFailed` - Triggered on risk rejection
- `Alert: InsufficientFunds` - Triggered on balance issues

## Escalation Path

### Level 1: Trading Bot Operator (0-15 minutes)
- Monitors order execution
- Triages rejection reasons
- Executes retry procedures

### Level 2: Risk Analyst (15-30 minutes)
- Investigates systematic issues
- Reviews risk limit configurations
- Coordinates with exchange if needed

### Level 3: Risk Team Lead (30+ minutes)
- Escalated for systemic issues
- Makes decisions on risk limit adjustments
- Coordinates with exchange relationships

## Quick Reference Commands

```bash
# Check recent order rejections
docker logs chiseai-api --since 1h | grep -iE "OrderRejected|rejected"

# View order status
curl -s "http://localhost:8000/api/v1/orders" | jq '.[] | select(.status == "rejected")'

# Retry rejected orders
./scripts/ops/retry_rejected_orders.sh --max_attempts 3

# Check risk metrics
curl -s "http://localhost:8000/api/v1/risk/metrics" | jq '.'

# Verify account balance
curl -s "http://localhost:8000/api/v1/exchange/bybit/balance" | jq '.'

# Cancel stale orders
./scripts/ops/cancel_stale_orders.sh --older_than 3600

# Monitor order stream
docker logs -f chiseai-api 2>&1 | grep -E "(order|trade|fill)"

# Calculate compliant position size
python3 scripts/risk/calculate_position.py --symbol btcusdt --max_risk_pct 1.0
```

## References

- [Bybit Order API Documentation](https://bybit-exchange.github.io/docs/v5/order/create-order)
- [Risk Management Guidelines](docs/risk-management-guidelines.md)
- [Position Sizing Calculator](scripts/risk/calculate_position.py)
