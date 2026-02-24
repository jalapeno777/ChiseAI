"""Unified High Availability Manager (NFR-006)."""
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from src.infrastructure.ha.failover import (
    FailoverConfig,
    FailoverManager,
    InstanceInfo,
)
from src.infrastructure.ha.health_check import (
    HealthCheckConfig,
    HealthCheckRegistry,
    HealthCheckResult,
)
from src.infrastructure.ha.load_balancer import (
    LoadBalancer,
    LoadBalancerConfig,
    LoadBalancingStrategy,
)
from src.infrastructure.ha.uptime_monitor import (
    UptimeMonitor,
    UptimeMonitorConfig,
    UptimeTarget,
)

logger = logging.getLogger(__name__)

@dataclass
class HAConfig:
    health_check_interval_seconds: float = 30.0
    health_check_timeout_seconds: float = 5.0
    unhealthy_threshold: int = 3
    healthy_threshold: int = 2
    failover_enabled: bool = True
    failover_timeout_seconds: float = 30.0
    auto_failback: bool = True
    failback_delay_seconds: float = 60.0
    load_balancing_strategy: LoadBalancingStrategy = LoadBalancingStrategy.ROUND_ROBIN
    max_connections_per_instance: int = 1000
    uptime_target_percentage: float = 99.9
    alert_threshold_percentage: float = 99.5
    critical_threshold_percentage: float = 99.0

class HighAvailabilityManager:
    """Unified manager for 99.9% uptime target."""
    
    def __init__(self, config: HAConfig | None = None):
        self.config = config or HAConfig()
        self._health_registry = HealthCheckRegistry()
        self._failover_manager = FailoverManager(FailoverConfig(
            failure_threshold=self.config.unhealthy_threshold,
            recovery_threshold=self.config.healthy_threshold,
            failover_timeout_seconds=self.config.failover_timeout_seconds,
            auto_failback=self.config.auto_failback,
            failback_delay_seconds=self.config.failback_delay_seconds,
        ))
        self._load_balancer = LoadBalancer(LoadBalancerConfig(
            strategy=self.config.load_balancing_strategy,
            max_connections_per_instance=self.config.max_connections_per_instance,
        ))
        self._uptime_monitor = UptimeMonitor(UptimeMonitorConfig())
        self._health_registry.add_callback(self._on_health_check_result)
        self._failover_manager.add_callback(self._on_failover_event)
        self._running = False
        self._services: dict[str, dict[str, Any]] = {}

    def register_service(self, service_name: str, instances: list[InstanceInfo], health_check_func, replicas=None) -> None:
        self._services[service_name] = {"instances": {inst.id: inst for inst in instances},
                                        "health_check_func": health_check_func,
                                        "registered_at": datetime.now(UTC)}
        self._uptime_monitor.register_target(UptimeTarget(
            service_name=service_name, target_percentage=self.config.uptime_target_percentage,
            alert_threshold_percentage=self.config.alert_threshold_percentage,
            critical_threshold_percentage=self.config.critical_threshold_percentage,
        ))
        for instance in instances:
            self._failover_manager.register_instance(instance)
            self._load_balancer.register_instance(instance)
        self._health_registry.register(HealthCheckConfig(
            name=f"{service_name}_health", check_func=lambda: self._check_service_health(service_name),
            interval_seconds=self.config.health_check_interval_seconds,
            timeout_seconds=self.config.health_check_timeout_seconds, critical=True,
        ))
        logger.info(f"Registered service with HA: {service_name}")

    def _check_service_health(self, service_name: str) -> bool:
        if service_name not in self._services: return False
        try: return self._services[service_name]["health_check_func"]()
        except Exception: return False

    def unregister_service(self, service_name: str) -> bool:
        if service_name not in self._services: return False
        service = self._services[service_name]
        for instance_id in service["instances"]:
            self._failover_manager.unregister_instance(instance_id)
            self._load_balancer.unregister_instance(instance_id)
        self._health_registry.unregister(f"{service_name}_health")
        self._uptime_monitor.unregister_target(service_name)
        del self._services[service_name]
        return True

    def get_instance(self, service_name: str, session_id: str | None = None) -> InstanceInfo | None:
        return self._load_balancer.select_instance(session_id)

    def _on_health_check_result(self, name: str, result: HealthCheckResult) -> None:
        if name.endswith("_health"):
            service_name = name[:-7]
            if self.config.failover_enabled:
                self._failover_manager.update_instance_health(service_name, result.status)
            self._load_balancer.update_instance_health(service_name, result.status)
            self._uptime_monitor.record_check(service_name, result.status)

    def _on_failover_event(self, event_type: str, data: str) -> None:
        logger.warning(f"Failover event: {event_type} -> {data}")

    def get_service_status(self, service_name: str) -> dict[str, Any] | None:
        if service_name not in self._services: return None
        service = self._services[service_name]
        return {"service_name": service_name, "registered_at": service["registered_at"].isoformat(),
                "instance_count": len(service["instances"]),
                "active_instance": self._failover_manager.active_instance.to_dict() if self._failover_manager.active_instance else None,
                "failover_state": self._failover_manager.state.value,
                "uptime": self._uptime_monitor.get_service_status(service_name)}

    def get_global_status(self) -> dict[str, Any]:
        return {"services": {name: self.get_service_status(name) for name in self._services},
                "health_registry": self._health_registry.to_dict(),
                "failover": self._failover_manager.get_status(),
                "load_balancer": self._load_balancer.get_stats(),
                "uptime": self._uptime_monitor.get_all_status()}

    def get_recent_alerts(self, hours: int = 24) -> list[dict[str, Any]]:
        return [a.to_dict() for a in self._uptime_monitor.get_recent_alerts(hours=hours)]

    def is_meeting_uptime_target(self) -> bool:
        status = self._uptime_monitor.get_all_status()
        return status.get("services_meeting_target", 0) == status.get("total_services", 0)

    async def start(self) -> None:
        if self._running: return
        self._running = True
        await self._health_registry.start_all()
        logger.info("HA Manager started")

    async def stop(self) -> None:
        self._running = False
        await self._health_registry.stop_all()
        logger.info("HA Manager stopped")

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, *args):
        await self.stop()

    def to_dict(self) -> dict[str, Any]:
        return self.get_global_status()

_global_manager: HighAvailabilityManager | None = None

def get_ha_manager() -> HighAvailabilityManager:
    global _global_manager
    if _global_manager is None: _global_manager = HighAvailabilityManager()
    return _global_manager

def reset_ha_manager() -> None:
    global _global_manager
    _global_manager = None
