"""Strategy engine tracing instrumentation"""

from opentelemetry import trace


def trace_strategy_execution(func):
    """Decorator to trace strategy execution"""

    def wrapper(*args, **kwargs):
        tracer = trace.get_tracer("chiseai-strategy")
        with tracer.start_as_current_span("strategy.execute") as span:
            strategy_id = kwargs.get("strategy_id", "unknown")
            span.set_attribute("chiseai.strategy.id", strategy_id)
            span.set_attribute("chiseai.execution.mode", kwargs.get("mode", "backtest"))
            return func(*args, **kwargs)

    return wrapper
