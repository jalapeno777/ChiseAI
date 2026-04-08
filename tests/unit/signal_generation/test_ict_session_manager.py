"""Tests for ICTSessionManager."""

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

from signal_generation.ict_session_manager import (
    REDIS_KEY_PREFIX,
    ICTSession,
    ICTSessionManager,
    ICTSessionStats,
    SessionType,
    _parse_time,
)


class TestParseTime:
    """Tests for _parse_time helper."""

    def test_parse_valid_time(self) -> None:
        """Test parsing valid time strings."""
        t = _parse_time("08:00")
        assert t.hour == 8
        assert t.minute == 0

        t = _parse_time("13:30")
        assert t.hour == 13
        assert t.minute == 30

        t = _parse_time("00:00")
        assert t.hour == 0
        assert t.minute == 0

        t = _parse_time("23:59")
        assert t.hour == 23
        assert t.minute == 59

    def test_parse_invalid_format(self) -> None:
        """Test that invalid formats raise ValueError."""
        with pytest.raises(ValueError):
            _parse_time("0800")  # No colon

        with pytest.raises(ValueError):
            _parse_time("25:00")  # Invalid hour

        with pytest.raises(ValueError):
            _parse_time("08:60")  # Invalid minute


class TestICTSession:
    """Tests for ICTSession dataclass."""

    def test_is_active_within_session(self) -> None:
        """Test is_active returns True within session bounds."""
        session = ICTSession(
            session_type=SessionType.LONDON,
            start_time=datetime(2026, 4, 7, 8, 0, tzinfo=ZoneInfo("UTC")),
            end_time=datetime(2026, 4, 7, 17, 0, tzinfo=ZoneInfo("UTC")),
            session_id="london_20260407",
        )
        current = datetime(2026, 4, 7, 12, 0, tzinfo=ZoneInfo("UTC"))
        assert session.is_active(current) is True

    def test_is_active_at_boundary(self) -> None:
        """Test is_active at session boundaries."""
        session = ICTSession(
            session_type=SessionType.LONDON,
            start_time=datetime(2026, 4, 7, 8, 0, tzinfo=ZoneInfo("UTC")),
            end_time=datetime(2026, 4, 7, 17, 0, tzinfo=ZoneInfo("UTC")),
            session_id="london_20260407",
        )
        # At start time
        assert (
            session.is_active(datetime(2026, 4, 7, 8, 0, tzinfo=ZoneInfo("UTC")))
            is True
        )
        # At end time
        assert (
            session.is_active(datetime(2026, 4, 7, 17, 0, tzinfo=ZoneInfo("UTC")))
            is True
        )

    def test_is_active_outside_session(self) -> None:
        """Test is_active returns False outside session bounds."""
        session = ICTSession(
            session_type=SessionType.LONDON,
            start_time=datetime(2026, 4, 7, 8, 0, tzinfo=ZoneInfo("UTC")),
            end_time=datetime(2026, 4, 7, 17, 0, tzinfo=ZoneInfo("UTC")),
            session_id="london_20260407",
        )
        # Before session
        assert (
            session.is_active(datetime(2026, 4, 7, 7, 0, tzinfo=ZoneInfo("UTC")))
            is False
        )
        # After session
        assert (
            session.is_active(datetime(2026, 4, 7, 18, 0, tzinfo=ZoneInfo("UTC")))
            is False
        )

    def test_is_active_none_session(self) -> None:
        """Test is_active for NONE session type returns False."""
        session = ICTSession(
            session_type=SessionType.NONE,
            start_time=datetime(2026, 4, 7, 0, 0, tzinfo=ZoneInfo("UTC")),
            end_time=datetime(2026, 4, 7, 0, 0, tzinfo=ZoneInfo("UTC")),
            session_id="none_20260407",
        )
        assert (
            session.is_active(datetime(2026, 4, 7, 12, 0, tzinfo=ZoneInfo("UTC")))
            is False
        )

    def test_to_dict(self) -> None:
        """Test session serialization to dictionary."""
        session = ICTSession(
            session_type=SessionType.LONDON,
            start_time=datetime(2026, 4, 7, 8, 0, tzinfo=ZoneInfo("UTC")),
            end_time=datetime(2026, 4, 7, 17, 0, tzinfo=ZoneInfo("UTC")),
            session_id="london_20260407",
            signals_emitted=5,
            duplicate_count=2,
        )
        d = session.to_dict()
        assert d["session_type"] == "london"
        assert d["session_id"] == "london_20260407"
        assert d["signals_emitted"] == 5
        assert d["duplicate_count"] == 2


class TestICTSessionManager:
    """Tests for ICTSessionManager."""

    @pytest.fixture
    def mock_redis(self) -> MagicMock:
        """Create mock Redis client."""
        return MagicMock()

    @pytest.fixture
    def manager(self, mock_redis: MagicMock) -> ICTSessionManager:
        """Create manager with mock Redis."""
        return ICTSessionManager(redis_client=mock_redis, key_prefix=REDIS_KEY_PREFIX)

    def test_make_key(self, manager: ICTSessionManager) -> None:
        """Test Redis key generation."""
        key = manager._make_key("london_20260407")
        assert key == f"{REDIS_KEY_PREFIX}:london_20260407"

    def test_get_session_id_for_time(self, manager: ICTSessionManager) -> None:
        """Test session ID generation."""
        current = datetime(2026, 4, 7, 12, 0, tzinfo=ZoneInfo("UTC"))
        session_id = manager._get_session_id_for_time(SessionType.LONDON, current)
        assert session_id == "london_20260407"

    def test_get_session_id_for_time_ny(self, manager: ICTSessionManager) -> None:
        """Test session ID generation for NY session."""
        current = datetime(2026, 4, 7, 14, 0, tzinfo=ZoneInfo("UTC"))
        session_id = manager._get_session_id_for_time(SessionType.NY, current)
        assert session_id == "ny_20260407"

    def test_get_current_session_type_london(
        self, manager: ICTSessionManager, mock_redis: MagicMock
    ) -> None:
        """Test London session type detection."""
        # Within London hours (14:00 UTC = 10:00 NY = 09:00 London... wait
        # 14:00 UTC is within London 08:00-17:00
        current = datetime(2026, 4, 7, 14, 0, tzinfo=ZoneInfo("UTC"))
        session_type = manager._get_current_session_type(current)
        assert session_type == SessionType.LONDON

    def test_get_current_session_type_ny(
        self, manager: ICTSessionManager, mock_redis: MagicMock
    ) -> None:
        """Test NY session type detection."""
        # 17:30 UTC is within NY 13:30-18:00 but after London ends (17:00)
        current = datetime(2026, 4, 7, 17, 30, tzinfo=ZoneInfo("UTC"))
        session_type = manager._get_current_session_type(current)
        assert session_type == SessionType.NY

    def test_get_current_session_type_none(
        self, manager: ICTSessionManager, mock_redis: MagicMock
    ) -> None:
        """Test no session type detection outside hours."""
        # 19:00 UTC is outside both London (17:00 end) and NY (18:00 end)
        current = datetime(2026, 4, 7, 19, 0, tzinfo=ZoneInfo("UTC"))
        session_type = manager._get_current_session_type(current)
        assert session_type == SessionType.NONE

    def test_get_current_session_no_session(
        self, manager: ICTSessionManager, mock_redis: MagicMock
    ) -> None:
        """Test get_current_session returns None outside session hours."""
        mock_redis.hgetall.return_value = {}
        current = datetime(2026, 4, 7, 19, 0, tzinfo=ZoneInfo("UTC"))
        with patch.object(
            manager, "_get_current_session_type", return_value=SessionType.NONE
        ):
            session = manager.get_current_session()
        assert session is None

    def test_get_current_session_with_data(
        self, manager: ICTSessionManager, mock_redis: MagicMock
    ) -> None:
        """Test get_current_session returns session with data."""
        mock_redis.hgetall.return_value = {
            "signals_emitted": "3",
            "duplicate_count": "1",
        }
        current = datetime(2026, 4, 7, 14, 0, tzinfo=ZoneInfo("UTC"))
        with patch.object(
            manager, "_get_current_session_type", return_value=SessionType.LONDON
        ):
            session = manager.get_current_session()
        assert session is not None
        assert session.session_type == SessionType.LONDON
        assert session.signals_emitted == 3
        assert session.duplicate_count == 1

    def test_is_duplicate_no_session(
        self, manager: ICTSessionManager, mock_redis: MagicMock
    ) -> None:
        """Test is_duplicate returns False when no session is active."""
        with patch.object(manager, "get_current_session", return_value=None):
            result = manager.is_duplicate("signal_123")
        assert result is False

    def test_is_duplicate_found(
        self, manager: ICTSessionManager, mock_redis: MagicMock
    ) -> None:
        """Test is_duplicate returns True when signal exists."""
        mock_session = MagicMock()
        mock_session.session_id = "london_20260407"
        mock_redis.sismember.return_value = True

        with patch.object(manager, "get_current_session", return_value=mock_session):
            result = manager.is_duplicate("signal_123")
        assert result is True
        mock_redis.sismember.assert_called_once()

    def test_is_duplicate_not_found(
        self, manager: ICTSessionManager, mock_redis: MagicMock
    ) -> None:
        """Test is_duplicate returns False when signal does not exist."""
        mock_session = MagicMock()
        mock_session.session_id = "london_20260407"
        mock_redis.sismember.return_value = False

        with patch.object(manager, "get_current_session", return_value=mock_session):
            result = manager.is_duplicate("signal_123")
        assert result is False

    def test_record_signal_no_session(
        self, manager: ICTSessionManager, mock_redis: MagicMock
    ) -> None:
        """Test record_signal does nothing when no session is active."""
        with patch.object(manager, "get_current_session", return_value=None):
            manager.record_signal("signal_123")
        # Redis should not be called
        mock_redis.sadd.assert_not_called()
        mock_redis.hincrby.assert_not_called()

    def test_record_signal_success(
        self, manager: ICTSessionManager, mock_redis: MagicMock
    ) -> None:
        """Test record_signal stores signal and increments counter."""
        mock_session = MagicMock()
        mock_session.session_id = "london_20260407"

        with patch.object(manager, "get_current_session", return_value=mock_session):
            manager.record_signal("signal_123")

        # Verify Redis calls
        mock_redis.sadd.assert_called_once()
        mock_redis.expire.assert_called()
        mock_redis.hincrby.assert_called_once()

    def test_record_duplicate_no_session(
        self, manager: ICTSessionManager, mock_redis: MagicMock
    ) -> None:
        """Test record_duplicate does nothing when no session is active."""
        with patch.object(manager, "get_current_session", return_value=None):
            manager.record_duplicate("signal_123")
        mock_redis.hincrby.assert_not_called()

    def test_record_duplicate_success(
        self, manager: ICTSessionManager, mock_redis: MagicMock
    ) -> None:
        """Test record_duplicate increments duplicate counter."""
        mock_session = MagicMock()
        mock_session.session_id = "london_20260407"

        with patch.object(manager, "get_current_session", return_value=mock_session):
            manager.record_duplicate("signal_456")

        mock_redis.hincrby.assert_called_once()

    def test_get_session_stats(
        self, manager: ICTSessionManager, mock_redis: MagicMock
    ) -> None:
        """Test get_session_stats aggregates correctly."""
        mock_redis.scan_iter.return_value = iter(
            [
                f"{REDIS_KEY_PREFIX}:london_20260407",
                f"{REDIS_KEY_PREFIX}:ny_20260407",
            ]
        )
        mock_redis.hgetall.side_effect = [
            {"signals_emitted": "5", "duplicate_count": "2"},
            {"signals_emitted": "3", "duplicate_count": "1"},
        ]

        with patch.object(manager, "get_current_session", return_value=None):
            stats = manager.get_session_stats()

        assert stats["total_sessions"] == 2
        assert stats["total_signals"] == 8
        assert stats["total_duplicates"] == 3
        assert stats["session_type_counts"]["london"] == 1
        assert stats["session_type_counts"]["ny"] == 1

    def test_clear_session_no_session(
        self, manager: ICTSessionManager, mock_redis: MagicMock
    ) -> None:
        """Test clear_session does nothing when no session is active."""
        with patch.object(manager, "get_current_session", return_value=None):
            manager.clear_session()
        mock_redis.delete.assert_not_called()

    def test_clear_session_success(
        self, manager: ICTSessionManager, mock_redis: MagicMock
    ) -> None:
        """Test clear_session deletes session data."""
        mock_session = MagicMock()
        mock_session.session_id = "london_20260407"

        with patch.object(manager, "get_current_session", return_value=mock_session):
            manager.clear_session()

        assert mock_redis.delete.call_count == 2  # session key + signals key


class TestICTSessionStats:
    """Tests for ICTSessionStats."""

    def test_to_dict_current_session_none(self) -> None:
        """Test stats serialization with no current session."""
        stats = ICTSessionStats(
            current_session=None,
            total_sessions=5,
            total_signals=10,
            total_duplicates=2,
        )
        d = stats.to_dict()
        assert d["current_session"] is None
        assert d["total_sessions"] == 5

    def test_to_dict_with_session(self) -> None:
        """Test stats serialization with active session."""
        session = ICTSession(
            session_type=SessionType.LONDON,
            start_time=datetime(2026, 4, 7, 8, 0, tzinfo=ZoneInfo("UTC")),
            end_time=datetime(2026, 4, 7, 17, 0, tzinfo=ZoneInfo("UTC")),
            session_id="london_20260407",
        )
        stats = ICTSessionStats(
            current_session=session,
            total_sessions=5,
            total_signals=10,
            total_duplicates=2,
        )
        d = stats.to_dict()
        assert d["current_session"]["session_type"] == "london"
        assert d["total_signals"] == 10
