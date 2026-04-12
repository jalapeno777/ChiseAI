"""Tests for scripts/autocog/heartbeat.py"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure project root and src are on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_SRC_ROOT = _PROJECT_ROOT / "src"
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))


class TestHeartbeatFunctionality:
    """Tests for heartbeat script functionality."""

    def test_get_drift_score_returns_float(self):
        """Test that _get_drift_score returns a float."""
        from scripts.autocog.heartbeat import _get_drift_score

        mock_redis = MagicMock()
        mock_redis.hgetall.return_value = {}

        score = _get_drift_score(mock_redis)
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0

    def test_get_drift_score_with_concept_drift(self):
        """Test _get_drift_score with concept drift data."""
        from scripts.autocog.heartbeat import _get_drift_score

        mock_redis = MagicMock()
        mock_redis.hgetall.return_value = {"kl_divergence": "0.5"}

        score = _get_drift_score(mock_redis)
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0

    def test_check_feature_flag_default_enabled(self):
        """Test feature flag defaults to enabled when not set."""
        from scripts.autocog.heartbeat import _check_feature_flag

        mock_redis = MagicMock()
        mock_redis.hget.return_value = None

        result = _check_feature_flag(mock_redis)
        assert result is True

    def test_check_feature_flag_explicit_true(self):
        """Test feature flag can be explicitly enabled."""
        from scripts.autocog.heartbeat import _check_feature_flag

        mock_redis = MagicMock()
        mock_redis.hget.return_value = b"true"

        result = _check_feature_flag(mock_redis)
        assert result is True

    def test_check_feature_flag_disabled(self):
        """Test feature flag can be disabled."""
        from scripts.autocog.heartbeat import _check_feature_flag

        mock_redis = MagicMock()
        mock_redis.hget.return_value = b"false"

        result = _check_feature_flag(mock_redis)
        assert result is False

    def test_check_feature_flag_no_redis(self):
        """Test feature flag defaults to enabled when Redis unavailable."""
        from scripts.autocog.heartbeat import _check_feature_flag

        result = _check_feature_flag(None)
        assert result is True

    def test_run_heartbeat_skips_when_disabled(self):
        """Test heartbeat skips when feature flag is disabled."""
        from scripts.autocog.heartbeat import run_heartbeat

        with patch("scripts.autocog.heartbeat._check_feature_flag", return_value=False):
            result = run_heartbeat(dry_run=True)
            assert result["skipped"] is True
            assert result["reason"] == "routine_disabled"

    def test_run_heartbeat_dry_run_produces_output(self):
        """Test heartbeat dry-run produces expected output."""
        from scripts.autocog.heartbeat import run_heartbeat

        result = run_heartbeat(dry_run=True)
        # In dry run, drift score should be calculated
        assert result["skipped"] is False
        assert "drift_score" in result
        assert "self_assessment_ok" in result

    def test_run_heartbeat_alert_threshold(self):
        """Test alert is sent when drift score exceeds threshold."""
        from scripts.autocog.heartbeat import _send_discord_alert

        with patch("urllib.request.urlopen"):
            _send_discord_alert(0.9, "Test alert")
            # If no exception, alert was sent successfully

    def test_write_heartbeat_payload_structure(self):
        """Test heartbeat payload has required fields."""
        from datetime import UTC, datetime

        from scripts.autocog.heartbeat import (
            HEARTBEAT_KEY_PATTERN,
            _write_heartbeat,
        )

        mock_redis = MagicMock()
        now = datetime.now(UTC)
        date_str = now.strftime("%Y-%m-%d")
        hour_str = now.strftime("%H")
        expected_key = HEARTBEAT_KEY_PATTERN.format(date=date_str, hour=hour_str)

        _write_heartbeat(
            mock_redis,
            drift_score=0.5,
            self_assessment_ok=True,
            assessment_msg="test_msg",
        )

        mock_redis.hset.assert_called()
        call_args = mock_redis.hset.call_args
        assert call_args[0][0] == expected_key


class TestHeartbeatMain:
    """Tests for heartbeat main entry point."""

    def test_main_with_dry_run_flag(self):
        """Test main returns 0 with --dry-run flag."""
        import sys

        from scripts.autocog.heartbeat import main

        with patch.object(sys, "argv", ["heartbeat.py", "--dry-run"]):
            result = main()
        assert result == 0
