# ErrorRateTracker Integration Points Analysis

**Story ID:** ST-WIRE-ERROR-RATE-TRACKER  
**Created:** 2026-04-12  
**Status:** Research Complete

## Overview

This document catalogs all integration points where `ErrorRateTracker` (`src/execution/alerts/error_rate_integration.py`) should record operations to enable error rate monitoring by category. Each integration point specifies the file:line, operation type, recommended `ErrorCategory` mapping, and success/failure classification rules.

---

## ErrorRateTracker API Reference

### Core Class

```python
class ErrorRateTracker:
    REDIS_KEY_PREFIX = "chise:paper:metrics:error_rate"

    def record_operation(
        self,
        category: ErrorCategory,
        success: bool = True,
        error_details: dict[str, Any] | None = None,
    ) -> ErrorRateSnapshot:
        """Record an operation outcome."""
```

### ErrorCategory Enum

```python
class ErrorCategory(Enum):
    API = "api"          # Exchange API calls, network failures
    VALIDATION = "validation"  # Input validation, signal quality gates
    EXECUTION = "execution"   # Order execution, fill simulation
    DATABASE = "database"     # Redis, persistence layer
    NETWORK = "network"       # Connectivity, timeouts
    UNKNOWN = "unknown"       # Catch-all for unclassified errors
```

### Alert Integration

```python
class ErrorRateAlertIntegration:
    async def check_and_alert(
        self, category: ErrorCategory | None = None
    ) -> dict[str, Any]:
        """Check rates and send Discord alerts if thresholds exceeded."""
```

---

## Integration Points

### 1. Orchestrator Order Operations

**File:** `src/execution/paper/orchestrator.py`

#### 1.1 G1_THROTTLE - Per-Symbol Cadence Rejection

| Attribute         | Value                                                                               |
| ----------------- | ----------------------------------------------------------------------------------- |
| **Location**      | `orchestrator.py:720-750`                                                           |
| **Operation**     | Signal throttled by per-symbol cadence                                              |
| **ErrorCategory** | `VALIDATION`                                                                        |
| **Success**       | `False`                                                                             |
| **Trigger**       | `SYMBOL_EVAL_INTERVAL_SECONDS` not elapsed since last signal                        |
| **error_details** | `{ "gate": "G1_THROTTLE", "symbol": signal.token, "reason": "per_symbol_cadence" }` |

**Code Snippet:**

```python
# Line 720-750 in orchestrator.py
async with self._lock:
    self._metrics["trades_rejected"] += 1
    self._metrics["gate_g1_throttle_count"] += 1
# ...
return PaperTradeResult(
    signal=signal,
    status=TradeStatus.REJECTED,
    reject_reason=["Signal throttled by per-symbol cadence"],
    correlation_id=correlation_id,
)
```

#### 1.2 G2_PAPER_KILL - Paper Kill Switch Active

| Attribute         | Value                                                             |
| ----------------- | ----------------------------------------------------------------- |
| **Location**      | `orchestrator.py:754-793`                                         |
| **Operation**     | Paper trading kill switch activated                               |
| **ErrorCategory** | `EXECUTION`                                                       |
| **Success**       | `False`                                                           |
| **Trigger**       | `paper_kill_switch.status.active == True`                         |
| **error_details** | `{ "gate": "G2_PAPER_KILL", "reason": paper_kill_status.reason }` |

#### 1.3 G3_LIVE_KILL - Live Kill Switch Triggered

| Attribute         | Value                                                           |
| ----------------- | --------------------------------------------------------------- |
| **Location**      | `orchestrator.py:796-827`                                       |
| **Operation**     | Live trading kill switch triggered                              |
| **ErrorCategory** | `EXECUTION`                                                     |
| **Success**       | `False`                                                         |
| **Trigger**       | `kill_switch.state.value == "triggered"`                        |
| **error_details** | `{ "gate": "G3_LIVE_KILL", "reason": "kill_switch_triggered" }` |

#### 1.4 G4_NO_PRICE - No Market Price Available

| Attribute         | Value                                                                            |
| ----------------- | -------------------------------------------------------------------------------- |
| **Location**      | `orchestrator.py:856-900`                                                        |
| **Operation**     | Cannot create order - no market price                                            |
| **ErrorCategory** | `VALIDATION`                                                                     |
| **Success**       | `False`                                                                          |
| **Trigger**       | `entry_price is None or entry_price <= 0`                                        |
| **error_details** | `{ "gate": "G4_NO_PRICE", "symbol": signal.token, "reason": "no_market_price" }` |

#### 1.5 G5_RISK_REJECT - Risk Validation Failed

| Attribute         | Value                                                                                    |
| ----------------- | ---------------------------------------------------------------------------------------- |
| **Location**      | `orchestrator.py:1114-1146`                                                              |
| **Operation**     | Risk enforcer rejected signal                                                            |
| **ErrorCategory** | `VALIDATION`                                                                             |
| **Success**       | `False`                                                                                  |
| **Trigger**       | `assessment.approved == False`                                                           |
| **error_details** | `{ "gate": "G5_RISK_REJECT", "violations": [v.message for v in assessment.violations] }` |

#### 1.6 G6_LLM_REJECT - LLM Decision Enhancement Rejection

| Attribute         | Value                                                                                      |
| ----------------- | ------------------------------------------------------------------------------------------ |
| **Location**      | `orchestrator.py:1001-1032`                                                                |
| **Operation**     | LLM enhancer rejected signal (no-go decision)                                              |
| **ErrorCategory** | `VALIDATION`                                                                               |
| **Success**       | `False`                                                                                    |
| **Trigger**       | `enhanced.go_no_go == False`                                                               |
| **error_details** | `{ "gate": "G6_LLM_REJECT", "reason": enhanced.rationale, "provider": enhanced.provider }` |

#### 1.7 G7_SAME_DIR_SKIP - Same Direction Position Skip

| Attribute         | Value                                                                                    |
| ----------------- | ---------------------------------------------------------------------------------------- |
| **Location**      | `orchestrator.py:948-976`                                                                |
| **Operation**     | Signal skipped - already in same direction position                                      |
| **ErrorCategory** | `VALIDATION`                                                                             |
| **Success**       | `True` (skip is not an error)                                                            |
| **Trigger**       | Same symbol, same direction already open                                                 |
| **error_details** | `{ "gate": "G7_SAME_DIR_SKIP", "symbol": signal.token, "side": signal.direction.value }` |

#### 1.8 Successful Order Placement

| Attribute         | Value                                             |
| ----------------- | ------------------------------------------------- |
| **Location**      | `orchestrator.py:process_signal()` → order placed |
| **Operation**     | Order successfully placed                         |
| **ErrorCategory** | `EXECUTION`                                       |
| **Success**       | `True`                                            |
| **Trigger**       | Order created and submitted to `order_simulator`  |

---

### 2. Connector Operations

**File:** `src/execution/connectors/bybit_demo_connector.py`

#### 2.1 place_order - Order Placement

| Attribute         | Value                                                                            |
| ----------------- | -------------------------------------------------------------------------------- |
| **Location**      | `bybit_demo_connector.py:766-989`                                                |
| **Operation**     | Place order via Bybit demo API                                                   |
| **ErrorCategory** | `API`                                                                            |
| **Success**       | `True` if `order.state == OrderState.FILLED` or `OrderState.PENDING`             |
| **Failure**       | `False` if `BybitAPIError` raised or `order.state == REJECTED`                   |
| **error_details** | `{ "order_id": order.order_id, "symbol": symbol, "error_code": exc.error_code }` |

**Code Snippet:**

```python
except BybitAPIError as exc:
    logger.error("DEMO EXECUTION FAILED (API error): %s", exc)
    # ... order rejected ...
    return order  # order.state == REJECTED
```

#### 2.2 cancel_order - Order Cancellation

| Attribute         | Value                                         |
| ----------------- | --------------------------------------------- |
| **Location**      | `bybit_demo_connector.py:1174-1245`           |
| **Operation**     | Cancel order via Bybit demo API               |
| **ErrorCategory** | `API`                                         |
| **Success**       | `True` if order cancelled successfully        |
| **Failure**       | `False` if `BybitAPIError` or other exception |
| **error_details** | `{ "order_id": order_id, "error": str(exc) }` |

#### 2.3 get_market_price - Price Fetch

| Attribute         | Value                                                                      |
| ----------------- | -------------------------------------------------------------------------- |
| **Location**      | `bybit_demo_connector.py:717-764`                                          |
| **Operation**     | Fetch market price from Bybit                                              |
| **ErrorCategory** | `API`                                                                      |
| **Success**       | `True` if price returned                                                   |
| **Failure**       | `False` if `BybitAPIError` or exception                                    |
| **error_details** | `{ "symbol": symbol, "operation": "get_market_price", "error": str(exc) }` |

#### 2.4 get_wallet_balance - Balance Query

| Attribute         | Value                                                      |
| ----------------- | ---------------------------------------------------------- |
| **Location**      | `bybit_demo_connector.py:1321-1389`                        |
| **Operation**     | Fetch wallet balance from Bybit                            |
| **ErrorCategory** | `API`                                                      |
| **Success**       | `True` if balance returned                                 |
| **Failure**       | `False` if `BybitAPIError` or exception                    |
| **error_details** | `{ "operation": "get_wallet_balance", "error": str(exc) }` |

#### 2.5 \_attach_trading_stops - TP/SL Attachment

| Attribute         | Value                                                                             |
| ----------------- | --------------------------------------------------------------------------------- |
| **Location**      | `bybit_demo_connector.py:1083-1173`                                               |
| **Operation**     | Attach take-profit/stop-loss to order                                             |
| **ErrorCategory** | `API`                                                                             |
| **Success**       | `True` if TP/SL attached                                                          |
| **Failure**       | `False` after `max_retries` exhausted                                             |
| **error_details** | `{ "order_id": order_id, "operation": "tp_sl_attach", "error": str(last_error) }` |

---

### 3. Signal Delivery Operations

**File:** `src/execution/signal_delivery/async_pipeline.py`

#### 3.1 deliver - Signal Delivery

| Attribute         | Value                                                                              |
| ----------------- | ---------------------------------------------------------------------------------- |
| **Location**      | `async_pipeline.py:178-278`                                                        |
| **Operation**     | Deliver signal to execution target                                                 |
| **ErrorCategory** | `NETWORK`                                                                          |
| **Success**       | `True` if `DeliveryStatus.DELIVERED`                                               |
| **Failure**       | `False` if `DeliveryStatus.FAILED` or `DeliveryStatus.TIMEOUT`                     |
| **error_details** | `{ "signal_id": signal_id, "status": result.status.value, "error": result.error }` |

#### 3.2 deliver_batch - Batch Delivery

| Attribute           | Value                                    |
| ------------------- | ---------------------------------------- |
| **Location**        | `async_pipeline.py:280-317`              |
| **Operation**       | Deliver multiple signals in batch        |
| **ErrorCategory**   | `NETWORK`                                |
| **Success**         | `True` if all `DeliveryStatus.DELIVERED` |
| **Partial Failure** | Record individually per signal outcome   |

---

### 4. Latency Monitor Operations

**File:** `src/execution/signal_delivery/latency_monitor.py`

#### 4.1 record_stage - Latency Recording

| Attribute         | Value                                                                  |
| ----------------- | ---------------------------------------------------------------------- |
| **Location**      | `latency_monitor.py:232-257`                                           |
| **Operation**     | Record latency for a pipeline stage                                    |
| **ErrorCategory** | `NETWORK` (for slow deliveries)                                        |
| **Success**       | `True` if latency within threshold                                     |
| **Slow**          | `True` if latency exceeds `warning_ms` threshold                       |
| **error_details** | `{ "signal_id": signal_id, "stage": stage, "latency_ms": latency_ms }` |

---

### 5. Throughput Tracker Operations

**File:** `src/execution/signal_delivery/throughput_tracker.py`

#### 5.1 record_signal - Throughput Recording

| Attribute         | Value                                                  |
| ----------------- | ------------------------------------------------------ |
| **Location**      | `throughput_tracker.py:166-200`                        |
| **Operation**     | Record signal delivery for throughput tracking         |
| **ErrorCategory** | `NETWORK`                                              |
| **Success**       | `True` if `success=True` passed                        |
| **Failure**       | `False` if `success=False`                             |
| **error_details** | `{ "signal_id": signal_id, "latency_ms": latency_ms }` |

---

## Success/Failure Classification Rules

### Order Operations (Orchestrator)

| Gate             | Classification     | Reason                                   |
| ---------------- | ------------------ | ---------------------------------------- |
| G1_THROTTLE      | **Failure**        | Validation rejected - per-symbol cadence |
| G2_PAPER_KILL    | **Failure**        | Execution blocked - paper kill active    |
| G3_LIVE_KILL     | **Failure**        | Execution blocked - live kill triggered  |
| G4_NO_PRICE      | **Failure**        | Validation rejected - no market price    |
| G5_RISK_REJECT   | **Failure**        | Validation rejected - risk violation     |
| G6_LLM_REJECT    | **Failure**        | Validation rejected - LLM no-go          |
| G7_SAME_DIR_SKIP | **Success** (skip) | Not an error, position already exists    |
| Order Placed     | **Success**        | Order created and submitted              |

### Connector Operations (BybitDemoConnector)

| Operation          | Success Condition                  | Failure Condition                             |
| ------------------ | ---------------------------------- | --------------------------------------------- |
| place_order        | `order.state in (FILLED, PENDING)` | Exception raised or `order.state == REJECTED` |
| cancel_order       | `True` (bool return)               | `False` (bool return)                         |
| get_market_price   | Price returned > 0                 | Exception or None/0                           |
| get_wallet_balance | Balance dict returned              | Exception raised                              |
| TP/SL attach       | All retries succeed                | All retries exhausted                         |

### Signal Delivery Operations

| Status      | Classification                 |
| ----------- | ------------------------------ |
| `DELIVERED` | **Success**                    |
| `FAILED`    | **Failure**                    |
| `TIMEOUT`   | **Failure**                    |
| `RETRYING`  | In progress (don't record yet) |

---

## Proposed Wiring Pattern

### Pattern 1: Decorator-Based Integration (Recommended)

```python
# src/execution/alerts/error_rate_decorators.py
from functools import wraps
from execution.alerts.error_rate_integration import ErrorRateTracker, ErrorCategory

# Global tracker instance (singleton)
_tracker: ErrorRateTracker | None = None

def get_tracker() -> ErrorRateTracker:
    global _tracker
    if _tracker is None:
        _tracker = ErrorRateTracker()
    return _tracker

def track_operation(category: ErrorCategory):
    """Decorator to track operation success/failure."""
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            tracker = get_tracker()
            success = True
            error_details = None
            try:
                result = await func(*args, **kwargs)
                # Check result for failure indicators
                if hasattr(result, 'state') and result.state.name == 'REJECTED':
                    success = False
                    error_details = {"order_id": getattr(result, 'order_id', None)}
                elif hasattr(result, 'is_success'):
                    success = result.is_success
                return result
            except Exception as e:
                success = False
                error_details = {"error": str(e), "operation": func.__name__}
                raise
            finally:
                tracker.record_operation(category, success, error_details)
        return async_wrapper
    return decorator

# Usage in bybit_demo_connector.py:
@track_operation(ErrorCategory.API)
async def place_order(self, symbol, side, order_type, quantity, price=None, ...):
    ...
```

### Pattern 2: Context Manager Integration

```python
# For orchestrator gates
from contextlib import asynccontextmanager

@asynccontextmanager
async def track_signal_processing(signal, gate_name: str, error_category: ErrorCategory):
    tracker = get_tracker()
    success = True
    error_details = {"gate": gate_name, "symbol": signal.token}
    try:
        yield
    except Exception as e:
        success = False
        error_details["error"] = str(e)
        raise
    finally:
        tracker.record_operation(error_category, success, error_details)

# Usage:
async with track_signal_processing(signal, "G5_RISK_REJECT", ErrorCategory.VALIDATION):
    assessment = await self.risk_enforcer.validate_order(...)
```

### Pattern 3: Direct Call Integration

```python
# In orchestrator.py - simplest direct integration
tracker = ErrorRateTracker()

# At each rejection point:
if not assessment.approved:
    tracker.record_operation(
        ErrorCategory.VALIDATION,
        success=False,
        error_details={
            "gate": "G5_RISK_REJECT",
            "violations": [v.message for v in assessment.violations],
            "symbol": signal.token,
        }
    )
```

---

## Redis Key Patterns

| Pattern                                                           | Description                                       |
| ----------------------------------------------------------------- | ------------------------------------------------- |
| `chise:paper:metrics:error_rate:<category>:stats`                 | Hash with total, errors, error_rate, last_updated |
| `chise:paper:metrics:error_rate:<category>:error_log`             | List of last 100 error details                    |
| `chise:paper:metrics:error_rate:<category>:last_alert:<severity>` | Cooldown tracking for alerts                      |

---

## Alert Thresholds

| Threshold                | Default Value | Description                           |
| ------------------------ | ------------- | ------------------------------------- |
| `warning`                | 5.0%          | Warning alert trigger                 |
| `critical`               | 10.0%         | Critical alert trigger                |
| `min_operations`         | 10            | Minimum ops before rate calculated    |
| `alert_cooldown_minutes` | 15            | Minimum time between duplicate alerts |

---

## Evidence of Analysis

| Source File                 | Key Integration Points Identified                               |
| --------------------------- | --------------------------------------------------------------- |
| `error_rate_integration.py` | ErrorRateTracker.record_operation(), ErrorCategory enum         |
| `orchestrator.py`           | G1-G7 rejection paths in process_signal()                       |
| `bybit_demo_connector.py`   | place_order, cancel_order, get_market_price, get_wallet_balance |
| `async_pipeline.py`         | deliver(), DeliveryStatus enum                                  |
| `latency_monitor.py`        | record_stage(), LatencyStage enum                               |
| `throughput_tracker.py`     | record_signal()                                                 |

---

## Next Steps

1. **Implement ErrorRateTracker singleton** with global access pattern
2. **Add decorator/decorator helpers** for common integration patterns
3. **Wire orchestrator rejections** (G1-G7) to tracker
4. **Wire connector operations** (place_order, cancel_order, etc.)
5. **Wire signal delivery** (deliver, deliver_batch)
6. **Verify Redis key writes** with integration tests
7. **Configure Discord alert webhook** for production use
