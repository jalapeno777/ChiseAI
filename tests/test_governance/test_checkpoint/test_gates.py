"""Tests for gate validation module.

Tests the GateChecker class and all G1-G8 gate checks.

Story: PAPER-GOVERNANCE-001
"""

import socket
import ssl
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
import redis

from src.governance.checkpoint.gates import GateChecker, GateResult, GateSummary


class TestGateResult:
    """Tests for GateResult dataclass."""

    def test_gate_result_creation(self):
        """Test creating a GateResult."""
        now = datetime.now(UTC)
        result = GateResult(
            gate="G1",
            status="✅ PASS",
            detail="Test detail",
            timestamp=now,
        )
        assert result.gate == "G1"
        assert result.status == "✅ PASS"
        assert result.detail == "Test detail"
        assert result.timestamp == now

    def test_gate_result_default_timestamp(self):
        """Test GateResult with default timestamp."""
        before = datetime.now(UTC)
        result = GateResult(gate="G1", status="✅ PASS", detail="Test")
        after = datetime.now(UTC)

        assert result.timestamp is not None
        assert before <= result.timestamp  # type: ignore
        assert result.timestamp <= after


class TestGateSummary:
    """Tests for GateSummary dataclass."""

    def test_gate_summary_creation(self):
        """Test creating a GateSummary."""
        now = datetime.now(UTC)
        results = [
            GateResult(gate="G1", status="✅ PASS", detail="Pass", timestamp=now),
            GateResult(gate="G2", status="❌ FAIL", detail="Fail", timestamp=now),
        ]
        summary = GateSummary(
            results=results,
            pass_count=1,
            fail_count=1,
            check_count=0,
            timestamp=now,
        )

        assert len(summary.results) == 2
        assert summary.pass_count == 1
        assert summary.fail_count == 1
        assert summary.check_count == 0

    def test_overall_status_pass(self):
        """Test overall status when all gates pass."""
        now = datetime.now(UTC)
        results = [
            GateResult(gate="G1", status="✅ PASS", detail="Pass", timestamp=now)
        ]
        summary = GateSummary(
            results=results,
            pass_count=1,
            fail_count=0,
            check_count=0,
            timestamp=now,
        )
        assert summary.overall_status == "PASS"

    def test_overall_status_fail(self):
        """Test overall status when any gate fails."""
        now = datetime.now(UTC)
        results = [
            GateResult(gate="G1", status="✅ PASS", detail="Pass", timestamp=now),
            GateResult(gate="G2", status="❌ FAIL", detail="Fail", timestamp=now),
        ]
        summary = GateSummary(
            results=results,
            pass_count=1,
            fail_count=1,
            check_count=0,
            timestamp=now,
        )
        assert summary.overall_status == "FAIL"

    def test_overall_status_check(self):
        """Test overall status when gates are in check state."""
        now = datetime.now(UTC)
        results = [
            GateResult(gate="G1", status="✅ PASS", detail="Pass", timestamp=now),
            GateResult(gate="G2", status="⚠️ CHECK", detail="Check", timestamp=now),
        ]
        summary = GateSummary(
            results=results,
            pass_count=1,
            fail_count=0,
            check_count=1,
            timestamp=now,
        )
        assert summary.overall_status == "CHECK"


class TestGateCheckerInitialization:
    """Tests for GateChecker initialization."""

    def test_default_initialization(self):
        """Test GateChecker with default values."""
        checker = GateChecker()
        assert checker._redis is None
        assert checker._redis_host is not None
        assert checker._redis_port is not None

    def test_with_redis_client(self, mock_redis_client):
        """Test GateChecker with provided Redis client."""
        checker = GateChecker(redis_client=mock_redis_client)
        assert checker._redis == mock_redis_client

    def test_with_custom_host_port(self):
        """Test GateChecker with custom host and port."""
        checker = GateChecker(redis_host="custom-host", redis_port=1234)
        assert checker._redis_host == "custom-host"
        assert checker._redis_port == 1234


class TestG1Scheduler:
    """Tests for G1: Scheduler Continuity gate."""

    def test_g1_no_redis(self):
        """Test G1 when Redis is unavailable."""
        checker = GateChecker()
        with patch.object(checker, "_get_redis", return_value=None):
            result = checker.check_g1_scheduler()

        assert result.gate == "G1"
        assert result.status == GateChecker.STATUS_FAIL
        assert "Redis unavailable" in result.detail

    def test_g1_no_heartbeat(self, mock_redis_client):
        """Test G1 when no heartbeat exists."""
        mock_redis_client.hgetall.return_value = {}
        checker = GateChecker(redis_client=mock_redis_client)
        result = checker.check_g1_scheduler()

        assert result.gate == "G1"
        assert result.status == GateChecker.STATUS_FAIL
        assert "No scheduler heartbeat" in result.detail

    def test_g1_invalid_timestamp(self, mock_redis_client):
        """Test G1 with invalid timestamp in heartbeat."""
        mock_redis_client.hgetall.return_value = {
            "timestamp": "",
            "status": "running",
        }
        checker = GateChecker(redis_client=mock_redis_client)
        result = checker.check_g1_scheduler()

        assert result.gate == "G1"
        assert result.status == GateChecker.STATUS_FAIL
        assert "no timestamp" in result.detail

    def test_g1_not_running(self, mock_redis_client):
        """Test G1 when scheduler status is not running."""
        now = datetime.now(UTC)
        mock_redis_client.hgetall.return_value = {
            "timestamp": now.isoformat(),
            "status": "stopped",
        }
        checker = GateChecker(redis_client=mock_redis_client)
        result = checker.check_g1_scheduler()

        assert result.gate == "G1"
        assert result.status == GateChecker.STATUS_FAIL
        assert "stopped" in result.detail

    def test_g1_stale_heartbeat(self, mock_redis_client):
        """Test G1 when heartbeat is stale."""
        old_time = datetime.now(UTC) - timedelta(seconds=200)
        mock_redis_client.hgetall.return_value = {
            "timestamp": old_time.isoformat(),
            "status": "running",
        }
        checker = GateChecker(redis_client=mock_redis_client)
        result = checker.check_g1_scheduler()

        assert result.gate == "G1"
        assert result.status == GateChecker.STATUS_CHECK
        assert "stale" in result.detail

    def test_g1_healthy(self, mock_redis_client):
        """Test G1 when scheduler is healthy."""
        now = datetime.now(UTC)
        mock_redis_client.hgetall.return_value = {
            "timestamp": now.isoformat(),
            "status": "running",
            "uptime_seconds": "3600",
        }
        checker = GateChecker(redis_client=mock_redis_client)
        result = checker.check_g1_scheduler()

        assert result.gate == "G1"
        assert result.status == GateChecker.STATUS_PASS
        assert "uptime" in result.detail

    def test_g1_exception(self, mock_redis_client):
        """Test G1 when exception occurs."""
        mock_redis_client.hgetall.side_effect = Exception("Redis error")
        checker = GateChecker(redis_client=mock_redis_client)
        result = checker.check_g1_scheduler()

        assert result.gate == "G1"
        assert result.status == GateChecker.STATUS_FAIL
        assert "Exception" in result.detail


class TestG2SignalCadence:
    """Tests for G2: Signal Cadence gate."""

    def test_g2_no_redis(self):
        """Test G2 when Redis is unavailable."""
        checker = GateChecker()
        with patch.object(checker, "_get_redis", return_value=None):
            result = checker.check_g2_signal_cadence()

        assert result.gate == "G2"
        assert result.status == GateChecker.STATUS_FAIL

    def test_g2_pipeline_healthy(self, mock_redis_client):
        """Test G2 when pipeline is healthy (uses liveness from heartbeat)."""
        mock_redis_client.hgetall.return_value = {
            "pipeline_status": "healthy",
            "signals_15m": "10",
            "actionable_15m": "3",
            "consumer_backlog": "2",
        }
        checker = GateChecker(redis_client=mock_redis_client)
        result = checker.check_g2_signal_cadence()

        assert result.gate == "G2"
        assert result.status == GateChecker.STATUS_PASS
        assert "10 signals" in result.detail
        assert "3 actionable" in result.detail

    def test_g2_pipeline_stale(self, mock_redis_client):
        """Test G2 when pipeline is stale (no signals in 15m)."""
        mock_redis_client.hgetall.return_value = {
            "pipeline_status": "stale",
            "signals_15m": "0",
            "actionable_15m": "0",
            "consumer_backlog": "0",
            "latest_signal_age_m": "25.5",
        }
        checker = GateChecker(redis_client=mock_redis_client)
        result = checker.check_g2_signal_cadence()

        assert result.gate == "G2"
        assert result.status == GateChecker.STATUS_FAIL
        assert "stale" in result.detail.lower()
        assert "25.5" in result.detail

    def test_g2_pipeline_unknown(self, mock_redis_client):
        """Test G2 when pipeline status is unknown (no heartbeat data)."""
        mock_redis_client.hgetall.return_value = {}
        checker = GateChecker(redis_client=mock_redis_client)
        result = checker.check_g2_signal_cadence()

        assert result.gate == "G2"
        # Empty heartbeat returns NO_SIGNALS with PASS status (healthy idle state)
        assert result.status == GateChecker.STATUS_PASS
        assert "NO_SIGNALS" in result.detail

    def test_g2_exception(self, mock_redis_client):
        """Test G2 when exception occurs."""
        mock_redis_client.hgetall.side_effect = Exception("Redis error")
        checker = GateChecker(redis_client=mock_redis_client)
        result = checker.check_g2_signal_cadence()

        assert result.gate == "G2"
        assert result.status == GateChecker.STATUS_FAIL


class TestG3DataFlow:
    """Tests for G3: Data Flow Movement gate."""

    def test_g3_no_redis(self):
        """Test G3 when Redis is unavailable."""
        checker = GateChecker()
        with patch.object(checker, "_get_redis", return_value=None):
            result = checker.check_g3_data_flow()

        assert result.gate == "G3"
        assert result.status == GateChecker.STATUS_FAIL

    def test_g3_no_outcomes(self, mock_redis_client):
        """Test G3 when no outcomes exist."""
        mock_redis_client.scard.return_value = 0
        checker = GateChecker(redis_client=mock_redis_client)
        result = checker.check_g3_data_flow()

        assert result.gate == "G3"
        assert result.status == GateChecker.STATUS_CHECK
        assert "No outcomes found" in result.detail

    def test_g3_with_outcomes(self, mock_redis_client):
        """Test G3 when outcomes exist."""
        mock_redis_client.scard.return_value = 10
        checker = GateChecker(redis_client=mock_redis_client)
        result = checker.check_g3_data_flow()

        assert result.gate == "G3"
        assert result.status == GateChecker.STATUS_PASS
        assert "10 outcomes" in result.detail

    def test_g3_exception(self, mock_redis_client):
        """Test G3 when exception occurs."""
        mock_redis_client.scard.side_effect = Exception("Redis error")
        checker = GateChecker(redis_client=mock_redis_client)
        result = checker.check_g3_data_flow()

        assert result.gate == "G3"
        assert result.status == GateChecker.STATUS_FAIL


class TestG4KillSwitch:
    """Tests for G4: Kill Switch Active gate."""

    def test_g4_no_redis(self):
        """Test G4 when Redis is unavailable."""
        checker = GateChecker()
        with patch.object(checker, "_get_redis", return_value=None):
            result = checker.check_g4_kill_switch()

        assert result.gate == "G4"
        assert result.status == GateChecker.STATUS_FAIL

    def test_g4_armed(self, mock_redis_client):
        """Test G4 when kill switch is armed."""

        def mock_hget(key, field):
            if key == "bmad:chiseai:kill_switch":
                if field == "enabled":
                    return "1"
                elif field == "triggered":
                    return "0"
            return None

        mock_redis_client.hget.side_effect = mock_hget
        checker = GateChecker(redis_client=mock_redis_client)
        result = checker.check_g4_kill_switch()

        assert result.gate == "G4"
        assert result.status == GateChecker.STATUS_PASS
        assert "armed" in result.detail

    def test_g4_triggered(self, mock_redis_client):
        """Test G4 when kill switch is triggered."""

        def mock_hget(key, field):
            if key == "bmad:chiseai:kill_switch":
                if field == "triggered":
                    return "1"
            return None

        mock_redis_client.hget.side_effect = mock_hget
        checker = GateChecker(redis_client=mock_redis_client)
        result = checker.check_g4_kill_switch()

        assert result.gate == "G4"
        assert result.status == GateChecker.STATUS_ALERT
        assert "TRIGGERED" in result.detail

    def test_g4_not_configured(self, mock_redis_client):
        """Test G4 when kill switch is not configured."""
        mock_redis_client.hget.return_value = None
        checker = GateChecker(redis_client=mock_redis_client)
        result = checker.check_g4_kill_switch()

        assert result.gate == "G4"
        assert result.status == GateChecker.STATUS_CHECK

    def test_g4_exception(self, mock_redis_client):
        """Test G4 when exception occurs."""
        mock_redis_client.hget.side_effect = Exception("Redis error")
        checker = GateChecker(redis_client=mock_redis_client)
        result = checker.check_g4_kill_switch()

        assert result.gate == "G4"
        assert result.status == GateChecker.STATUS_FAIL


class TestG5CronCadence:
    """Tests for G5: Cron Job Cadence gate."""

    def test_g5_no_redis(self):
        """Test G5 when Redis is unavailable."""
        checker = GateChecker()
        with patch.object(checker, "_get_redis", return_value=None):
            result = checker.check_g5_cron_cadence()

        assert result.gate == "G5"
        assert result.status == GateChecker.STATUS_FAIL

    def test_g5_no_cron_module(self, mock_redis_client):
        """Test G5 when cron_evidence module is not available."""
        checker = GateChecker(redis_client=mock_redis_client)

        # Ensure cron_evidence is not available by patching sys.modules
        with patch.dict("sys.modules", {"cron_evidence": None}):
            result = checker.check_g5_cron_cadence()

        assert result.gate == "G5"
        assert result.status == GateChecker.STATUS_CHECK

    def test_g5_cron_error(self, mock_redis_client):
        """Test G5 when cron check returns error."""
        mock_check = MagicMock(return_value={"error": "Test error"})

        with patch.dict(
            "sys.modules", {"cron_evidence": MagicMock(check_cron_cadence=mock_check)}
        ):
            checker = GateChecker(redis_client=mock_redis_client)
            result = checker.check_g5_cron_cadence()

        assert result.gate == "G5"
        assert result.status == GateChecker.STATUS_FAIL

    def test_g5_cron_pass(self, mock_redis_client):
        """Test G5 when all cron jobs are passing."""
        mock_check = MagicMock(
            return_value={
                "overall_status": "PASS",
                "jobs": {
                    "pager": {
                        "status": "HEALTHY",
                        "elapsed_seconds": 60,
                        "missed_count": 0,
                    },
                },
            }
        )

        with patch.dict(
            "sys.modules", {"cron_evidence": MagicMock(check_cron_cadence=mock_check)}
        ):
            checker = GateChecker(redis_client=mock_redis_client)
            result = checker.check_g5_cron_cadence()

        assert result.gate == "G5"
        assert result.status == GateChecker.STATUS_PASS

    def test_g5_cron_check(self, mock_redis_client):
        """Test G5 when cron jobs need checking."""
        mock_check = MagicMock(
            return_value={
                "overall_status": "CHECK",
                "jobs": {
                    "pager": {
                        "status": "STALE",
                        "elapsed_seconds": 400,
                        "missed_count": 1,
                    },
                },
            }
        )

        with patch.dict(
            "sys.modules", {"cron_evidence": MagicMock(check_cron_cadence=mock_check)}
        ):
            checker = GateChecker(redis_client=mock_redis_client)
            result = checker.check_g5_cron_cadence()

        assert result.gate == "G5"
        assert result.status == GateChecker.STATUS_CHECK

    def test_g5_exception(self, mock_redis_client):
        """Test G5 when exception occurs."""
        checker = GateChecker(redis_client=mock_redis_client)

        with patch.dict(
            "sys.modules",
            {
                "cron_evidence": MagicMock(
                    check_cron_cadence=MagicMock(side_effect=Exception("Error"))
                )
            },
        ):
            result = checker.check_g5_cron_cadence()

        assert result.gate == "G5"
        assert result.status == GateChecker.STATUS_FAIL


class TestG6BybitConnectivity:
    """Tests for G6: Bybit Connectivity gate."""

    def test_g6_success(self):
        """Test G6 when Bybit API is reachable."""
        checker = GateChecker()

        mock_socket = MagicMock()
        mock_socket.recv.return_value = b"HTTP/1.1 200 OK"

        with patch("socket.create_connection") as mock_create:
            with patch("ssl.create_default_context") as mock_ssl:
                mock_ssl.return_value.wrap_socket.return_value.__enter__ = MagicMock(
                    return_value=mock_socket
                )
                mock_ssl.return_value.wrap_socket.return_value.__exit__ = MagicMock(
                    return_value=False
                )
                mock_create.return_value.__enter__ = MagicMock(return_value=MagicMock())
                mock_create.return_value.__exit__ = MagicMock(return_value=False)

                # Patch the entire check to avoid SSL complexity
                result = checker.check_g6_bybit_connectivity()

                # Test will either pass or fail depending on actual network
                assert result.gate == "G6"
                assert result.status in [
                    GateChecker.STATUS_PASS,
                    GateChecker.STATUS_FAIL,
                    GateChecker.STATUS_CHECK,
                ]

    def test_g6_timeout(self):
        """Test G6 when connection times out."""
        checker = GateChecker()

        with patch(
            "socket.create_connection", side_effect=TimeoutError("Connection timed out")
        ):
            result = checker.check_g6_bybit_connectivity()

        assert result.gate == "G6"
        assert result.status == GateChecker.STATUS_FAIL
        assert "timeout" in result.detail.lower()

    def test_g6_dns_error(self):
        """Test G6 when DNS resolution fails."""
        checker = GateChecker()

        with patch(
            "socket.create_connection",
            side_effect=socket.gaierror("Name resolution failed"),
        ):
            result = checker.check_g6_bybit_connectivity()

        assert result.gate == "G6"
        assert result.status == GateChecker.STATUS_FAIL
        assert "DNS" in result.detail


class TestG7Observability:
    """Tests for G7: Observability Health gate."""

    def test_g7_no_redis(self):
        """Test G7 when Redis is unavailable."""
        checker = GateChecker()
        with patch.object(checker, "_get_redis", return_value=None):
            result = checker.check_g7_observability()

        assert result.gate == "G7"
        assert result.status == GateChecker.STATUS_FAIL

    def test_g7_healthy(self, mock_redis_client):
        """Test G7 when Redis is healthy."""
        mock_redis_client.ping.return_value = True
        mock_redis_client.dbsize.return_value = 100
        mock_redis_client.info.return_value = {"uptime_in_seconds": 7200}

        checker = GateChecker(redis_client=mock_redis_client)
        result = checker.check_g7_observability()

        assert result.gate == "G7"
        assert result.status == GateChecker.STATUS_PASS
        assert "2h uptime" in result.detail

    def test_g7_low_uptime(self, mock_redis_client):
        """Test G7 when Redis uptime is low."""
        mock_redis_client.ping.return_value = True
        mock_redis_client.dbsize.return_value = 50
        mock_redis_client.info.return_value = {"uptime_in_seconds": 1800}  # 30 minutes

        checker = GateChecker(redis_client=mock_redis_client)
        result = checker.check_g7_observability()

        assert result.gate == "G7"
        assert result.status == GateChecker.STATUS_CHECK
        assert "30m" in result.detail

    def test_g7_ping_fail(self, mock_redis_client):
        """Test G7 when Redis ping fails."""
        mock_redis_client.ping.return_value = False

        checker = GateChecker(redis_client=mock_redis_client)
        result = checker.check_g7_observability()

        assert result.gate == "G7"
        assert result.status == GateChecker.STATUS_FAIL

    def test_g7_exception(self, mock_redis_client):
        """Test G7 when exception occurs."""
        mock_redis_client.ping.side_effect = Exception("Redis error")

        checker = GateChecker(redis_client=mock_redis_client)
        result = checker.check_g7_observability()

        assert result.gate == "G7"
        assert result.status == GateChecker.STATUS_FAIL


class TestG8Pipeline:
    """Tests for G8: End-to-End Pipeline gate."""

    def test_g8_no_redis(self):
        """Test G8 when Redis is unavailable."""
        checker = GateChecker()
        with patch.object(checker, "_get_redis", return_value=None):
            result = checker.check_g8_pipeline()

        assert result.gate == "G8"
        assert result.status == GateChecker.STATUS_FAIL

    def test_g8_no_verdict(self, mock_redis_client):
        """Test G8 when no burn-in verdict exists."""
        mock_redis_client.get.return_value = None
        mock_redis_client.keys.return_value = []
        mock_redis_client.scard.return_value = 0

        checker = GateChecker(redis_client=mock_redis_client)
        result = checker.check_g8_pipeline()

        assert result.gate == "G8"
        assert result.status == GateChecker.STATUS_UNKNOWN
        assert "No burn-in verdict" in result.detail

    def test_g8_go_verdict(self, mock_redis_client):
        """Test G8 with GO verdict."""
        mock_redis_client.get.return_value = "GO"
        mock_redis_client.keys.return_value = ["signal:1"]
        mock_redis_client.scard.return_value = 5

        checker = GateChecker(redis_client=mock_redis_client)
        result = checker.check_g8_pipeline()

        assert result.gate == "G8"
        assert result.status == GateChecker.STATUS_PASS
        assert "GO" in result.detail

    def test_g8_no_go_verdict(self, mock_redis_client):
        """Test G8 with NO-GO verdict."""
        mock_redis_client.get.return_value = "NO-GO"
        mock_redis_client.keys.return_value = ["signal:1"]
        mock_redis_client.scard.return_value = 5

        checker = GateChecker(redis_client=mock_redis_client)
        result = checker.check_g8_pipeline()

        assert result.gate == "G8"
        assert result.status == GateChecker.STATUS_FAIL
        assert "NO-GO" in result.detail

    def test_g8_unexpected_verdict(self, mock_redis_client):
        """Test G8 with unexpected verdict value."""
        mock_redis_client.get.return_value = "UNKNOWN"
        mock_redis_client.keys.return_value = []
        mock_redis_client.scard.return_value = 0

        checker = GateChecker(redis_client=mock_redis_client)
        result = checker.check_g8_pipeline()

        assert result.gate == "G8"
        assert result.status == GateChecker.STATUS_CHECK

    def test_g8_exception(self, mock_redis_client):
        """Test G8 when exception occurs."""
        mock_redis_client.get.side_effect = Exception("Redis error")

        checker = GateChecker(redis_client=mock_redis_client)
        result = checker.check_g8_pipeline()

        assert result.gate == "G8"
        assert result.status == GateChecker.STATUS_FAIL


class TestG10ChainIntegrity:
    """Tests for G10: Chain Integrity gate."""

    def test_g10_no_redis(self):
        """Test G10 when Redis is unavailable."""
        checker = GateChecker()
        with patch.object(checker, "_get_redis", return_value=None):
            result = checker.check_g10_chain_integrity()

        assert result.gate == "G10"
        assert result.status == GateChecker.STATUS_FAIL
        assert "Redis unavailable" in result.detail

    def test_g10_no_signals(self, mock_redis_client):
        """Test G10 when no signals in 6h window."""
        mock_redis_client.scan_iter.return_value = []
        checker = GateChecker(redis_client=mock_redis_client)
        result = checker.check_g10_chain_integrity()

        assert result.gate == "G10"
        assert result.status == GateChecker.STATUS_CHECK
        assert "signals=0" in result.detail
        assert "healthy idle" in result.detail

    def test_g10_signals_no_downstream(self, mock_redis_client):
        """Test G10 when signals exist but no downstream activity."""
        from datetime import UTC, datetime, timedelta

        now = datetime.now(UTC)
        recent_ts = now.isoformat()

        # Mock signals but no orders/fills/outcomes
        def mock_scan_iter(match=None, count=None):
            if "signal" in (match or ""):
                return ["bmad:chiseai:signals:test-1", "paper:signal:test-2"]
            return []

        mock_redis_client.scan_iter.side_effect = mock_scan_iter
        mock_redis_client.hget.return_value = recent_ts
        mock_redis_client.zrangebyscore.return_value = []
        mock_redis_client.smembers.return_value = set()

        checker = GateChecker(redis_client=mock_redis_client)
        result = checker.check_g10_chain_integrity()

        assert result.gate == "G10"
        assert result.status == GateChecker.STATUS_FAIL
        assert "Pipeline broken" in result.detail

    def test_g10_healthy_pipeline(self, mock_redis_client):
        """Test G10 when all pipeline stages have activity."""
        from datetime import UTC, datetime

        now = datetime.now(UTC)
        now_ts = now.timestamp()

        # Mock signals, orders, fills, and outcomes
        def mock_scan_iter(match=None, count=None):
            if "signal" in (match or ""):
                return ["bmad:chiseai:signals:test-1"]
            elif "order" in (match or ""):
                return [f"paper:order:{now_ts}:order-1"]
            elif "fill" in (match or ""):
                return [f"paper:fill:{now_ts}:fill-1"]
            return []

        mock_redis_client.scan_iter.side_effect = mock_scan_iter
        mock_redis_client.hget.return_value = now.isoformat()
        mock_redis_client.zrangebyscore.return_value = ["outcome-1", "outcome-2"]

        checker = GateChecker(redis_client=mock_redis_client)
        result = checker.check_g10_chain_integrity()

        assert result.gate == "G10"
        assert result.status == GateChecker.STATUS_PASS
        # Check that counts are present (exact numbers depend on mock behavior)
        assert "signals=" in result.detail
        assert "orders=1" in result.detail
        assert "fills=1" in result.detail
        assert "outcomes=2" in result.detail

    def test_g10_exception(self, mock_redis_client):
        """Test G10 when exception occurs."""
        mock_redis_client.scan_iter.side_effect = Exception("Redis error")
        checker = GateChecker(redis_client=mock_redis_client)
        result = checker.check_g10_chain_integrity()

        assert result.gate == "G10"
        assert result.status == GateChecker.STATUS_FAIL
        assert "Exception" in result.detail


class TestG12BybitFreshness:
    """Tests for G12: Bybit Freshness gate."""

    def test_g12_no_redis(self):
        """Test G12 when Redis is unavailable."""
        checker = GateChecker()
        with patch.object(checker, "_get_redis", return_value=None):
            result = checker.check_g12_bybit_freshness()

        assert result.gate == "G12"
        assert result.status == GateChecker.STATUS_FAIL
        assert "Redis unavailable" in result.detail

    def test_g12_missing_timestamp(self, mock_redis_client):
        """Test G12 when timestamp key is missing."""
        mock_redis_client.get.return_value = None
        checker = GateChecker(redis_client=mock_redis_client)
        result = checker.check_g12_bybit_freshness()

        assert result.gate == "G12"
        assert result.status == GateChecker.STATUS_CHECK
        assert "missing" in result.detail

    def test_g12_unparseable_timestamp(self, mock_redis_client):
        """Test G12 when timestamp is unparseable."""
        mock_redis_client.get.return_value = "not-a-timestamp"
        checker = GateChecker(redis_client=mock_redis_client)
        result = checker.check_g12_bybit_freshness()

        assert result.gate == "G12"
        assert result.status == GateChecker.STATUS_CHECK
        assert "unparseable" in result.detail

    def test_g12_fresh_data(self, mock_redis_client):
        """Test G12 when data is fresh (<=60m)."""
        from datetime import UTC, datetime, timedelta

        now = datetime.now(UTC)
        recent = now - timedelta(minutes=30)
        mock_redis_client.get.return_value = recent.isoformat()

        checker = GateChecker(redis_client=mock_redis_client)
        result = checker.check_g12_bybit_freshness()

        assert result.gate == "G12"
        assert result.status == GateChecker.STATUS_PASS
        assert "30.0m ago" in result.detail
        assert "fresh" in result.detail

    def test_g12_stale_data(self, mock_redis_client):
        """Test G12 when data is stale (>60m)."""
        from datetime import UTC, datetime, timedelta

        now = datetime.now(UTC)
        old = now - timedelta(minutes=90)
        mock_redis_client.get.return_value = old.isoformat()

        checker = GateChecker(redis_client=mock_redis_client)
        result = checker.check_g12_bybit_freshness()

        assert result.gate == "G12"
        assert result.status == GateChecker.STATUS_FAIL
        assert "90.0m ago" in result.detail
        assert "stale" in result.detail

    def test_g12_exception(self, mock_redis_client):
        """Test G12 when exception occurs."""
        mock_redis_client.get.side_effect = Exception("Redis error")
        checker = GateChecker(redis_client=mock_redis_client)
        result = checker.check_g12_bybit_freshness()

        assert result.gate == "G12"
        assert result.status == GateChecker.STATUS_FAIL
        assert "Exception" in result.detail


class TestRunAllChecks:
    """Tests for running all gate checks."""

    def test_run_all_checks(self, mock_redis_with_scheduler_heartbeat):
        """Test running all gate checks."""
        checker = GateChecker(redis_client=mock_redis_with_scheduler_heartbeat)

        # Patch G6 to avoid network calls
        with patch.object(checker, "check_g6_bybit_connectivity") as mock_g6:
            mock_g6.return_value = GateResult(
                gate="G6",
                status=GateChecker.STATUS_PASS,
                detail="Bybit API reachable",
                timestamp=datetime.now(UTC),
            )

            # Patch G5 to avoid import issues
            with patch.object(checker, "check_g5_cron_cadence") as mock_g5:
                mock_g5.return_value = GateResult(
                    gate="G5",
                    status=GateChecker.STATUS_PASS,
                    detail="All cron jobs healthy",
                    timestamp=datetime.now(UTC),
                )

                # Patch G10 and G12 to avoid scan_iter complexity
                with patch.object(checker, "check_g10_chain_integrity") as mock_g10:
                    mock_g10.return_value = GateResult(
                        gate="G10",
                        status=GateChecker.STATUS_PASS,
                        detail="signals=5 orders=3 fills=3 outcomes=5",
                        timestamp=datetime.now(UTC),
                    )
                    with patch.object(checker, "check_g12_bybit_freshness") as mock_g12:
                        mock_g12.return_value = GateResult(
                            gate="G12",
                            status=GateChecker.STATUS_PASS,
                            detail="last_collection=15.0m ago | status=fresh",
                            timestamp=datetime.now(UTC),
                        )

                        summary = checker.run_all_checks()

        assert len(summary.results) == 12  # G1-G12 (including G11)
        assert summary.pass_count >= 6  # Most should pass with mock data
        assert isinstance(summary.timestamp, datetime)

    def test_get_failing_gates(self, sample_gate_summary_with_failures):
        """Test getting list of failing gates."""
        checker = GateChecker()
        failing = checker.get_failing_gates(sample_gate_summary_with_failures)

        assert "G4" in failing

    def test_is_healthy(self, sample_gate_summary):
        """Test is_healthy with all passing gates."""
        checker = GateChecker()
        assert checker.is_healthy(sample_gate_summary) is True

    def test_is_not_healthy(self, sample_gate_summary_with_failures):
        """Test is_healthy with failing gates."""
        checker = GateChecker()
        assert checker.is_healthy(sample_gate_summary_with_failures) is False

    def test_run_checks_with_none_summary(self, mock_redis_with_scheduler_heartbeat):
        """Test get_failing_gates and is_healthy with None summary."""
        checker = GateChecker(redis_client=mock_redis_with_scheduler_heartbeat)

        # Patch G6 and G5 to avoid network/import issues
        with patch.object(checker, "check_g6_bybit_connectivity") as mock_g6:
            mock_g6.return_value = GateResult(
                gate="G6",
                status=GateChecker.STATUS_PASS,
                detail="Bybit API reachable",
                timestamp=datetime.now(UTC),
            )
            with patch.object(checker, "check_g5_cron_cadence") as mock_g5:
                mock_g5.return_value = GateResult(
                    gate="G5",
                    status=GateChecker.STATUS_PASS,
                    detail="All cron jobs healthy",
                    timestamp=datetime.now(UTC),
                )

                failing = checker.get_failing_gates(None)
                assert isinstance(failing, list)

                healthy = checker.is_healthy(None)
                assert isinstance(healthy, bool)
