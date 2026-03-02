"""Load Balancer for High Availability Infrastructure (NFR-006)."""

import logging
import random
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from types import TracebackType
from typing import Any

from src.infrastructure.ha.failover import InstanceInfo
from src.infrastructure.ha.health_check import HealthStatus

logger = logging.getLogger(__name__)


class LoadBalancingStrategy(Enum):
    ROUND_ROBIN = "round_robin"
    WEIGHTED_ROUND_ROBIN = "weighted_round_robin"
    LEAST_CONNECTIONS = "least_connections"
    RANDOM = "random"


@dataclass
class ConnectionStats:
    active_connections: int = 0
    total_connections: int = 0
    total_requests: int = 0
    failed_requests: int = 0
    total_response_time_ms: float = 0.0
    last_request_time: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "active_connections": self.active_connections,
            "total_connections": self.total_connections,
            "total_requests": self.total_requests,
            "failed_requests": self.failed_requests,
            "avg_response_time_ms": (
                self.total_response_time_ms / self.total_requests
                if self.total_requests > 0
                else 0
            ),
            "last_request_time": (
                self.last_request_time.isoformat() if self.last_request_time else None
            ),
        }


@dataclass
class LoadBalancerConfig:
    strategy: LoadBalancingStrategy = LoadBalancingStrategy.ROUND_ROBIN
    health_check_interval_seconds: float = 10.0
    max_connections_per_instance: int = 1000
    sticky_sessions: bool = False


class LoadBalancer:
    def __init__(self, config: LoadBalancerConfig | None = None):
        self.config = config or LoadBalancerConfig()
        self._instances: dict[str, InstanceInfo] = {}
        self._connection_stats: dict[str, ConnectionStats] = defaultdict(
            ConnectionStats
        )
        self._sticky_sessions: dict[str, str] = {}
        self._round_robin_index = 0

    def register_instance(self, instance: InstanceInfo) -> None:
        self._instances[instance.id] = instance
        self._connection_stats[instance.id] = ConnectionStats()
        logger.info(f"Registered instance with load balancer: {instance.id}")

    def unregister_instance(self, instance_id: str) -> bool:
        if instance_id in self._instances:
            del self._instances[instance_id]
            if instance_id in self._connection_stats:
                del self._connection_stats[instance_id]
            return True
        return False

    def update_instance_health(self, instance_id: str, status: HealthStatus) -> None:
        if instance_id in self._instances:
            self._instances[instance_id].health_status = status
            self._instances[instance_id].last_check = datetime.now(UTC)

    def select_instance(self, session_id: str | None = None) -> InstanceInfo | None:
        if (
            self.config.sticky_sessions
            and session_id
            and session_id in self._sticky_sessions
        ):
            instance = self._instances.get(self._sticky_sessions[session_id])
            if instance and instance.health_status == HealthStatus.HEALTHY:
                return instance
            del self._sticky_sessions[session_id]
        healthy = self._get_healthy_instances()
        if not healthy:
            return None
        selected = self._apply_strategy(healthy)
        if selected and self.config.sticky_sessions and session_id:
            self._sticky_sessions[session_id] = selected.id
        return selected

    def _get_healthy_instances(self) -> list[InstanceInfo]:
        return [
            i
            for i in self._instances.values()
            if i.health_status == HealthStatus.HEALTHY
            and self._connection_stats[i.id].active_connections
            < self.config.max_connections_per_instance
        ]

    def _apply_strategy(self, instances: list[InstanceInfo]) -> InstanceInfo | None:
        if not instances:
            return None
        if self.config.strategy == LoadBalancingStrategy.ROUND_ROBIN:
            self._round_robin_index = (self._round_robin_index + 1) % len(instances)
            return instances[self._round_robin_index]
        elif self.config.strategy == LoadBalancingStrategy.LEAST_CONNECTIONS:
            return min(
                instances, key=lambda x: self._connection_stats[x.id].active_connections
            )
        elif self.config.strategy == LoadBalancingStrategy.RANDOM:
            return random.choice(instances)
        return instances[0]

    def acquire_connection(self, instance_id: str) -> bool:
        if instance_id not in self._instances:
            return False
        stats = self._connection_stats[instance_id]
        if stats.active_connections >= self.config.max_connections_per_instance:
            return False
        stats.active_connections += 1
        stats.total_connections += 1
        return True

    def release_connection(self, instance_id: str) -> None:
        if (
            instance_id in self._connection_stats
            and self._connection_stats[instance_id].active_connections > 0
        ):
            self._connection_stats[instance_id].active_connections -= 1

    def record_request(
        self, instance_id: str, success: bool, response_time_ms: float
    ) -> None:
        if instance_id not in self._connection_stats:
            return
        stats = self._connection_stats[instance_id]
        stats.total_requests += 1
        stats.total_response_time_ms += response_time_ms
        stats.last_request_time = datetime.now(UTC)
        if not success:
            stats.failed_requests += 1

    def get_stats(self) -> dict[str, Any]:
        return {
            "strategy": self.config.strategy.value,
            "total_instances": len(self._instances),
            "healthy_instances": len(self._get_healthy_instances()),
            "instances": {
                id: {
                    "info": inst.to_dict(),
                    "stats": self._connection_stats[id].to_dict(),
                }
                for id, inst in self._instances.items()
            },
            "sticky_sessions": len(self._sticky_sessions),
        }


class ConnectionContext:
    """Context manager for load-balanced connections."""

    def __init__(
        self, load_balancer: LoadBalancer, session_id: str | None = None
    ) -> None:
        self._load_balancer = load_balancer
        self._session_id = session_id
        self._instance: InstanceInfo | None = None
        self._start_time: float = 0.0
        self._success: bool = False

    async def __aenter__(self) -> InstanceInfo | None:
        self._instance = self._load_balancer.select_instance(self._session_id)
        if self._instance and self._load_balancer.acquire_connection(self._instance.id):
            self._start_time = time.perf_counter()
            return self._instance
        return None

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool:
        if self._instance:
            response_time_ms = (time.perf_counter() - self._start_time) * 1000
            success = exc_type is None
            self._load_balancer.record_request(
                self._instance.id, success, response_time_ms
            )
            self._load_balancer.release_connection(self._instance.id)
        return False

    def mark_success(self) -> None:
        self._success = True
