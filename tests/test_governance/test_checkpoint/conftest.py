"""Shared fixtures for checkpoint tests.

Story: PAPER-GOVERNANCE-001
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
import redis
from src.governance.checkpoint.gates import GateChecker, GateResult, GateSummary
from src.governance.checkpoint.state import (
    CheckpointRecord,
    CheckpointState,
    CheckpointStatus,
)


@pytest.fixture
def mock_redis_client():
    """Create a mock Redis client."""
    mock = MagicMock(spec=redis.Redis)
    mock.hgetall.return_value = {}
    mock.hget.return_value = None
    mock.hset.return_value = True
    mock.get.return_value = None
    mock.set.return_value = True
    mock.keys.return_value = []
    mock.scard.return_value = 0
    mock.lpush.return_value = True
    mock.ltrim.return_value = True
    mock.lrange.return_value = []
    mock.ping.return_value = True
    mock.dbsize.return_value = 100
    mock.info.return_value = {"uptime_in_seconds": 7200}
    return mock


@pytest.fixture
def mock_redis_with_scheduler_heartbeat():
    """Create a mock Redis with scheduler heartbeat data."""
    mock = MagicMock(spec=redis.Redis)
    now = datetime.now(UTC)
    mock.hgetall.return_value = {
        "timestamp": now.isoformat(),
        "status": "running",
        "uptime_seconds": "3600",
    }
    mock.keys.return_value = [
        "bmad:chiseai:signals:test-1",
        "bmad:chiseai:signals:test-2",
    ]
    mock.scard.return_value = 5
    mock.hget.side_effect = lambda key, field: {
        ("bmad:chiseai:kill_switch", "enabled"): "1",
        ("bmad:chiseai:kill_switch", "triggered"): "0",
    }.get((key, field), None)
    mock.get.return_value = "GO"
    mock.ping.return_value = True
    mock.dbsize.return_value = 100
    mock.info.return_value = {"uptime_in_seconds": 7200}
    return mock


@pytest.fixture
def sample_gate_results():
    """Create sample gate results for testing."""
    now = datetime.now(UTC)
    return [
        GateResult(
            gate="G1", status="✅ PASS", detail="Heartbeat 30s ago", timestamp=now
        ),
        GateResult(
            gate="G2", status="✅ PASS", detail="2 signals in Redis", timestamp=now
        ),
        GateResult(
            gate="G3", status="✅ PASS", detail="5 outcomes recorded", timestamp=now
        ),
        GateResult(
            gate="G4",
            status="✅ PASS",
            detail="Kill switch armed and ready",
            timestamp=now,
        ),
        GateResult(
            gate="G5", status="✅ PASS", detail="pager:PASS(60s)", timestamp=now
        ),
        GateResult(
            gate="G6", status="✅ PASS", detail="Bybit API reachable", timestamp=now
        ),
        GateResult(
            gate="G7",
            status="✅ PASS",
            detail="Redis OK, 100 keys, 2h uptime",
            timestamp=now,
        ),
        GateResult(
            gate="G8", status="✅ PASS", detail="Burn-in verdict: GO", timestamp=now
        ),
    ]


@pytest.fixture
def sample_gate_summary(sample_gate_results):
    """Create a sample gate summary with all passing gates."""
    return GateSummary(
        results=sample_gate_results,
        pass_count=8,
        fail_count=0,
        check_count=0,
        timestamp=datetime.now(UTC),
    )


@pytest.fixture
def sample_gate_summary_with_failures():
    """Create a sample gate summary with some failures."""
    now = datetime.now(UTC)
    results = [
        GateResult(
            gate="G1", status="✅ PASS", detail="Heartbeat 30s ago", timestamp=now
        ),
        GateResult(
            gate="G2",
            status="⚠️ CHECK",
            detail="No signals found in Redis",
            timestamp=now,
        ),
        GateResult(
            gate="G3",
            status="⚠️ CHECK",
            detail="No outcomes found in Redis",
            timestamp=now,
        ),
        GateResult(
            gate="G4",
            status="❌ FAIL",
            detail="Kill switch not configured",
            timestamp=now,
        ),
        GateResult(
            gate="G5", status="⚠️ CHECK", detail="pager:CHECK(5m)", timestamp=now
        ),
        GateResult(
            gate="G6", status="✅ PASS", detail="Bybit API reachable", timestamp=now
        ),
        GateResult(gate="G7", status="✅ PASS", detail="Redis OK", timestamp=now),
        GateResult(
            gate="G8",
            status="❓ UNKNOWN",
            detail="No burn-in verdict found",
            timestamp=now,
        ),
    ]
    return GateSummary(
        results=results,
        pass_count=3,
        fail_count=1,
        check_count=3,
        timestamp=now,
    )


@pytest.fixture
def sample_checkpoint_record():
    """Create a sample checkpoint record."""
    return CheckpointRecord(
        checkpoint_id="checkpoint-20240311-120000",
        state=CheckpointState.COMPLETED,
        status=CheckpointStatus.HEALTHY,
        created_at=datetime.now(UTC),
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
        metadata={"test": True, "source": "test_fixture"},
    )


@pytest.fixture
def mock_datetime_now():
    """Fixture to mock datetime.now() for consistent testing."""
    fixed_now = datetime(2024, 3, 11, 12, 0, 0, tzinfo=UTC)
    with patch("src.governance.checkpoint.gates.datetime") as mock_dt:
        mock_dt.now.return_value = fixed_now
        mock_dt.fromisoformat = datetime.fromisoformat
        yield fixed_now


@pytest.fixture
def patch_redis_connection():
    """Fixture to patch Redis connection attempts."""
    with patch("redis.Redis") as mock_redis_class:
        mock_instance = MagicMock()
        mock_redis_class.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def gate_checker_with_mock_redis(mock_redis_client):
    """Create a GateChecker with a mock Redis client."""
    return GateChecker(redis_client=mock_redis_client)
