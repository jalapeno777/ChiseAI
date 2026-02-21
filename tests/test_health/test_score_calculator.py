"""Additional tests for score calculator module.

For PAPER-003-001: Unified Health Monitoring System
"""

import pytest

from src.health.score_calculator import (
    ComponentScore,
    HealthScore,
    ScoreCalculator,
)
from src.health import ComponentType, HealthStatus


class TestComponentScoreExtended:
    """Extended tests for ComponentScore."""

    def test_weighted_score_calculation(self):
        """Test weighted score calculation."""
        score = ComponentScore(
            component=ComponentType.REDIS,
            score=80.0,
            weight=0.1,
        )
        assert score.weighted_score == 8.0  # 80 * 0.1

    def test_green_status(self):
        """Test GREEN status."""
        score = ComponentScore(ComponentType.REDIS, 95.0, 0.1)
        assert score.status == HealthStatus.GREEN

    def test_red_status(self):
        """Test RED status."""
        score = ComponentScore(ComponentType.REDIS, 50.0, 0.1)
        assert score.status == HealthStatus.RED

    def test_to_dict_with_details(self):
        """Test to_dict with complex details."""
        score = ComponentScore(
            component=ComponentType.REDIS,
            score=85.0,
            weight=0.1,
            details={
                "is_connected": True,
                "error_rate": 0.5,
                "nested": {"key": "value"},
            },
        )
        result = score.to_dict()
        assert result["details"]["nested"]["key"] == "value"


class TestHealthScoreExtended:
    """Extended tests for HealthScore."""

    def test_empty_component_scores(self):
        """Test with no component scores."""
        health = HealthScore(overall_score=0.0, component_scores=[])
        assert health.overall_score == 0.0
        assert health.status == HealthStatus.RED

    def test_red_overall_status(self):
        """Test RED overall status."""
        health = HealthScore(overall_score=50.0, component_scores=[])
        assert health.status == HealthStatus.RED

    def test_get_component_score_found(self):
        """Test getting component score when found."""
        redis_score = ComponentScore(ComponentType.REDIS, 90.0, 0.1)
        health = HealthScore(85.0, [redis_score])

        found = health.get_component_score(ComponentType.REDIS)
        assert found is not None
        assert found.score == 90.0

    def test_get_component_score_not_found(self):
        """Test getting component score when not found."""
        redis_score = ComponentScore(ComponentType.REDIS, 90.0, 0.1)
        health = HealthScore(85.0, [redis_score])

        found = health.get_component_score(ComponentType.INFLUXDB)
        assert found is None

    def test_to_dict_empty_components(self):
        """Test to_dict with no components."""
        health = HealthScore(overall_score=75.0, component_scores=[])
        result = health.to_dict()
        assert result["overall_score"] == 75.0
        assert result["status"] == "yellow"
        assert result["component_scores"] == []


class TestScoreCalculatorExtended:
    """Extended tests for ScoreCalculator."""

    def test_all_component_weights_present(self):
        """Test that all components have weights defined."""
        calculator = ScoreCalculator()

        for component in ComponentType:
            assert (
                component in calculator.COMPONENT_WEIGHTS
            ), f"Missing weight for {component}"

    def test_orchestrator_high_score(self):
        """Test orchestrator score with good health."""
        calculator = ScoreCalculator()
        health_data = {
            "is_running": True,
            "error_rate": 0.0,
            "latency_ms": 500,
            "last_success_seconds_ago": 30,
        }
        score = calculator.calculate_component_score(
            ComponentType.ORCHESTRATOR, health_data
        )
        assert score.score > 80  # Should be high with good metrics

    def test_orchestrator_low_score_not_running(self):
        """Test orchestrator score when not running."""
        calculator = ScoreCalculator()
        health_data = {
            "is_running": False,
            "error_rate": 0.0,
            "latency_ms": 500,
        }
        score = calculator.calculate_component_score(
            ComponentType.ORCHESTRATOR, health_data
        )
        assert score.score <= 60  # Should be low when not running

    def test_orchestrator_high_latency(self):
        """Test orchestrator score with high latency."""
        calculator = ScoreCalculator()
        health_data = {
            "is_running": True,
            "error_rate": 0.0,
            "latency_ms": 2500,  # Very high
            "last_success_seconds_ago": 30,
        }
        score = calculator.calculate_component_score(
            ComponentType.ORCHESTRATOR, health_data
        )
        assert score.score < 100  # Should be reduced due to latency

    def test_orchestrator_inactivity(self):
        """Test orchestrator score with inactivity."""
        calculator = ScoreCalculator()
        health_data = {
            "is_running": True,
            "error_rate": 0.0,
            "latency_ms": 500,
            "last_success_seconds_ago": 300,  # 5 minutes
        }
        score = calculator.calculate_component_score(
            ComponentType.ORCHESTRATOR, health_data
        )
        assert score.score < 100  # Should be reduced due to inactivity

    def test_redis_high_score(self):
        """Test Redis score with good health."""
        calculator = ScoreCalculator()
        health_data = {
            "is_connected": True,
            "error_rate": 0.0,
            "response_time_ms": 10,
            "circuit_breaker_open": False,
        }
        score = calculator.calculate_component_score(ComponentType.REDIS, health_data)
        assert score.score == 100

    def test_redis_disconnected(self):
        """Test Redis score when disconnected."""
        calculator = ScoreCalculator()
        health_data = {
            "is_connected": False,
            "error_rate": 0.0,
            "response_time_ms": 10,
            "circuit_breaker_open": False,
        }
        score = calculator.calculate_component_score(ComponentType.REDIS, health_data)
        assert score.score == 60  # 100 - 40 for disconnected

    def test_redis_circuit_breaker_open(self):
        """Test Redis score with circuit breaker open."""
        calculator = ScoreCalculator()
        health_data = {
            "is_connected": True,
            "error_rate": 0.0,
            "response_time_ms": 10,
            "circuit_breaker_open": True,
        }
        score = calculator.calculate_component_score(ComponentType.REDIS, health_data)
        assert score.score == 70  # 100 - 30 for circuit breaker

    def test_redis_high_error_rate(self):
        """Test Redis score with high error rate."""
        calculator = ScoreCalculator()
        health_data = {
            "is_connected": True,
            "error_rate": 2.0,  # 2% error rate
            "response_time_ms": 10,
            "circuit_breaker_open": False,
        }
        score = calculator.calculate_component_score(ComponentType.REDIS, health_data)
        assert score.score == 50  # 100 - 50 for 2% error rate

    def test_bybit_high_score(self):
        """Test Bybit score with good health."""
        calculator = ScoreCalculator()
        health_data = {
            "is_connected": True,
            "latency_ms": 100,
            "reconnect_count": 0,
            "data_gap_seconds": 0,
        }
        score = calculator.calculate_component_score(ComponentType.BYBIT, health_data)
        assert score.score == 100

    def test_bybit_disconnected(self):
        """Test Bybit score when disconnected."""
        calculator = ScoreCalculator()
        health_data = {
            "is_connected": False,
            "latency_ms": 100,
            "reconnect_count": 0,
            "data_gap_seconds": 0,
        }
        score = calculator.calculate_component_score(ComponentType.BYBIT, health_data)
        assert score.score == 60  # 100 - 40 for disconnected

    def test_bybit_high_latency(self):
        """Test Bybit score with high latency."""
        calculator = ScoreCalculator()
        health_data = {
            "is_connected": True,
            "latency_ms": 1500,  # Very high
            "reconnect_count": 0,
            "data_gap_seconds": 0,
        }
        score = calculator.calculate_component_score(ComponentType.BYBIT, health_data)
        assert score.score == 70  # 100 - 30 for high latency

    def test_bybit_reconnects(self):
        """Test Bybit score with multiple reconnects."""
        calculator = ScoreCalculator()
        health_data = {
            "is_connected": True,
            "latency_ms": 100,
            "reconnect_count": 4,  # 4 reconnects
            "data_gap_seconds": 0,
        }
        score = calculator.calculate_component_score(ComponentType.BYBIT, health_data)
        assert score.score == 80  # 100 - 20 for reconnects

    def test_bybit_data_gap(self):
        """Test Bybit score with data gap."""
        calculator = ScoreCalculator()
        health_data = {
            "is_connected": True,
            "latency_ms": 100,
            "reconnect_count": 0,
            "data_gap_seconds": 50,  # 50 second gap
        }
        score = calculator.calculate_component_score(ComponentType.BYBIT, health_data)
        # Penalty: min((50/10)*10, 30) = min(50, 30) = 30
        assert score.score == 70  # 100 - 30 for 30s+ gap (capped)

    def test_kill_switch_armed(self):
        """Test kill-switch score when armed."""
        calculator = ScoreCalculator()
        health_data = {
            "state": "ARMED",
            "last_test_seconds_ago": 0,
            "error_rate": 0.0,
        }
        score = calculator.calculate_component_score(
            ComponentType.KILL_SWITCH, health_data
        )
        assert score.score == 100

    def test_kill_switch_triggered(self):
        """Test kill-switch score when triggered."""
        calculator = ScoreCalculator()
        health_data = {
            "state": "TRIGGERED",
            "last_test_seconds_ago": 0,
            "error_rate": 0.0,
        }
        score = calculator.calculate_component_score(
            ComponentType.KILL_SWITCH, health_data
        )
        assert score.score == 80  # 100 - 20 for triggered

    def test_kill_switch_old_test(self):
        """Test kill-switch score with old test."""
        calculator = ScoreCalculator()
        health_data = {
            "state": "ARMED",
            "last_test_seconds_ago": 86400 * 3,  # 3 days
            "error_rate": 0.0,
        }
        score = calculator.calculate_component_score(
            ComponentType.KILL_SWITCH, health_data
        )
        assert score.score == 70  # 100 - 30 for 3 days without test

    def test_kill_switch_unknown_state(self):
        """Test kill-switch score with unknown state."""
        calculator = ScoreCalculator()
        health_data = {
            "state": "UNKNOWN",
            "last_test_seconds_ago": 0,
            "error_rate": 0.0,
        }
        score = calculator.calculate_component_score(
            ComponentType.KILL_SWITCH, health_data
        )
        assert score.score == 60  # 100 - 40 for unknown state

    def test_calculate_overall_score_single_component(self):
        """Test overall score with single component."""
        calculator = ScoreCalculator()
        component_scores = [
            ComponentScore(ComponentType.REDIS, 100.0, 1.0),
        ]
        health = calculator.calculate_overall_score(component_scores)
        assert health.overall_score == 100.0

    def test_calculate_overall_score_weighted_average(self):
        """Test overall score is weighted average."""
        calculator = ScoreCalculator()
        component_scores = [
            ComponentScore(ComponentType.REDIS, 100.0, 0.5),
            ComponentScore(ComponentType.INFLUXDB, 0.0, 0.5),
        ]
        health = calculator.calculate_overall_score(component_scores)
        assert health.overall_score == 50.0

    def test_calculate_overall_score_three_components(self):
        """Test overall score with three components."""
        calculator = ScoreCalculator()
        component_scores = [
            ComponentScore(ComponentType.REDIS, 100.0, 0.5),
            ComponentScore(ComponentType.INFLUXDB, 80.0, 0.3),
            ComponentScore(ComponentType.BYBIT, 60.0, 0.2),
        ]
        health = calculator.calculate_overall_score(component_scores)
        # (100 * 0.5 + 80 * 0.3 + 60 * 0.2) / 1.0 = 50 + 24 + 12 = 86
        assert health.overall_score == 86.0

    def test_position_tracker_score(self):
        """Test position tracker score calculation."""
        calculator = ScoreCalculator()
        health_data = {
            "is_running": True,
            "position_count": 5,
        }
        score = calculator.calculate_component_score(
            ComponentType.POSITION_TRACKER, health_data
        )
        assert score.component == ComponentType.POSITION_TRACKER
        assert 0 <= score.score <= 100

    def test_order_simulator_score(self):
        """Test order simulator score calculation."""
        calculator = ScoreCalculator()
        health_data = {
            "is_running": True,
            "order_count": 10,
        }
        score = calculator.calculate_component_score(
            ComponentType.ORDER_SIMULATOR, health_data
        )
        assert score.component == ComponentType.ORDER_SIMULATOR
        assert 0 <= score.score <= 100

    def test_influxdb_score(self):
        """Test InfluxDB score calculation."""
        calculator = ScoreCalculator()
        health_data = {
            "is_connected": True,
            "error_rate": 0.0,
            "response_time_ms": 50,
        }
        score = calculator.calculate_component_score(
            ComponentType.INFLUXDB, health_data
        )
        assert score.component == ComponentType.INFLUXDB
        assert score.score == 100

    def test_postgresql_score(self):
        """Test PostgreSQL score calculation."""
        calculator = ScoreCalculator()
        health_data = {
            "is_connected": True,
            "error_rate": 0.0,
            "response_time_ms": 20,
        }
        score = calculator.calculate_component_score(
            ComponentType.POSTGRESQL, health_data
        )
        assert score.component == ComponentType.POSTGRESQL
        assert score.score == 100

    def test_bitget_score(self):
        """Test Bitget score calculation."""
        calculator = ScoreCalculator()
        health_data = {
            "is_connected": True,
            "latency_ms": 100,
            "reconnect_count": 0,
            "data_gap_seconds": 0,
        }
        score = calculator.calculate_component_score(ComponentType.BITGET, health_data)
        assert score.component == ComponentType.BITGET
        assert score.score == 100

    def test_default_score_for_unknown_data(self):
        """Test default score when unknown component data provided."""
        calculator = ScoreCalculator()
        # Test with a component that doesn't match standard patterns
        # (This shouldn't happen in practice but tests the default case)
        health_data = {"unknown_field": "value"}
        score = calculator.calculate_component_score(
            ComponentType.KILL_SWITCH, health_data
        )
        # Should still return a valid score based on kill-switch logic
        assert 0 <= score.score <= 100

    def test_edge_case_score_bounds(self):
        """Test that scores are always within 0-100 bounds."""
        calculator = ScoreCalculator()

        # Test extreme error rates
        health_data = {
            "is_connected": True,
            "error_rate": 100.0,  # Extreme
            "response_time_ms": 10000,  # Extreme
            "circuit_breaker_open": True,
        }
        score = calculator.calculate_component_score(ComponentType.REDIS, health_data)
        assert score.score == 0  # Should be clamped to 0

        # Test minimum case
        health_data_min = {
            "is_connected": False,
            "error_rate": 0.0,
            "response_time_ms": 0,
            "circuit_breaker_open": False,
        }
        score_min = calculator.calculate_component_score(
            ComponentType.REDIS, health_data_min
        )
        assert score_min.score == 60  # Just disconnected penalty
