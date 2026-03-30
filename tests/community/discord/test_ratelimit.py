"""
Tests for Discord Community Rate Limiter.

Validates rate limiting behavior for commands, messages, and identify operations.
"""


import pytest
from src.community.discord.ratelimit import (
    RateLimitConfig,
    RateLimiter,
    RateLimitStatus,
)


class TestRateLimiter:
    """Test cases for RateLimiter class."""

    @pytest.fixture
    def config(self):
        """Create a test configuration."""
        return RateLimitConfig(
            commands_per_user_per_minute=5,
            messages_per_channel_per_minute=20,
            identify_per_second=5.0,
        )

    @pytest.fixture
    def rate_limiter(self, config):
        """Create a RateLimiter instance for testing."""
        return RateLimiter(config=config)

    @pytest.mark.asyncio
    async def test_initialization(self, rate_limiter, config):
        """Test rate limiter initializes correctly."""
        assert rate_limiter.config == config
        assert rate_limiter._user_commands == {}
        assert rate_limiter._channel_messages == {}
        assert rate_limiter._user_status == {}
        assert rate_limiter._channel_status == {}

    @pytest.mark.asyncio
    async def test_command_rate_limit_allows_under_limit(self, rate_limiter):
        """Test that commands under the limit are allowed."""
        user_id = "12345"

        # First 5 commands should be allowed
        for i in range(5):
            allowed, status = await rate_limiter.check_user_command(user_id)
            assert allowed is True

    @pytest.mark.asyncio
    async def test_command_rate_limit_blocks_over_limit(self, rate_limiter):
        """Test that commands over the limit are blocked."""
        user_id = "12345"

        # Exhaust the limit
        for _ in range(5):
            await rate_limiter.check_user_command(user_id)

        # Next command should be blocked
        allowed, status = await rate_limiter.check_user_command(user_id)
        assert allowed is False
        assert status.is_limited is True

    @pytest.mark.asyncio
    async def test_message_rate_limit(self, rate_limiter):
        """Test message rate limiting per channel."""
        channel_id = "99999"

        # 20 messages should be allowed
        for i in range(20):
            allowed, status = await rate_limiter.check_channel_message(channel_id)
            assert allowed is True

        # 21st message should be blocked
        allowed, status = await rate_limiter.check_channel_message(channel_id)
        assert allowed is False
        assert status.is_limited is True

    @pytest.mark.asyncio
    async def test_identify_rate_limit(self, rate_limiter):
        """Test identify rate limiting."""
        # First identify should be allowed
        result = await rate_limiter.check_identify()
        assert result is True

        # Immediate second identify should be blocked
        result = await rate_limiter.check_identify()
        assert result is False

    @pytest.mark.asyncio
    async def test_get_user_status(self, rate_limiter):
        """Test getting status for user command bucket."""
        user_id = "12345"

        # Use some commands
        await rate_limiter.check_user_command(user_id)
        await rate_limiter.check_user_command(user_id)

        status = rate_limiter.get_user_status(user_id)

        assert status is not None
        assert status.max_count == 5
        assert status.current_count == 2
        assert status.is_limited is False

    @pytest.mark.asyncio
    async def test_get_user_status_when_limited(self, rate_limiter):
        """Test getting status when rate limited."""
        user_id = "12345"

        # Exhaust the limit (5 allowed) + 1 that triggers limit
        for _ in range(5):
            await rate_limiter.check_user_command(user_id)

        # 6th call should be rate limited
        allowed, limited_status = await rate_limiter.check_user_command(user_id)
        assert allowed is False
        assert limited_status.is_limited is True

        status = rate_limiter.get_user_status(user_id)

        assert status is not None
        assert status.remaining == 0
        assert status.is_limited is True

    @pytest.mark.asyncio
    async def test_get_user_status_nonexistent(self, rate_limiter):
        """Test getting status for non-existent user."""
        status = rate_limiter.get_user_status("99999")

        assert status is not None
        assert status.current_count == 0
        assert status.is_limited is False

    @pytest.mark.asyncio
    async def test_get_channel_status(self, rate_limiter):
        """Test getting channel message status."""
        channel_id = "99999"

        # Use some messages
        await rate_limiter.check_channel_message(channel_id)
        await rate_limiter.check_channel_message(channel_id)

        status = rate_limiter.get_channel_status(channel_id)

        assert status is not None
        assert status.max_count == 20
        assert status.current_count == 2
        assert status.is_limited is False

    @pytest.mark.asyncio
    async def test_clear_user_warnings(self, rate_limiter):
        """Test clearing user warnings."""
        user_id = "12345"

        # Use commands to trigger warnings
        for _ in range(4):
            await rate_limiter.check_user_command(user_id)

        # Warning should be set
        status = rate_limiter.get_user_status(user_id)

        # Clear warnings
        await rate_limiter.clear_user_warnings(user_id)

        # Verify cleared (warning_sent should be False)
        status = rate_limiter.get_user_status(user_id)
        assert status.warning_sent is False

    @pytest.mark.asyncio
    async def test_clear_channel_warnings(self, rate_limiter):
        """Test clearing channel warnings."""
        channel_id = "99999"

        # Use messages to trigger warnings
        for _ in range(16):  # 80% of 20
            await rate_limiter.check_channel_message(channel_id)

        # Clear warnings
        await rate_limiter.clear_channel_warnings(channel_id)

        # Verify cleared
        status = rate_limiter.get_channel_status(channel_id)
        assert status.warning_sent is False


class TestRateLimitConfig:
    """Test cases for RateLimitConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = RateLimitConfig()

        assert config.commands_per_user_per_minute == 5
        assert config.messages_per_channel_per_minute == 20
        assert config.identify_per_second == 5.0
        assert config.warning_threshold == 0.8

    def test_custom_config(self):
        """Test custom configuration."""
        config = RateLimitConfig(
            commands_per_user_per_minute=10,
            messages_per_channel_per_minute=50,
        )

        assert config.commands_per_user_per_minute == 10
        assert config.messages_per_channel_per_minute == 50
        # Unchanged values should still be defaults
        assert config.identify_per_second == 5.0

    def test_from_dict(self):
        """Test creating config from dictionary."""
        data = {
            "commands_per_user_per_minute": 10,
            "messages_per_channel_per_minute": 30,
            "identify_per_second": 10.0,
            "warning_threshold": 0.9,
        }

        config = RateLimitConfig.from_dict(data)

        assert config.commands_per_user_per_minute == 10
        assert config.messages_per_channel_per_minute == 30
        assert config.identify_per_second == 10.0
        assert config.warning_threshold == 0.9


class TestRateLimitStatus:
    """Test cases for RateLimitStatus dataclass."""

    def test_status_creation(self):
        """Test creating a status object."""
        status = RateLimitStatus(current_count=2, max_count=5, is_limited=False)

        assert status.current_count == 2
        assert status.max_count == 5
        assert status.remaining == 3
        assert status.is_limited is False

    def test_status_limited(self):
        """Test status when limited."""
        status = RateLimitStatus(current_count=5, max_count=5, is_limited=True)

        assert status.is_limited is True
        assert status.remaining == 0

    def test_usage_percentage(self):
        """Test usage percentage calculation."""
        status = RateLimitStatus(current_count=4, max_count=5, is_limited=False)

        assert status.usage_percentage == 0.8

    def test_usage_percentage_zero_max(self):
        """Test usage percentage with zero max returns 0."""
        status = RateLimitStatus(current_count=0, max_count=0, is_limited=False)

        assert status.usage_percentage == 0.0

    def test_remaining_property(self):
        """Test remaining property calculation."""
        status = RateLimitStatus(current_count=3, max_count=5, is_limited=False)

        assert status.remaining == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
