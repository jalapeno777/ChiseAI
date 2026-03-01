# Recap Semantics Runbook

> **Story**: ST-VENUE-001  
> **Last Updated**: 2026-03-01  
> **Owner**: Venue Provenance & Recap System

## Table of Contents

1. [Overview](#overview)
2. [Canonical vs Telemetry Distinction](#canonical-vs-telemetry-distinction)
3. [Reconciliation System](#reconciliation-system)
4. [Venue Provenance in Recaps](#venue-provenance-in-recaps)
5. [Bybit Demo Mode Validation](#bybit-demo-mode-validation)
6. [Troubleshooting Guide](#troubleshooting-guide)
7. [Example Recap Output](#example-recap-output)

---

## Overview

The **Recap System** provides end-of-session summaries that validate trading activity integrity by comparing:

- **Canonical persisted counts**: The authoritative record of trading activity stored in the database
- **Telemetry events**: Real-time event streams that may have gaps or delays

Recaps are generated at the end of each trading session and serve as the primary mechanism for:
- Detecting data loss or corruption
- Validating venue-specific trading behavior
- Ensuring compliance with demo/paper trading constraints
- Providing auditable records for post-trade analysis

### Key Principles

1. **Canonical data is truth**: Database records are the authoritative source
2. **Telemetry is advisory**: Event streams provide real-time visibility but are not audited
3. **Reconciliation catches drift**: Automated comparison identifies discrepancies
4. **Venue context matters**: Different venues have different validation rules

---

## Canonical vs Telemetry Distinction

### Canonical Persisted Counts

Canonical counts are stored in the database and represent the **authoritative record** of all trading activity.

| Aspect | Description |
|--------|-------------|
| **Storage** | PostgreSQL database (`trades`, `orders`, `positions` tables) |
| **Source** | Order confirmations and trade reports from venues |
| **Reliability** | High - persisted after venue acknowledgment |
| **Auditability** | Full - every record has timestamps and venue references |
| **Use in Recaps** | Primary metric for all counts and calculations |

**Key Canonical Metrics:**
- `total_orders`: Count of orders persisted in database
- `filled_orders`: Count of orders with `status = 'filled'`
- `total_volume`: Sum of `filled_qty` across all filled orders
- `realized_pnl`: Calculated from position closes
- `unrealized_pnl`: Mark-to-market on open positions

### Telemetry Events

Telemetry provides real-time visibility but is **explicitly non-audited**.

| Aspect | Description |
|--------|-------------|
| **Storage** | Redis streams, InfluxDB time-series |
| **Source** | WebSocket events, order book updates |
| **Reliability** | Best-effort - may have gaps during network issues |
| **Auditability** | None - used for monitoring only |
| **Use in Recaps** | Advisory comparison only |

**Key Telemetry Metrics:**
- `telemetry_orders_seen`: Orders observed via WebSocket
- `telemetry_fills_seen`: Fill events received
- `telemetry_volume_estimated`: Volume calculated from fill events

### Critical Distinction

```
┌─────────────────────────────────────────────────────────────┐
│  CANONICAL (Audited)          TELEMETRY (Non-Audited)       │
├─────────────────────────────────────────────────────────────┤
│  • Database records           • Real-time streams           │
│  • Venue-confirmed            • Best-effort delivery        │
│  • Used for P&L calculations  • Used for monitoring         │
│  • Regulatory compliant       • May have gaps               │
│  • Source of truth            • Advisory only               │
└─────────────────────────────────────────────────────────────┘
```

**Rule**: When telemetry and canonical counts differ, **canonical wins**. Telemetry discrepancies are logged as warnings but never override database records.

---

## Reconciliation System

The reconciliation block compares canonical and telemetry metrics to detect data quality issues.

### Reconciliation States

| State | Threshold | Meaning | Action Required |
|-------|-----------|---------|-----------------|
| **OK** | < 1% difference | Data quality acceptable | None |
| **WARN** | 1-5% difference | Minor discrepancy detected | Review logs |
| **FAIL** | > 5% difference | Significant data loss | Investigate immediately |

### Threshold Configuration

```yaml
reconciliation:
  thresholds:
    order_count:
      warn: 0.01    # 1% difference triggers WARN
      fail: 0.05    # 5% difference triggers FAIL
    fill_count:
      warn: 0.01
      fail: 0.05
    volume:
      warn: 0.01
      fail: 0.05
    pnl:
      warn: 0.005   # 0.5% for P&L (stricter)
      fail: 0.02    # 2% for P&L
```

### Reconciliation Block Output

```json
{
  "reconciliation": {
    "status": "OK",
    "checks": {
      "order_count": {
        "canonical": 150,
        "telemetry": 148,
        "difference_pct": 1.33,
        "status": "WARN"
      },
      "fill_count": {
        "canonical": 142,
        "telemetry": 142,
        "difference_pct": 0.0,
        "status": "OK"
      },
      "volume": {
        "canonical": 1250000.50,
        "telemetry": 1249875.25,
        "difference_pct": 0.01,
        "status": "OK"
      }
    }
  }
}
```

### Interpreting Reconciliation Results

**OK State:**
- All metrics within acceptable tolerance
- Session data integrity confirmed
- No action required

**WARN State:**
- Minor discrepancies detected
- Likely causes:
  - Network hiccups during session
  - Late-arriving telemetry events
  - Clock skew between systems
- Action: Review session logs for anomalies

**FAIL State:**
- Significant data quality issues
- Likely causes:
  - Extended network outage
  - Venue API issues
  - Database write failures
  - Critical bug in order processing
- Action: Immediate investigation required
  - Check venue API status
  - Review error logs
  - Verify database connectivity
  - Consider session rollback if live trading

---

## Venue Provenance in Recaps

Venue provenance tracks the origin and context of all trading activity.

### Provenance Fields

| Field | Description | Example |
|-------|-------------|---------|
| `venue_id` | Unique venue identifier | `bybit`, `binance`, `okx` |
| `venue_type` | Trading environment type | `live`, `demo`, `paper` |
| `account_id` | Venue-specific account | `subaccount_001` |
| `api_key_id` | API key identifier (masked) | `bb_***_prod` |
| `session_id` | Unique session identifier | `sess_20260301_001` |

### Venue-Specific Validation

Each venue has specific validation rules that are checked during recap generation:

#### Bybit
- Demo mode restrictions enforced
- Testnet vs mainnet validation
- API key permissions verified

#### Binance
- Spot vs futures account segregation
- Testnet flag verification
- Trading pair whitelist checks

#### OKX
- Demo trading account validation
- Paper trading mode checks
- Subaccount isolation verified

### Provenance in Recap Output

```json
{
  "venue_provenance": {
    "venue_id": "bybit",
    "venue_type": "demo",
    "account_id": "demo_account_001",
    "api_key_id": "bb_demo_***",
    "session_id": "sess_20260301_001",
    "validation": {
      "demo_mode_verified": true,
      "testnet_flag": true,
      "api_permissions": ["read", "trade"],
      "restrictions": {
        "max_order_size": 100000,
        "max_position_size": 500000,
        "allowed_symbols": ["BTCUSDT", "ETHUSDT"]
      }
    }
  }
}
```

---

## Bybit Demo Mode Validation

Bybit demo mode has specific constraints that are validated during recap generation.

### Demo Mode Constraints

| Constraint | Value | Validation |
|------------|-------|------------|
| **Max Order Size** | 100,000 USDT | Reject orders exceeding limit |
| **Max Position Size** | 500,000 USDT | Reject positions exceeding limit |
| **Allowed Symbols** | Configured whitelist | Reject non-whitelisted pairs |
| **Trading Hours** | 24/7 (no restrictions) | N/A |
| **Leverage Limits** | Venue-defined | Check against account settings |

### Validation Checks

1. **Order Size Validation**
   ```python
   if order.notional_value > DEMO_MAX_ORDER_SIZE:
       log_warning(f"Order {order.id} exceeds demo max size")
       mark_for_review()
   ```

2. **Position Limit Validation**
   ```python
   if position.total_notional > DEMO_MAX_POSITION_SIZE:
       log_error(f"Position {position.id} exceeds demo limit")
       trigger_position_review()
   ```

3. **Symbol Whitelist Validation**
   ```python
   if order.symbol not in DEMO_ALLOWED_SYMBOLS:
       log_error(f"Symbol {order.symbol} not in demo whitelist")
       reject_order()
   ```

### Demo Mode Recap Indicators

```json
{
  "bybit_demo_validation": {
    "mode": "demo",
    "testnet": true,
    "constraints_applied": true,
    "violations": [],
    "warnings": [
      {
        "type": "order_size",
        "order_id": "ord_12345",
        "message": "Order near max size limit (95% of limit)"
      }
    ]
  }
}
```

### Demo vs Live Detection

The recap system automatically detects trading mode:

```python
def detect_bybit_mode(api_key, api_secret):
    """
    Detect if Bybit credentials are for demo/testnet or live.
    Returns: 'demo' | 'live'
    """
    # Testnet API keys start with specific prefixes
    if api_key.startswith('KxH'):
        return 'demo'  # Testnet
    
    # Check API endpoint response
    response = bybit_client.get_api_key_info()
    if response['is_testnet']:
        return 'demo'
    
    return 'live'
```

---

## Troubleshooting Guide

### Common Issues and Resolutions

#### Issue: High Telemetry Discrepancy (WARN/FAIL)

**Symptoms:**
- Reconciliation shows >1% difference between canonical and telemetry
- Missing events in telemetry streams

**Diagnosis:**
```bash
# Check Redis stream health
redis-cli XLEN telemetry:orders
redis-cli XLEN telemetry:fills

# Check for consumer group lag
redis-cli XINFO GROUPS telemetry:orders

# Review InfluxDB connection
influx ping
```

**Resolution:**
1. Check network connectivity to Redis/InfluxDB
2. Verify telemetry consumer is running
3. Restart telemetry consumer if lag detected
4. Review logs for dropped events

#### Issue: Venue API Errors During Recap

**Symptoms:**
- Recap generation fails with venue API errors
- Missing order/position data

**Diagnosis:**
```bash
# Check venue API status
curl https://api.bybit.com/v5/market/time
curl https://api.binance.com/api/v3/ping

# Review API rate limits
redis-cli HGET venue:bybit:rate_limit remaining
```

**Resolution:**
1. Check venue status page for outages
2. Verify API key permissions
3. Wait for rate limit reset if exceeded
4. Retry recap generation with backoff

#### Issue: Demo Mode Validation Failures

**Symptoms:**
- Orders rejected for exceeding demo limits
- Recap shows constraint violations

**Diagnosis:**
```bash
# Check current demo constraints
cat config/bybit_demo_constraints.yaml

# Review recent orders for violations
psql -c "SELECT * FROM orders WHERE venue = 'bybit' AND created_at > NOW() - INTERVAL '1 hour'"
```

**Resolution:**
1. Verify trading mode (demo vs live)
2. Adjust order sizes to comply with limits
3. Update symbol whitelist if needed
4. Contact venue support if limits need adjustment

#### Issue: Database Connectivity During Recap

**Symptoms:**
- Recap generation times out
- Database connection errors

**Diagnosis:**
```bash
# Check PostgreSQL connectivity
psql -c "SELECT 1"

# Check connection pool status
redis-cli HGET db:connection_pool active_connections

# Review slow queries
psql -c "SELECT * FROM pg_stat_activity WHERE state = 'active'"
```

**Resolution:**
1. Verify PostgreSQL is running
2. Check connection pool limits
3. Kill long-running queries if blocking
4. Restart connection pool if exhausted

### Debug Commands

```bash
# Generate manual recap for specific session
python scripts/generate_recap.py --session-id sess_20260301_001 --verbose

# Check reconciliation status
python scripts/check_reconciliation.py --session-id sess_20260301_001

# Validate venue constraints
python scripts/validate_venue_constraints.py --venue bybit --mode demo

# Review telemetry gaps
python scripts/analyze_telemetry_gaps.py --start-time 2026-03-01T00:00:00Z --end-time 2026-03-01T23:59:59Z
```

---

## Example Recap Output

Below is a complete example of a recap output with explanations.

```json
{
  "recap": {
    "metadata": {
      "session_id": "sess_20260301_001",
      "generated_at": "2026-03-01T23:59:59Z",
      "session_start": "2026-03-01T00:00:00Z",
      "session_end": "2026-03-01T23:59:59Z",
      "duration_hours": 24
    },
    
    "venue_provenance": {
      "venue_id": "bybit",
      "venue_type": "demo",
      "account_id": "demo_account_001",
      "api_key_id": "bb_demo_***",
      "session_id": "sess_20260301_001",
      "validation": {
        "demo_mode_verified": true,
        "testnet_flag": true,
        "api_permissions": ["read", "trade"],
        "restrictions": {
          "max_order_size": 100000,
          "max_position_size": 500000,
          "allowed_symbols": ["BTCUSDT", "ETHUSDT"]
        }
      }
    },
    
    "canonical_metrics": {
      "orders": {
        "total": 150,
        "filled": 142,
        "cancelled": 5,
        "rejected": 3,
        "fill_rate_pct": 94.67
      },
      "trades": {
        "total_count": 142,
        "total_volume": 1250000.50,
        "avg_trade_size": 8802.82,
        "largest_trade": 50000.00,
        "smallest_trade": 100.00
      },
      "positions": {
        "opened": 12,
        "closed": 10,
        "open_at_end": 2,
        "avg_position_size": 62500.00
      },
      "pnl": {
        "realized": 1250.75,
        "unrealized": 325.50,
        "total": 1576.25,
        "return_pct": 0.13
      }
    },
    
    "telemetry_metrics": {
      "orders_seen": 148,
      "fills_seen": 142,
      "volume_estimated": 1249875.25,
      "events_processed": 15234,
      "events_dropped": 12
    },
    
    "reconciliation": {
      "status": "WARN",
      "overall_health": "ACCEPTABLE",
      "checks": {
        "order_count": {
          "canonical": 150,
          "telemetry": 148,
          "difference": 2,
          "difference_pct": 1.33,
          "status": "WARN",
          "thresholds": {
            "warn": 1.0,
            "fail": 5.0
          }
        },
        "fill_count": {
          "canonical": 142,
          "telemetry": 142,
          "difference": 0,
          "difference_pct": 0.0,
          "status": "OK",
          "thresholds": {
            "warn": 1.0,
            "fail": 5.0
          }
        },
        "volume": {
          "canonical": 1250000.50,
          "telemetry": 1249875.25,
          "difference": 125.25,
          "difference_pct": 0.01,
          "status": "OK",
          "thresholds": {
            "warn": 1.0,
            "fail": 5.0
          }
        },
        "pnl": {
          "canonical": 1576.25,
          "telemetry": 1576.10,
          "difference": 0.15,
          "difference_pct": 0.01,
          "status": "OK",
          "thresholds": {
            "warn": 0.5,
            "fail": 2.0
          }
        }
      },
      "warnings": [
        {
          "check": "order_count",
          "message": "Telemetry missed 2 orders (1.33% difference)",
          "severity": "low",
          "recommended_action": "Review telemetry consumer logs for gaps"
        }
      ]
    },
    
    "bybit_demo_validation": {
      "mode": "demo",
      "testnet": true,
      "constraints_applied": true,
      "violations": [],
      "warnings": [
        {
          "type": "order_size",
          "order_id": "ord_67890",
          "message": "Order at 95% of max size limit",
          "timestamp": "2026-03-01T14:23:45Z"
        }
      ],
      "constraint_summary": {
        "max_order_size_violations": 0,
        "max_position_size_violations": 0,
        "symbol_whitelist_violations": 0
      }
    },
    
    "summary": {
      "session_health": "HEALTHY",
      "data_quality": "ACCEPTABLE",
      "trading_activity": "ACTIVE",
      "recommendations": [
        "Minor telemetry gaps detected - review consumer health",
        "One order approached demo size limit - consider position sizing",
        "Overall session completed successfully"
      ]
    }
  }
}
```

### Explanation of Key Sections

**Metadata**: Session identification and timing information

**Venue Provenance**: Complete context about where and how trading occurred, including demo mode verification

**Canonical Metrics**: The authoritative record of all trading activity from the database

**Telemetry Metrics**: Real-time event counts for comparison (advisory only)

**Reconciliation**: Automated comparison with status indicators and thresholds

**Bybit Demo Validation**: Venue-specific constraint checks and violations

**Summary**: Human-readable assessment of session health and recommendations

---

## Related Documentation

- [Bybit Demo Routing](bybit-demo-routing.md) - Demo mode configuration
- [Trade History Recap](trade-history-recap.md) - Historical recap generation
- [Incident Response](incident_response.md) - Handling recap failures
- [Paper Trading Operations](paper-trading-operations.md) - Paper trading validation

---

## Changelog

| Date | Version | Changes |
|------|---------|---------|
| 2026-03-01 | 1.0.0 | Initial runbook creation for ST-VENUE-001 |
