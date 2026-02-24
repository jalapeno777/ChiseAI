"""Redundancy Manager for High Availability Infrastructure (NFR-006)."""
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)

class RedundancyLevel(Enum):
    NONE = "none"
    ACTIVE_PASSIVE = "active_passive"
    ACTIVE_ACTIVE = "active_active"
    MULTI_ACTIVE = "multi_active"

class ReplicationMode(Enum):
    SYNC = "sync"
    ASYNC = "async"
    SEMI_SYNC = "semi_sync"

@dataclass
class ReplicaInfo:
    id: str
    location: str
    is_primary: bool = False
    is_synced: bool = False
    replication_lag_ms: float = 0.0
    last_sync_time: Optional[datetime] = None
    health_score: float = 100.0

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "location": self.location, "is_primary": self.is_primary,
                "is_synced": self.is_synced, "replication_lag_ms": self.replication_lag_ms,
                "last_sync_time": self.last_sync_time.isoformat() if self.last_sync_time else None,
                "health_score": self.health_score}

@dataclass
class RedundancyConfig:
    level: RedundancyLevel = RedundancyLevel.ACTIVE_PASSIVE
    replication_mode: ReplicationMode = ReplicationMode.ASYNC
    min_replicas: int = 2
    max_replication_lag_ms: float = 5000.0
    sync_timeout_seconds: float = 5.0
    health_check_interval_seconds: float = 30.0
    auto_promote_on_failure: bool = True

class DataReplicator:
    def __init__(self, config: RedundancyConfig | None = None):
        self.config = config or RedundancyConfig()
        self._replicas: dict[str, ReplicaInfo] = {}
        self._primary_id: Optional[str] = None

    @property
    def primary(self) -> Optional[ReplicaInfo]:
        return self._replicas.get(self._primary_id) if self._primary_id else None

    def register_replica(self, replica: ReplicaInfo) -> None:
        self._replicas[replica.id] = replica
        if replica.is_primary: self._primary_id = replica.id
        logger.info(f"Registered replica: {replica.id}")

    def unregister_replica(self, replica_id: str) -> bool:
        if replica_id in self._replicas:
            del self._replicas[replica_id]
            if self._primary_id == replica_id: self._primary_id = None
            return True
        return False

    def get_replicas(self) -> list[ReplicaInfo]:
        return list(self._replicas.values())

    def get_healthy_replicas(self) -> list[ReplicaInfo]:
        return [r for r in self._replicas.values()
                if r.health_score > 50 and r.replication_lag_ms <= self.config.max_replication_lag_ms]

    def update_replica_status(self, replica_id: str, is_synced: bool, lag_ms: float) -> None:
        if replica_id not in self._replicas: return
        replica = self._replicas[replica_id]
        replica.is_synced = is_synced
        replica.replication_lag_ms = lag_ms
        replica.last_sync_time = datetime.now(timezone.utc)
        if lag_ms <= 1000: replica.health_score = 100
        elif lag_ms <= 3000: replica.health_score = 80
        elif lag_ms <= self.config.max_replication_lag_ms: replica.health_score = 50
        else: replica.health_score = 20

    def promote_replica(self, replica_id: str) -> bool:
        if replica_id not in self._replicas: return False
        replica = self._replicas[replica_id]
        if replica.health_score < 50: return False
        if self._primary_id and self._primary_id in self._replicas:
            self._replicas[self._primary_id].is_primary = False
        replica.is_primary = True
        self._primary_id = replica_id
        logger.warning(f"Promoted replica to primary: {replica_id}")
        return True

    def get_status(self) -> dict[str, Any]:
        return {"level": self.config.level.value, "replication_mode": self.config.replication_mode.value,
                "primary": self.primary.to_dict() if self.primary else None,
                "replicas": {id: r.to_dict() for id, r in self._replicas.items()},
                "healthy_count": len(self.get_healthy_replicas()), "min_replicas": self.config.min_replicas,
                "meets_requirements": len(self.get_healthy_replicas()) >= self.config.min_replicas}

class ServiceRedundancyManager:
    def __init__(self, config: RedundancyConfig | None = None):
        self.config = config or RedundancyConfig()
        self._services: dict[str, dict[str, Any]] = {}
        self._data_replicators: dict[str, DataReplicator] = {}

    def register_service(self, service_name: str, redundancy_level: RedundancyLevel | None = None,
                        replication_config: RedundancyConfig | None = None) -> None:
        level = redundancy_level or self.config.level
        self._services[service_name] = {"name": service_name, "level": level,
                                        "registered_at": datetime.now(timezone.utc), "failover_count": 0}
        if replication_config:
            self._data_replicators[service_name] = DataReplicator(replication_config)
        logger.info(f"Registered service for redundancy: {service_name}")

    def unregister_service(self, service_name: str) -> bool:
        if service_name in self._services:
            del self._services[service_name]
            if service_name in self._data_replicators: del self._data_replicators[service_name]
            return True
        return False

    def get_data_replicator(self, service_name: str) -> Optional[DataReplicator]:
        return self._data_replicators.get(service_name)

    def get_service_status(self, service_name: str) -> Optional[dict[str, Any]]:
        if service_name not in self._services: return None
        service = self._services[service_name]
        status = {"name": service_name, "level": service["level"].value,
                  "failover_count": service["failover_count"], "registered_at": service["registered_at"].isoformat()}
        if service_name in self._data_replicators:
            status["data_replication"] = self._data_replicators[service_name].get_status()
        return status

    def get_all_status(self) -> dict[str, Any]:
        return {"services": {name: self.get_service_status(name) for name in self._services},
                "total_services": len(self._services)}

    def record_failover(self, service_name: str) -> None:
        if service_name in self._services:
            self._services[service_name]["failover_count"] += 1

class RedundancyOrchestrator:
    def __init__(self):
        self._manager = ServiceRedundancyManager()

    def setup_service(self, service_name: str, level: RedundancyLevel = RedundancyLevel.ACTIVE_PASSIVE,
                     replicas: list[ReplicaInfo] | None = None) -> None:
        config = RedundancyConfig(level=level)
        self._manager.register_service(service_name, level, config)
        if replicas:
            replicator = self._manager.get_data_replicator(service_name)
            if replicator:
                for replica in replicas:
                    replicator.register_replica(replica)
        logger.info(f"Set up redundancy for {service_name}: level={level.value}")

    def get_global_status(self) -> dict[str, Any]:
        return self._manager.get_all_status()
