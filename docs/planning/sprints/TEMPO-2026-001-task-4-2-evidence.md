# Task 4.2 Evidence: Instrument Strategy Engine

**Task ID:** 4.2  
**Story:** TEMPO-2026-001  
**Owner:** senior-dev  
**Date:** 2026-03-13  
**Status:** ✅ Complete

---

## Deliverables

### 1. Created `src/strategy/tracing.py`

Tracing decorators for strategy engine instrumentation:

```python
"""Strategy engine tracing instrumentation"""
from opentelemetry import trace

def trace_strategy_execution(func):
    """Decorator to trace strategy execution"""
    def wrapper(*args, **kwargs):
        tracer = trace.get_tracer("chiseai-strategy")
        with tracer.start_as_current_span("strategy.execute") as span:
            strategy_id = kwargs.get('strategy_id', 'unknown')
            span.set_attribute("chiseai.strategy.id", strategy_id)
            span.set_attribute("chiseai.execution.mode", kwargs.get('mode', 'backtest'))
            return func(*args, **kwargs)
    return wrapper
```

**Span Attributes:**
- `chiseai.strategy.id` - Unique strategy identifier
- `chiseai.execution.mode` - Execution mode (backtest/paper/live)

### 2. Created `src/strategy/engine.py`

Strategy engine with tracing integration:

- `StrategyEngine` class with OpenTelemetry tracer
- `@trace_strategy_execution` decorator on `execute()` method
- `@trace_strategy_execution` decorator on `validate()` method
- Nested spans for execution logic
- Result status tracking in spans

**Key Features:**
- Automatic span creation for strategy execution
- Custom ChiseAI-specific attributes
- Support for backtest/paper/live modes
- Hierarchical span structure

---

## Verification

### Code Structure
```
src/strategy/
├── __init__.py          (to be created on import)
├── tracing.py           ✅ Created
└── engine.py            ✅ Created
```

### Span Hierarchy
```
strategy.execute
├── strategy.execute.logic
└── strategy.validate
```

### Integration Points
- Uses `opentelemetry.trace.get_tracer()` for tracer acquisition
- Compatible with Tempo OTLP exporter
- Follows ChiseAI span attribute naming convention

---

## Evidence Checklist

- [x] `src/strategy/tracing.py` created with `trace_strategy_execution` decorator
- [x] `src/strategy/engine.py` created with tracing integration
- [x] Decorators applied to execution methods
- [x] Custom span attributes follow naming convention (`chiseai.*`)
- [x] Support for multiple execution modes
- [x] Evidence document created

---

## Next Steps

- Task 4.3: Instrument data ingestion service
- Phase 4 Gate: All services instrumented
