"""Integration tests for ICT session components.

These tests use a real Redis connection for integration testing.
Skip if Redis is not available.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

# CRITICAL: Add src to path BEFORE any signal_generation imports
_worktree_src = Path(__file__).parent.parent.parent / "src"
if str(_worktree_src) not in sys.path:
    sys.path.insert(0, str(_worktree_src))

from signal_generation.ict_session_filter import ICTSessionFilter
from signal_generation.ict_session_manager import ICTSessionManager, SessionType
from signal_generation.models import Signal, SignalDirection, SignalStatus


def is_redis_available() -> bool:
    """Check if Redis is available."""
    try:
        import redis

        client = redis.Redis(host="host.docker.internal", port=6379, db=0)
        client.ping()
        return True
    except Exception:
        return False


requires_redis = pytest.mark.skipif(
    not is_redis_available(), reason="Redis not available"
)


@requires_redis
class TestICTSessionManagerIntegration:
    """Integration tests for ICTSessionManager with real Redis."""

    @pytest.fixture(autouse=True)
    def setup_teardown(self) -> None:
        """Clean up Redis keys before and after tests."""
        import redis

        client = redis.Redis(
            host="host.docker.internal", port=6379, db=0, decode_responses=True
        )
        # Clean up any test keys
        for key in client.scan_iter(match="chiseai:ict:session:*", count=100):
            client.delete(key)
        yield
        # Clean up after
        for key in client.scan_iter(match="chiseai:ict:session:*", count=100):
            client.delete(key)

    def test_session_london_active(self) -> None:
        """Test detecting London session is active at 14:00 UTC."""
        manager = ICTSessionManager()
        # 14:00 UTC is within London 08:00-17:00
        current = datetime(2026, 4, 7, 14, 0, tzinfo=ZoneInfo("UTC"))
        session = manager.get_current_session()
        assert session is not None
        assert session.session_type == SessionType.LONDON

    def test_session_ny_active(self) -> None:
        """Test detecting NY session is active at 15:30 UTC."""
        manager = ICTSessionManager()
        # 15:30 UTC is within NY 13:30-18:00
        current = datetime(2026, 4, 7, 15, 30, tzinfo=ZoneInfo("UTC"))
        session = manager.get_current_session()
        assert session is not None
        assert session.session_type == SessionType.NY

    def test_session_none_outside_hours(self) -> None:
        """Test no session detected outside session hours."""
        manager = ICTSessionManager()
        # 19:00 UTC is outside both London (until 17:00) and NY (until 18:00)
        current = datetime(2026, 4, 7, 19, 0, tzinfo=ZoneInfo("UTC"))
        session = manager.get_current_session()
        assert session is None

    def test_record_and_retrieve_signal(self) -> None:
        """Test recording and retrieving signal."""
        manager = ICTSessionManager()
        # Use a time within London session
        current = datetime(2026, 4, 7, 14, 0, tzinfo=ZoneInfo("UTC"))

        # Clear any existing data
        manager.clear_session()

        signal_id = "test_signal_integration_001"
        manager.record_signal(signal_id)

        # Verify it's not a duplicate now
        assert manager.is_duplicate(signal_id) is True

    def test_session_stats_after_signals(self) -> None:
        """Test session stats update after recording signals."""
        manager = ICTSessionManager()
        current = datetime(2026, 4, 7, 14, 0, tzinfo=ZoneInfo("UTC"))
        manager.clear_session()

        manager.record_signal("signal_001")
        manager.record_signal("signal_002")
        manager.record_duplicate("signal_001")  # Already recorded

        session = manager.get_current_session()
        assert session is not None
        assert session.signals_emitted == 2

    def test_clear_session(self) -> None:
        """Test clearing session data."""
        manager = ICTSessionManager()
        current = datetime(2026, 4, 7, 14, 0, tzinfo=ZoneInfo("UTC"))

        manager.record_signal("signal_001")
        manager.clear_session()

        session = manager.get_current_session()
        assert session is not None
        assert session.signals_emitted == 0


@requires_redis
class TestICTSessionFilterIntegration:
    """Integration tests for ICTSessionFilter with real Redis."""

    @pytest.fixture(autouse=True)
    def setup_teardown(self) -> None:
        """Clean up Redis keys before and after tests."""
        import redis

        client = redis.Redis(
            host="host.docker.internal", port=6379, db=0, decode_responses=True
        )
        # Clean up any test keys
        for key in client.scan_iter(match="chiseai:ict:session:*", count=100):
            client.delete(key)
        for key in client.scan_iter(match="chiseai:ict:filter:*", count=100):
            client.delete(key)
        yield
        # Clean up after
        for key in client.scan_iter(match="chiseai:ict:session:*", count=100):
            client.delete(key)
        for key in client.scan_iter(match="chiseai:ict:filter:*", count=100):
            client.delete(key)

    def test_filter_signals_in_session(
        self,
    ) -> None:
        """Test filtering signals within an active session."""
        filter_ = ICTSessionFilter()
        current = datetime(2026, 4, 7, 14, 0, tzinfo=ZoneInfo("UTC"))

        signals = [
            Signal(
                token="BTC/USDT",
                direction=SignalDirection.LONG,
                confidence=0.85,
                base_score=75.0,
                timestamp=current,
                status=SignalStatus.ACTIONABLE,
                timeframe="1H",
                signal_id="integration_sig_001",
                metadata={"quality_score": 0.7},
            ),
            Signal(
                token="ETH/USDT",
                direction=SignalDirection.SHORT,
                confidence=0.75,
                base_score=70.0,
                timestamp=current,
                status=SignalStatus.ACTIONABLE,
                timeframe="1H",
                signal_id="integration_sig_002",
                metadata={"quality_score": 0.6},
            ),
        ]

        allowed = filter_.filter_signals(signals)
        assert len(allowed) == 2

    def test_filter_blocks_duplicate(self) -> None:
        """Test that duplicate signals are blocked."""
        filter_ = ICTSessionFilter()
        current = datetime(2026, 4, 7, 14, 0, tzinfo=ZoneInfo("UTC"))

        signal = Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.85,
            base_score=75.0,
            timestamp=current,
            status=SignalStatus.ACTIONABLE,
            timeframe="1H",
            signal_id="integration_dup_sig",
            metadata={"quality_score": 0.7},
        )

        # First call should allow
        assert filter_.is_signal_allowed(signal) is True

        # Second call should block as duplicate
        assert filter_.is_signal_allowed(signal) is False

        metrics = filter_.get_filter_metrics()
        assert metrics.signals_allowed == 1
        assert metrics.signals_blocked_duplicate == 1

    def test_filter_blocks_low_quality(self) -> None:
        """Test that low quality signals are blocked."""
        filter_ = ICTSessionFilter()
        current = datetime(2026, 4, 7, 14, 0, tzinfo=ZoneInfo("UTC"))

        signal = Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.85,
            base_score=75.0,
            timestamp=current,
            status=SignalStatus.ACTIONABLE,
            timeframe="1H",
            signal_id="integration_low_quality_sig",
            metadata={"quality_score": 0.2},  # Below 0.5 threshold
        )

        result = filter_.is_signal_allowed(signal)
        assert result is False

        metrics = filter_.get_filter_metrics()
        assert metrics.signals_blocked_low_quality == 1
