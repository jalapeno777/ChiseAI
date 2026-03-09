"""Tests for ACP persistence connectivity.

Verifies Redis and InfluxDB connections from the ACP runtime.

EP-NS-008: Autonomous Control Plane
"""

from __future__ import annotations

import os
import sys
import time
import uuid

import pytest

# Set environment variables for testing (agent environment uses host.docker.internal)
os.environ.setdefault("ACP_REDIS_HOST", "host.docker.internal")
os.environ.setdefault("ACP_INFLUXDB_HOST", "host.docker.internal")

# Import directly from submodules to avoid circular imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from autonomous_control_plane.config.settings import Settings
from autonomous_control_plane.core.orchestrator import ACPOrchestrator
from autonomous_control_plane.events.bus import Event, EventBus, EventPriority

INFLUX_TOKEN = os.getenv("ACP_INFLUXDB_TOKEN") or os.getenv("INFLUXDB_TOKEN", "")


class TestSettingsConnectionChecks:
    """Test connection health check methods in Settings."""

    def test_settings_loads_correct_defaults(self):
        """Test that settings load correct default values."""
        s = Settings.from_env()

        # Redis should use chiseai-redis by default (ACP container environment)
        assert s.redis.host == "host.docker.internal"  # Overridden for agent env
        assert s.redis.port == 6380

        # InfluxDB should use chiseai-influxdb by default (ACP container environment)
        assert s.influxdb.host == "host.docker.internal"  # Overridden for agent env
        assert s.influxdb.port == 18087
        assert s.influxdb.bucket == "chiseai"
        assert s.influxdb.org == "chiseai"

        # Token should come from environment, never from a hardcoded default.
        assert s.influxdb.token == INFLUX_TOKEN

    def test_check_redis_connection(self):
        """Test Redis connection check."""
        s = Settings.from_env()
        is_healthy, message = s.check_redis_connection()

        # Should connect successfully in test environment
        assert is_healthy is True, f"Redis connection failed: {message}"
        assert "successful" in message.lower()
        assert "host.docker.internal:6380" in message

    def test_check_influxdb_connection(self):
        """Test InfluxDB connection check."""
        if not INFLUX_TOKEN:
            pytest.skip("INFLUXDB_TOKEN / ACP_INFLUXDB_TOKEN not configured")

        s = Settings.from_env()
        is_healthy, message = s.check_influxdb_connection()

        # Should connect successfully in test environment
        assert is_healthy is True, f"InfluxDB connection failed: {message}"
        assert "successful" in message.lower()
        assert "host.docker.internal:18087" in message

    def test_check_all_connections(self):
        """Test checking all persistence connections."""
        if not INFLUX_TOKEN:
            pytest.skip("INFLUXDB_TOKEN / ACP_INFLUXDB_TOKEN not configured")

        s = Settings.from_env()
        results = s.check_all_connections()

        assert "redis" in results
        assert "influxdb" in results

        redis_healthy, redis_msg = results["redis"]
        influxdb_healthy, influxdb_msg = results["influxdb"]

        assert redis_healthy is True, f"Redis failed: {redis_msg}"
        assert influxdb_healthy is True, f"InfluxDB failed: {influxdb_msg}"


class TestOrchestrator:
    """Test ACPOrchestrator persistence connections."""

    def test_orchestrator_singleton(self):
        """Test that orchestrator is a singleton."""
        orch1 = ACPOrchestrator()
        orch2 = ACPOrchestrator()
        assert orch1 is orch2

    def test_orchestrator_start_stop(self):
        """Test orchestrator start and stop lifecycle."""
        # Create a fresh orchestrator instance for testing
        orchestrator = ACPOrchestrator.__new__(ACPOrchestrator)
        orchestrator._initialized = False
        orchestrator._pending_settings = None

        orchestrator.__init__()

        try:
            orchestrator.start()
            assert orchestrator._running is True

            # Check health after start
            health = orchestrator.health_check()
            assert health["running"] is True

            # Should have attempted connections
            # (may or may not succeed depending on test environment)

        finally:
            orchestrator.stop()
            assert orchestrator._running is False

    def test_orchestrator_health_check(self):
        """Test orchestrator health check."""
        orchestrator = ACPOrchestrator.__new__(ACPOrchestrator)
        orchestrator._initialized = False
        orchestrator._pending_settings = None

        orchestrator.__init__()

        try:
            orchestrator.start()
            health = orchestrator.health_check()

            assert "running" in health
            assert "redis" in health
            assert "influxdb" in health

            redis_health = health["redis"]
            assert "connected" in redis_health
            assert "healthy" in redis_health
            assert "message" in redis_health

        finally:
            orchestrator.stop()

    def test_orchestrator_reconnect(self):
        """Test orchestrator reconnection."""
        orchestrator = ACPOrchestrator.__new__(ACPOrchestrator)
        orchestrator._initialized = False
        orchestrator._pending_settings = None

        orchestrator.__init__()

        try:
            orchestrator.start()
            results = orchestrator.reconnect()

            assert "redis" in results
            assert "influxdb" in results

        finally:
            orchestrator.stop()


class TestEventBus:
    """Test EventBus with Redis Pub/Sub."""

    def test_event_bus_singleton(self):
        """Test that event bus is a singleton."""
        bus1 = EventBus()
        bus2 = EventBus()
        assert bus1 is bus2

    def test_event_creation(self):
        """Test event creation and serialization."""
        event = Event(
            event_type="test.event",
            payload={"key": "value"},
            source="test",
            priority=EventPriority.HIGH,
        )

        assert event.event_type == "test.event"
        assert event.payload == {"key": "value"}
        assert event.source == "test"
        assert event.priority == EventPriority.HIGH
        assert event.event_id is not None

        # Test serialization
        event_dict = event.to_dict()
        assert event_dict["event_type"] == "test.event"

        event_json = event.to_json()
        assert isinstance(event_json, str)

        # Test deserialization
        restored = Event.from_json(event_json)
        assert restored.event_type == event.event_type
        assert restored.payload == event.payload

    def test_event_bus_local_dispatch(self):
        """Test event bus local event dispatch."""
        bus = EventBus.__new__(EventBus)
        bus._initialized = False
        bus._pending_redis = None
        bus.__init__()

        received_events = []

        def handler(event: Event):
            received_events.append(event)

        try:
            bus.start()
            bus.subscribe("test.event", handler)

            event = Event(event_type="test.event", payload={"data": "test"})
            bus.publish(event)

            # Give a moment for dispatch
            time.sleep(0.1)

            assert len(received_events) == 1
            assert received_events[0].event_type == "test.event"
            assert received_events[0].payload == {"data": "test"}

        finally:
            bus.stop()

    def test_event_bus_global_handler(self):
        """Test event bus global handler."""
        bus = EventBus.__new__(EventBus)
        bus._initialized = False
        bus._pending_redis = None
        bus.__init__()

        received_events = []

        def global_handler(event: Event):
            received_events.append(event)

        try:
            bus.start()
            bus.subscribe_all(global_handler)

            event = Event(event_type="any.event", payload={"data": "test"})
            bus.publish(event)

            time.sleep(0.1)

            assert len(received_events) == 1
            assert received_events[0].event_type == "any.event"

        finally:
            bus.stop()

    def test_event_bus_health_check(self):
        """Test event bus health check."""
        bus = EventBus.__new__(EventBus)
        bus._initialized = False
        bus._pending_redis = None
        bus.__init__()

        try:
            bus.start()
            health = bus.health_check()

            assert "running" in health
            assert "redis_connected" in health
            assert "handler_count" in health
            assert "global_handler_count" in health

        finally:
            bus.stop()


class TestPersistenceIntegration:
    """Integration tests for persistence layer."""

    def test_end_to_end_persistence(self):
        """Test end-to-end persistence connectivity."""
        # Test settings connections
        s = Settings.from_env()
        connections = s.check_all_connections()

        assert connections["redis"][0] is True, "Redis must be connected"
        assert connections["influxdb"][0] is True, "InfluxDB must be connected"

    def test_data_flow_to_influxdb(self):
        """Test that data can be written to InfluxDB."""
        from influxdb_client.client.influxdb_client import InfluxDBClient
        from influxdb_client.client.write_api import SYNCHRONOUS

        s = Settings.from_env()

        client = InfluxDBClient(
            url=s.influxdb.url,
            token=s.influxdb.token,
            org=s.influxdb.org,
        )

        try:
            # Test write
            write_api = client.write_api(write_options=SYNCHRONOUS)

            test_point = {
                "measurement": "test_measurement",
                "tags": {"test": "persistence"},
                "fields": {"value": 42.0},
                "time": int(time.time() * 1e9),
            }

            write_api.write(
                bucket=s.influxdb.bucket,
                org=s.influxdb.org,
                record=test_point,
            )

            # If we get here, write succeeded
            assert True

        finally:
            client.close()

    def test_data_flow_to_redis(self):
        """Test that data can be written to Redis."""
        import redis as redis_lib

        s = Settings.from_env()

        client = redis_lib.Redis(
            host=s.redis.host,
            port=s.redis.port,
            db=s.redis.db,
            socket_timeout=s.redis.socket_timeout,
            decode_responses=True,
        )

        try:
            # Test write
            test_key = f"test:persistence:{uuid.uuid4()}"
            test_value = "test_data"

            client.set(test_key, test_value, ex=60)  # 60 second expiry
            retrieved = client.get(test_key)

            assert retrieved == test_value

            # Clean up
            client.delete(test_key)

        finally:
            client.close()


class TestGracefulDegradation:
    """Test graceful degradation when services are unavailable."""

    def test_redis_fallback_when_unavailable(self):
        """Test that Redis falls back to in-memory mode when unavailable."""
        s = Settings.from_env()

        # Temporarily change to invalid host
        original_host = s.redis.host
        s.redis.host = "invalid-host-that-does-not-exist"

        try:
            is_healthy, message = s.check_redis_connection()
            assert is_healthy is False
            assert "failed" in message.lower() or "error" in message.lower()
        finally:
            s.redis.host = original_host

    def test_influxdb_fallback_when_unavailable(self):
        """Test that InfluxDB falls back when unavailable."""
        s = Settings.from_env()

        # Temporarily change to invalid host
        original_host = s.influxdb.host
        s.influxdb.host = "invalid-host-that-does-not-exist"

        try:
            is_healthy, message = s.check_influxdb_connection()
            assert is_healthy is False
            assert "failed" in message.lower() or "error" in message.lower()
        finally:
            s.influxdb.host = original_host

    def test_orchestrator_handles_connection_failure(self):
        """Test orchestrator handles connection failures gracefully."""
        # Create orchestrator with invalid settings
        bad_settings = Settings.from_env()
        bad_settings.redis.host = "invalid-host"
        bad_settings.influxdb.host = "invalid-host"

        orchestrator = ACPOrchestrator.__new__(ACPOrchestrator)
        orchestrator._initialized = False
        orchestrator._pending_settings = bad_settings
        orchestrator.__init__(bad_settings)

        try:
            orchestrator.start()

            # Should be running but with failed connections
            assert orchestrator._running is True
            assert orchestrator.is_redis_connected is False
            assert orchestrator.is_influxdb_connected is False

            # Health check should report failures
            health = orchestrator.health_check()
            assert health["running"] is True
            assert health["redis"]["connected"] is False
            assert health["influxdb"]["connected"] is False

        finally:
            orchestrator.stop()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
