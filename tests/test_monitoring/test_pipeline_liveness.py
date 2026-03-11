"""Tests for pipeline liveness monitoring.

Validates that pipeline health checks correctly detect:
- Healthy pipeline with signals
- Healthy no-signal condition (analysis running but no actionable signals)
- Stale pipeline detection (no signals in 15 minutes)
- Consumer backlog calculation

Part of PAPER-DIAG-001: Implement robust pipeline health checks.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

# Add project root to path
import sys
import os

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from scripts.monitoring.scheduler_heartbeat import (
    check_pipeline_liveness,
    record_enhanced_heartbeat,
    run_liveness_check,
    LIVENESS_KEY,
    HEARTBEAT_TTL_SECONDS,
)


class TestCheckPipelineLiveness:
    """Tests for check_pipeline_liveness function."""

    def test_no_redis_client_returns_no_data(self):
        """Test that None client returns no_recent_data status."""
        result = check_pipeline_liveness(None, max_stale_minutes=15)

        assert result["status"] == "no_recent_data"
        assert result["healthy"] is False
        assert result["analysis_attempts_last_15m"] == 0
        assert result["latest_signal_age_minutes"] is None

    def test_healthy_pipeline_with_signals(self):
        """Test healthy state when signals exist in last 15m (AC1)."""
        mock_redis = MagicMock()

        now = datetime.now(UTC)
        five_min_ago = (now - timedelta(minutes=5)).isoformat()

        # Mock scan to return signal keys
        mock_redis.scan.side_effect = [
            (0, ["paper:signal:test-1", "paper:signal:test-2"]),
        ]

        # Mock scan_iter for backlog calculation
        mock_redis.scan_iter.return_value = [
            "paper:signal:test-1",
            "paper:signal:test-2",
        ]

        # Mock hgetall to return signal data with timestamps
        def mock_hgetall(key):
            return {
                "timestamp": five_min_ago,
                "status": "actionable",
                "symbol": "BTCUSDT",
            }

        mock_redis.hgetall = mock_hgetall
        mock_redis.scard.return_value = 0

        result = check_pipeline_liveness(mock_redis, max_stale_minutes=15)

        assert result["healthy"] is True
        assert result["status"] == "healthy"
        assert result["analysis_attempts_last_15m"] == 2
        assert result["actionable_signals_last_15m"] == 2
        assert result["consumer_backlog"] == 2

    def test_healthy_no_actionable_signals(self):
        """Test healthy no-signal condition (AC3).

        When signals exist but none are actionable, pipeline is healthy.
        """
        mock_redis = MagicMock()

        now = datetime.now(UTC)
        five_min_ago = (now - timedelta(minutes=5)).isoformat()

        mock_redis.scan.side_effect = [
            (0, ["paper:signal:test-1", "paper:signal:test-2"]),
        ]

        def mock_hgetall(key):
            return {
                "timestamp": five_min_ago,
                "status": "hold",  # Not actionable
                "symbol": "BTCUSDT",
            }

        mock_redis.hgetall = mock_hgetall
        mock_redis.scard.return_value = 0

        result = check_pipeline_liveness(mock_redis, max_stale_minutes=15)

        # AC3: Healthy no-signal condition should pass
        assert result["healthy"] is True
        assert result["status"] == "healthy"
        assert result["analysis_attempts_last_15m"] == 2
        assert result["actionable_signals_last_15m"] == 0

    def test_stale_pipeline_detection(self):
        """Test stale pipeline detection (AC2).

        If no signals in last 15 minutes, pipeline is stale.
        """
        mock_redis = MagicMock()

        now = datetime.now(UTC)
        # Signal timestamp is 20 minutes old
        old_time = (now - timedelta(minutes=20)).isoformat()

        mock_redis.scan.side_effect = [
            (0, ["paper:signal:test-1"]),
        ]

        def mock_hgetall(key):
            return {
                "timestamp": old_time,
                "status": "actionable",
                "symbol": "BTCUSDT",
            }

        mock_redis.hgetall = mock_hgetall
        mock_redis.scard.return_value = 0

        result = check_pipeline_liveness(mock_redis, max_stale_minutes=15)

        # AC2: Stale loop detectable within 15 minutes
        assert result["healthy"] is False
        assert result["status"] == "stale"
        assert result["analysis_attempts_last_15m"] == 0

    def test_no_recent_data_when_no_signals(self):
        """Test no_recent_data status when no signals exist."""
        mock_redis = MagicMock()

        # No signals at all
        mock_redis.scan.side_effect = [(0, [])]
        mock_redis.scard.return_value = 0

        result = check_pipeline_liveness(mock_redis, max_stale_minutes=15)

        assert result["healthy"] is False
        assert result["status"] == "no_recent_data"
        assert result["latest_signal_age_minutes"] is None

    def test_consumer_backlog_calculation(self):
        """Test consumer backlog metric calculation (AC4)."""
        mock_redis = MagicMock()

        now = datetime.now(UTC)
        five_min_ago = (now - timedelta(minutes=5)).isoformat()

        # Simulate 15 total signals
        signal_keys = [f"paper:signal:test-{i}" for i in range(15)]
        mock_redis.scan.side_effect = [
            (0, signal_keys),
        ]

        # Mock scan_iter for backlog calculation
        mock_redis.scan_iter.return_value = signal_keys

        def mock_hgetall(key):
            return {
                "timestamp": five_min_ago,
                "status": "actionable",
            }

        mock_redis.hgetall = mock_hgetall

        # Only 5 processed
        mock_redis.scard.return_value = 5

        result = check_pipeline_liveness(mock_redis, max_stale_minutes=15)

        # AC4: Consumer backlog metric implemented
        assert result["consumer_backlog"] == 10
        assert result["healthy"] is True

    def test_high_backlog_warning(self):
        """Test that high backlog is tracked but doesn't fail health."""
        mock_redis = MagicMock()

        now = datetime.now(UTC)
        five_min_ago = (now - timedelta(minutes=5)).isoformat()

        # High backlog (>10 signals)
        signal_keys = [f"paper:signal:test-{i}" for i in range(25)]
        mock_redis.scan.side_effect = [
            (0, signal_keys),
        ]

        # Mock scan_iter for backlog calculation
        mock_redis.scan_iter.return_value = signal_keys

        def mock_hgetall(key):
            return {
                "timestamp": five_min_ago,
                "status": "actionable",
            }

        mock_redis.hgetall = mock_hgetall
        mock_redis.scard.return_value = 5  # 20 unprocessed

        result = check_pipeline_liveness(mock_redis, max_stale_minutes=15)

        assert result["consumer_backlog"] == 20
        assert result["consumer_backlog"] > 10
        # Pipeline is still healthy because signals exist
        assert result["healthy"] is True

    def test_consumer_backlog_cannot_be_negative(self):
        """Test that backlog cannot go negative (processed > total edge case)."""
        mock_redis = MagicMock()

        now = datetime.now(UTC)
        five_min_ago = (now - timedelta(minutes=5)).isoformat()

        mock_redis.scan.side_effect = [
            (0, ["paper:signal:test-1"]),  # 1 signal
        ]

        def mock_hgetall(key):
            return {
                "timestamp": five_min_ago,
                "status": "actionable",
            }

        mock_redis.hgetall = mock_hgetall
        mock_redis.scard.return_value = 5  # But 5 processed somehow

        result = check_pipeline_liveness(mock_redis, max_stale_minutes=15)

        # Backlog should be 0, not -4
        assert result["consumer_backlog"] == 0

    def test_latest_signal_age_calculation(self):
        """Test that latest signal age is correctly calculated."""
        mock_redis = MagicMock()

        now = datetime.now(UTC)
        two_min_ago = (now - timedelta(minutes=2)).isoformat()

        mock_redis.scan.side_effect = [
            (0, ["paper:signal:test-1"]),
        ]

        def mock_hgetall(key):
            return {
                "timestamp": two_min_ago,
                "status": "actionable",
            }

        mock_redis.hgetall = mock_hgetall
        mock_redis.scard.return_value = 0

        result = check_pipeline_liveness(mock_redis, max_stale_minutes=15)

        # Should be approximately 2 minutes
        assert result["latest_signal_age_minutes"] is not None
        assert 1.5 <= result["latest_signal_age_minutes"] <= 2.5


class TestRecordEnhancedHeartbeat:
    """Tests for record_enhanced_heartbeat function."""

    def test_records_liveness_data(self):
        """Test that liveness data is recorded to Redis (AC1)."""
        mock_redis = MagicMock()

        liveness_data = {
            "healthy": True,
            "latest_signal_age_minutes": 5.0,
            "analysis_attempts_last_15m": 10,
            "actionable_signals_last_15m": 3,
            "consumer_backlog": 2,
            "status": "healthy",
        }

        result = record_enhanced_heartbeat(mock_redis, liveness_data)

        assert result is True
        mock_redis.hset.assert_called_once()
        mock_redis.expire.assert_called_once_with(LIVENESS_KEY, HEARTBEAT_TTL_SECONDS)

        # Verify the data was stored
        call_args = mock_redis.hset.call_args
        assert call_args[1]["mapping"]["status"] == "running"
        assert call_args[1]["mapping"]["pipeline_status"] == "healthy"
        assert call_args[1]["mapping"]["analysis_attempts_15m"] == "10"
        assert call_args[1]["mapping"]["actionable_signals_15m"] == "3"
        assert call_args[1]["mapping"]["consumer_backlog"] == "2"

    def test_degraded_status_recorded(self):
        """Test that degraded status is recorded when unhealthy."""
        mock_redis = MagicMock()

        liveness_data = {
            "healthy": False,
            "latest_signal_age_minutes": 25.0,
            "analysis_attempts_last_15m": 0,
            "actionable_signals_last_15m": 0,
            "consumer_backlog": 0,
            "status": "stale",
        }

        result = record_enhanced_heartbeat(mock_redis, liveness_data)

        assert result is True
        call_args = mock_redis.hset.call_args
        assert call_args[1]["mapping"]["status"] == "degraded"
        assert call_args[1]["mapping"]["pipeline_status"] == "stale"

    def test_handles_redis_error(self):
        """Test that Redis errors are handled gracefully."""
        mock_redis = MagicMock()
        mock_redis.hset.side_effect = Exception("Redis connection error")

        liveness_data = {
            "healthy": True,
            "latest_signal_age_minutes": 5.0,
            "analysis_attempts_last_15m": 10,
            "actionable_signals_last_15m": 3,
            "consumer_backlog": 2,
            "status": "healthy",
        }

        result = record_enhanced_heartbeat(mock_redis, liveness_data)

        assert result is False


class TestRunLivenessCheck:
    """Tests for run_liveness_check integration."""

    @patch("scripts.monitoring.scheduler_heartbeat.get_redis_client")
    def test_integration_healthy_pipeline(self, mock_get_client):
        """Test full integration for healthy pipeline."""
        mock_redis = MagicMock()
        mock_get_client.return_value = mock_redis

        now = datetime.now(UTC)
        five_min_ago = (now - timedelta(minutes=5)).isoformat()

        mock_redis.scan.side_effect = [
            (0, ["paper:signal:test-1", "paper:signal:test-2"]),
        ]

        def mock_hgetall(key):
            return {
                "timestamp": five_min_ago,
                "status": "actionable",
            }

        mock_redis.hgetall = mock_hgetall
        mock_redis.scard.return_value = 0

        result = run_liveness_check()

        assert result["healthy"] is True
        assert result["analysis_attempts_last_15m"] == 2
        mock_get_client.assert_called_once()

    @patch("scripts.monitoring.scheduler_heartbeat.get_redis_client")
    def test_integration_connection_failure(self, mock_get_client):
        """Test handling of Redis connection failure."""
        mock_get_client.return_value = None

        result = run_liveness_check()

        assert result["healthy"] is False
        assert "error" in result


class TestStaleDetectionEdgeCases:
    """Edge case tests for stale detection."""

    def test_exactly_at_threshold_boundary(self):
        """Test behavior at exactly 15 minute boundary."""
        mock_redis = MagicMock()

        now = datetime.now(UTC)
        exactly_15m_ago = now - timedelta(minutes=15)

        mock_redis.scan.side_effect = [
            (0, ["paper:signal:test-1"]),
        ]

        def mock_hgetall(key):
            return {
                "timestamp": exactly_15m_ago.isoformat(),
                "status": "actionable",
            }

        mock_redis.hgetall = mock_hgetall
        mock_redis.scard.return_value = 0

        result = check_pipeline_liveness(mock_redis, max_stale_minutes=15)

        # Exactly at threshold should count as stale (> comparison)
        assert result["analysis_attempts_last_15m"] == 0

    def test_just_inside_threshold(self):
        """Test behavior just inside 15 minute window."""
        mock_redis = MagicMock()

        now = datetime.now(UTC)
        just_inside = now - timedelta(minutes=14, seconds=59)

        mock_redis.scan.side_effect = [
            (0, ["paper:signal:test-1"]),
        ]

        def mock_hgetall(key):
            return {
                "timestamp": just_inside.isoformat(),
                "status": "actionable",
            }

        mock_redis.hgetall = mock_hgetall
        mock_redis.scard.return_value = 0

        result = check_pipeline_liveness(mock_redis, max_stale_minutes=15)

        assert result["analysis_attempts_last_15m"] == 1
        assert result["healthy"] is True

    def test_just_outside_threshold(self):
        """Test behavior just outside 15 minute window."""
        mock_redis = MagicMock()

        now = datetime.now(UTC)
        just_outside = now - timedelta(minutes=15, seconds=1)

        mock_redis.scan.side_effect = [
            (0, ["paper:signal:test-1"]),
        ]

        def mock_hgetall(key):
            return {
                "timestamp": just_outside.isoformat(),
                "status": "actionable",
            }

        mock_redis.hgetall = mock_hgetall
        mock_redis.scard.return_value = 0

        result = check_pipeline_liveness(mock_redis, max_stale_minutes=15)

        assert result["analysis_attempts_last_15m"] == 0
        assert result["healthy"] is False


class TestMetricsCalculation:
    """Tests for various metric calculations."""

    def test_multiple_signal_keys_pagination(self):
        """Test that scan pagination works correctly."""
        mock_redis = MagicMock()

        now = datetime.now(UTC)
        five_min_ago = (now - timedelta(minutes=5)).isoformat()

        # Simulate pagination with multiple scan calls
        mock_redis.scan.side_effect = [
            (1, ["paper:signal:test-1", "paper:signal:test-2"]),
            (0, ["paper:signal:test-3"]),
        ]

        def mock_hgetall(key):
            return {
                "timestamp": five_min_ago,
                "status": "actionable",
            }

        mock_redis.hgetall = mock_hgetall
        mock_redis.scard.return_value = 0

        result = check_pipeline_liveness(mock_redis, max_stale_minutes=15)

        assert result["analysis_attempts_last_15m"] == 3

    def test_invalid_timestamp_handled_gracefully(self):
        """Test that invalid timestamps don't crash the function."""
        mock_redis = MagicMock()

        mock_redis.scan.side_effect = [
            (0, ["paper:signal:test-1", "paper:signal:test-2"]),
        ]

        call_count = [0]

        def mock_hgetall(key):
            call_count[0] += 1
            if call_count[0] == 1:
                return {"timestamp": "invalid-timestamp", "status": "actionable"}
            else:
                return {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "status": "actionable",
                }

        mock_redis.hgetall = mock_hgetall
        mock_redis.scard.return_value = 0

        result = check_pipeline_liveness(mock_redis, max_stale_minutes=15)

        # Should handle invalid timestamp gracefully and count valid one
        assert result["analysis_attempts_last_15m"] == 1
        assert result["healthy"] is True
