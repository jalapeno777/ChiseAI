"""Paper Canary Planning & Gates module.

This module implements the paper canary deployment system with:
- Canary deployment at 10% of paper portfolio allocation
- Gate criteria checks (max 5% drawdown, min 55% win rate, 7-day duration)
- Automatic rollback on gate failure
- 15-minute monitoring schedule
- Integration with promotion packet workflow

Example usage:
    from execution.canary import (
        CanaryDeployment,
        GateCriteria,
        create_canary_deployment,
        GateEvaluator,
        RollbackHandler,
        CanaryMonitor,
    )

    # Create a canary deployment
    canary = create_canary_deployment(
        canary_id="canary-001",
        strategy_id="strategy-v2",
        champion_strategy_id="strategy-v1",
        allocation_pct=10.0,
    )

    # Start the canary
    canary.start(initial_equity=10000.0)

    # Set up monitoring
    monitor = CanaryMonitor()
    monitor.register_canary(canary)
    await monitor.start()
"""

from execution.canary.gate_evaluator import GateEvaluator
from execution.canary.models import (
    CanaryDeployment,
    CanaryMetrics,
    CanaryStatus,
    GateCheck,
    GateCheckResult,
    GateCriteria,
    create_canary_deployment,
)
from execution.canary.monitor import (
    CanaryMonitor,
    MonitoringCheck,
    create_canary_monitor,
)
from execution.canary.promotion import (
    PromotionEvidence,
    PromotionPacket,
    PromotionPacketGenerator,
    create_promotion_packet_generator,
)
from execution.canary.rollback import (
    RollbackHandler,
    RollbackResult,
    RollbackStatus,
    create_rollback_handler,
)
from execution.canary.storage import (
    CanaryRecord,
    CanaryStorage,
    InMemoryCanaryStorage,
    create_canary_storage,
)

__all__ = [
    # Models
    "CanaryDeployment",
    "CanaryMetrics",
    "CanaryStatus",
    "GateCheck",
    "GateCheckResult",
    "GateCriteria",
    "create_canary_deployment",
    # Gate Evaluator
    "GateEvaluator",
    # Rollback
    "RollbackHandler",
    "RollbackResult",
    "RollbackStatus",
    "create_rollback_handler",
    # Monitor
    "CanaryMonitor",
    "MonitoringCheck",
    "create_canary_monitor",
    # Storage
    "CanaryRecord",
    "CanaryStorage",
    "InMemoryCanaryStorage",
    "create_canary_storage",
    # Promotion
    "PromotionEvidence",
    "PromotionPacket",
    "PromotionPacketGenerator",
    "create_promotion_packet_generator",
]
