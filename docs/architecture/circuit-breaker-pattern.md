# Circuit Breaker Pattern Architecture

## Overview

The circuit breaker pattern is a resilience mechanism that prevents cascading failures when calling external services. It monitors failure rates and temporarily blocks calls when a service is failing, allowing it time to recover.

## Implementation

### Core Components

#### CircuitBreaker Class

Located in `src/common/circuit_breaker.py`, the `CircuitBreaker` class provides:

- **Three states**: CLOSED (normal), OPEN (failing fast), HALF_OPEN (testing recovery)
- **Configurable thresholds**: failure_threshold, timeout_seconds, half_open_max_calls
- **Thread-safe operations**: Uses RLock for concurrent access
- **Multiple usage patterns**: `call()` wrapper, `can_execute()` manual control, context manager

#### CircuitBreakerRegistry

Singleton registry for managing multiple circuit breakers:

- Centralized management of circuit breakers by name
- Global operations: reset_all, force_open_all, force_close_all
- Monitoring: get_all_states for health dashboards

### State Machine

```
                    failure_threshold reached
        ┌──────────────────────────────────────────┐
        │                                          ▼
   ┌─────────┐      timeout elapsed      ┌───────────┐
   │  CLOSED │◄──────────────────────────│ HALF_OPEN │
   └────┬────┘                           └─────┬─────┘
        │                                        │
        │ record_success()              record_success()
        │ (half_open_max_calls met)              │
        │                               record_failure()
        ▼                                        │
   ┌─────────┐                                   │
   │  OPEN   │◄──────────────────────────────────┘
   └─────────┘     any failure in HALF_OPEN
```

### Configuration

Default configuration:
- `failure_threshold`: 5 failures before opening
- `timeout_seconds`: 60 seconds before trying half-open
- `half_open_max_calls`: 3 calls allowed in half-open state

### Usage Patterns

#### Pattern 1: Using call() wrapper

```python
from common.circuit_breaker import CircuitBreaker, CircuitBreakerOpen

cb = CircuitBreaker(failure_threshold=5, name="redis")

try:
    result = cb.call(redis_client.get, "key")
except CircuitBreakerOpen:
    # Circuit is open - use fallback
    result = get_from_cache("key")
except RedisError as e:
    # Other Redis error - already recorded as failure
    result = None
```

#### Pattern 2: Manual control

```python
if cb.can_execute():
    try:
        result = external_service()
        cb.record_success()
    except Exception as e:
        cb.record_failure(str(e))
        raise
else:
    # Circuit is open
    raise ServiceUnavailable()
```

#### Pattern 3: Context manager

```python
try:
    with cb:
        result = external_service()
except CircuitBreakerOpen:
    # Circuit is open
    result = fallback_value
```

## Integration with Paper Trading

### PaperPositionTracker Integration

The `PaperTracker` class in `src/portfolio/paper_tracker.py` uses circuit breaker protection for Redis operations:

```python
self._redis_circuit = CircuitBreaker(
    failure_threshold=5,
    timeout_seconds=60.0,
    half_open_max_calls=3,
    name=f"redis_{portfolio_id}",
)
```

### Protected Operations

1. **get_position(symbol)**: Fetches position from Redis
   - On CircuitBreakerOpen: Returns from memory cache
   - On other errors: Returns from memory cache

2. **save_position(symbol, position)**: Saves position to Redis
   - Always saves to memory first
   - On CircuitBreakerOpen: Logs warning, returns False
   - On other errors: Logs error, returns False

3. **update_position(symbol, updates)**: Updates position in Redis
   - Always updates memory first
   - On CircuitBreakerOpen: Logs warning, returns memory value
   - On other errors: Logs error, returns memory value

4. **delete_position(symbol)**: Deletes position from Redis
   - Always deletes from memory first
   - On CircuitBreakerOpen: Logs warning, returns False
   - On other errors: Logs error, returns False

### Fallback Strategy

When the circuit breaker is open:
1. Operations continue using in-memory state
2. Warnings are logged for monitoring
3. Redis health metrics are updated
4. Alerts can be triggered via `on_redis_failure()`

## Monitoring

### Metrics

The circuit breaker tracks:
- `failure_count`: Total failures recorded
- `success_count`: Total successes recorded
- `rejection_count`: Calls rejected due to open circuit
- `state_transition_count`: Number of state changes
- `consecutive_successes`: For half-open recovery detection
- `consecutive_failures`: For threshold detection

### Health Endpoints

```python
# Get circuit breaker state
cb.get_state_dict()

# Returns:
{
    "name": "redis_paper_trading",
    "state": "CLOSED",
    "failure_threshold": 5,
    "timeout_seconds": 60.0,
    "half_open_max_calls": 3,
    "last_error": None,
    "metrics": {
        "failure_count": 0,
        "success_count": 42,
        "rejection_count": 0,
        ...
    }
}
```

### Alerting

Integration with alert system via `PaperTracker.on_redis_failure()`:
- Circuit breaker state changes trigger alerts
- High error rates trigger alerts
- Recovery (CLOSED state) is logged at INFO level

## Testing

### Unit Tests

Comprehensive test suite in `tests/test_common/test_circuit_breaker.py`:
- State machine transitions
- Thread safety
- Configuration options
- Registry operations
- Context manager usage

Run tests:
```bash
pytest tests/test_common/test_circuit_breaker.py -v
```

### Coverage

Current coverage: 97%

## Best Practices

1. **Always have fallbacks**: When circuit is open, have a fallback strategy (cache, memory, degraded mode)

2. **Log state transitions**: State changes should be visible in logs for debugging

3. **Monitor metrics**: Track rejection rates and state transitions in dashboards

4. **Tune thresholds**: Adjust failure_threshold and timeout_seconds based on service characteristics

5. **Use descriptive names**: Circuit breaker names should identify the protected service

6. **Test failure scenarios**: Include circuit breaker open scenarios in integration tests

## Future Enhancements

1. **Adaptive timeouts**: Adjust timeout based on historical recovery times
2. **Sliding window**: Use time-based sliding window for failure counting
3. **Per-exception configuration**: Different thresholds for different exception types
4. **Metrics export**: Integration with Prometheus/Grafana
5. **Distributed circuit breaker**: Coordination across multiple instances

## References

- [Circuit Breaker Pattern - Martin Fowler](https://martinfowler.com/bliki/CircuitBreaker.html)
- [Release It! - Michael Nygard](https://pragprog.com/titles/mnee2/release-it-second-edition/)
