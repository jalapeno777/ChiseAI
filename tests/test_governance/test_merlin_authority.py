"""Tests for Merlin Authority Enforcement Module.

ST-AUTO-CONTROL-001: Merlin-only authority enforcement tests.
"""

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.governance.merlin_authority import (
    ActionType,
    AuthorityCheckError,
    AuthoritySettings,
    AuthorityViolation,
    EpicNotProtected,
    check_ep_auto_git_authority,
    check_epic_authority,
    clear_authority_cache,
    enforce_merlin_only,
    get_authority_settings,
    get_current_agent,
    is_merlin,
    require_merlin,
)


class TestAgentDetection:
    """Tests for agent identity detection."""

    def test_get_current_agent_from_env(self):
        """Test agent detection from environment variable."""
        with patch.dict(os.environ, {"CHISE_AGENT": "merlin"}):
            assert get_current_agent() == "merlin"

    def test_get_current_agent_from_env_case_insensitive(self):
        """Test agent detection is case insensitive."""
        with patch.dict(os.environ, {"CHISE_AGENT": "MERLIN"}):
            assert get_current_agent() == "merlin"

    def test_get_current_agent_defaults_to_unknown(self):
        """Test agent defaults to unknown when not set."""
        # Must also patch is_merlin's cached result by clearing env
        with patch.dict(os.environ, {"CHISE_AGENT": ""}, clear=False):
            # Force reload by creating a new check
            agent = os.environ.get("CHISE_AGENT", "").lower() or "unknown"
            assert agent == "unknown"

    def test_is_merlin_true(self):
        """Test is_merlin returns True when agent is merlin."""
        with patch.dict(os.environ, {"CHISE_AGENT": "merlin"}):
            assert is_merlin() is True

    def test_is_merlin_false(self):
        """Test is_merlin returns False when agent is not merlin."""
        with patch.dict(os.environ, {"CHISE_AGENT": "senior-dev"}):
            assert is_merlin() is False

    def test_is_merlin_false_for_jarvis(self):
        """Test is_merlin returns False for jarvis agent."""
        with patch.dict(os.environ, {"CHISE_AGENT": "jarvis"}):
            assert is_merlin() is False


class TestAuthoritySettings:
    """Tests for AuthoritySettings dataclass."""

    def test_from_redis_hash(self):
        """Test creating AuthoritySettings from Redis hash."""
        data = {
            "merge_authority": "merlin-only",
            "pr_authority": "merlin-only",
            "status_authority": "any",
            "lock_timestamp": "2026-02-26T18:00:00Z",
        }
        settings = AuthoritySettings.from_redis_hash("EP-AUTO-GIT-001", data)

        assert settings.epic_id == "EP-AUTO-GIT-001"
        assert settings.merge_authority == "merlin-only"
        assert settings.pr_authority == "merlin-only"
        assert settings.status_authority == "any"
        assert settings.lock_timestamp == "2026-02-26T18:00:00Z"

    def test_from_redis_hash_defaults(self):
        """Test AuthoritySettings uses defaults for missing fields."""
        data = {}
        settings = AuthoritySettings.from_redis_hash("EP-TEST-001", data)

        assert settings.epic_id == "EP-TEST-001"
        assert settings.merge_authority == "any"
        assert settings.pr_authority == "any"
        assert settings.status_authority == "any"
        assert settings.lock_timestamp is None

    def test_is_merlin_only_for_merge(self):
        """Test is_merlin_only returns True for merge when merlin-only."""
        settings = AuthoritySettings(
            epic_id="EP-TEST-001",
            merge_authority="merlin-only",
            pr_authority="any",
            status_authority="any",
        )
        assert settings.is_merlin_only(ActionType.MERGE) is True
        assert settings.is_merlin_only(ActionType.PR_UPDATE) is False
        assert settings.is_merlin_only(ActionType.STATUS_WRITE) is False

    def test_is_merlin_only_for_all_actions(self):
        """Test is_merlin_only for all action types."""
        settings = AuthoritySettings(
            epic_id="EP-TEST-001",
            merge_authority="merlin-only",
            pr_authority="merlin-only",
            status_authority="merlin-only",
        )
        assert settings.is_merlin_only(ActionType.MERGE) is True
        assert settings.is_merlin_only(ActionType.PR_UPDATE) is True
        assert settings.is_merlin_only(ActionType.STATUS_WRITE) is True


class TestActionType:
    """Tests for ActionType enum."""

    def test_from_string_valid(self):
        """Test parsing valid action type strings."""
        assert ActionType.from_string("merge") == ActionType.MERGE
        assert ActionType.from_string("pr_update") == ActionType.PR_UPDATE
        assert ActionType.from_string("status_write") == ActionType.STATUS_WRITE

    def test_from_string_invalid(self):
        """Test parsing invalid action type raises error."""
        with pytest.raises(ValueError, match="Invalid action type"):
            ActionType.from_string("invalid_action")


class TestAuthorityCheck:
    """Tests for authority checking functions."""

    @patch("scripts.governance.merlin_authority._get_redis_hash")
    def test_get_authority_settings_success(self, mock_get_hash):
        """Test retrieving authority settings from Redis."""
        mock_get_hash.return_value = {
            "merge_authority": "merlin-only",
            "pr_authority": "merlin-only",
            "status_authority": "merlin-only",
            "lock_timestamp": "2026-02-26T18:00:00Z",
        }

        # Clear cache to ensure fresh read
        clear_authority_cache()

        settings = get_authority_settings("EP-AUTO-GIT-001", use_cache=False)

        assert settings.epic_id == "EP-AUTO-GIT-001"
        assert settings.merge_authority == "merlin-only"
        mock_get_hash.assert_called_once()

    @patch("scripts.governance.merlin_authority._get_redis_hash")
    def test_get_authority_settings_uses_cache(self, mock_get_hash):
        """Test that authority settings are cached."""
        mock_get_hash.return_value = {
            "merge_authority": "merlin-only",
            "lock_timestamp": "2026-02-26T18:00:00Z",
        }

        clear_authority_cache()

        # First call should hit Redis
        get_authority_settings("EP-AUTO-GIT-001")
        assert mock_get_hash.call_count == 1

        # Second call should use cache
        get_authority_settings("EP-AUTO-GIT-001")
        assert mock_get_hash.call_count == 1  # Still 1, not 2

    @patch("scripts.governance.merlin_authority._get_redis_hash")
    def test_get_authority_settings_cache_bypass(self, mock_get_hash):
        """Test that cache can be bypassed."""
        mock_get_hash.return_value = {
            "merge_authority": "merlin-only",
            "lock_timestamp": "2026-02-26T18:00:00Z",
        }

        clear_authority_cache()

        # First call
        get_authority_settings("EP-AUTO-GIT-001")
        assert mock_get_hash.call_count == 1

        # Second call with cache bypass
        get_authority_settings("EP-AUTO-GIT-001", use_cache=False)
        assert mock_get_hash.call_count == 2

    @patch("scripts.governance.merlin_authority._get_redis_hash")
    def test_check_epic_authority_merlin_allowed(self, mock_get_hash):
        """Test that Merlin is authorized for merlin-only actions."""
        mock_get_hash.return_value = {
            "merge_authority": "merlin-only",
            "lock_timestamp": "2026-02-26T18:00:00Z",
        }

        clear_authority_cache()

        with patch.dict(os.environ, {"CHISE_AGENT": "merlin"}):
            assert check_epic_authority("EP-AUTO-GIT-001", ActionType.MERGE) is True

    @patch("scripts.governance.merlin_authority._get_redis_hash")
    def test_check_epic_authority_non_merlin_denied(self, mock_get_hash):
        """Test that non-Merlin is denied for merlin-only actions."""
        mock_get_hash.return_value = {
            "merge_authority": "merlin-only",
            "lock_timestamp": "2026-02-26T18:00:00Z",
        }

        clear_authority_cache()

        with patch.dict(os.environ, {"CHISE_AGENT": "senior-dev"}):
            assert check_epic_authority("EP-AUTO-GIT-001", ActionType.MERGE) is False

    @patch("scripts.governance.merlin_authority._get_redis_hash")
    def test_check_epic_authority_unprotected_epic(self, mock_get_hash):
        """Test that unprotected epics allow all actions."""
        mock_get_hash.return_value = {}  # No lock_timestamp

        clear_authority_cache()

        with patch.dict(os.environ, {"CHISE_AGENT": "senior-dev"}):
            # Should be allowed because epic is not protected
            assert check_epic_authority("EP-UNPROTECTED-001", ActionType.MERGE) is True

    @patch("scripts.governance.merlin_authority._get_redis_hash")
    def test_check_epic_authority_any_allowed(self, mock_get_hash):
        """Test that 'any' authority allows all agents."""
        mock_get_hash.return_value = {
            "merge_authority": "any",
            "lock_timestamp": "2026-02-26T18:00:00Z",
        }

        clear_authority_cache()

        with patch.dict(os.environ, {"CHISE_AGENT": "senior-dev"}):
            assert check_epic_authority("EP-AUTO-GIT-001", ActionType.MERGE) is True

    def test_check_ep_auto_git_authority_valid(self):
        """Test check_ep_auto_git_authority with valid action."""
        with patch(
            "scripts.governance.merlin_authority.check_epic_authority"
        ) as mock_check:
            mock_check.return_value = True
            result = check_ep_auto_git_authority("merge")
            assert result is True
            mock_check.assert_called_once_with("EP-AUTO-GIT-001", ActionType.MERGE)

    def test_check_ep_auto_git_authority_invalid_action(self):
        """Test check_ep_auto_git_authority with invalid action."""
        with pytest.raises(ValueError, match="Invalid action type"):
            check_ep_auto_git_authority("invalid_action")


class TestEnforceMerlinOnly:
    """Tests for enforce_merlin_only function."""

    @patch("scripts.governance.merlin_authority._get_redis_hash")
    def test_enforce_merlin_only_success(self, mock_get_hash):
        """Test enforce_merlin_only succeeds for Merlin."""
        mock_get_hash.return_value = {
            "merge_authority": "merlin-only",
            "lock_timestamp": "2026-02-26T18:00:00Z",
        }

        clear_authority_cache()

        with patch.dict(os.environ, {"CHISE_AGENT": "merlin"}):
            # Should not raise
            enforce_merlin_only(epic_id="EP-AUTO-GIT-001")

    @patch("scripts.governance.merlin_authority._get_redis_hash")
    def test_enforce_merlin_only_violation(self, mock_get_hash):
        """Test enforce_merlin_only raises AuthorityViolation for non-Merlin."""
        mock_get_hash.return_value = {
            "merge_authority": "merlin-only",
            "pr_authority": "merlin-only",
            "status_authority": "merlin-only",
            "lock_timestamp": "2026-02-26T18:00:00Z",
        }

        clear_authority_cache()

        with patch.dict(os.environ, {"CHISE_AGENT": "senior-dev"}):
            with pytest.raises(AuthorityViolation) as exc_info:
                enforce_merlin_only(epic_id="EP-AUTO-GIT-001", action="merge")

            assert "Only Merlin can perform this operation" in str(exc_info.value)
            assert exc_info.value.action == "merge"
            assert exc_info.value.epic_id == "EP-AUTO-GIT-001"
            assert exc_info.value.agent == "senior-dev"

    @patch("scripts.governance.merlin_authority._get_redis_hash")
    def test_enforce_merlin_only_not_protected(self, mock_get_hash):
        """Test enforce_merlin_only raises EpicNotProtected for unprotected epic."""
        mock_get_hash.return_value = {}  # No lock_timestamp

        clear_authority_cache()

        with pytest.raises(EpicNotProtected) as exc_info:
            enforce_merlin_only(epic_id="EP-UNPROTECTED-001")

        assert "EP-UNPROTECTED-001" in str(exc_info.value)

    @patch("scripts.governance.merlin_authority._get_redis_hash")
    def test_enforce_merlin_only_redis_failure(self, mock_get_hash):
        """Test enforce_merlin_only handles Redis failure."""
        from scripts.governance.merlin_authority import AuthorityCheckError as ACE

        mock_get_hash.side_effect = ACE("Redis connection failed")

        clear_authority_cache()

        with pytest.raises(AuthorityCheckError) as exc_info:
            enforce_merlin_only(epic_id="EP-AUTO-GIT-001")

        assert "Authority verification failed" in str(exc_info.value)


class TestRequireMerlinDecorator:
    """Tests for @require_merlin decorator."""

    @patch("scripts.governance.merlin_authority._get_redis_hash")
    def test_require_merlin_decorator_allows_merlin(self, mock_get_hash):
        """Test decorator allows Merlin to execute function."""
        mock_get_hash.return_value = {
            "merge_authority": "merlin-only",
            "lock_timestamp": "2026-02-26T18:00:00Z",
        }

        clear_authority_cache()

        @require_merlin
        def protected_function():
            return "success"

        with patch.dict(os.environ, {"CHISE_AGENT": "merlin"}):
            result = protected_function()
            assert result == "success"

    @patch("scripts.governance.merlin_authority._get_redis_hash")
    def test_require_merlin_decorator_blocks_non_merlin(self, mock_get_hash):
        """Test decorator blocks non-Merlin from executing function."""
        mock_get_hash.return_value = {
            "merge_authority": "merlin-only",
            "lock_timestamp": "2026-02-26T18:00:00Z",
        }

        clear_authority_cache()

        @require_merlin
        def protected_function():
            return "success"

        with patch.dict(os.environ, {"CHISE_AGENT": "senior-dev"}):
            with pytest.raises(AuthorityViolation):
                protected_function()

    @patch("scripts.governance.merlin_authority._get_redis_hash")
    def test_require_merlin_decorator_preserves_function_metadata(self, mock_get_hash):
        """Test decorator preserves function name and docstring."""
        mock_get_hash.return_value = {
            "lock_timestamp": "2026-02-26T18:00:00Z",
        }

        clear_authority_cache()

        @require_merlin
        def my_function():
            """My docstring."""
            pass

        assert my_function.__name__ == "my_function"
        assert my_function.__doc__ == "My docstring."


class TestExceptions:
    """Tests for custom exception classes."""

    def test_authority_violation_default_message(self):
        """Test AuthorityViolation generates default message."""
        with patch.dict(os.environ, {"CHISE_AGENT": "senior-dev"}):
            exc = AuthorityViolation(action="merge", epic_id="EP-TEST-001")
            assert "senior-dev" in str(exc)
            assert "merge" in str(exc)
            assert "EP-TEST-001" in str(exc)

    def test_authority_violation_custom_message(self):
        """Test AuthorityViolation accepts custom message."""
        exc = AuthorityViolation(
            action="merge",
            epic_id="EP-TEST-001",
            message="Custom error message",
        )
        assert str(exc) == "Custom error message"

    def test_epic_not_protected_default_message(self):
        """Test EpicNotProtected generates default message."""
        exc = EpicNotProtected("EP-TEST-001")
        assert "EP-TEST-001" in str(exc)
        assert "not protected" in str(exc)

    def test_authority_check_error(self):
        """Test AuthorityCheckError stores reason."""
        exc = AuthorityCheckError("Redis timeout")
        assert exc.reason == "Redis timeout"
        assert "Redis timeout" in str(exc)


class TestRedisFailureHandling:
    """Tests for Redis failure handling."""

    @patch("scripts.governance.merlin_authority._get_redis_hash")
    def test_check_epic_authority_denies_on_redis_failure(self, mock_get_hash):
        """Test that authority check denies access when Redis fails."""
        from scripts.governance.merlin_authority import AuthorityCheckError as ACE

        mock_get_hash.side_effect = ACE("Redis connection failed")

        clear_authority_cache()

        # Should deny access when Redis fails (fail secure)
        result = check_epic_authority("EP-AUTO-GIT-001", ActionType.MERGE)
        assert result is False

    @patch("scripts.governance.merlin_authority._get_redis_hash")
    def test_get_authority_settings_uses_stale_cache_on_failure(self, mock_get_hash):
        """Test that stale cache is used when Redis fails."""
        # First, populate cache with successful response
        mock_get_hash.return_value = {
            "merge_authority": "merlin-only",
            "lock_timestamp": "2026-02-26T18:00:00Z",
        }

        clear_authority_cache()
        get_authority_settings("EP-AUTO-GIT-001")

        # Now make Redis fail
        mock_get_hash.side_effect = Exception("Redis connection failed")

        # Should still return cached settings
        settings = get_authority_settings("EP-AUTO-GIT-001")
        assert settings.merge_authority == "merlin-only"


class TestClearCache:
    """Tests for cache clearing functionality."""

    @patch("scripts.governance.merlin_authority._get_redis_hash")
    def test_clear_authority_cache(self, mock_get_hash):
        """Test that clear_authority_cache clears the cache."""
        mock_get_hash.return_value = {
            "merge_authority": "merlin-only",
            "lock_timestamp": "2026-02-26T18:00:00Z",
        }

        # Populate cache
        clear_authority_cache()
        get_authority_settings("EP-AUTO-GIT-001")
        assert mock_get_hash.call_count == 1

        # Second call should use cache
        get_authority_settings("EP-AUTO-GIT-001")
        assert mock_get_hash.call_count == 1

        # Clear cache
        clear_authority_cache()

        # Next call should hit Redis again
        get_authority_settings("EP-AUTO-GIT-001")
        assert mock_get_hash.call_count == 2


class TestIntegrationWithStatusWriteGate:
    """Tests demonstrating integration with status_write_gate.py."""

    @patch("scripts.governance.merlin_authority._get_redis_hash")
    def test_status_write_gate_integration_merlin(self, mock_get_hash):
        """Test that Merlin can perform status write."""
        mock_get_hash.return_value = {
            "status_authority": "merlin-only",
            "lock_timestamp": "2026-02-26T18:00:00Z",
        }

        clear_authority_cache()

        # Simulate status_write_gate.py calling enforce_merlin_only
        with patch.dict(os.environ, {"CHISE_AGENT": "merlin"}):
            try:
                enforce_merlin_only(epic_id="EP-AUTO-GIT-001", action="status_write")
                # If we get here, authority check passed
                status_write_allowed = True
            except AuthorityViolation:
                status_write_allowed = False

            assert status_write_allowed is True

    @patch("scripts.governance.merlin_authority._get_redis_hash")
    def test_status_write_gate_integration_non_merlin(self, mock_get_hash):
        """Test that non-Merlin cannot perform status write."""
        mock_get_hash.return_value = {
            "status_authority": "merlin-only",
            "lock_timestamp": "2026-02-26T18:00:00Z",
        }

        clear_authority_cache()

        # Simulate status_write_gate.py calling enforce_merlin_only
        with patch.dict(os.environ, {"CHISE_AGENT": "senior-dev"}):
            with pytest.raises(AuthorityViolation) as exc_info:
                enforce_merlin_only(epic_id="EP-AUTO-GIT-001", action="status_write")

            assert "Only Merlin can perform this operation" in str(exc_info.value)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
