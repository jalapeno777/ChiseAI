"""Tests for paper kill switch.

For PAPER-009: Emergency kill switch for paper trading
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.execution.paper.paper_kill_switch import (
    PAPER_KILL_SWITCH_KEY,
    PaperKillSwitchActiveError,
    PaperKillSwitchManager,
    PaperKillSwitchStatus,
    activate_sync,
    deactivate_sync,
    get_status_sync,
)


class TestPaperKillSwitchStatus:
    """Tests for PaperKillSwitchStatus dataclass."""

    def test_inactive_status(self):
        """Test inactive status initialization."""
        status = PaperKillSwitchStatus(active=False)
        assert status.active is False
        assert status.reason == ""
        assert status.activated_at is None
        assert status.activated_by == ""
        assert status.ttl_remaining is None

    def test_active_status(self):
        """Test active status initialization."""
        status = PaperKillSwitchStatus(
            active=True,
            reason="test reason",
            activated_at="2024-01-01T00:00:00+00:00",
            activated_by="test_user",
            ttl_remaining=300,
        )
        assert status.active is True
        assert status.reason == "test reason"
        assert status.activated_at == "2024-01-01T00:00:00+00:00"
        assert status.activated_by == "test_user"
        assert status.ttl_remaining == 300

    def test_to_dict(self):
        """Test conversion to dictionary."""
        status = PaperKillSwitchStatus(
            active=True,
            reason="test reason",
            activated_at="2024-01-01T00:00:00+00:00",
            activated_by="test_user",
            ttl_remaining=300,
        )
        d = status.to_dict()
        assert d["active"] is True
        assert d["reason"] == "test reason"
        assert d["activated_at"] == "2024-01-01T00:00:00+00:00"
        assert d["activated_by"] == "test_user"
        assert d["ttl_remaining"] == 300

    def test_str_repr_inactive(self):
        """Test string representation of inactive status."""
        status = PaperKillSwitchStatus(active=False)
        s = str(status)
        assert "INACTIVE" in s
        assert "processing enabled" in s

    def test_str_repr_active(self):
        """Test string representation of active status."""
        status = PaperKillSwitchStatus(
            active=True,
            reason="emergency stop",
            activated_at="2024-01-01T00:00:00+00:00",
            activated_by="manual",
            ttl_remaining=300,
        )
        s = str(status)
        assert "ACTIVE" in s
        assert "emergency stop" in s
        assert "manual" in s
        assert "300s" in s


class TestPaperKillSwitchManager:
    """Tests for PaperKillSwitchManager."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        redis = MagicMock()
        redis.hgetall = AsyncMock()
        redis.ttl = AsyncMock()
        redis.hset = AsyncMock()
        redis.expire = AsyncMock()
        redis.delete = AsyncMock()
        redis.pipeline = MagicMock()
        return redis

    @pytest.fixture
    def manager(self, mock_redis):
        """Create manager with mock Redis."""
        return PaperKillSwitchManager(redis_client=mock_redis, default_ttl=3600)

    @pytest.mark.asyncio
    async def test_get_status_inactive(self, manager, mock_redis):
        """Test getting status when kill switch is inactive."""
        mock_redis.hgetall.return_value = {}
        mock_redis.ttl.return_value = -2  # Key doesn't exist

        status = await manager.get_status()

        assert status.active is False
        mock_redis.hgetall.assert_called_once_with(PAPER_KILL_SWITCH_KEY)

    @pytest.mark.asyncio
    async def test_get_status_active(self, manager, mock_redis):
        """Test getting status when kill switch is active."""
        mock_redis.hgetall.return_value = {
            "active": "true",
            "reason": "test reason",
            "activated_at": "2024-01-01T00:00:00+00:00",
            "activated_by": "test_user",
        }
        mock_redis.ttl.return_value = 300

        status = await manager.get_status()

        assert status.active is True
        assert status.reason == "test reason"
        assert status.activated_by == "test_user"
        assert status.ttl_remaining == 300

    @pytest.mark.asyncio
    async def test_is_active(self, manager, mock_redis):
        """Test is_active method."""
        mock_redis.hgetall.return_value = {}
        mock_redis.ttl.return_value = -2

        is_active = await manager.is_active()
        assert is_active is False

    @pytest.mark.asyncio
    async def test_activate(self, manager, mock_redis):
        """Test activating kill switch."""
        mock_pipe = MagicMock()
        mock_pipe.__aenter__ = AsyncMock(return_value=mock_pipe)
        mock_pipe.__aexit__ = AsyncMock(return_value=None)
        mock_pipe.hset = AsyncMock()
        mock_pipe.expire = AsyncMock()
        mock_pipe.execute = AsyncMock()
        mock_redis.pipeline.return_value = mock_pipe

        result = await manager.activate(reason="test", activated_by="user", ttl=60)

        assert result is True
        mock_pipe.hset.assert_called_once()
        mock_pipe.expire.assert_called_once_with(PAPER_KILL_SWITCH_KEY, 60)
        mock_pipe.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_deactivate(self, manager, mock_redis):
        """Test deactivating kill switch."""
        mock_redis.delete.return_value = 1

        result = await manager.deactivate()

        assert result is True
        mock_redis.delete.assert_called_once_with(PAPER_KILL_SWITCH_KEY)

    @pytest.mark.asyncio
    async def test_check_and_raise_if_active_not_active(self, manager, mock_redis):
        """Test check_and_raise_if_active when not active."""
        mock_redis.hgetall.return_value = {}
        mock_redis.ttl.return_value = -2

        # Should not raise
        await manager.check_and_raise_if_active()

    @pytest.mark.asyncio
    async def test_check_and_raise_if_active_is_active(self, manager, mock_redis):
        """Test check_and_raise_if_active when active."""
        mock_redis.hgetall.return_value = {
            "active": "true",
            "reason": "test reason",
            "activated_at": "2024-01-01T00:00:00+00:00",
            "activated_by": "test_user",
        }
        mock_redis.ttl.return_value = 300

        with pytest.raises(PaperKillSwitchActiveError) as exc_info:
            await manager.check_and_raise_if_active()
        assert "test reason" in str(exc_info.value)


class TestPaperKillSwitchActiveError:
    """Tests for PaperKillSwitchActiveError."""

    def test_default_message(self):
        """Test default error message."""
        error = PaperKillSwitchActiveError()
        assert error.message == "Paper kill switch is active"

    def test_custom_message(self):
        """Test custom error message."""
        error = PaperKillSwitchActiveError("Custom reason")
        assert error.message == "Custom reason"


class TestSyncFunctions:
    """Tests for synchronous convenience functions."""

    def test_activate_sync(self):
        """Test activate_sync function."""
        with patch(
            "src.execution.paper.paper_kill_switch.get_redis_client"
        ) as mock_get_redis:
            mock_redis = MagicMock()
            mock_pipe = MagicMock()
            mock_pipe.hset = MagicMock()
            mock_pipe.expire = MagicMock()
            mock_pipe.execute = MagicMock()
            mock_redis.pipeline.return_value = mock_pipe
            mock_get_redis.return_value = mock_redis

            result = activate_sync(reason="sync test", ttl=120)

            assert result is True
            mock_pipe.hset.assert_called_once()
            mock_pipe.expire.assert_called_once_with(PAPER_KILL_SWITCH_KEY, 120)
            mock_pipe.execute.assert_called_once()

    def test_deactivate_sync(self):
        """Test deactivate_sync function."""
        with patch(
            "src.execution.paper.paper_kill_switch.get_redis_client"
        ) as mock_get_redis:
            mock_redis = MagicMock()
            mock_redis.delete.return_value = 1
            mock_get_redis.return_value = mock_redis

            result = deactivate_sync()

            assert result is True
            mock_redis.delete.assert_called_once_with(PAPER_KILL_SWITCH_KEY)

    def test_get_status_sync_inactive(self):
        """Test get_status_sync when inactive."""
        with patch(
            "src.execution.paper.paper_kill_switch.get_redis_client"
        ) as mock_get_redis:
            mock_redis = MagicMock()
            mock_redis.hgetall.return_value = {}
            mock_redis.ttl.return_value = -2
            mock_get_redis.return_value = mock_redis

            status = get_status_sync()

            assert status.active is False


class TestTTLExpiry:
    """Tests for TTL expiry behavior."""

    @pytest.fixture
    def mock_redis_short_ttl(self):
        """Create a mock Redis client with short TTL."""
        redis = MagicMock()
        redis.hgetall = AsyncMock()
        redis.ttl = AsyncMock()
        return redis

    @pytest.mark.asyncio
    async def test_ttl_counts_down(self, mock_redis_short_ttl):
        """Test that TTL counts down correctly."""
        # First call returns 60s remaining
        mock_redis_short_ttl.hgetall.return_value = {
            "active": "true",
            "reason": "test",
            "activated_at": "2024-01-01T00:00:00+00:00",
            "activated_by": "user",
        }
        mock_redis_short_ttl.ttl.return_value = 60

        manager = PaperKillSwitchManager(redis_client=mock_redis_short_ttl)
        status = await manager.get_status()

        assert status.active is True
        assert status.ttl_remaining == 60

    @pytest.mark.asyncio
    async def test_expired_key_returns_inactive(self, mock_redis_short_ttl):
        """Test that expired key returns inactive status."""
        mock_redis_short_ttl.hgetall.return_value = {}
        mock_redis_short_ttl.ttl.return_value = -2  # Key doesn't exist

        manager = PaperKillSwitchManager(redis_client=mock_redis_short_ttl)
        status = await manager.get_status()

        assert status.active is False


class TestKillSwitchSETKeyFallback:
    """Tests for kill switch SET key fallback (FIX 3f).

    When someone activates the kill switch via `SET paper:kill_switch:global true`
    (wrong key, wrong type), the system should still detect it.
    """

    @pytest.mark.asyncio
    async def test_set_key_fallback_activates_kill_switch(self):
        """Test that SET key fallback activates kill switch when hash is empty."""
        mock_redis = AsyncMock()
        mock_redis.hgetall.return_value = {}  # No hash key
        mock_redis.get.return_value = b"true"  # SET key exists

        manager = PaperKillSwitchManager(redis_client=mock_redis)
        status = await manager.get_status()

        assert status.active is True
        assert status.reason == "emergency_manual_activation"
        assert status.activated_by == "manual_redis_set"

    @pytest.mark.asyncio
    async def test_set_key_fallback_with_string_yes(self):
        """Test SET key fallback with 'yes' value."""
        mock_redis = AsyncMock()
        mock_redis.hgetall.return_value = {}
        mock_redis.get.return_value = "yes"

        manager = PaperKillSwitchManager(redis_client=mock_redis)
        status = await manager.get_status()

        assert status.active is True

    @pytest.mark.asyncio
    async def test_set_key_fallback_with_string_1(self):
        """Test SET key fallback with '1' value."""
        mock_redis = AsyncMock()
        mock_redis.hgetall.return_value = {}
        mock_redis.get.return_value = b"1"

        manager = PaperKillSwitchManager(redis_client=mock_redis)
        status = await manager.get_status()

        assert status.active is True

    @pytest.mark.asyncio
    async def test_set_key_fallback_ignores_false_values(self):
        """Test that SET key fallback ignores false-like values."""
        mock_redis = AsyncMock()
        mock_redis.hgetall.return_value = {}
        mock_redis.get.return_value = b"false"

        manager = PaperKillSwitchManager(redis_client=mock_redis)
        status = await manager.get_status()

        assert status.active is False

    @pytest.mark.asyncio
    async def test_set_key_fallback_none_value(self):
        """Test SET key fallback when key doesn't exist (None)."""
        mock_redis = AsyncMock()
        mock_redis.hgetall.return_value = {}
        mock_redis.get.return_value = None

        manager = PaperKillSwitchManager(redis_client=mock_redis)
        status = await manager.get_status()

        assert status.active is False

    @pytest.mark.asyncio
    async def test_hash_key_takes_precedence_over_set_key(self):
        """Test that hash key is checked first and takes precedence."""
        mock_redis = AsyncMock()
        mock_redis.hgetall.return_value = {
            "active": "true",
            "reason": "test_hash",
            "activated_at": "2024-01-01T00:00:00+00:00",
            "activated_by": "hash_user",
        }
        mock_redis.ttl.return_value = 300
        # SET key also exists but should be ignored
        mock_redis.get.return_value = b"true"

        manager = PaperKillSwitchManager(redis_client=mock_redis)
        status = await manager.get_status()

        assert status.active is True
        assert status.reason == "test_hash"
        assert status.activated_by == "hash_user"
        # SET key should NOT have been checked
        mock_redis.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_set_key_fallback_exception_non_blocking(self):
        """Test that SET key fallback exception doesn't block."""
        mock_redis = AsyncMock()
        mock_redis.hgetall.return_value = {}
        mock_redis.get.side_effect = Exception("Redis error")

        manager = PaperKillSwitchManager(redis_client=mock_redis)
        status = await manager.get_status()

        # Should still return inactive (not crash)
        assert status.active is False


class TestKillSwitchSETKeyFallbackSync:
    """Tests for kill switch SET key fallback in sync mode."""

    def test_sync_set_key_fallback_activates(self):
        """Test that sync SET key fallback activates kill switch."""
        mock_redis = MagicMock()
        mock_redis.hgetall.return_value = {}
        mock_redis.get.return_value = b"true"

        with patch(
            "src.execution.paper.paper_kill_switch.get_redis_client",
            return_value=mock_redis,
        ):
            # Clear sync cache
            import src.execution.paper.paper_kill_switch as mod

            mod._sync_status_cache = None
            mod._sync_status_cache_time = None

            status = get_status_sync()

            assert status.active is True
            assert status.reason == "emergency_manual_activation"

    def test_sync_set_key_fallback_inactive_when_none(self):
        """Test that sync fallback returns inactive when SET key is None."""
        mock_redis = MagicMock()
        mock_redis.hgetall.return_value = {}
        mock_redis.get.return_value = None

        with patch(
            "src.execution.paper.paper_kill_switch.get_redis_client",
            return_value=mock_redis,
        ):
            import src.execution.paper.paper_kill_switch as mod

            mod._sync_status_cache = None
            mod._sync_status_cache_time = None

            status = get_status_sync()

            assert status.active is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
