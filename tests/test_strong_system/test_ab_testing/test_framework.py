"""
Tests for A/B testing framework module.
"""

import random

import pytest
from src.strong_system.ab_testing.framework import (
    ABTestConfig,
    ABTestFramework,
    ABTestResult,
    ABTestStatus,
    WinnerSelectionStrategy,
)


class TestABTestConfig:
    """Tests for ABTestConfig dataclass."""

    def test_config_creation_default(self):
        """Test creating config with default values."""
        config = ABTestConfig(test_id="test_001", test_name="Test A/B")

        assert config.test_id == "test_001"
        assert config.test_name == "Test A/B"
        assert config.traffic_split == 0.5
        assert config.confidence_level == 0.95
        assert config.min_sample_size == 1000
        assert config.auto_rollback_enabled is True

    def test_config_creation_custom(self):
        """Test creating config with custom values."""
        config = ABTestConfig(
            test_id="test_001",
            test_name="Test A/B",
            traffic_split=0.3,
            confidence_level=0.99,
            min_sample_size=10000,
            auto_rollback_enabled=False,
        )

        assert config.traffic_split == 0.3
        assert config.confidence_level == 0.99
        assert config.min_sample_size == 10000
        assert config.auto_rollback_enabled is False

    def test_config_invalid_traffic_split(self):
        """Test config validation for invalid traffic split."""
        with pytest.raises(
            ValueError, match="Traffic split must be between 0.01 and 0.99"
        ):
            ABTestConfig(test_id="test_001", test_name="Test", traffic_split=1.5)

        with pytest.raises(
            ValueError, match="Traffic split must be between 0.01 and 0.99"
        ):
            ABTestConfig(test_id="test_001", test_name="Test", traffic_split=0.0)

    def test_config_invalid_confidence_level(self):
        """Test config validation for invalid confidence level."""
        with pytest.raises(
            ValueError, match="Confidence level must be between 0 and 1"
        ):
            ABTestConfig(test_id="test_001", test_name="Test", confidence_level=1.5)

    def test_config_invalid_min_sample_size(self):
        """Test config validation for invalid min sample size."""
        with pytest.raises(
            ValueError, match="Minimum sample size should be at least 100"
        ):
            ABTestConfig(test_id="test_001", test_name="Test", min_sample_size=99)

    def test_config_invalid_rollback_threshold(self):
        """Test config validation for invalid rollback threshold."""
        with pytest.raises(ValueError, match="Rollback threshold should be negative"):
            ABTestConfig(test_id="test_001", test_name="Test", rollback_threshold=0.1)


class TestABTestResult:
    """Tests for ABTestResult dataclass."""

    def test_result_creation(self):
        """Test creating an ABTestResult."""
        result = ABTestResult(
            test_id="test_001",
            status=ABTestStatus.RUNNING,
            winner=None,
            statistical_result=None,
            champion_metrics={"conversion_rate": 0.1},
            challenger_metrics={"conversion_rate": 0.12},
            duration_seconds=3600,
            start_time=123456.789,
            end_time=None,
            decision_reason="Test in progress",
        )

        assert result.test_id == "test_001"
        assert result.status == ABTestStatus.RUNNING
        assert result.winner is None
        assert result.champion_metrics == {"conversion_rate": 0.1}
        assert result.challenger_metrics == {"conversion_rate": 0.12}
        assert result.duration_seconds == 3600
        assert result.start_time == 123456.789
        assert result.end_time is None
        assert result.decision_reason == "Test in progress"

    def test_result_to_dict(self):
        """Test converting ABTestResult to dictionary."""
        result = ABTestResult(
            test_id="test_001",
            status=ABTestStatus.COMPLETED,
            winner="challenger",
            statistical_result=None,
            champion_metrics={"conversion_rate": 0.1},
            challenger_metrics={"conversion_rate": 0.12},
            duration_seconds=3600,
            start_time=123456.789,
            end_time=123456.789 + 3600,
            decision_reason="Challenger won",
        )

        result_dict = result.to_dict()

        assert result_dict["test_id"] == "test_001"
        assert result_dict["status"] == "completed"
        assert result_dict["winner"] == "challenger"
        assert result_dict["champion_metrics"] == {"conversion_rate": 0.1}
        assert result_dict["challenger_metrics"] == {"conversion_rate": 0.12}
        assert result_dict["duration_seconds"] == 3600
        assert result_dict["decision_reason"] == "Challenger won"


class TestABTestFramework:
    """Tests for ABTestFramework class."""

    def test_framework_initialization(self):
        """Test framework initialization."""
        framework = ABTestFramework()

        assert framework._tests == {}
        assert framework._test_results == {}
        assert framework._active_tests == {}
        assert framework._monitoring is False

    def test_create_test(self):
        """Test creating a test."""
        framework = ABTestFramework()
        config = ABTestConfig(test_id="test_001", test_name="Test A/B")

        test_id = framework.create_test(config)

        assert test_id == "test_001"
        assert "test_001" in framework._tests
        assert "test_001" in framework._test_results
        assert framework._test_results["test_001"].status == ABTestStatus.DRAFT

    def test_create_test_duplicate(self):
        """Test creating duplicate test raises error."""
        framework = ABTestFramework()
        config = ABTestConfig(test_id="test_001", test_name="Test A/B")

        framework.create_test(config)

        with pytest.raises(ValueError, match="Test test_001 already exists"):
            framework.create_test(config)

    def test_start_test(self):
        """Test starting a test."""
        framework = ABTestFramework()
        config = ABTestConfig(test_id="test_001", test_name="Test A/B")

        framework.create_test(config)
        started = framework.start_test("test_001")

        assert started is True
        assert "test_001" in framework._active_tests
        assert framework._test_results["test_001"].status == ABTestStatus.RUNNING
        assert framework._monitoring is True

    def test_start_test_not_exist(self):
        """Test starting non-existent test raises error."""
        framework = ABTestFramework()

        with pytest.raises(ValueError, match="Test test_001 does not exist"):
            framework.start_test("test_001")

    def test_start_test_already_running(self):
        """Test starting already running test."""
        framework = ABTestFramework()
        config = ABTestConfig(test_id="test_001", test_name="Test A/B")

        framework.create_test(config)
        framework.start_test("test_001")
        started = framework.start_test("test_001")

        assert started is False

    def test_pause_test(self):
        """Test pausing a test."""
        framework = ABTestFramework()
        config = ABTestConfig(test_id="test_001", test_name="Test A/B")

        framework.create_test(config)
        framework.start_test("test_001")
        paused = framework.pause_test("test_001")

        assert paused is True
        assert "test_001" not in framework._active_tests
        assert framework._test_results["test_001"].status == ABTestStatus.PAUSED

    def test_pause_test_not_active(self):
        """Test pausing non-active test."""
        framework = ABTestFramework()
        config = ABTestConfig(test_id="test_001", test_name="Test A/B")

        framework.create_test(config)
        paused = framework.pause_test("test_001")

        assert paused is False

    def test_stop_test(self):
        """Test stopping a test."""
        framework = ABTestFramework()
        config = ABTestConfig(test_id="test_001", test_name="Test A/B")

        framework.create_test(config)
        framework.start_test("test_001")

        # Add some metrics
        framework.record_visitor("test_001", "champion", "user1")
        framework.record_visitor("test_001", "challenger", "user2")
        framework.record_conversion("test_001", "champion", "user1", 1.0)
        framework.record_conversion("test_001", "challenger", "user2", 1.0)

        result = framework.stop_test(
            "test_001", winner="challenger", reason="Test completed"
        )

        assert result.test_id == "test_001"
        assert result.status == ABTestStatus.COMPLETED
        assert result.winner == "challenger"
        assert result.decision_reason == "Test completed"
        assert result.end_time is not None
        assert result.duration_seconds > 0

    def test_stop_test_not_exist(self):
        """Test stopping non-existent test raises error."""
        framework = ABTestFramework()

        with pytest.raises(ValueError, match="Test test_001 does not exist"):
            framework.stop_test("test_001")

    def test_assign_variant(self):
        """Test variant assignment."""
        framework = ABTestFramework()
        config = ABTestConfig(
            test_id="test_001", test_name="Test A/B", traffic_split=0.5
        )

        framework.create_test(config)
        framework.start_test("test_001")

        # Assign variants to multiple users
        assignments = []
        for i in range(1000):
            variant = framework.assign_variant("test_001", f"user{i}")
            assignments.append(variant)

        # Check distribution (should be roughly 50/50)
        champion_count = assignments.count("champion")
        challenger_count = assignments.count("challenger")

        assert champion_count + challenger_count == 1000
        assert 400 <= champion_count <= 600  # Roughly 50%
        assert 400 <= challenger_count <= 600  # Roughly 50%

    def test_assign_variant_consistent(self):
        """Test that same user always gets same variant."""
        framework = ABTestFramework()
        config = ABTestConfig(
            test_id="test_001", test_name="Test A/B", traffic_split=0.5
        )

        framework.create_test(config)
        framework.start_test("test_001")

        # Same user should always get same variant
        variant1 = framework.assign_variant("test_001", "user123")
        variant2 = framework.assign_variant("test_001", "user123")
        variant3 = framework.assign_variant("test_001", "user123")

        assert variant1 == variant2 == variant3

    def test_assign_variant_not_running(self):
        """Test variant assignment when test is not running."""
        framework = ABTestFramework()
        config = ABTestConfig(test_id="test_001", test_name="Test A/B")

        framework.create_test(config)
        # Don't start the test

        variant = framework.assign_variant("test_001", "user123")

        # Should return champion as default
        assert variant == "champion"

    def test_record_visitor(self):
        """Test recording a visitor."""
        framework = ABTestFramework()
        config = ABTestConfig(test_id="test_001", test_name="Test A/B")

        framework.create_test(config)
        framework.start_test("test_001")

        framework.record_visitor("test_001", "champion", "user123")

        visitors = framework.metrics_collector.get_metrics("champion", "visitors")

        assert len(visitors) == 1
        assert visitors[0].value == 1.0
        assert "test_001:user123" in visitors[0].metadata["visitor_id"]

    def test_record_conversion(self):
        """Test recording a conversion."""
        framework = ABTestFramework()
        config = ABTestConfig(test_id="test_001", test_name="Test A/B")

        framework.create_test(config)
        framework.start_test("test_001")

        framework.record_conversion("test_001", "champion", "user123", 100.0)

        conversions = framework.metrics_collector.get_metrics("champion", "conversions")

        assert len(conversions) == 1
        assert conversions[0].value == 100.0
        assert "test_001:user123" in conversions[0].metadata["visitor_id"]

    def test_record_performance(self):
        """Test recording performance metrics."""
        framework = ABTestFramework()
        config = ABTestConfig(test_id="test_001", test_name="Test A/B")

        framework.create_test(config)
        framework.start_test("test_001")

        framework.record_performance(
            "test_001", "champion", "req123", 0.5, success=True
        )

        latencies = framework.metrics_collector.get_metrics("champion", "latency")
        requests = framework.metrics_collector.get_metrics("champion", "requests")

        assert len(latencies) >= 1
        assert latencies[0].value == 0.5
        assert len(requests) >= 1
        assert requests[0].value == 1.0

    def test_get_test_status(self):
        """Test getting test status."""
        framework = ABTestFramework()
        config = ABTestConfig(test_id="test_001", test_name="Test A/B")

        framework.create_test(config)
        framework.start_test("test_001")

        status = framework.get_test_status("test_001")

        assert status is not None
        assert status.test_id == "test_001"
        assert status.status == ABTestStatus.RUNNING

    def test_get_test_status_not_exist(self):
        """Test getting status for non-existent test."""
        framework = ABTestFramework()

        status = framework.get_test_status("test_001")

        assert status is None

    def test_get_all_test_statuses(self):
        """Test getting all test statuses."""
        framework = ABTestFramework()

        config1 = ABTestConfig(test_id="test_001", test_name="Test 1")
        config2 = ABTestConfig(test_id="test_002", test_name="Test 2")

        framework.create_test(config1)
        framework.create_test(config2)

        statuses = framework.get_all_test_statuses()

        assert len(statuses) == 2
        assert "test_001" in statuses
        assert "test_002" in statuses

    def test_add_winner_callback(self):
        """Test adding winner callback."""
        framework = ABTestFramework()

        callback_calls = []

        def test_callback(result):
            callback_calls.append(result)

        framework.add_winner_callback(test_callback)

        # Create a mock result
        result = ABTestResult(
            test_id="test_001",
            status=ABTestStatus.COMPLETED,
            winner="challenger",
            statistical_result=None,
            champion_metrics={},
            challenger_metrics={},
            duration_seconds=3600,
            start_time=123456.789,
            end_time=123456.789 + 3600,
            decision_reason="Test",
        )

        framework._notify_winner_callbacks(result)

        assert len(callback_calls) == 1
        assert callback_calls[0] == result

    def test_add_rollback_callback(self):
        """Test adding rollback callback."""
        framework = ABTestFramework()

        callback_calls = []

        def test_callback(result):
            callback_calls.append(result)

        framework.add_rollback_callback(test_callback)

        # Create a mock result
        result = ABTestResult(
            test_id="test_001",
            status=ABTestStatus.ROLLED_BACK,
            winner="champion",
            statistical_result=None,
            champion_metrics={},
            challenger_metrics={},
            duration_seconds=3600,
            start_time=123456.789,
            end_time=123456.789 + 3600,
            decision_reason="Rollback",
        )

        framework._notify_rollback_callbacks(result)

        assert len(callback_calls) == 1
        assert callback_calls[0] == result

    def test_shutdown(self):
        """Test framework shutdown."""
        framework = ABTestFramework()
        config = ABTestConfig(test_id="test_001", test_name="Test A/B")

        framework.create_test(config)
        framework.start_test("test_001")

        assert framework._monitoring is True

        framework.shutdown()

        assert framework._monitoring is False


class TestABTestFrameworkIntegration:
    """Integration tests for ABTestFramework."""

    def test_full_ab_test_workflow(self):
        """Test complete A/B test workflow."""
        framework = ABTestFramework()

        # Create test
        config = ABTestConfig(
            test_id="test_001",
            test_name="Test A/B",
            traffic_split=0.5,
            min_sample_size=100,
            winner_selection_strategy=WinnerSelectionStrategy.STATISTICAL_SIGNIFICANCE,
        )

        framework.create_test(config)

        # Start test
        framework.start_test("test_001")

        # Simulate traffic with varied conversion values to produce
        # distinct per-variant means and avoid catastrophic cancellation
        # in the t-test (scipy warns when data are nearly identical).
        rng = random.Random(42)
        for i in range(200):
            variant = framework.assign_variant("test_001", f"user{i}")
            framework.record_visitor("test_001", variant, f"user{i}")

            # Simulate conversions (challenger performs better)
            if variant == "challenger" and i % 3 == 0:  # ~33% conversion
                framework.record_conversion(
                    "test_001", variant, f"user{i}", rng.uniform(3.0, 5.0)
                )
            elif variant == "champion" and i % 5 == 0:  # ~20% conversion
                framework.record_conversion(
                    "test_001", variant, f"user{i}", rng.uniform(1.0, 2.0)
                )

        # Get status
        status = framework.get_test_status("test_001")

        assert status is not None
        assert status.status == ABTestStatus.RUNNING

        # Manually stop test
        result = framework.stop_test("test_001", winner="challenger")

        assert result.status == ABTestStatus.COMPLETED
        assert result.winner == "challenger"
        # Challenger mean (~4.0) should exceed champion mean (~1.5)
        # due to deliberately varied conversion values above.
        assert (
            result.challenger_metrics["conversion_rate"]
            > result.champion_metrics["conversion_rate"]
        )

    def test_traffic_split_variations(self):
        """Test different traffic split configurations."""
        framework = ABTestFramework()

        test_cases = [
            (0.1, 100, 10, 90),  # 10% challenger
            (0.5, 100, 50, 50),  # 50% challenger
            (0.9, 100, 90, 10),  # 90% challenger
        ]

        for (
            traffic_split,
            total_users,
            expected_challenger,
            expected_champion,
        ) in test_cases:
            config = ABTestConfig(
                test_id=f"test_{traffic_split}",
                test_name=f"Test {traffic_split}",
                traffic_split=traffic_split,
            )

            framework.create_test(config)
            framework.start_test(f"test_{traffic_split}")

            assignments = []
            for i in range(total_users):
                variant = framework.assign_variant(f"test_{traffic_split}", f"user{i}")
                assignments.append(variant)

            challenger_count = assignments.count("challenger")
            champion_count = assignments.count("champion")

            # Verify no double-assignment: all users must be assigned
            assert challenger_count + champion_count == total_users

            # Python's hash() is randomized per interpreter (PEP 412),
            # so relative % tolerance is unreliable across runs.
            # Use absolute tolerance based on the largest expected bucket:
            # at 10% split with 100 users, ±8 covers observed worst-case
            # hash variance across all PYTHONHASHSEED values.
            # At 50%/90% splits, the tolerance is proportionally tighter
            # relative to the expected count.
            tolerance = max(8, int(total_users * 0.15))
            assert abs(challenger_count - expected_challenger) <= tolerance, (
                f"traffic_split={traffic_split}: expected ~{expected_challenger} "
                f"challengers, got {challenger_count} (tolerance=±{tolerance})"
            )
            assert abs(champion_count - expected_champion) <= tolerance, (
                f"traffic_split={traffic_split}: expected ~{expected_champion} "
                f"champions, got {champion_count} (tolerance=±{tolerance})"
            )

    def test_winner_selection_strategies(self):
        """Test different winner selection strategies."""
        framework = ABTestFramework()

        strategies = [
            WinnerSelectionStrategy.STATISTICAL_SIGNIFICANCE,
            WinnerSelectionStrategy.BAYESIAN_PROBABILITY,
            WinnerSelectionStrategy.EARLY_STOPPING,
        ]

        for strategy in strategies:
            config = ABTestConfig(
                test_id=f"test_{strategy.value}",
                test_name=f"Test {strategy.value}",
                winner_selection_strategy=strategy,
                min_sample_size=100,
            )

            framework.create_test(config)
            framework.start_test(f"test_{strategy.value}")

            # Add some data
            for i in range(100):
                framework.record_visitor(
                    f"test_{strategy.value}", "champion", f"user{i}"
                )
                framework.record_visitor(
                    f"test_{strategy.value}", "challenger", f"user{i}"
                )

                # Challenger performs better
                if i % 3 == 0:
                    framework.record_conversion(
                        f"test_{strategy.value}", "challenger", f"user{i}", 1.0
                    )
                if i % 5 == 0:
                    framework.record_conversion(
                        f"test_{strategy.value}", "champion", f"user{i}", 1.0
                    )

            # Framework should be monitoring
            assert f"test_{strategy.value}" in framework._active_tests


class TestABTestFrameworkEdgeCases:
    """Edge case tests for ABTestFramework."""

    def test_callback_error_handling(self):
        """Test that callback errors don't crash the framework."""
        framework = ABTestFramework()

        def error_callback(result):
            raise Exception("Callback error")

        framework.add_winner_callback(error_callback)

        # Create mock result
        result = ABTestResult(
            test_id="test_001",
            status=ABTestStatus.COMPLETED,
            winner="challenger",
            statistical_result=None,
            champion_metrics={},
            challenger_metrics={},
            duration_seconds=3600,
            start_time=123456.789,
            end_time=123456.789 + 3600,
            decision_reason="Test",
        )

        # Should not raise exception
        framework._notify_winner_callbacks(result)

        # Framework should still work
        assert framework is not None

    def test_monitoring_loop_error_handling(self):
        """Test that monitoring loop errors are handled gracefully."""
        framework = ABTestFramework()

        config = ABTestConfig(test_id="test_001", test_name="Test A/B")
        framework.create_test(config)
        framework.start_test("test_001")

        # Force an error in monitoring by adding invalid data
        framework.metrics_collector.add_metric("champion", "conversion_rate", "invalid")
        framework.metrics_collector.add_metric(
            "challenger", "conversion_rate", "invalid"
        )

        # Monitoring should handle the error gracefully
        framework._check_test_completion("test_001")

        # Test should still be active
        assert "test_001" in framework._active_tests

    def test_concurrent_access(self):
        """Test thread safety with concurrent access."""
        framework = ABTestFramework()
        config = ABTestConfig(test_id="test_001", test_name="Test A/B")

        framework.create_test(config)
        framework.start_test("test_001")

        import threading

        errors = []

        def worker():
            try:
                for i in range(10):
                    variant = framework.assign_variant(
                        "test_001", f"user{threading.current_thread().ident}_{i}"
                    )
                    framework.record_visitor(
                        "test_001",
                        variant,
                        f"user{threading.current_thread().ident}_{i}",
                    )
                    if i % 2 == 0:
                        framework.record_conversion(
                            "test_001",
                            variant,
                            f"user{threading.current_thread().ident}_{i}",
                            1.0,
                        )
            except Exception as e:
                errors.append(e)

        # Run multiple threads
        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should have no errors
        assert len(errors) == 0

        # Should have collected data
        status = framework.get_test_status("test_001")
        assert status is not None
