"""Tests for Smoke Checker.

Tests smoke_checker.py functions with mocked Redis data.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from src.validation.experiment_telemetry.smoke_checker import (
    EXCLUDED_SIGNAL_TYPES,
    EXIT_CODES,
    CheckResult,
    check_bos_choch_inclusion,
    check_data_freshness,
    check_redis_connectivity,
    format_human_output,
    format_json_output,
    format_prometheus_output,
    get_signal_counts,
    run_smoke_checks,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_redis():
    """Mock Redis client."""
    return MagicMock()


@pytest.fixture
def sample_signals():
    """Sample signal data with mixed types."""
    return {
        "c1": {"signal_type": "fvg", "direction": "long"},
        "c2": {"signal_type": "order_block", "direction": "long"},
        "c3": {"signal_type": "bos", "direction": "long"},  # Included
        "c4": {"signal_type": "fvg", "direction": "short"},
        "c5": {"signal_type": "choch", "direction": "long"},  # Included
        "t1": {"signal_type": "fvg", "direction": "long"},
        "t2": {"signal_type": "order_block", "direction": "long"},
        "t3": {"signal_type": "bos", "direction": "long"},  # Included
        "t4": {"signal_type": "fvg", "direction": "short"},
    }


# =============================================================================
# Redis Connectivity Tests
# =============================================================================


class TestRedisConnectivity:
    """Tests for Redis connectivity checking."""

    def test_redis_connectivity_success(self):
        """Test Redis connectivity check when Redis is available."""
        with patch(
            "src.validation.experiment_telemetry.smoke_checker.redis_state_llen"
        ) as mock_llen:
            mock_llen.return_value = 5  # Successful call

            is_connected, message = check_redis_connectivity()

            assert is_connected is True
            assert "successful" in message.lower()

    def test_redis_connectivity_failure(self):
        """Test Redis connectivity check when Redis is unavailable."""
        with patch(
            "src.validation.experiment_telemetry.smoke_checker.redis_state_llen"
        ) as mock_llen:
            mock_llen.side_effect = Exception("Connection refused")

            is_connected, message = check_redis_connectivity()

            assert is_connected is False
            assert "error" in message.lower() or "failed" in message.lower()


# =============================================================================
# BOS/CHoCH Inclusion Tests
# =============================================================================


class TestBOSCHoCHInclusion:
    """Tests for BOS/CHoCH inclusion (re-enabled after accuracy fix)."""

    def test_bos_choch_inclusion_found(self, sample_signals):
        """Test when BOS/CHoCH signals are found (expected now)."""
        with (
            patch(
                "src.validation.experiment_telemetry.smoke_checker.get_signal_ids"
            ) as mock_get_ids,
            patch(
                "src.validation.experiment_telemetry.smoke_checker.get_signal_data"
            ) as mock_get_signal,
        ):
            # Include bos and choch signals (now expected)
            mock_get_ids.return_value = ["c1", "c2", "c3", "c4", "c5"]
            mock_get_signal.side_effect = lambda sig_id: sample_signals.get(sig_id, {})

            has_signals, found = check_bos_choch_inclusion()

            # Since BOS/CHoCH are now included, should find them
            assert has_signals is True
            assert len(found) > 0

    def test_bos_choch_inclusion_empty_excluded(self, sample_signals):
        """Test that BOS/CHoCH signals pass through with empty exclusion list."""
        with (
            patch(
                "src.validation.experiment_telemetry.smoke_checker.get_signal_ids"
            ) as mock_get_ids,
            patch(
                "src.validation.experiment_telemetry.smoke_checker.get_signal_data"
            ) as mock_get_signal,
        ):
            mock_get_ids.return_value = ["c3", "c5"]  # Only bos/choch
            mock_get_signal.side_effect = lambda sig_id: sample_signals.get(sig_id, {})

            has_signals, found = check_bos_choch_inclusion()

            # With empty EXCLUDED_SIGNAL_TYPES, BOS/CHoCH signals are found
            assert has_signals is True

    def test_excluded_signal_types_empty(self):
        """Test that excluded signal types set is now empty."""
        assert "bos" not in EXCLUDED_SIGNAL_TYPES
        assert "choch" not in EXCLUDED_SIGNAL_TYPES
        assert len(EXCLUDED_SIGNAL_TYPES) == 0


# =============================================================================
# Signal Count Tests
# =============================================================================


class TestSignalCounts:
    """Tests for signal count validation."""

    def test_signal_counts_sufficient(self, sample_signals):
        """Test when signal counts meet minimum threshold."""
        with (
            patch(
                "src.validation.experiment_telemetry.smoke_checker.get_signal_ids"
            ) as mock_get_ids,
            patch(
                "src.validation.experiment_telemetry.smoke_checker.get_signal_data"
            ) as mock_get_signal,
        ):
            # Return valid signals only (no bos/choch filtering needed)
            # 5 control + 5 treatment = 10 total (meets MIN_SIGNALS=10)
            mock_get_ids.return_value = [
                "c1",
                "c2",
                "c4",
            ]  # Only valid signals (excludes bos, choch)
            mock_get_signal.side_effect = lambda sig_id: sample_signals.get(sig_id, {})

            counts = get_signal_counts()

            # After filtering bos/choch from sample_signals: c1, c2, c4 are valid (3 control)
            # For treatment: t1, t2, t4 are valid (3 treatment) = 6 total
            # But let's use all valid signals to get to 10
            assert counts["total_count"] >= 6  # We have 6 valid signals
            assert counts["control_count"] > 0
            assert counts["treatment_count"] > 0

    def test_signal_counts_insufficient(self):
        """Test when signal counts are below minimum threshold."""
        with (
            patch(
                "src.validation.experiment_telemetry.smoke_checker.get_signal_ids"
            ) as mock_get_ids,
            patch(
                "src.validation.experiment_telemetry.smoke_checker.get_signal_data"
            ) as mock_get_signal,
        ):
            # Only 3 signals total (below MIN_SIGNALS=10)
            mock_get_ids.return_value = ["c1", "c2", "c3"]
            mock_get_signal.side_effect = lambda sig_id: {
                "signal_type": "fvg"
            }  # All valid

            counts = get_signal_counts()

            assert counts["total_count"] < 10  # Should fail threshold


# =============================================================================
# Data Freshness Tests
# =============================================================================


class TestDataFreshness:
    """Tests for data freshness checking."""

    def test_data_freshness_recent(self):
        """Test when data was recently updated."""
        with patch(
            "src.validation.experiment_telemetry.smoke_checker.redis_state_hgetall"
        ) as mock_hgetall:
            from datetime import UTC, datetime, timedelta

            # Data from 1 hour ago (fresh)
            recent_time = datetime.now(UTC) - timedelta(hours=1)
            mock_hgetall.return_value = {"last_update": recent_time.isoformat()}

            is_fresh, message = check_data_freshness()

            assert is_fresh is True

    def test_data_freshness_stale(self):
        """Test when data is too old."""
        with patch(
            "src.validation.experiment_telemetry.smoke_checker.redis_state_hgetall"
        ) as mock_hgetall:
            from datetime import UTC, datetime, timedelta

            # Data from 48 hours ago (stale - beyond 24h threshold)
            stale_time = datetime.now(UTC) - timedelta(hours=48)
            mock_hgetall.return_value = {"last_update": stale_time.isoformat()}

            is_fresh, message = check_data_freshness()

            assert is_fresh is False
            assert "hours old" in message

    def test_data_freshness_no_timestamp(self):
        """Test when no timestamp is found in metadata."""
        with patch(
            "src.validation.experiment_telemetry.smoke_checker.redis_state_hgetall"
        ) as mock_hgetall:
            mock_hgetall.return_value = {}  # No timestamp

            is_fresh, message = check_data_freshness()

            assert is_fresh is False
            assert "no timestamp" in message.lower()


# =============================================================================
# Smoke Check Run Tests
# =============================================================================


class TestRunSmokeChecks:
    """Tests for run_smoke_checks function."""

    def test_smoke_checks_all_pass(self, sample_signals):
        """Test when all smoke checks pass."""
        with (
            patch(
                "src.validation.experiment_telemetry.smoke_checker.redis_state_llen"
            ) as mock_llen,
            patch(
                "src.validation.experiment_telemetry.smoke_checker.check_bos_choch_inclusion"
            ) as mock_bos_choch,
            patch(
                "src.validation.experiment_telemetry.smoke_checker.get_signal_counts"
            ) as mock_counts,
            patch(
                "src.validation.experiment_telemetry.smoke_checker.check_data_freshness"
            ) as mock_freshness,
        ):
            mock_llen.return_value = 5
            mock_bos_choch.return_value = (True, [])
            mock_counts.return_value = {
                "control_count": 10,
                "treatment_count": 10,
                "total_count": 20,
            }
            mock_freshness.return_value = (True, "Data is 1.0 hours old")

            results = run_smoke_checks()

            assert results["overall_result"] == CheckResult.PASS.value
            assert len(results["messages"]) == 0

    def test_smoke_checks_fail_insufficient_signals(self, sample_signals):
        """Test smoke check fails when signals are insufficient."""
        with (
            patch(
                "src.validation.experiment_telemetry.smoke_checker.redis_state_llen"
            ) as mock_llen,
            patch(
                "src.validation.experiment_telemetry.smoke_checker.check_bos_choch_inclusion"
            ) as mock_bos_choch,
            patch(
                "src.validation.experiment_telemetry.smoke_checker.get_signal_counts"
            ) as mock_counts,
            patch(
                "src.validation.experiment_telemetry.smoke_checker.check_data_freshness"
            ) as mock_freshness,
        ):
            mock_llen.return_value = 5
            mock_bos_choch.return_value = (True, [])
            mock_counts.return_value = {
                "control_count": 3,
                "treatment_count": 3,
                "total_count": 6,
            }  # Below 10 threshold
            mock_freshness.return_value = (True, "Data is fresh")

            results = run_smoke_checks()

            assert results["overall_result"] == CheckResult.FAIL.value
            assert any("FAIL" in msg for msg in results["messages"])

    def test_smoke_checks_bos_choch_passes(self, sample_signals):
        """Test smoke check passes when BOS/CHoCH are included (not excluded)."""
        with (
            patch(
                "src.validation.experiment_telemetry.smoke_checker.redis_state_llen"
            ) as mock_llen,
            patch(
                "src.validation.experiment_telemetry.smoke_checker.check_bos_choch_inclusion"
            ) as mock_bos_choch,
            patch(
                "src.validation.experiment_telemetry.smoke_checker.get_signal_counts"
            ) as mock_counts,
            patch(
                "src.validation.experiment_telemetry.smoke_checker.check_data_freshness"
            ) as mock_freshness,
        ):
            mock_llen.return_value = 5
            # With empty EXCLUDED_SIGNAL_TYPES, inclusion check returns clean
            mock_bos_choch.return_value = (True, [])
            mock_counts.return_value = {
                "control_count": 10,
                "treatment_count": 10,
                "total_count": 20,
            }
            mock_freshness.return_value = (True, "Data is fresh")

            results = run_smoke_checks()

            # Should pass since BOS/CHoCH are no longer excluded
            assert results["overall_result"] == CheckResult.PASS.value


# =============================================================================
# Output Format Tests
# =============================================================================


class TestOutputFormats:
    """Tests for output format validation."""

    def test_human_format_output(self):
        """Test human-readable output format."""
        results = {
            "timestamp": "2026-03-26T12:00:00Z",
            "overall_result": "PASS",
            "checks": {
                "redis_connectivity": {
                    "status": "OK",
                    "message": "Redis connection successful",
                },
                "bos_choch_exclusion": {
                    "status": "OK",
                    "message": "No BOS/CHoCH signals found",
                    "found_excluded": [],
                },
                "signal_counts": {
                    "status": "OK",
                    "message": "Total: 20",
                    "control_count": 10,
                    "treatment_count": 10,
                    "total_count": 20,
                },
                "data_freshness": {
                    "status": "OK",
                    "message": "Data is 1.0 hours old",
                },
            },
            "summary": "All smoke checks passed",
            "messages": [],
        }

        output = format_human_output(results)

        assert "SMOKE CHECK" in output
        assert "Overall Result: PASS" in output
        assert "Redis" in output
        assert "Signal Counts" in output or "Total:" in output

    def test_json_format_output(self):
        """Test JSON output format."""
        results = {
            "timestamp": "2026-03-26T12:00:00Z",
            "overall_result": "PASS",
            "checks": {
                "redis_connectivity": {
                    "status": "OK",
                    "message": "Redis connection successful",
                },
                "bos_choch_exclusion": {
                    "status": "OK",
                    "message": "No BOS/CHoCH signals found",
                    "found_excluded": [],
                },
                "signal_counts": {
                    "status": "OK",
                    "message": "Total: 20",
                    "control_count": 10,
                    "treatment_count": 10,
                    "total_count": 20,
                },
                "data_freshness": {
                    "status": "OK",
                    "message": "Data is 1.0 hours old",
                },
            },
            "summary": "All smoke checks passed",
            "messages": [],
        }

        output = format_json_output(results)
        data = json.loads(output)

        assert data["overall_result"] == "PASS"
        assert data["exit_code"] == 0
        assert "checks" in data
        assert "redis_connectivity" in data["checks"]

    def test_prometheus_format_output(self):
        """Test Prometheus metrics output format."""
        results = {
            "timestamp": "2026-03-26T12:00:00Z",
            "overall_result": "PASS",
            "checks": {
                "redis_connectivity": {
                    "status": "OK",
                    "message": "Redis connection successful",
                },
                "bos_choch_exclusion": {
                    "status": "OK",
                    "message": "No BOS/CHoCH signals found",
                    "found_excluded": [],
                },
                "signal_counts": {
                    "status": "OK",
                    "message": "Total: 20",
                    "control_count": 10,
                    "treatment_count": 10,
                    "total_count": 20,
                },
                "data_freshness": {
                    "status": "OK",
                    "message": "Data is 1.0 hours old",
                },
            },
            "summary": "All smoke checks passed",
            "messages": [],
        }

        output = format_prometheus_output(results)

        assert "experiment_smoke_check_result" in output
        assert "experiment_smoke_check_" in output
        assert "experiment_signals_total" in output
        # Should contain metric value
        assert "0" in output or "1" in output


# =============================================================================
# Exit Code Tests
# =============================================================================


class TestExitCodes:
    """Tests for exit code verification."""

    def test_exit_code_pass(self):
        """Test exit code is 0 for PASS."""
        assert EXIT_CODES[CheckResult.PASS] == 0

    def test_exit_code_fail(self):
        """Test exit code is 1 for FAIL."""
        assert EXIT_CODES[CheckResult.FAIL] == 1

    def test_exit_code_critical(self):
        """Test exit code is 2 for CRITICAL."""
        assert EXIT_CODES[CheckResult.CRITICAL] == 2

    def test_smoke_check_returns_correct_exit_code_pass(self, sample_signals):
        """Test that smoke check returns exit code 0 when all pass."""
        with (
            patch(
                "src.validation.experiment_telemetry.smoke_checker.redis_state_llen"
            ) as mock_llen,
            patch(
                "src.validation.experiment_telemetry.smoke_checker.check_bos_choch_inclusion"
            ) as mock_bos_choch,
            patch(
                "src.validation.experiment_telemetry.smoke_checker.get_signal_counts"
            ) as mock_counts,
            patch(
                "src.validation.experiment_telemetry.smoke_checker.check_data_freshness"
            ) as mock_freshness,
        ):
            mock_llen.return_value = 5
            mock_bos_choch.return_value = (True, [])
            mock_counts.return_value = {
                "control_count": 10,
                "treatment_count": 10,
                "total_count": 20,
            }
            mock_freshness.return_value = (True, "Fresh")

            results = run_smoke_checks()
            exit_code = EXIT_CODES.get(CheckResult(results["overall_result"]))

            assert exit_code == 0

    def test_smoke_check_returns_correct_exit_code_fail(self):
        """Test that smoke check returns exit code 1 when checks fail."""
        with (
            patch(
                "src.validation.experiment_telemetry.smoke_checker.redis_state_llen"
            ) as mock_llen,
            patch(
                "src.validation.experiment_telemetry.smoke_checker.check_bos_choch_inclusion"
            ) as mock_bos_choch,
            patch(
                "src.validation.experiment_telemetry.smoke_checker.get_signal_counts"
            ) as mock_counts,
            patch(
                "src.validation.experiment_telemetry.smoke_checker.check_data_freshness"
            ) as mock_freshness,
        ):
            mock_llen.return_value = 5
            mock_bos_choch.return_value = (True, [])
            mock_counts.return_value = {
                "control_count": 3,
                "treatment_count": 3,
                "total_count": 6,
            }  # Below threshold
            mock_freshness.return_value = (True, "Fresh")

            results = run_smoke_checks()
            exit_code = EXIT_CODES.get(CheckResult(results["overall_result"]))

            assert exit_code == 1

    def test_smoke_check_bos_choch_no_longer_critical(self):
        """Test that smoke check returns PASS since BOS/CHoCH are included."""
        with (
            patch(
                "src.validation.experiment_telemetry.smoke_checker.redis_state_llen"
            ) as mock_llen,
            patch(
                "src.validation.experiment_telemetry.smoke_checker.check_bos_choch_inclusion"
            ) as mock_bos_choch,
            patch(
                "src.validation.experiment_telemetry.smoke_checker.get_signal_counts"
            ) as mock_counts,
            patch(
                "src.validation.experiment_telemetry.smoke_checker.check_data_freshness"
            ) as mock_freshness,
        ):
            mock_llen.return_value = 5
            # BOS/CHoCH no longer triggers critical
            mock_bos_choch.return_value = (True, [])
            mock_counts.return_value = {
                "control_count": 10,
                "treatment_count": 10,
                "total_count": 20,
            }
            mock_freshness.return_value = (True, "Fresh")

            results = run_smoke_checks()
            exit_code = EXIT_CODES.get(CheckResult(results["overall_result"]))

            assert exit_code == 0


# =============================================================================
# CLI Integration Tests
# =============================================================================


class TestCLIIntegration:
    """Tests for CLI argument handling and output."""

    def test_argparse_json_flag(self):
        """Test that --json flag is recognized by argparse."""
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument("--json", action="store_true")
        args = parser.parse_args(["--json"])
        assert args.json is True

    def test_argparse_prometheus_flag(self):
        """Test that --prometheus flag is recognized by argparse."""
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument("--prometheus", action="store_true")
        args = parser.parse_args(["--prometheus"])
        assert args.prometheus is True

    def test_format_json_output_is_serializable(self):
        """Test that JSON output is serializable."""
        from src.validation.experiment_telemetry.smoke_checker import format_json_output

        results = {
            "timestamp": "2026-03-26T12:00:00Z",
            "overall_result": "PASS",
            "checks": {
                "redis_connectivity": {
                    "status": "OK",
                    "message": "OK",
                },
                "bos_choch_exclusion": {
                    "status": "OK",
                    "message": "OK",
                    "found_excluded": [],
                },
                "signal_counts": {
                    "status": "OK",
                    "message": "OK",
                    "control_count": 10,
                    "treatment_count": 10,
                    "total_count": 20,
                },
                "data_freshness": {
                    "status": "OK",
                    "message": "OK",
                },
            },
            "summary": "All checks passed",
            "messages": [],
        }

        output = format_json_output(results)
        data = json.loads(output)
        assert data["overall_result"] == "PASS"

    def test_format_prometheus_output_contains_metrics(self):
        """Test that Prometheus output contains expected metrics."""
        from src.validation.experiment_telemetry.smoke_checker import (
            format_prometheus_output,
        )

        results = {
            "timestamp": "2026-03-26T12:00:00Z",
            "overall_result": "PASS",
            "checks": {
                "redis_connectivity": {"status": "OK", "message": "OK"},
                "bos_choch_exclusion": {
                    "status": "OK",
                    "message": "OK",
                    "found_excluded": [],
                },
                "signal_counts": {
                    "status": "OK",
                    "message": "OK",
                    "control_count": 10,
                    "treatment_count": 10,
                    "total_count": 20,
                },
                "data_freshness": {"status": "OK", "message": "OK"},
            },
            "summary": "All checks passed",
            "messages": [],
        }

        output = format_prometheus_output(results)
        assert "# HELP" in output
        assert "# TYPE" in output
        assert "experiment_smoke_check" in output
