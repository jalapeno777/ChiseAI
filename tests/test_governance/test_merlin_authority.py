#!/usr/bin/env python3
"""
Comprehensive tests for merlin_authority module.

This test suite covers:
- Exception classes
- Agent detection (environment variable, process detection)
- Authority settings parsing
- Authority checks for different actions
- Redis failure handling (fail-secure)
- Decorator functionality
"""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from unittest.mock import MagicMock, patch

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

# Create a mock redis_state module for testing
mock_redis_state = MagicMock()
sys.modules["redis_state"] = mock_redis_state

from scripts.governance.merlin_authority import (
    AuthorityAction,
    AuthorityCheckError,
    AuthorityCheckResult,
    AuthoritySetting,
    AuthorityViolation,
    EpicNotProtected,
    _clear_cache,
    _detect_agent_from_environment,
    _detect_agent_from_process,
    _get_cached,
    _get_redis_authority_settings,
    _parse_authority_setting,
    _set_cached,
    check_ep_auto_git_authority,
    check_epic_authority,
    enforce_merlin_only,
    is_merlin,
    require_merlin,
    verify_git_sha,
)


class TestExceptionClasses(unittest.TestCase):
    """Test the exception classes."""

    def test_authority_violation_basic(self) -> None:
        """Test AuthorityViolation with basic parameters."""
        exc = AuthorityViolation(action="merge", agent="jarvis")

        self.assertEqual(exc.action, "merge")
        self.assertEqual(exc.agent, "jarvis")
        self.assertIsNone(exc.epic_id)
        self.assertIn("jarvis", str(exc))
        self.assertIn("merge", str(exc))

    def test_authority_violation_with_epic(self) -> None:
        """Test AuthorityViolation with epic_id."""
        exc = AuthorityViolation(
            action="status", agent="worker-1", epic_id="EP-AUTO-GIT-001"
        )

        self.assertEqual(exc.epic_id, "EP-AUTO-GIT-001")
        self.assertIn("EP-AUTO-GIT-001", str(exc))

    def test_authority_violation_custom_message(self) -> None:
        """Test AuthorityViolation with custom message."""
        custom_msg = "Custom violation message"
        exc = AuthorityViolation(action="merge", agent="test", message=custom_msg)

        self.assertEqual(str(exc), custom_msg)

    def test_epic_not_protected_basic(self) -> None:
        """Test EpicNotProtected exception."""
        exc = EpicNotProtected(epic_id="EP-UNKNOWN-001")

        self.assertEqual(exc.epic_id, "EP-UNKNOWN-001")
        self.assertIn("EP-UNKNOWN-001", str(exc))

    def test_epic_not_protected_custom_message(self) -> None:
        """Test EpicNotProtected with custom message."""
        custom_msg = "Custom not protected message"
        exc = EpicNotProtected(epic_id="EP-TEST", message=custom_msg)

        self.assertEqual(str(exc), custom_msg)

    def test_authority_check_error_basic(self) -> None:
        """Test AuthorityCheckError with basic parameters."""
        exc = AuthorityCheckError(reason="Redis timeout")

        self.assertEqual(exc.reason, "Redis timeout")
        self.assertIsNone(exc.original_error)
        self.assertIn("Redis timeout", str(exc))

    def test_authority_check_error_with_original(self) -> None:
        """Test AuthorityCheckError with original exception."""
        original = ConnectionError("Cannot connect")
        exc = AuthorityCheckError(reason="Connection failed", original_error=original)

        self.assertEqual(exc.original_error, original)
        self.assertIn("ConnectionError", str(exc))


class TestAuthorityEnums(unittest.TestCase):
    """Test the authority enumeration classes."""

    def test_authority_action_values(self) -> None:
        """Test AuthorityAction enum values."""
        self.assertEqual(AuthorityAction.MERGE.value, "merge")
        self.assertEqual(AuthorityAction.PR.value, "pr")
        self.assertEqual(AuthorityAction.STATUS.value, "status")

    def test_authority_setting_values(self) -> None:
        """Test AuthoritySetting enum values."""
        self.assertEqual(AuthoritySetting.MERLIN_ONLY.value, "merlin-only")
        self.assertEqual(AuthoritySetting.OPEN.value, "open")
        self.assertEqual(AuthoritySetting.RESTRICTED.value, "restricted")


class TestAuthorityCheckResult(unittest.TestCase):
    """Test the AuthorityCheckResult dataclass."""

    def test_result_creation(self) -> None:
        """Test creating an AuthorityCheckResult."""
        result = AuthorityCheckResult(
            authorized=True,
            action="merge",
            agent="merlin",
            epic_id="EP-AUTO-GIT-001",
            setting="merlin-only",
            reason="Agent is merlin",
        )

        self.assertTrue(result.authorized)
        self.assertEqual(result.action, "merge")
        self.assertEqual(result.agent, "merlin")
        self.assertEqual(result.epic_id, "EP-AUTO-GIT-001")
        self.assertEqual(result.setting, "merlin-only")
        self.assertEqual(result.reason, "Agent is merlin")


class TestAgentDetection(unittest.TestCase):
    """Test agent detection functionality."""

    def test_is_merlin_explicit(self) -> None:
        """Test is_merlin with explicit agent name."""
        self.assertTrue(is_merlin("merlin"))
        self.assertTrue(is_merlin("MERLIN"))
        self.assertTrue(is_merlin("Merlin"))

    def test_is_merlin_not_merlin(self) -> None:
        """Test is_merlin returns False for non-merlin agents."""
        self.assertFalse(is_merlin("jarvis"))
        self.assertFalse(is_merlin("worker-1"))
        self.assertFalse(is_merlin(""))

    @patch.dict(os.environ, {"AGENT_NAME": "merlin"}, clear=True)
    def test_detect_agent_from_environment_merlin(self) -> None:
        """Test detecting merlin from environment variable."""
        agent = _detect_agent_from_environment()
        self.assertEqual(agent, "merlin")

    @patch.dict(os.environ, {"AGENT_NAME": "jarvis"}, clear=True)
    def test_detect_agent_from_environment_jarvis(self) -> None:
        """Test detecting jarvis from environment variable."""
        agent = _detect_agent_from_environment()
        self.assertEqual(agent, "jarvis")

    @patch.dict(os.environ, {}, clear=True)
    def test_detect_agent_from_environment_empty(self) -> None:
        """Test detection when environment variable is not set."""
        # When AGENT_NAME is not set, it falls back to process detection
        # which may return "unknown" or something from parent process
        agent = _detect_agent_from_environment()
        # Should return a string (either detected or "unknown")
        self.assertIsInstance(agent, str)

    @patch.dict(os.environ, {"AGENT_NAME": "  MERLIN  "}, clear=True)
    def test_detect_agent_from_environment_whitespace(self) -> None:
        """Test that whitespace is stripped from agent name."""
        agent = _detect_agent_from_environment()
        self.assertEqual(agent, "merlin")

    @patch.dict(os.environ, {}, clear=True)
    def test_is_merlin_from_environment(self) -> None:
        """Test is_merlin detects from environment when no argument given."""
        with patch.dict(os.environ, {"AGENT_NAME": "merlin"}):
            self.assertTrue(is_merlin())

        with patch.dict(os.environ, {"AGENT_NAME": "jarvis"}):
            self.assertFalse(is_merlin())


class TestCache(unittest.TestCase):
    """Test the caching functionality."""

    def setUp(self) -> None:
        """Clear cache before each test."""
        _clear_cache()

    def tearDown(self) -> None:
        """Clear cache after each test."""
        _clear_cache()

    def test_cache_set_and_get(self) -> None:
        """Test setting and getting cached values."""
        _set_cached("test_key", "test_value")
        value = _get_cached("test_key")
        self.assertEqual(value, "test_value")

    def test_cache_miss(self) -> None:
        """Test getting non-existent cache key."""
        value = _get_cached("non_existent_key")
        self.assertIsNone(value)

    def test_cache_expiration(self) -> None:
        """Test that cache entries expire after TTL."""
        import time

        # Set a value
        _set_cached("expire_key", "expire_value")

        # Should exist immediately
        self.assertEqual(_get_cached("expire_key"), "expire_value")

        # Manually expire by setting timestamp in the past
        # We need to access the internal cache to do this
        from scripts.governance import merlin_authority

        merlin_authority._authority_cache["expire_key"] = ("expire_value", 0)

        # Should be expired now
        value = _get_cached("expire_key")
        self.assertIsNone(value)


class TestParseAuthoritySetting(unittest.TestCase):
    """Test authority setting parsing."""

    def test_parse_merlin_only(self) -> None:
        """Test parsing merlin-only setting."""
        settings = {"merge_authority": "merlin-only"}
        result = _parse_authority_setting(settings, "merge")
        self.assertEqual(result, AuthoritySetting.MERLIN_ONLY)

    def test_parse_open(self) -> None:
        """Test parsing open setting."""
        settings = {"pr_authority": "open"}
        result = _parse_authority_setting(settings, "pr")
        self.assertEqual(result, AuthoritySetting.OPEN)

    def test_parse_unknown_defaults_to_restricted(self) -> None:
        """Test that unknown settings default to restricted."""
        settings = {"status_authority": "unknown-value"}
        result = _parse_authority_setting(settings, "status")
        self.assertEqual(result, AuthoritySetting.RESTRICTED)

    def test_parse_missing_key(self) -> None:
        """Test parsing when key is missing."""
        settings = {}
        result = _parse_authority_setting(settings, "merge")
        self.assertEqual(result, AuthoritySetting.RESTRICTED)

    def test_parse_case_insensitive(self) -> None:
        """Test that parsing is case insensitive."""
        settings = {"merge_authority": "MERLIN-ONLY"}
        result = _parse_authority_setting(settings, "merge")
        self.assertEqual(result, AuthoritySetting.MERLIN_ONLY)


class TestRedisAuthoritySettings(unittest.TestCase):
    """Test Redis authority settings retrieval."""

    def setUp(self) -> None:
        """Clear cache before each test."""
        _clear_cache()

    def tearDown(self) -> None:
        """Clear cache after each test."""
        _clear_cache()

    @patch("redis_state.hgetall")
    def test_get_settings_success(self, mock_hgetall) -> None:
        """Test successful retrieval of authority settings."""
        mock_hgetall.return_value = {
            "merge_authority": "merlin-only",
            "pr_authority": "merlin-only",
            "status_authority": "merlin-only",
        }

        settings = _get_redis_authority_settings("EP-AUTO-GIT-001")

        self.assertEqual(settings["merge_authority"], "merlin-only")
        self.assertEqual(settings["pr_authority"], "merlin-only")
        self.assertEqual(settings["status_authority"], "merlin-only")

    @patch("redis_state.hgetall")
    def test_get_settings_empty_raises_epic_not_protected(self, mock_hgetall) -> None:
        """Test that empty settings raise EpicNotProtected."""
        mock_hgetall.return_value = {}

        with self.assertRaises(EpicNotProtected) as context:
            _get_redis_authority_settings("EP-UNKNOWN-001")

        self.assertEqual(context.exception.epic_id, "EP-UNKNOWN-001")

    @patch("redis_state.hgetall")
    def test_get_settings_none_raises_epic_not_protected(self, mock_hgetall) -> None:
        """Test that None settings raise EpicNotProtected."""
        mock_hgetall.return_value = None

        with self.assertRaises(EpicNotProtected):
            _get_redis_authority_settings("EP-UNKNOWN-001")

    @patch("redis_state.hgetall")
    def test_get_settings_uses_cache(self, mock_hgetall) -> None:
        """Test that settings are cached."""
        mock_hgetall.return_value = {"merge_authority": "merlin-only"}

        # First call should hit Redis
        settings1 = _get_redis_authority_settings("EP-AUTO-GIT-001")
        self.assertEqual(mock_hgetall.call_count, 1)

        # Second call should use cache
        settings2 = _get_redis_authority_settings("EP-AUTO-GIT-001")
        self.assertEqual(mock_hgetall.call_count, 1)  # Still 1, not 2
        self.assertEqual(settings1, settings2)

    def test_get_settings_import_error(self) -> None:
        """Test handling of import error for redis_state."""
        # Create a mock module that raises ImportError on hgetall access
        mock_module = MagicMock()
        mock_module.hgetall.side_effect = ImportError("No module named 'redis_state'")

        with patch.dict("sys.modules", {"redis_state": mock_module}):
            with self.assertRaises(AuthorityCheckError) as context:
                _get_redis_authority_settings("EP-AUTO-GIT-001")

            self.assertIn("Redis module not available", str(context.exception))

    @patch("redis_state.hgetall")
    def test_get_settings_redis_error(self, mock_hgetall) -> None:
        """Test handling of Redis errors."""
        mock_hgetall.side_effect = ConnectionError("Redis connection failed")

        with self.assertRaises(AuthorityCheckError) as context:
            _get_redis_authority_settings("EP-AUTO-GIT-001")

        self.assertIn("Failed to query Redis", str(context.exception))


class TestCheckEpicAuthority(unittest.TestCase):
    """Test the check_epic_authority function."""

    def setUp(self) -> None:
        """Clear cache before each test."""
        _clear_cache()

    def tearDown(self) -> None:
        """Clear cache after each test."""
        _clear_cache()

    @patch("scripts.governance.merlin_authority._get_redis_authority_settings")
    def test_check_merlin_authorized(self, mock_get_settings) -> None:
        """Test that merlin is authorized for merlin-only actions."""
        mock_get_settings.return_value = {"merge_authority": "merlin-only"}

        result = check_epic_authority("merge", "EP-AUTO-GIT-001", "merlin")

        self.assertTrue(result.authorized)
        self.assertEqual(result.agent, "merlin")
        self.assertEqual(result.action, "merge")

    @patch("scripts.governance.merlin_authority._get_redis_authority_settings")
    def test_check_non_merlin_denied(self, mock_get_settings) -> None:
        """Test that non-merlin is denied for merlin-only actions."""
        mock_get_settings.return_value = {"merge_authority": "merlin-only"}

        result = check_epic_authority("merge", "EP-AUTO-GIT-001", "jarvis")

        self.assertFalse(result.authorized)
        self.assertEqual(result.agent, "jarvis")

    @patch("scripts.governance.merlin_authority._get_redis_authority_settings")
    def test_check_open_setting(self, mock_get_settings) -> None:
        """Test that open setting allows all agents."""
        mock_get_settings.return_value = {"pr_authority": "open"}

        result = check_epic_authority("pr", "EP-AUTO-GIT-001", "any-agent")

        self.assertTrue(result.authorized)

    @patch("scripts.governance.merlin_authority._get_redis_authority_settings")
    def test_check_restricted_setting(self, mock_get_settings) -> None:
        """Test that restricted setting denies all agents."""
        mock_get_settings.return_value = {"status_authority": "restricted"}

        result = check_epic_authority("status", "EP-AUTO-GIT-001", "merlin")

        self.assertFalse(result.authorized)

    @patch("scripts.governance.merlin_authority._get_redis_authority_settings")
    def test_check_auto_detect_agent(self, mock_get_settings) -> None:
        """Test that agent is auto-detected when not provided."""
        mock_get_settings.return_value = {"merge_authority": "merlin-only"}

        with patch.dict(os.environ, {"AGENT_NAME": "test-agent"}):
            result = check_epic_authority("merge", "EP-AUTO-GIT-001")
            self.assertEqual(result.agent, "test-agent")

    @patch("scripts.governance.merlin_authority._get_redis_authority_settings")
    def test_check_epic_not_protected(self, mock_get_settings) -> None:
        """Test that EpicNotProtected is raised for unprotected epics."""
        from scripts.governance.merlin_authority import EpicNotProtected

        mock_get_settings.side_effect = EpicNotProtected("EP-UNKNOWN")

        with self.assertRaises(EpicNotProtected):
            check_epic_authority("merge", "EP-UNKNOWN")


class TestCheckEpAutoGitAuthority(unittest.TestCase):
    """Test the check_ep_auto_git_authority convenience function."""

    def setUp(self) -> None:
        """Clear cache before each test."""
        _clear_cache()

    def tearDown(self) -> None:
        """Clear cache after each test."""
        _clear_cache()

    @patch("scripts.governance.merlin_authority._get_redis_authority_settings")
    def test_check_ep_auto_git(self, mock_get_settings) -> None:
        """Test checking authority for EP-AUTO-GIT."""
        mock_get_settings.return_value = {"merge_authority": "merlin-only"}

        result = check_ep_auto_git_authority("merge", "merlin")

        self.assertTrue(result.authorized)
        self.assertEqual(result.epic_id, "EP-AUTO-GIT-001")


class TestEnforceMerlinOnly(unittest.TestCase):
    """Test the enforce_merlin_only function."""

    def setUp(self) -> None:
        """Clear cache before each test."""
        _clear_cache()

    def tearDown(self) -> None:
        """Clear cache after each test."""
        _clear_cache()

    @patch("scripts.governance.merlin_authority._get_redis_authority_settings")
    def test_enforce_merlin_succeeds(self, mock_get_settings) -> None:
        """Test that enforcement succeeds for merlin."""
        mock_get_settings.return_value = {"merge_authority": "merlin-only"}

        result = enforce_merlin_only("merge", "EP-AUTO-GIT-001", "merlin")

        self.assertTrue(result.authorized)

    @patch("scripts.governance.merlin_authority._get_redis_authority_settings")
    def test_enforce_non_merlin_raises(self, mock_get_settings) -> None:
        """Test that enforcement raises for non-merlin."""
        mock_get_settings.return_value = {"merge_authority": "merlin-only"}

        with self.assertRaises(AuthorityViolation) as context:
            enforce_merlin_only("merge", "EP-AUTO-GIT-001", "jarvis")

        self.assertEqual(context.exception.action, "merge")
        self.assertEqual(context.exception.agent, "jarvis")


class TestRequireMerlinDecorator(unittest.TestCase):
    """Test the @require_merlin decorator."""

    def setUp(self) -> None:
        """Clear cache before each test."""
        _clear_cache()

    def tearDown(self) -> None:
        """Clear cache after each test."""
        _clear_cache()

    @patch("scripts.governance.merlin_authority._get_redis_authority_settings")
    def test_decorator_allows_merlin(self, mock_get_settings) -> None:
        """Test that decorator allows merlin to execute function."""
        mock_get_settings.return_value = {"execute_authority": "merlin-only"}

        @require_merlin(action="execute")
        def protected_function():
            return "success"

        with patch.dict(os.environ, {"AGENT_NAME": "merlin"}):
            result = protected_function()
            self.assertEqual(result, "success")

    @patch("scripts.governance.merlin_authority._get_redis_authority_settings")
    def test_decorator_blocks_non_merlin(self, mock_get_settings) -> None:
        """Test that decorator blocks non-merlin from executing function."""
        mock_get_settings.return_value = {"execute_authority": "merlin-only"}

        @require_merlin(action="execute")
        def protected_function():
            return "success"

        with patch.dict(os.environ, {"AGENT_NAME": "jarvis"}):
            with self.assertRaises(AuthorityViolation):
                protected_function()

    @patch("scripts.governance.merlin_authority._get_redis_authority_settings")
    def test_decorator_preserves_function_metadata(self, mock_get_settings) -> None:
        """Test that decorator preserves function name and docstring."""
        mock_get_settings.return_value = {"test_authority": "merlin-only"}

        @require_merlin(action="test")
        def my_function():
            """My docstring."""
            return "result"

        self.assertEqual(my_function.__name__, "my_function")
        self.assertEqual(my_function.__doc__, "My docstring.")

    @patch("scripts.governance.merlin_authority._get_redis_authority_settings")
    def test_decorator_with_arguments(self, mock_get_settings) -> None:
        """Test that decorated function can accept arguments."""
        mock_get_settings.return_value = {"process_authority": "merlin-only"}

        @require_merlin(action="process")
        def process_data(data: str, count: int) -> str:
            return f"{data}:{count}"

        with patch.dict(os.environ, {"AGENT_NAME": "merlin"}):
            result = process_data("test", 42)
            self.assertEqual(result, "test:42")


class TestVerifyGitSha(unittest.TestCase):
    """Test the verify_git_sha function."""

    @patch("subprocess.run")
    def test_verify_valid_sha(self, mock_run) -> None:
        """Test verifying a valid SHA."""
        mock_run.return_value = MagicMock(returncode=0, stdout="commit\n", stderr="")

        result = verify_git_sha("abc1234")
        self.assertTrue(result)

    @patch("subprocess.run")
    def test_verify_invalid_sha(self, mock_run) -> None:
        """Test verifying an invalid SHA."""
        mock_run.return_value = MagicMock(
            returncode=128, stdout="", stderr="fatal: Not a valid object name"
        )

        result = verify_git_sha("invalid")
        self.assertFalse(result)

    @patch("subprocess.run")
    def test_verify_with_repo_path(self, mock_run) -> None:
        """Test verifying SHA with custom repo path."""
        mock_run.return_value = MagicMock(returncode=0, stdout="commit\n", stderr="")

        result = verify_git_sha("abc1234", "/path/to/repo")
        self.assertTrue(result)

        # Verify the command was called with -C flag
        call_args = mock_run.call_args[0][0]
        self.assertIn("-C", call_args)
        self.assertIn("/path/to/repo", call_args)

    @patch("subprocess.run")
    def test_verify_timeout(self, mock_run) -> None:
        """Test handling of timeout."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["git"], timeout=10)

        result = verify_git_sha("abc1234")
        self.assertFalse(result)

    @patch("subprocess.run")
    def test_verify_exception(self, mock_run) -> None:
        """Test handling of general exceptions."""
        mock_run.side_effect = Exception("Unexpected error")

        result = verify_git_sha("abc1234")
        self.assertFalse(result)

    def test_verify_empty_sha(self) -> None:
        """Test verifying empty SHA."""
        result = verify_git_sha("")
        self.assertFalse(result)

    def test_verify_invalid_format(self) -> None:
        """Test verifying SHA with invalid format."""
        # SHA that's too short and doesn't match pattern
        result = verify_git_sha("abc")
        self.assertFalse(result)


class TestFailSecureBehavior(unittest.TestCase):
    """Test fail-secure behavior when Redis is unavailable."""

    def setUp(self) -> None:
        """Clear cache before each test."""
        _clear_cache()

    def tearDown(self) -> None:
        """Clear cache after each test."""
        _clear_cache()

    @patch("redis_state.hgetall")
    def test_fail_secure_on_redis_error(self, mock_hgetall) -> None:
        """Test that access is denied when Redis raises an error."""
        mock_hgetall.side_effect = ConnectionError("Redis unavailable")

        with self.assertRaises(AuthorityCheckError):
            check_ep_auto_git_authority("merge", "merlin")

    @patch("redis_state.hgetall")
    def test_fail_secure_on_redis_timeout(self, mock_hgetall) -> None:
        """Test that access is denied when Redis times out."""
        mock_hgetall.side_effect = TimeoutError("Redis timeout")

        with self.assertRaises(AuthorityCheckError):
            check_ep_auto_git_authority("merge", "merlin")

    def test_fail_secure_on_import_error(self) -> None:
        """Test that access is denied when redis_state cannot be imported."""
        with patch.dict("sys.modules", {"redis_state": None}):
            with self.assertRaises(AuthorityCheckError):
                check_ep_auto_git_authority("merge", "merlin")


class TestIntegration(unittest.TestCase):
    """Integration tests for the complete workflow."""

    def setUp(self) -> None:
        """Clear cache before each test."""
        _clear_cache()

    def tearDown(self) -> None:
        """Clear cache after each test."""
        _clear_cache()

    @patch("redis_state.hgetall")
    def test_full_authorization_flow(self, mock_hgetall) -> None:
        """Test complete authorization flow from check to enforcement."""
        mock_hgetall.return_value = {
            "merge_authority": "merlin-only",
            "pr_authority": "merlin-only",
            "status_authority": "merlin-only",
        }

        # Step 1: Check authority
        result = check_ep_auto_git_authority("merge", "merlin")
        self.assertTrue(result.authorized)

        # Step 2: Verify git SHA
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="commit\n", stderr=""
            )
            sha_valid = verify_git_sha("19e9e62")
            self.assertTrue(sha_valid)

        # Step 3: Enforce authority
        enforcement_result = enforce_merlin_only("merge", "EP-AUTO-GIT-001", "merlin")
        self.assertTrue(enforcement_result.authorized)

    @patch("redis_state.hgetall")
    def test_unauthorized_flow_blocked(self, mock_hgetall) -> None:
        """Test that unauthorized flow is properly blocked."""
        mock_hgetall.return_value = {
            "merge_authority": "merlin-only",
        }

        # Check authority for non-merlin
        result = check_ep_auto_git_authority("merge", "worker-1")
        self.assertFalse(result.authorized)

        # Enforcement should raise
        with self.assertRaises(AuthorityViolation):
            enforce_merlin_only("merge", "EP-AUTO-GIT-001", "worker-1")


if __name__ == "__main__":
    unittest.main(verbosity=2)
