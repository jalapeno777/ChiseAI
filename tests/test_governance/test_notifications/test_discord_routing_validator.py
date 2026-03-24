"""Tests for Discord routing configuration validator.

Tests for AUTOCOG-004: Discord routing config validator
"""

from __future__ import annotations

from src.governance.notifications.discord_notifier import (
    CHANNEL_ID_PATTERN,
    WEBHOOK_URL_PATTERN,
    validate_routing_config,
)


class TestChannelIdPattern:
    """Test cases for CHANNEL_ID_PATTERN regex."""

    def test_valid_channel_id_17_digits(self) -> None:
        """Test 17-digit channel ID matches pattern."""
        assert CHANNEL_ID_PATTERN.match("12345678901234567") is not None

    def test_valid_channel_id_18_digits(self) -> None:
        """Test 18-digit channel ID matches pattern."""
        assert CHANNEL_ID_PATTERN.match("123456789012345678") is not None

    def test_valid_channel_id_19_digits(self) -> None:
        """Test 19-digit channel ID matches pattern."""
        assert CHANNEL_ID_PATTERN.match("1234567890123456789") is not None

    def test_valid_channel_id_20_digits(self) -> None:
        """Test 20-digit channel ID matches pattern."""
        assert CHANNEL_ID_PATTERN.match("12345678901234567890") is not None

    def test_invalid_channel_id_16_digits(self) -> None:
        """Test 16-digit channel ID does not match pattern."""
        assert CHANNEL_ID_PATTERN.match("1234567890123456") is None

    def test_invalid_channel_id_21_digits(self) -> None:
        """Test 21-digit channel ID does not match pattern."""
        assert CHANNEL_ID_PATTERN.match("123456789012345678901") is None

    def test_invalid_channel_id_non_numeric(self) -> None:
        """Test non-numeric channel ID does not match pattern."""
        assert CHANNEL_ID_PATTERN.match("1234567890abcdefg") is None

    def test_invalid_channel_id_with_spaces(self) -> None:
        """Test channel ID with spaces does not match pattern."""
        assert CHANNEL_ID_PATTERN.match("123456789 01234567") is None

    def test_invalid_channel_id_empty(self) -> None:
        """Test empty channel ID does not match pattern."""
        assert CHANNEL_ID_PATTERN.match("") is None


class TestWebhookUrlPattern:
    """Test cases for WEBHOOK_URL_PATTERN regex."""

    def test_valid_webhook_url(self) -> None:
        """Test valid Discord webhook URL matches pattern."""
        url = "https://discord.com/api/webhooks/12345678901234567890/abcdefghijklmnopqrstuvwxyz"
        assert WEBHOOK_URL_PATTERN.match(url) is not None

    def test_valid_webhook_url_with_hyphens(self) -> None:
        """Test webhook URL with hyphens in token matches pattern."""
        url = "https://discord.com/api/webhooks/12345678901234567/abc-def_ghi"
        assert WEBHOOK_URL_PATTERN.match(url) is not None

    def test_valid_webhook_url_with_underscores(self) -> None:
        """Test webhook URL with underscores in token matches pattern."""
        url = "https://discord.com/api/webhooks/123456789012345678/abc_def_ghi"
        assert WEBHOOK_URL_PATTERN.match(url) is not None

    def test_invalid_webhook_url_http(self) -> None:
        """Test HTTP webhook URL does not match pattern (requires HTTPS)."""
        url = "http://discord.com/api/webhooks/12345678901234567890/abcdefghijklmnopqrstuvwxyz"
        assert WEBHOOK_URL_PATTERN.match(url) is None

    def test_invalid_webhook_url_wrong_domain(self) -> None:
        """Test webhook URL with wrong domain does not match pattern."""
        url = "https://example.com/api/webhooks/12345678901234567890/abcdefghijklmnopqrstuvwxyz"
        assert WEBHOOK_URL_PATTERN.match(url) is None

    def test_invalid_webhook_url_missing_token(self) -> None:
        """Test webhook URL without token does not match pattern."""
        url = "https://discord.com/api/webhooks/12345678901234567890/"
        assert WEBHOOK_URL_PATTERN.match(url) is None

    def test_invalid_webhook_url_invalid_id_length(self) -> None:
        """Test webhook URL with invalid ID length does not match pattern."""
        url = "https://discord.com/api/webhooks/12345/abcdefghijklmnopqrstuvwxyz"
        assert WEBHOOK_URL_PATTERN.match(url) is None


class TestValidateRoutingConfig:
    """Test cases for validate_routing_config function."""

    def test_valid_complete_config(self) -> None:
        """Test validation passes with all required severity levels."""
        config = {
            "high": {"channel_id": "1234567890123456789"},
            "medium": {"channel_id": "9876543210987654321"},
            "low": {"channel_id": "1111111111111111111"},
            "critical": {"channel_id": "2222222222222222222"},
        }

        result = validate_routing_config(config)

        assert result["valid"] is True
        assert result["errors"] == []
        assert result["missing"] == []

    def test_valid_config_with_webhooks(self) -> None:
        """Test validation passes with webhook URLs."""
        config = {
            "high": {
                "channel_id": "1234567890123456789",
                "webhook_url": "https://discord.com/api/webhooks/12345678901234567890/abcdef",
            },
            "medium": {"channel_id": "9876543210987654321"},
            "low": {"channel_id": "1111111111111111111"},
            "critical": {
                "channel_id": "2222222222222222222",
                "webhook_url": "https://discord.com/api/webhooks/98765432109876543210/xyz",
            },
        }

        result = validate_routing_config(config)

        assert result["valid"] is True
        assert result["errors"] == []
        assert result["missing"] == []

    def test_missing_all_severity_levels(self) -> None:
        """Test validation fails when all severity levels are missing."""
        config = {}

        result = validate_routing_config(config)

        assert result["valid"] is False
        assert len(result["missing"]) == 4
        assert sorted(result["missing"]) == ["critical", "high", "low", "medium"]
        assert any(
            "Missing required severity levels" in err for err in result["errors"]
        )

    def test_missing_one_severity_level(self) -> None:
        """Test validation fails when one severity level is missing."""
        config = {
            "high": {"channel_id": "1234567890123456789"},
            "medium": {"channel_id": "9876543210987654321"},
            "low": {"channel_id": "1111111111111111111"},
            # Missing "critical"
        }

        result = validate_routing_config(config)

        assert result["valid"] is False
        assert result["missing"] == ["critical"]
        assert any("critical" in err for err in result["errors"])

    def test_missing_multiple_severity_levels(self) -> None:
        """Test validation fails when multiple severity levels are missing."""
        config = {
            "high": {"channel_id": "1234567890123456789"},
            "medium": {"channel_id": "9876543210987654321"},
            # Missing "low" and "critical"
        }

        result = validate_routing_config(config)

        assert result["valid"] is False
        assert sorted(result["missing"]) == ["critical", "low"]

    def test_invalid_channel_id_too_short(self) -> None:
        """Test validation fails for channel ID that is too short."""
        config = {
            "high": {"channel_id": "12345"},  # Too short
            "medium": {"channel_id": "9876543210987654321"},
            "low": {"channel_id": "1111111111111111111"},
            "critical": {"channel_id": "2222222222222222222"},
        }

        result = validate_routing_config(config)

        assert result["valid"] is False
        assert any(
            "high" in err and "invalid channel_id" in err for err in result["errors"]
        )

    def test_invalid_channel_id_too_long(self) -> None:
        """Test validation fails for channel ID that is too long."""
        config = {
            "high": {"channel_id": "123456789012345678901"},  # 21 digits, too long
            "medium": {"channel_id": "9876543210987654321"},
            "low": {"channel_id": "1111111111111111111"},
            "critical": {"channel_id": "2222222222222222222"},
        }

        result = validate_routing_config(config)

        assert result["valid"] is False
        assert any(
            "high" in err and "invalid channel_id" in err for err in result["errors"]
        )

    def test_invalid_channel_id_non_numeric(self) -> None:
        """Test validation fails for non-numeric channel ID."""
        config = {
            "high": {"channel_id": "abc123def456ghi789"},
            "medium": {"channel_id": "9876543210987654321"},
            "low": {"channel_id": "1111111111111111111"},
            "critical": {"channel_id": "2222222222222222222"},
        }

        result = validate_routing_config(config)

        assert result["valid"] is False
        assert any(
            "high" in err and "invalid channel_id" in err for err in result["errors"]
        )

    def test_missing_channel_id(self) -> None:
        """Test validation fails when channel_id is missing."""
        config = {
            "high": {},  # Missing channel_id
            "medium": {"channel_id": "9876543210987654321"},
            "low": {"channel_id": "1111111111111111111"},
            "critical": {"channel_id": "2222222222222222222"},
        }

        result = validate_routing_config(config)

        assert result["valid"] is False
        assert any(
            "high" in err and "missing" in err.lower() for err in result["errors"]
        )

    def test_invalid_webhook_url_format(self) -> None:
        """Test validation fails for invalid webhook URL format."""
        config = {
            "high": {
                "channel_id": "1234567890123456789",
                "webhook_url": "https://example.com/webhook",
            },
            "medium": {"channel_id": "9876543210987654321"},
            "low": {"channel_id": "1111111111111111111"},
            "critical": {"channel_id": "2222222222222222222"},
        }

        result = validate_routing_config(config)

        assert result["valid"] is False
        assert any("high" in err and "webhook_url" in err for err in result["errors"])

    def test_channel_id_conflict_same_channel_multiple_severities(self) -> None:
        """Test validation fails when same channel ID is used for multiple severities."""
        config = {
            "high": {"channel_id": "1234567890123456789"},
            "medium": {"channel_id": "1234567890123456789"},  # Same as high
            "low": {"channel_id": "1234567890123456789"},  # Same as high
            "critical": {"channel_id": "2222222222222222222"},
        }

        result = validate_routing_config(config)

        assert result["valid"] is False
        assert any("used for multiple" in err.lower() for err in result["errors"])
        assert any("1234567890123456789" in err for err in result["errors"])

    def test_channel_id_type_error(self) -> None:
        """Test validation fails when channel_id is not a string."""
        config = {
            "high": {"channel_id": 1234567890123456789},  # Integer instead of string
            "medium": {"channel_id": "9876543210987654321"},
            "low": {"channel_id": "1111111111111111111"},
            "critical": {"channel_id": "2222222222222222222"},
        }

        result = validate_routing_config(config)

        assert result["valid"] is False
        assert any("high" in err and "int" in err for err in result["errors"])

    def test_webhook_url_type_error(self) -> None:
        """Test validation fails when webhook_url is not a string."""
        config = {
            "high": {
                "channel_id": "1234567890123456789",
                "webhook_url": 12345,  # Integer instead of string
            },
            "medium": {"channel_id": "9876543210987654321"},
            "low": {"channel_id": "1111111111111111111"},
            "critical": {"channel_id": "2222222222222222222"},
        }

        result = validate_routing_config(config)

        assert result["valid"] is False
        assert any("high" in err and "webhook_url" in err for err in result["errors"])

    def test_config_not_a_dict(self) -> None:
        """Test validation fails when config is not a dictionary."""
        result = validate_routing_config("not a dict")

        assert result["valid"] is False
        assert "dictionary" in result["errors"][0]
        assert sorted(result["missing"]) == ["critical", "high", "low", "medium"]

    def test_severity_config_not_a_dict(self) -> None:
        """Test validation fails when severity configuration is not a dictionary."""
        config = {
            "high": "not a dict",
            "medium": {"channel_id": "9876543210987654321"},
            "low": {"channel_id": "1111111111111111111"},
            "critical": {"channel_id": "2222222222222222222"},
        }

        result = validate_routing_config(config)

        assert result["valid"] is False
        assert any("high" in err and "dictionary" in err for err in result["errors"])

    def test_unknown_configuration_keys(self) -> None:
        """Test validation fails for unknown configuration keys."""
        config = {
            "high": {
                "channel_id": "1234567890123456789",
                "unknown_key": "some_value",
            },
            "medium": {"channel_id": "9876543210987654321"},
            "low": {"channel_id": "1111111111111111111"},
            "critical": {"channel_id": "2222222222222222222"},
        }

        result = validate_routing_config(config)

        assert result["valid"] is False
        assert any("unknown" in err.lower() for err in result["errors"])
        assert any("unknown_key" in err for err in result["errors"])

    def test_multiple_errors_reported(self) -> None:
        """Test that all errors are reported, not just the first one."""
        config = {
            "high": {"channel_id": "123"},  # Too short
            "medium": {"channel_id": "9876543210987654321"},
            "low": {"channel_id": "1111111111111111111"},
            # Missing "critical"
        }

        result = validate_routing_config(config)

        assert result["valid"] is False
        assert len(result["errors"]) >= 2  # Should have missing critical + invalid high
        assert "critical" in result["missing"]

    def test_extra_severity_levels_allowed(self) -> None:
        """Test that extra severity levels beyond required are allowed."""
        config = {
            "high": {"channel_id": "1234567890123456789"},
            "medium": {"channel_id": "9876543210987654321"},
            "low": {"channel_id": "1111111111111111111"},
            "critical": {"channel_id": "2222222222222222222"},
            "info": {"channel_id": "3333333333333333333"},  # Extra level
            "debug": {"channel_id": "4444444444444444444"},  # Extra level
        }

        result = validate_routing_config(config)

        assert result["valid"] is True
        assert result["errors"] == []
        assert result["missing"] == []

    def test_empty_config(self) -> None:
        """Test validation of empty config returns proper structure."""
        result = validate_routing_config({})

        assert result["valid"] is False
        assert len(result["missing"]) == 4
        assert len(result["errors"]) >= 1
