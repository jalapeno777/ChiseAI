"""Tests for Redundancy Manager."""

from src.redundancy.manager import (
    DataReplicator,
    RedundancyConfig,
    RedundancyLevel,
    RedundancyOrchestrator,
    ReplicaInfo,
    ServiceRedundancyManager,
)


class TestReplicaInfo:
    """Tests for ReplicaInfo."""

    def test_replica_creation(self):
        """Test creating a replica info."""
        replica = ReplicaInfo(
            id="replica-1",
            location="us-east-1",
            is_primary=True,
        )
        assert replica.id == "replica-1"
        assert replica.location == "us-east-1"
        assert replica.is_primary
        assert replica.health_score == 100.0

    def test_replica_to_dict(self):
        """Test converting replica to dictionary."""
        replica = ReplicaInfo(
            id="replica-1",
            location="us-east-1",
            is_synced=True,
            replication_lag_ms=100.0,
        )
        d = replica.to_dict()
        assert d["id"] == "replica-1"
        assert d["is_synced"]
        assert d["replication_lag_ms"] == 100.0


class TestDataReplicator:
    """Tests for DataReplicator."""

    def test_replicator_creation(self):
        """Test creating a data replicator."""
        config = RedundancyConfig()
        replicator = DataReplicator(config)
        assert replicator.primary is None

    def test_register_replica(self, data_replicator, sample_replica):
        """Test registering a replica."""
        data_replicator.register_replica(sample_replica)
        assert len(data_replicator.get_replicas()) == 1
        assert data_replicator.primary is not None

    def test_unregister_replica(self, data_replicator, sample_replica):
        """Test unregistering a replica."""
        data_replicator.register_replica(sample_replica)
        assert data_replicator.unregister_replica(sample_replica.id)
        assert len(data_replicator.get_replicas()) == 0

    def test_update_replica_status(self, data_replicator, sample_replica):
        """Test updating replica status."""
        data_replicator.register_replica(sample_replica)
        data_replicator.update_replica_status(
            sample_replica.id,
            is_synced=True,
            lag_ms=500.0,
        )

        replicas = data_replicator.get_replicas()
        assert replicas[0].is_synced
        assert replicas[0].replication_lag_ms == 500.0

    def test_health_score_calculation(self, data_replicator, sample_replica):
        """Test health score based on lag."""
        data_replicator.register_replica(sample_replica)

        # Low lag = high health
        data_replicator.update_replica_status(sample_replica.id, True, 500.0)
        assert data_replicator.get_replicas()[0].health_score == 100

        # Medium lag = medium health
        data_replicator.update_replica_status(sample_replica.id, True, 3000.0)
        assert data_replicator.get_replicas()[0].health_score == 50

        # High lag = low health
        data_replicator.update_replica_status(sample_replica.id, True, 10000.0)
        assert data_replicator.get_replicas()[0].health_score == 20

    def test_get_healthy_replicas(self, data_replicator, sample_replicas):
        """Test getting healthy replicas."""
        for replica in sample_replicas:
            data_replicator.register_replica(replica)

        # Update statuses
        data_replicator.update_replica_status("replica-primary", True, 100.0)
        data_replicator.update_replica_status("replica-secondary-1", True, 100.0)
        data_replicator.update_replica_status(
            "replica-secondary-2", True, 10000.0
        )  # Unhealthy

        healthy = data_replicator.get_healthy_replicas()
        assert len(healthy) == 2

    def test_promote_replica(self, data_replicator, sample_replicas):
        """Test promoting a replica to primary."""
        for replica in sample_replicas:
            data_replicator.register_replica(replica)

        # Promote secondary
        data_replicator.update_replica_status("replica-secondary-1", True, 100.0)
        assert data_replicator.promote_replica("replica-secondary-1")

        # Check new primary
        assert data_replicator.primary.id == "replica-secondary-1"

    def test_promote_unhealthy_fails(self, data_replicator, sample_replicas):
        """Test that promoting unhealthy replica fails."""
        for replica in sample_replicas:
            data_replicator.register_replica(replica)

        # Make replica unhealthy
        data_replicator.update_replica_status("replica-secondary-1", False, 10000.0)
        assert not data_replicator.promote_replica("replica-secondary-1")

    def test_get_status(self, data_replicator, sample_replicas):
        """Test getting replicator status."""
        for replica in sample_replicas:
            data_replicator.register_replica(replica)

        status = data_replicator.get_status()
        assert status["level"] == RedundancyLevel.ACTIVE_PASSIVE.value
        assert status["primary"] is not None
        assert status["healthy_count"] == 3


class TestServiceRedundancyManager:
    """Tests for ServiceRedundancyManager."""

    def test_manager_creation(self):
        """Test creating a service redundancy manager."""
        manager = ServiceRedundancyManager()
        assert len(manager._services) == 0

    def test_register_service(self):
        """Test registering a service."""
        manager = ServiceRedundancyManager()
        manager.register_service("api", RedundancyLevel.ACTIVE_ACTIVE)

        status = manager.get_service_status("api")
        assert status["name"] == "api"
        assert status["level"] == "active_active"

    def test_unregister_service(self):
        """Test unregistering a service."""
        manager = ServiceRedundancyManager()
        manager.register_service("api")
        assert manager.unregister_service("api")
        assert not manager.unregister_service("nonexistent")

    def test_get_data_replicator(self):
        """Test getting data replicator for service."""
        config = RedundancyConfig(min_replicas=2)
        manager = ServiceRedundancyManager()
        manager.register_service("database", replication_config=config)

        replicator = manager.get_data_replicator("database")
        assert replicator is not None

    def test_record_failover(self):
        """Test recording failover events."""
        manager = ServiceRedundancyManager()
        manager.register_service("api")

        manager.record_failover("api")
        manager.record_failover("api")

        status = manager.get_service_status("api")
        assert status["failover_count"] == 2

    def test_get_all_status(self):
        """Test getting all services status."""
        manager = ServiceRedundancyManager()
        manager.register_service("api")
        manager.register_service("web")

        status = manager.get_all_status()
        assert status["total_services"] == 2
        assert "api" in status["services"]
        assert "web" in status["services"]


class TestRedundancyOrchestrator:
    """Tests for RedundancyOrchestrator."""

    def test_orchestrator_creation(self):
        """Test creating an orchestrator."""
        orchestrator = RedundancyOrchestrator()
        assert orchestrator._manager is not None

    def test_setup_service(self, sample_replicas):
        """Test setting up a service with replicas."""
        orchestrator = RedundancyOrchestrator()
        orchestrator.setup_service(
            "database",
            level=RedundancyLevel.ACTIVE_PASSIVE,
            replicas=sample_replicas,
        )

        status = orchestrator.get_global_status()
        assert status["total_services"] == 1

    def test_get_global_status(self):
        """Test getting global status."""
        orchestrator = RedundancyOrchestrator()
        orchestrator.setup_service("api")
        orchestrator.setup_service("web")

        status = orchestrator.get_global_status()
        assert status["total_services"] == 2


class TestRedundancyLevels:
    """Tests for different redundancy levels."""

    def test_active_passive(self):
        """Test active-passive redundancy."""
        config = RedundancyConfig(level=RedundancyLevel.ACTIVE_PASSIVE)
        replicator = DataReplicator(config)

        # Should require at least min_replicas
        status = replicator.get_status()
        assert status["level"] == "active_passive"

    def test_active_active(self):
        """Test active-active redundancy."""
        config = RedundancyConfig(level=RedundancyLevel.ACTIVE_ACTIVE)
        replicator = DataReplicator(config)

        status = replicator.get_status()
        assert status["level"] == "active_active"

    def test_meets_requirements(self, sample_replicas):
        """Test meeting redundancy requirements."""
        config = RedundancyConfig(
            level=RedundancyLevel.ACTIVE_PASSIVE,
            min_replicas=2,
        )
        replicator = DataReplicator(config)

        # Not enough replicas
        replicator.register_replica(sample_replicas[0])
        assert not replicator.get_status()["meets_requirements"]

        # Add more replicas
        replicator.register_replica(sample_replicas[1])
        assert replicator.get_status()["meets_requirements"]
