"""Tests for Redundancy Manager."""
import pytest
from datetime import datetime, timezone

from src.redundancy.manager import (
    RedundancyLevel, ReplicationMode, ReplicaInfo, RedundancyConfig,
    DataReplicator, ServiceRedundancyManager, RedundancyOrchestrator
)


class TestRedundancyLevel:
    """Tests for RedundancyLevel enum."""
    
    def test_level_values(self):
        """Test that all expected level values exist."""
        assert RedundancyLevel.NONE.value == "none"
        assert RedundancyLevel.ACTIVE_PASSIVE.value == "active_passive"
        assert RedundancyLevel.ACTIVE_ACTIVE.value == "active_active"
        assert RedundancyLevel.MULTI_ACTIVE.value == "multi_active"


class TestReplicationMode:
    """Tests for ReplicationMode enum."""
    
    def test_mode_values(self):
        """Test that all expected mode values exist."""
        assert ReplicationMode.SYNC.value == "sync"
        assert ReplicationMode.ASYNC.value == "async"
        assert ReplicationMode.SEMI_SYNC.value == "semi_sync"


class TestReplicaInfo:
    """Tests for ReplicaInfo dataclass."""
    
    def test_replica_creation(self):
        """Test creating a replica."""
        replica = ReplicaInfo(
            id="replica-1",
            location="us-east-1",
        )
        assert replica.id == "replica-1"
        assert replica.location == "us-east-1"
        assert replica.is_primary is False
        assert replica.health_score == 100.0
    
    def test_replica_to_dict(self):
        """Test serializing replica to dict."""
        replica = ReplicaInfo(
            id="replica-1",
            location="us-east-1",
            is_primary=True,
            replication_lag_ms=50.0,
        )
        d = replica.to_dict()
        assert d["id"] == "replica-1"
        assert d["location"] == "us-east-1"
        assert d["is_primary"] is True
        assert d["replication_lag_ms"] == 50.0


class TestRedundancyConfig:
    """Tests for RedundancyConfig dataclass."""
    
    def test_config_defaults(self):
        """Test default config values."""
        config = RedundancyConfig()
        assert config.level == RedundancyLevel.ACTIVE_PASSIVE
        assert config.replication_mode == ReplicationMode.ASYNC
        assert config.min_replicas == 2
        assert config.max_replication_lag_ms == 5000.0
    
    def test_config_custom_values(self):
        """Test custom config values."""
        config = RedundancyConfig(
            level=RedundancyLevel.ACTIVE_ACTIVE,
            replication_mode=ReplicationMode.SYNC,
            min_replicas=3,
            max_replication_lag_ms=1000.0,
        )
        assert config.level == RedundancyLevel.ACTIVE_ACTIVE
        assert config.replication_mode == ReplicationMode.SYNC
        assert config.min_replicas == 3


class TestDataReplicator:
    """Tests for DataReplicator class."""
    
    def test_initial_state(self, data_replicator):
        """Test initial replicator state."""
        assert data_replicator.primary is None
        assert len(data_replicator.get_replicas()) == 0
    
    def test_register_replica(self, data_replicator, replica_info):
        """Test registering a replica."""
        data_replicator.register_replica(replica_info)
        assert len(data_replicator.get_replicas()) == 1
        assert data_replicator.primary is not None
    
    def test_unregister_replica(self, data_replicator, replica_info):
        """Test unregistering a replica."""
        data_replicator.register_replica(replica_info)
        result = data_replicator.unregister_replica("replica-1")
        assert result is True
        assert len(data_replicator.get_replicas()) == 0
    
    def test_unregister_nonexistent(self, data_replicator):
        """Test unregistering non-existent replica."""
        result = data_replicator.unregister_replica("nonexistent")
        assert result is False
    
    def test_get_healthy_replicas(self, data_replicator, replica_info, backup_replica):
        """Test getting healthy replicas."""
        data_replicator.register_replica(replica_info)
        backup_replica.health_score = 80
        data_replicator.register_replica(backup_replica)
        
        healthy = data_replicator.get_healthy_replicas()
        assert len(healthy) == 2
    
    def test_get_healthy_replicas_excludes_unhealthy(self, data_replicator, replica_info):
        """Test that unhealthy replicas are excluded."""
        replica_info.health_score = 10  # Too low
        data_replicator.register_replica(replica_info)
        
        healthy = data_replicator.get_healthy_replicas()
        assert len(healthy) == 0
    
    def test_update_replica_status(self, data_replicator, replica_info):
        """Test updating replica status."""
        data_replicator.register_replica(replica_info)
        data_replicator.update_replica_status("replica-1", is_synced=True, lag_ms=100)
        
        replica = data_replicator._replicas["replica-1"]
        assert replica.is_synced is True
        assert replica.replication_lag_ms == 100
        assert replica.health_score == 100
    
    def test_update_replica_status_health_score(self, data_replicator, replica_info):
        """Test health score calculation based on lag."""
        data_replicator.register_replica(replica_info)
        
        # Low lag = 100 score
        data_replicator.update_replica_status("replica-1", is_synced=True, lag_ms=500)
        assert data_replicator._replicas["replica-1"].health_score == 100
        
        # Medium lag = 80 score
        data_replicator.update_replica_status("replica-1", is_synced=True, lag_ms=2000)
        assert data_replicator._replicas["replica-1"].health_score == 80
        
        # High lag = 50 score
        data_replicator.update_replica_status("replica-1", is_synced=True, lag_ms=4000)
        assert data_replicator._replicas["replica-1"].health_score == 50
    
    def test_promote_replica(self, data_replicator, replica_info, backup_replica):
        """Test promoting a replica to primary."""
        data_replicator.register_replica(replica_info)
        backup_replica.health_score = 100
        data_replicator.register_replica(backup_replica)
        
        result = data_replicator.promote_replica("replica-2")
        assert result is True
        assert data_replicator.primary.id == "replica-2"
        assert data_replicator._replicas["replica-1"].is_primary is False
    
    def test_promote_replica_unhealthy(self, data_replicator, replica_info, backup_replica):
        """Test promoting an unhealthy replica fails."""
        data_replicator.register_replica(replica_info)
        backup_replica.health_score = 10
        data_replicator.register_replica(backup_replica)
        
        result = data_replicator.promote_replica("replica-2")
        assert result is False
        assert data_replicator.primary.id == "replica-1"
    
    def test_get_status(self, data_replicator, replica_info):
        """Test getting replicator status."""
        data_replicator.register_replica(replica_info)
        status = data_replicator.get_status()
        
        assert "level" in status
        assert "replication_mode" in status
        assert "primary" in status
        assert "replicas" in status
        assert "meets_requirements" in status


class TestServiceRedundancyManager:
    """Tests for ServiceRedundancyManager class."""
    
    def test_initial_state(self):
        """Test initial manager state."""
        manager = ServiceRedundancyManager()
        assert len(manager._services) == 0
    
    def test_register_service(self):
        """Test registering a service."""
        manager = ServiceRedundancyManager()
        manager.register_service("test-service")
        assert "test-service" in manager._services
    
    def test_register_service_with_config(self):
        """Test registering service with custom config."""
        manager = ServiceRedundancyManager()
        config = RedundancyConfig(level=RedundancyLevel.ACTIVE_ACTIVE)
        manager.register_service("test-service", replication_config=config)
        
        assert "test-service" in manager._data_replicators
    
    def test_unregister_service(self):
        """Test unregistering a service."""
        manager = ServiceRedundancyManager()
        manager.register_service("test-service")
        result = manager.unregister_service("test-service")
        assert result is True
        assert "test-service" not in manager._services
    
    def test_unregister_nonexistent(self):
        """Test unregistering non-existent service."""
        manager = ServiceRedundancyManager()
        result = manager.unregister_service("nonexistent")
        assert result is False
    
    def test_get_data_replicator(self):
        """Test getting data replicator for service."""
        manager = ServiceRedundancyManager()
        config = RedundancyConfig()
        manager.register_service("test-service", replication_config=config)
        
        replicator = manager.get_data_replicator("test-service")
        assert replicator is not None
    
    def test_get_service_status(self):
        """Test getting service status."""
        manager = ServiceRedundancyManager()
        manager.register_service("test-service")
        
        status = manager.get_service_status("test-service")
        assert status is not None
        assert status["name"] == "test-service"
    
    def test_get_service_status_nonexistent(self):
        """Test getting status of non-existent service."""
        manager = ServiceRedundancyManager()
        status = manager.get_service_status("nonexistent")
        assert status is None
    
    def test_get_all_status(self):
        """Test getting all services status."""
        manager = ServiceRedundancyManager()
        manager.register_service("service-1")
        manager.register_service("service-2")
        
        status = manager.get_all_status()
        assert "services" in status
        assert status["total_services"] == 2
    
    def test_record_failover(self):
        """Test recording a failover."""
        manager = ServiceRedundancyManager()
        manager.register_service("test-service")
        
        manager.record_failover("test-service")
        
        status = manager.get_service_status("test-service")
        assert status["failover_count"] == 1


class TestRedundancyOrchestrator:
    """Tests for RedundancyOrchestrator class."""
    
    def test_setup_service(self):
        """Test setting up a service."""
        orchestrator = RedundancyOrchestrator()
        orchestrator.setup_service("test-service")
        
        status = orchestrator.get_global_status()
        assert status["total_services"] == 1
    
    def test_setup_service_with_replicas(self):
        """Test setting up service with replicas."""
        orchestrator = RedundancyOrchestrator()
        replicas = [
            ReplicaInfo(id="r1", location="us-east-1", is_primary=True),
            ReplicaInfo(id="r2", location="us-west-1", is_primary=False),
        ]
        orchestrator.setup_service(
            "test-service",
            level=RedundancyLevel.ACTIVE_PASSIVE,
            replicas=replicas,
        )
        
        status = orchestrator.get_global_status()
        assert "test-service" in status["services"]
    
    def test_get_global_status(self):
        """Test getting global status."""
        orchestrator = RedundancyOrchestrator()
        orchestrator.setup_service("service-1")
        orchestrator.setup_service("service-2")
        
        status = orchestrator.get_global_status()
        assert status["total_services"] == 2


class TestHealthScoreCalculation:
    """Tests for health score calculation."""
    
    def test_health_score_boundaries(self, data_replicator, replica_info):
        """Test health score at different lag boundaries."""
        data_replicator.register_replica(replica_info)
        
        # Test different lag values
        test_cases = [
            (500, 100),   # Low lag -> 100
            (1000, 100),  # At 1s threshold -> 100
            (2000, 80),   # At 3s threshold -> 80
            (4000, 50),   # At 5s threshold -> 50
            (6000, 20),   # Over max -> 20
        ]
        
        for lag, expected_score in test_cases:
            data_replicator.update_replica_status("replica-1", is_synced=True, lag_ms=lag)
            assert data_replicator._replicas["replica-1"].health_score == expected_score, \
                f"Expected {expected_score} for lag {lag}ms"
