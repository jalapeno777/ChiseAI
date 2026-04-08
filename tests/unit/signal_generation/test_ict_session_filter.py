"""Tests for ICTSessionFilter."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

# CRITICAL: Add src to path BEFORE any signal_generation imports
# This must happen at module load time before pytest's import hook
# interferes with the path resolution
_worktree_src = Path(__file__).parent.parent.parent.parent / "src"
if str(_worktree_src) not in sys.path:
    sys.path.insert(0, str(_worktree_src))

from signal_generation.ict_session_filter import FilterMetrics, ICTSessionFilter
from signal_generation.models import Signal, SignalDirection, SignalStatus


class TestFilterMetrics:
    """Tests for FilterMetrics dataclass."""

    def test_block_rate_zero_total(self) -> None:
        """Test block_rate is 0.0 when no signals processed."""
        metrics = FilterMetrics()
        assert metrics.block_rate == 0.0

    def test_block_rate_calculation(self) -> None:
        """Test block_rate calculates correctly."""
        metrics = FilterMetrics(total_processed=100, signals_blocked=25)
        assert metrics.block_rate == 0.25

    def test_allow_rate_zero_total(self) -> None:
        """Test allow_rate is 0.0 when no signals processed."""
        metrics = FilterMetrics()
        assert metrics.allow_rate == 0.0

    def test_allow_rate_calculation(self) -> None:
        """Test allow_rate calculates correctly."""
        metrics = FilterMetrics(total_processed=100, signals_allowed=80)
        assert metrics.allow_rate == 0.80

    def test_to_dict(self) -> None:
        """Test metrics serialization."""
        metrics = FilterMetrics(
            total_processed=50,
            signals_allowed=40,
            signals_blocked=10,
            signals_blocked_no_session=5,
            signals_blocked_duplicate=3,
            signals_blocked_low_quality=2,
        )
        d = metrics.to_dict()
        assert d["total_processed"] == 50
        assert d["signals_allowed"] == 40
        assert d["signals_blocked"] == 10
        assert d["block_rate"] == 0.2
        assert d["allow_rate"] == 0.8


class TestICTSessionFilter:
    """Tests for ICTSessionFilter."""

    @pytest.fixture
    def mock_session_manager(self) -> MagicMock:
        """Create mock session manager."""
        return MagicMock()

    @pytest.fixture
    def filter_(self, mock_session_manager: MagicMock) -> ICTSessionFilter:
        """Create filter with mock session manager."""
        return ICTSessionFilter(session_manager=mock_session_manager)

    @pytest.fixture
    def sample_signal(self) -> Signal:
        """Create a sample signal for testing."""
        return Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=0.85,
            base_score=75.0,
            timestamp=datetime(2026, 4, 7, 14, 0, tzinfo=ZoneInfo("UTC")),
            status=SignalStatus.ACTIONABLE,
            timeframe="1H",
            signal_id="test_signal_001",
        )

    def test_init_default_values(self, mock_session_manager: MagicMock) -> None:
        """Test filter initializes with default values."""
        filter_ = ICTSessionFilter(session_manager=mock_session_manager)
        assert filter_._threshold == 0.5
        assert filter_.metrics.total_processed == 0

    def test_init_custom_threshold(self, mock_session_manager: MagicMock) -> None:
        """Test filter accepts custom threshold."""
        filter_ = ICTSessionFilter(
            session_manager=mock_session_manager, quality_threshold=0.7
        )
        assert filter_._threshold == 0.7

    def test_init_env_threshold(self, mock_session_manager: MagicMock) -> None:
        """Test filter reads threshold from environment."""
        with patch("signal_generation.ict_session_filter.os.getenv") as mock_get:
            # Make os.getenv return 0.6 for ICT_SIGNAL_QUALITY_THRESHOLD and "6379" for REDIS_PORT
            def mock_getenv(key, default=None):
                if key == "ICT_SIGNAL_QUALITY_THRESHOLD":
                    return "0.6"
                elif key == "REDIS_PORT":
                    return "6379"
                elif key == "REDIS_HOST":
                    return "host.docker.internal"
                return default

            mock_get.side_effect = mock_getenv
            filter_ = ICTSessionFilter(session_manager=mock_session_manager)
            assert filter_._threshold == 0.6

    def test_get_quality_score_present(
        self, filter_: ICTSessionFilter, sample_signal: Signal
    ) -> None:
        """Test extracting quality score when present."""
        sample_signal.metadata["quality_score"] = 0.75
        score = filter_._get_quality_score(sample_signal)
        assert score == 0.75

    def test_get_quality_score_missing(
        self, filter_: ICTSessionFilter, sample_signal: Signal
    ) -> None:
        """Test extracting quality score when missing."""
        score = filter_._get_quality_score(sample_signal)
        assert score is None

    def test_is_signal_allowed_no_session(
        self,
        filter_: ICTSessionFilter,
        mock_session_manager: MagicMock,
        sample_signal: Signal,
    ) -> None:
        """Test signal blocked when no active session."""
        mock_session_manager.get_current_session.return_value = None

        result = filter_.is_signal_allowed(sample_signal)

        assert result is False
        assert filter_.metrics.signals_blocked_no_session == 1

    def test_is_signal_allowed_duplicate(
        self,
        filter_: ICTSessionFilter,
        mock_session_manager: MagicMock,
        sample_signal: Signal,
    ) -> None:
        """Test signal blocked when duplicate."""
        mock_session = MagicMock()
        mock_session_manager.get_current_session.return_value = mock_session
        mock_session_manager.is_duplicate.return_value = True

        result = filter_.is_signal_allowed(sample_signal)

        assert result is False
        assert filter_.metrics.signals_blocked_duplicate == 1
        mock_session_manager.record_duplicate.assert_called_once_with(
            sample_signal.signal_id
        )

    def test_is_signal_allowed_low_quality(
        self,
        filter_: ICTSessionFilter,
        mock_session_manager: MagicMock,
        sample_signal: Signal,
    ) -> None:
        """Test signal blocked when quality below threshold."""
        mock_session = MagicMock()
        mock_session_manager.get_current_session.return_value = mock_session
        mock_session_manager.is_duplicate.return_value = False
        sample_signal.metadata["quality_score"] = 0.3  # Below 0.5 threshold

        result = filter_.is_signal_allowed(sample_signal)

        assert result is False
        assert filter_.metrics.signals_blocked_low_quality == 1

    def test_is_signal_allowed_passes_all_checks(
        self,
        filter_: ICTSessionFilter,
        mock_session_manager: MagicMock,
        sample_signal: Signal,
    ) -> None:
        """Test signal allowed when all checks pass."""
        mock_session = MagicMock()
        mock_session_manager.get_current_session.return_value = mock_session
        mock_session_manager.is_duplicate.return_value = False
        sample_signal.metadata["quality_score"] = 0.7  # Above 0.5 threshold

        result = filter_.is_signal_allowed(sample_signal)

        assert result is True
        assert filter_.metrics.signals_allowed == 1
        mock_session_manager.record_signal.assert_called_once_with(
            sample_signal.signal_id
        )

    def test_is_signal_allowed_no_quality_score_above_threshold(
        self,
        filter_: ICTSessionFilter,
        mock_session_manager: MagicMock,
        sample_signal: Signal,
    ) -> None:
        """Test signal allowed when quality_score missing but other checks pass."""
        mock_session = MagicMock()
        mock_session_manager.get_current_session.return_value = mock_session
        mock_session_manager.is_duplicate.return_value = False
        # No quality_score in metadata

        result = filter_.is_signal_allowed(sample_signal)

        assert result is True
        assert filter_.metrics.signals_allowed == 1

    def test_filter_signals_empty_list(self, filter_: ICTSessionFilter) -> None:
        """Test filtering empty list returns empty list."""
        result = filter_.filter_signals([])
        assert result == []

    def test_filter_signals_all_allowed(
        self, filter_: ICTSessionFilter, mock_session_manager: MagicMock
    ) -> None:
        """Test filtering list where all signals are allowed."""
        mock_session = MagicMock()
        mock_session_manager.get_current_session.return_value = mock_session
        mock_session_manager.is_duplicate.return_value = False

        signals = [
            Signal(
                token="BTC/USDT",
                direction=SignalDirection.LONG,
                confidence=0.85,
                base_score=75.0,
                timestamp=datetime(2026, 4, 7, 14, 0, tzinfo=ZoneInfo("UTC")),
                status=SignalStatus.ACTIONABLE,
                timeframe="1H",
                signal_id=f"sig_{i}",
            )
            for i in range(3)
        ]

        result = filter_.filter_signals(signals)

        assert len(result) == 3
        assert filter_.metrics.total_processed == 3
        assert filter_.metrics.signals_allowed == 3

    def test_filter_signals_mixed(
        self, filter_: ICTSessionFilter, mock_session_manager: MagicMock
    ) -> None:
        """Test filtering list with mixed allowed/blocked signals."""
        mock_session = MagicMock()
        mock_session_manager.get_current_session.return_value = mock_session

        # First signal: allowed
        mock_session_manager.is_duplicate.return_value = False

        signals = [
            Signal(
                token="BTC/USDT",
                direction=SignalDirection.LONG,
                confidence=0.85,
                base_score=75.0,
                timestamp=datetime(2026, 4, 7, 14, 0, tzinfo=ZoneInfo("UTC")),
                status=SignalStatus.ACTIONABLE,
                timeframe="1H",
                signal_id="sig_allowed",
            ),
            Signal(
                token="ETH/USDT",
                direction=SignalDirection.SHORT,
                confidence=0.75,
                base_score=70.0,
                timestamp=datetime(2026, 4, 7, 14, 0, tzinfo=ZoneInfo("UTC")),
                status=SignalStatus.ACTIONABLE,
                timeframe="1H",
                signal_id="sig_duplicate",
            ),
        ]

        # First call returns False (not duplicate), second returns True (duplicate)
        mock_session_manager.is_duplicate.side_effect = [False, True]

        result = filter_.filter_signals(signals)

        assert len(result) == 1
        assert result[0].signal_id == "sig_allowed"
        assert filter_.metrics.total_processed == 2
        assert filter_.metrics.signals_allowed == 1
        assert filter_.metrics.signals_blocked_duplicate == 1

    def test_get_filter_metrics(
        self,
        filter_: ICTSessionFilter,
        mock_session_manager: MagicMock,
        sample_signal: Signal,
    ) -> None:
        """Test get_filter_metrics returns current metrics."""
        mock_session_manager.get_current_session.return_value = None
        filter_.is_signal_allowed(sample_signal)

        metrics = filter_.get_filter_metrics()

        assert metrics.total_processed == 1
        assert metrics.signals_blocked_no_session == 1
        assert metrics.signals_blocked == 1

    def test_metrics_emission_event(
        self,
        filter_: ICTSessionFilter,
        mock_session_manager: MagicMock,
        sample_signal: Signal,
    ) -> None:
        """Test that metrics events are emitted to Redis."""
        mock_session = MagicMock()
        mock_session_manager.get_current_session.return_value = mock_session
        mock_session_manager.is_duplicate.return_value = False
        sample_signal.metadata["quality_score"] = 0.7

        with patch.object(filter_, "_get_redis") as mock_get_redis:
            mock_redis = MagicMock()
            mock_get_redis.return_value = mock_redis

            filter_.is_signal_allowed(sample_signal)

            mock_redis.lpush.assert_called()
