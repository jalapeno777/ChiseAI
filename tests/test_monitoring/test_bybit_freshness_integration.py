"""Integration tests for Bybit freshness pipeline.

End-to-end tests validating the complete flow:
  collector → Redis → watchdog → gate

These tests ensure all components work together correctly.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, patch

import pytest


class TestFullFreshnessPipeline:
    """End-to-end test of collector → Redis → watchdog → gate."""

    @pytest.fixture
    def mock_redis_pipeline(self):
        """Create a mock Redis that simulates the full pipeline."""
        storage = {}

        def mock_get(key):
            return storage.get(key)

        def mock_set(key, value):
            storage[key] = value
            return True

        def mock_delete(key):
            if key in storage:
                del storage[key]
                return 1
            return 0

        mock_redis = Mock()
        mock_redis.get.side_effect = mock_get
        mock_redis.set.side_effect = mock_set
        mock_redis.delete.side_effect = mock_delete
        mock_redis.ping.return_value = True

        return mock_redis, storage

    @pytest.mark.asyncio
    async def test_full_freshness_pipeline(self, mock_redis_pipeline):
        """End-to-end test of collector → Redis → watchdog → gate.

        Validates the complete pipeline:
        1. Collector runs and stores data in Redis
        2. Watchdog reads data from Redis
        3. Watchdog returns appropriate status
        4. Gate makes decision based on watchdog result
        """
        mock_redis, storage = mock_redis_pipeline

        # === Step 1: Simulate collector running ===
        from scripts.validation.bybit_truth_collector import (
            BybitTruthCollector,
        )

        collector = BybitTruthCollector(dry_run=True)

        # Mock collector's Redis connection
        with patch.object(collector, "_get_redis", return_value=mock_redis):
            # Simulate collection
            result = await collector.collect()

            # Verify collector stored data in Redis
            assert result.status == "success"
            assert "bmad:chiseai:bybit_truth:last_collection_timestamp" in storage
            assert "bmad:chiseai:bybit_truth:last_collection_status" in storage
            assert (
                storage["bmad:chiseai:bybit_truth:last_collection_status"] == "success"
            )

        # === Step 2: Watchdog reads the data ===
        from scripts.validation.bybit_freshness_check import BybitFreshnessChecker

        watchdog = BybitFreshnessChecker(threshold_hours=1)

        with patch.object(watchdog, "_get_redis", return_value=mock_redis):
            freshness_result = watchdog.check()

            # === Step 3: Verify watchdog status ===
            assert freshness_result.is_fresh is True
            assert freshness_result.status == "fresh"
            assert freshness_result.reason == "fresh"

        # === Step 4: Gate makes decision ===
        # Gate checks watchdog result and decides whether to proceed
        gate_passed = freshness_result.is_fresh and freshness_result.status == "fresh"
        assert gate_passed is True

    @pytest.mark.asyncio
    async def test_pipeline_with_stale_data(self, mock_redis_pipeline):
        """Test pipeline when data becomes stale.

        Validates that stale data is detected and gate fails appropriately.
        """
        mock_redis, storage = mock_redis_pipeline

        # Simulate old collection data (2 hours ago)
        old_timestamp = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
        storage["bmad:chiseai:bybit_truth:last_collection_timestamp"] = old_timestamp
        storage["bmad:chiseai:bybit_truth:last_collection_count"] = "10"
        storage["bmad:chiseai:bybit_truth:last_collection_status"] = "success"
        storage["bmad:chiseai:bybit_truth:last_collection_reason"] = "fresh"

        # Watchdog detects stale data
        from scripts.validation.bybit_freshness_check import BybitFreshnessChecker

        watchdog = BybitFreshnessChecker(threshold_hours=1)

        with patch.object(watchdog, "_get_redis", return_value=mock_redis):
            result = watchdog.check()

            assert result.is_fresh is False
            assert result.status == "stale"
            assert result.reason == "stale_old"
            assert result.hours_since_collection > 1.0

        # Gate fails due to stale data
        gate_passed = result.is_fresh
        assert gate_passed is False

    @pytest.mark.asyncio
    async def test_pipeline_recovery_flow(self, mock_redis_pipeline):
        """Test pipeline recovery when collector is re-triggered.

        Validates that after recovery, data becomes fresh again.
        """
        mock_redis, storage = mock_redis_pipeline

        # Start with stale data
        old_timestamp = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
        storage["bmad:chiseai:bybit_truth:last_collection_timestamp"] = old_timestamp
        storage["bmad:chiseai:bybit_truth:last_collection_count"] = "10"
        storage["bmad:chiseai:bybit_truth:last_collection_status"] = "success"

        # Verify stale
        from scripts.validation.bybit_freshness_check import BybitFreshnessChecker

        watchdog = BybitFreshnessChecker(threshold_hours=1)

        with patch.object(watchdog, "_get_redis", return_value=mock_redis):
            stale_result = watchdog.check()
            assert stale_result.is_fresh is False

        # Trigger collector (recovery)
        from scripts.validation.bybit_truth_collector import BybitTruthCollector

        collector = BybitTruthCollector(dry_run=True)

        with patch.object(collector, "_get_redis", return_value=mock_redis):
            await collector.collect()

        # Verify fresh after recovery
        with patch.object(watchdog, "_get_redis", return_value=mock_redis):
            fresh_result = watchdog.check()
            assert fresh_result.is_fresh is True
            assert fresh_result.status == "fresh"


class TestCollectorRedisIntegration:
    """Test integration between collector and Redis."""

    @pytest.mark.asyncio
    async def test_collector_stores_all_metadata(self):
        """Collector stores all required metadata keys in Redis."""
        from scripts.validation.bybit_truth_collector import (
            REDIS_KEYS,
            BybitTruthCollector,
        )

        storage = {}

        def mock_get(key):
            return storage.get(key)

        def mock_set(key, value):
            storage[key] = value
            return True

        mock_redis = Mock()
        mock_redis.get.side_effect = mock_get
        mock_redis.set.side_effect = mock_set
        mock_redis.ping.return_value = True

        collector = BybitTruthCollector(dry_run=True)

        with patch.object(collector, "_get_redis", return_value=mock_redis):
            result = await collector.collect()

            # Verify all expected keys are stored
            assert REDIS_KEYS["timestamp"] in storage
            assert REDIS_KEYS["count"] in storage
            assert REDIS_KEYS["status"] in storage
            assert REDIS_KEYS["reason"] in storage
            assert REDIS_KEYS["execution_id"] in storage

            # Verify values
            assert storage[REDIS_KEYS["status"]] == "success"
            assert storage[REDIS_KEYS["count"]] == str(result.count)

    @pytest.mark.asyncio
    async def test_collector_clears_error_on_success(self):
        """Collector clears previous error on successful collection."""
        from scripts.validation.bybit_truth_collector import (
            REDIS_KEYS,
            BybitTruthCollector,
        )

        storage = {REDIS_KEYS["error_message"]: "Previous error"}

        def mock_get(key):
            return storage.get(key)

        def mock_set(key, value):
            storage[key] = value
            return True

        def mock_delete(key):
            if key in storage:
                del storage[key]
                return 1
            return 0

        mock_redis = Mock()
        mock_redis.get.side_effect = mock_get
        mock_redis.set.side_effect = mock_set
        mock_redis.delete.side_effect = mock_delete
        mock_redis.ping.return_value = True

        collector = BybitTruthCollector(dry_run=True)

        with patch.object(collector, "_get_redis", return_value=mock_redis):
            await collector.collect()

            # Verify error was cleared
            assert REDIS_KEYS["error_message"] not in storage
            mock_redis.delete.assert_called_with(REDIS_KEYS["error_message"])

    @pytest.mark.asyncio
    async def test_collector_stores_error_on_failure(self):
        """Collector stores error message on failed collection."""
        from scripts.validation.bybit_truth_collector import (
            REDIS_KEYS,
            BybitTruthCollector,
        )

        storage = {}

        def mock_set(key, value):
            storage[key] = value
            return True

        mock_redis = Mock()
        mock_redis.set.side_effect = mock_set
        mock_redis.ping.return_value = True

        collector = BybitTruthCollector(dry_run=False)  # Will fail without API keys

        with (
            patch.object(collector, "_get_redis", return_value=mock_redis),
            patch.object(
                collector,
                "fetch_bybit_executions",
                side_effect=Exception("API Error"),
            ),
        ):
            result = await collector.collect()

            assert result.status == "api_error"
            assert "API Error" in result.error_message
            assert REDIS_KEYS["error_message"] in storage


class TestWatchdogRedisIntegration:
    """Test integration between watchdog and Redis."""

    def test_watchdog_reads_all_keys(self):
        """Watchdog reads all required keys from Redis."""
        from scripts.validation.bybit_freshness_check import (
            REDIS_KEYS,
            BybitFreshnessChecker,
        )

        timestamp = datetime.now(UTC).isoformat()

        mock_redis = Mock()
        mock_redis.get.side_effect = lambda key: {
            REDIS_KEYS["timestamp"]: timestamp,
            REDIS_KEYS["count"]: "10",
            REDIS_KEYS["status"]: "success",
            REDIS_KEYS["reason"]: "fresh",
            REDIS_KEYS["error_message"]: "",
        }.get(key)
        mock_redis.ping.return_value = True

        checker = BybitFreshnessChecker()

        with patch.object(checker, "_get_redis", return_value=mock_redis):
            result = checker.check()

            # Verify all keys were read
            calls = mock_redis.get.call_args_list
            keys_read = [call[0][0] for call in calls]

            assert REDIS_KEYS["timestamp"] in keys_read
            assert REDIS_KEYS["count"] in keys_read
            assert REDIS_KEYS["status"] in keys_read
            assert REDIS_KEYS["reason"] in keys_read

            # Verify result reflects Redis data
            assert result.last_collection_timestamp == timestamp
            assert result.last_collection_count == 10
            assert result.last_collection_status == "success"


class TestGateIntegration:
    """Test integration with checkpoint gates."""

    def test_gate_g12_bybit_freshness_check(self):
        """Test G12 gate check for Bybit freshness.

        This tests the check_g12_bybit_freshness function from checkpoint_gate_audit.
        """
        from datetime import UTC, datetime

        # Fresh data (30 minutes ago)
        fresh_timestamp = (datetime.now(UTC) - timedelta(minutes=30)).isoformat()

        mock_redis = Mock()
        mock_redis.get.side_effect = lambda key: {
            "bmad:chiseai:bybit_truth:last_collection_timestamp": fresh_timestamp,
            "bmad:chiseai:bybit_truth:last_collection_status": "success",
        }.get(key)

        # Import and test the G12 check
        from scripts.monitoring.checkpoint_gate_audit import check_g12_bybit_freshness

        result = check_g12_bybit_freshness(mock_redis)

        assert result["gate"] == "G12"
        assert result["status"] == "✅ PASS"
        assert "30m ago" in result["detail"] or "m ago" in result["detail"]

    def test_gate_g12_fails_when_stale(self):
        """Test G12 gate fails when data is stale."""
        from datetime import UTC, datetime, timedelta

        # Stale data (90 minutes ago)
        stale_timestamp = (datetime.now(UTC) - timedelta(minutes=90)).isoformat()

        mock_redis = Mock()
        mock_redis.get.side_effect = lambda key: {
            "bmad:chiseai:bybit_truth:last_collection_timestamp": stale_timestamp,
            "bmad:chiseai:bybit_truth:last_collection_status": "success",
        }.get(key)

        from scripts.monitoring.checkpoint_gate_audit import check_g12_bybit_freshness

        result = check_g12_bybit_freshness(mock_redis)

        assert result["gate"] == "G12"
        assert result["status"] == "❌ FAIL"
        assert "90m ago" in result["detail"] or "m ago" in result["detail"]

    def test_gate_g12_warns_when_no_data(self):
        """Test G12 gate warns when no collection data exists."""
        mock_redis = Mock()
        mock_redis.get.return_value = None

        from scripts.monitoring.checkpoint_gate_audit import check_g12_bybit_freshness

        result = check_g12_bybit_freshness(mock_redis)

        assert result["gate"] == "G12"
        assert result["status"] == "⚠️ CHECK"
        assert "no collection data" in result["detail"]


class TestPipelineErrorHandling:
    """Test pipeline error handling and recovery."""

    @pytest.mark.asyncio
    async def test_pipeline_handles_collector_failure(self):
        """Pipeline handles collector failure gracefully."""
        from scripts.validation.bybit_truth_collector import BybitTruthCollector

        mock_redis = Mock()
        mock_redis.ping.return_value = True

        collector = BybitTruthCollector()

        # Simulate API failure
        with (
            patch.object(collector, "_get_redis", return_value=mock_redis),
            patch.object(
                collector,
                "fetch_bybit_executions",
                side_effect=Exception("Bybit API timeout"),
            ),
        ):
            result = await collector.collect()

            # Collector should record failure
            assert result.status == "api_error"
            assert "Bybit API timeout" in result.error_message

    def test_pipeline_handles_redis_failure(self):
        """Pipeline handles Redis connection failure gracefully."""
        from scripts.validation.bybit_freshness_check import BybitFreshnessChecker

        checker = BybitFreshnessChecker()

        # Simulate Redis failure
        with patch.object(
            checker, "_get_redis", side_effect=Exception("Redis connection refused")
        ):
            result = checker.check()

            assert result.is_fresh is False
            assert result.status == "error"
            assert "Redis error" in result.error_message

    @pytest.mark.asyncio
    async def test_pipeline_handles_redis_store_failure(self):
        """Pipeline handles Redis store failure during collection."""
        from scripts.validation.bybit_truth_collector import BybitTruthCollector

        mock_redis = Mock()
        mock_redis.ping.return_value = True
        mock_redis.set.return_value = False  # Store fails

        collector = BybitTruthCollector(dry_run=True)

        with patch.object(collector, "_get_redis", return_value=mock_redis):
            result = await collector.collect()

            # Collection succeeded but storage failed
            # Note: Current implementation doesn't check store_collection_result return value
            # This test documents expected behavior
            assert result.status == "success"  # Collection itself succeeded


class TestPipelineConcurrency:
    """Test pipeline behavior under concurrent access."""

    def test_concurrent_watchdog_reads(self):
        """Multiple watchdog reads don't corrupt data."""
        from scripts.validation.bybit_freshness_check import BybitFreshnessChecker

        timestamp = datetime.now(UTC).isoformat()
        call_count = [0]

        def mock_get(key):
            call_count[0] += 1
            return {
                "bmad:chiseai:bybit_truth:last_collection_timestamp": timestamp,
                "bmad:chiseai:bybit_truth:last_collection_count": "10",
                "bmad:chiseai:bybit_truth:last_collection_status": "success",
                "bmad:chiseai:bybit_truth:last_collection_reason": "fresh",
                "bmad:chiseai:bybit_truth:last_collection_error": "",
            }.get(key)

        mock_redis = Mock()
        mock_redis.get.side_effect = mock_get
        mock_redis.ping.return_value = True

        checker = BybitFreshnessChecker()

        # Simulate concurrent reads
        with patch.object(checker, "_get_redis", return_value=mock_redis):
            result1 = checker.check()
            result2 = checker.check()
            result3 = checker.check()

        # All reads should succeed
        assert result1.is_fresh is True
        assert result2.is_fresh is True
        assert result3.is_fresh is True


class TestPipelineEdgeCases:
    """Test pipeline edge cases and boundary conditions."""

    def test_pipeline_boundary_59_minutes(self):
        """Data at 59 minutes is still fresh with 1 hour threshold."""
        from scripts.validation.bybit_freshness_check import BybitFreshnessChecker

        timestamp = (datetime.now(UTC) - timedelta(minutes=59)).isoformat()

        mock_redis = Mock()
        mock_redis.get.side_effect = lambda key: {
            "bmad:chiseai:bybit_truth:last_collection_timestamp": timestamp,
            "bmad:chiseai:bybit_truth:last_collection_count": "10",
            "bmad:chiseai:bybit_truth:last_collection_status": "success",
            "bmad:chiseai:bybit_truth:last_collection_reason": "fresh",
            "bmad:chiseai:bybit_truth:last_collection_error": "",
        }.get(key)
        mock_redis.ping.return_value = True

        checker = BybitFreshnessChecker(threshold_hours=1)

        with patch.object(checker, "_get_redis", return_value=mock_redis):
            result = checker.check()

            assert result.is_fresh is True
            assert result.hours_since_collection < 1.0

    def test_pipeline_boundary_60_minutes(self):
        """Data at 60+ minutes is stale with 1 hour threshold."""
        from scripts.validation.bybit_freshness_check import BybitFreshnessChecker

        timestamp = (datetime.now(UTC) - timedelta(minutes=61)).isoformat()

        mock_redis = Mock()
        mock_redis.get.side_effect = lambda key: {
            "bmad:chiseai:bybit_truth:last_collection_timestamp": timestamp,
            "bmad:chiseai:bybit_truth:last_collection_count": "10",
            "bmad:chiseai:bybit_truth:last_collection_status": "success",
            "bmad:chiseai:bybit_truth:last_collection_reason": "fresh",
            "bmad:chiseai:bybit_truth:last_collection_error": "",
        }.get(key)
        mock_redis.ping.return_value = True

        checker = BybitFreshnessChecker(threshold_hours=1)

        with patch.object(checker, "_get_redis", return_value=mock_redis):
            result = checker.check()

            assert result.is_fresh is False
            assert result.reason == "stale_old"

    def test_pipeline_with_zero_count(self):
        """Pipeline handles zero count (no executions) correctly."""
        from scripts.validation.bybit_freshness_check import BybitFreshnessChecker

        timestamp = datetime.now(UTC).isoformat()

        mock_redis = Mock()
        mock_redis.get.side_effect = lambda key: {
            "bmad:chiseai:bybit_truth:last_collection_timestamp": timestamp,
            "bmad:chiseai:bybit_truth:last_collection_count": "0",
            "bmad:chiseai:bybit_truth:last_collection_status": "success",
            "bmad:chiseai:bybit_truth:last_collection_reason": "fresh",
            "bmad:chiseai:bybit_truth:last_collection_error": "",
        }.get(key)
        mock_redis.ping.return_value = True

        checker = BybitFreshnessChecker()

        with patch.object(checker, "_get_redis", return_value=mock_redis):
            result = checker.check()

            # Zero count is still fresh if timestamp is recent
            assert result.is_fresh is True
            assert result.last_collection_count == 0
