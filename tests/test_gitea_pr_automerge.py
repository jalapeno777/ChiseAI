"""Tests for Gitea PR auto-merge script."""

from __future__ import annotations

import importlib
import json
import os
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest
import scripts.gitea_pr_automerge as automerge
from scripts.gitea_pr_automerge import (
    _check_merge_conflict,
    _commit_status,
    _create_pr,
    _get_pr,
    _get_pr_reviews,
    _has_required_approval,
    _merge_pr,
    _post_pr_comment,
    _req_json,
    _try_merge_with_retry,
    main,
)


class MockResponse:
    """Mock urllib response."""

    def __init__(self, data: dict | list, status: int = 200):
        self._data = data
        self.status = status

    def read(self) -> bytes:
        return json.dumps(self._data).encode("utf-8")


class TestReqJson:
    """Tests for _req_json function."""

    @patch("urllib.request.urlopen")
    def test_get_request_success(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value.__enter__.return_value = MockResponse(
            {"id": 1, "title": "Test PR"}
        )
        result = _req_json("GET", "http://test/api", "token123")
        assert result == {"id": 1, "title": "Test PR"}

    @patch("urllib.request.urlopen")
    def test_post_request_with_body(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value.__enter__.return_value = MockResponse(
            {"number": 42, "title": "New PR"}
        )
        result = _req_json("POST", "http://test/api", "token123", {"title": "New PR"})
        assert result == {"number": 42, "title": "New PR"}

    @patch("urllib.request.urlopen")
    def test_http_error_raises_runtime_error(self, mock_urlopen: MagicMock) -> None:
        from urllib.error import HTTPError

        mock_urlopen.side_effect = HTTPError(
            "http://test/api",
            404,
            "Not Found",
            None,  # type: ignore[arg-type]
            BytesIO(b'{"message": "not found"}'),
        )
        with pytest.raises(RuntimeError) as exc_info:
            _req_json("GET", "http://test/api", "token123")
        assert "HTTP 404" in str(exc_info.value)


class TestGetPr:
    """Tests for _get_pr function."""

    @patch("scripts.gitea_pr_automerge._req_json")
    def test_get_existing_pr(self, mock_req: MagicMock) -> None:
        mock_req.return_value = [
            {
                "number": 1,
                "title": "Test PR",
                "head": {"ref": "feature-branch", "sha": "abc123"},
            }
        ]
        result = _get_pr("owner", "repo", "http://test", "token", "feature-branch")
        assert result is not None
        assert result["number"] == 1
        assert result["title"] == "Test PR"

    @patch("scripts.gitea_pr_automerge._req_json")
    def test_get_pr_not_found(self, mock_req: MagicMock) -> None:
        mock_req.return_value = []
        result = _get_pr("owner", "repo", "http://test", "token", "feature-branch")
        assert result is None

    @patch("scripts.gitea_pr_automerge._req_json")
    def test_get_pr_empty_response(self, mock_req: MagicMock) -> None:
        mock_req.return_value = None
        result = _get_pr("owner", "repo", "http://test", "token", "feature-branch")
        assert result is None


class TestCreatePr:
    """Tests for _create_pr function."""

    @patch("scripts.gitea_pr_automerge._req_json")
    def test_create_pr_success(self, mock_req: MagicMock) -> None:
        mock_req.return_value = {
            "number": 42,
            "title": "ST-CI-002 Test PR",
            "head": {"sha": "abc123"},
        }
        result = _create_pr(
            "owner",
            "repo",
            "http://test",
            "token",
            head="feature-branch",
            base="main",
            title="ST-CI-002 Test PR",
            body="PR description",
        )
        assert result["number"] == 42
        assert result["title"] == "ST-CI-002 Test PR"
        mock_req.assert_called_once()
        call_args = mock_req.call_args
        assert call_args[0][0] == "POST"
        assert "pulls" in call_args[0][1]

    @patch("scripts.gitea_pr_automerge._req_json")
    def test_create_pr_includes_story_id_in_title(self, mock_req: MagicMock) -> None:
        """Test that PR title includes story ID (AC1)."""
        mock_req.return_value = {
            "number": 42,
            "title": "ST-CI-002 feature-branch",
            "head": {"sha": "abc123"},
        }
        _create_pr(
            "owner",
            "repo",
            "http://test",
            "token",
            head="feature-branch",
            base="main",
            title="ST-CI-002 feature-branch",
            body="PR description",
        )
        call_args = mock_req.call_args
        assert "ST-CI-002" in call_args[0][3]["title"]


class TestCommitStatus:
    """Tests for _commit_status function."""

    @patch("scripts.gitea_pr_automerge._req_json")
    def test_get_commit_status_success(self, mock_req: MagicMock) -> None:
        mock_req.return_value = {
            "state": "success",
            "statuses": [
                {"context": "ci/woodpecker/push/woodpecker", "state": "success"}
            ],
        }
        result = _commit_status("owner", "repo", "http://test", "token", "abc123")
        assert result["state"] == "success"
        assert len(result["statuses"]) == 1

    @patch("scripts.gitea_pr_automerge._req_json")
    def test_get_commit_status_pending(self, mock_req: MagicMock) -> None:
        mock_req.return_value = {
            "state": "pending",
            "statuses": [
                {"context": "ci/woodpecker/push/woodpecker", "state": "pending"}
            ],
        }
        result = _commit_status("owner", "repo", "http://test", "token", "abc123")
        assert result["state"] == "pending"

    @patch("scripts.gitea_pr_automerge._req_json")
    def test_get_commit_status_failure(self, mock_req: MagicMock) -> None:
        """Test required context check failure state."""
        mock_req.return_value = {
            "state": "failure",
            "statuses": [
                {"context": "ci/woodpecker/push/woodpecker", "state": "failure"}
            ],
        }
        result = _commit_status("owner", "repo", "http://test", "token", "abc123")
        assert result["state"] == "failure"

    @patch("scripts.gitea_pr_automerge._req_json")
    def test_get_commit_status_error(self, mock_req: MagicMock) -> None:
        """Test required context check error state."""
        mock_req.return_value = {
            "state": "error",
            "statuses": [
                {"context": "ci/woodpecker/push/woodpecker", "state": "error"}
            ],
        }
        result = _commit_status("owner", "repo", "http://test", "token", "abc123")
        assert result["state"] == "error"


class TestGetPrReviews:
    """Tests for _get_pr_reviews function (AC4)."""

    @patch("scripts.gitea_pr_automerge._req_json")
    def test_get_reviews_with_approvals(self, mock_req: MagicMock) -> None:
        mock_req.return_value = [
            {"id": 1, "state": "APPROVED", "user": {"login": "reviewer1"}},
            {"id": 2, "state": "COMMENTED", "user": {"login": "reviewer2"}},
        ]
        result = _get_pr_reviews("owner", "repo", "http://test", "token", 42)
        assert len(result) == 2
        assert result[0]["state"] == "APPROVED"

    @patch("scripts.gitea_pr_automerge._req_json")
    def test_get_reviews_empty(self, mock_req: MagicMock) -> None:
        mock_req.return_value = []
        result = _get_pr_reviews("owner", "repo", "http://test", "token", 42)
        assert result == []

    @patch("scripts.gitea_pr_automerge._req_json")
    def test_get_reviews_error_returns_empty(self, mock_req: MagicMock) -> None:
        mock_req.side_effect = RuntimeError("API error")
        result = _get_pr_reviews("owner", "repo", "http://test", "token", 42)
        assert result == []

    @patch("scripts.gitea_pr_automerge._req_json")
    def test_get_reviews_non_list_response(self, mock_req: MagicMock) -> None:
        mock_req.return_value = {"error": "not found"}
        result = _get_pr_reviews("owner", "repo", "http://test", "token", 42)
        assert result == []


class TestHasRequiredApproval:
    """Tests for _has_required_approval function (AC4)."""

    def test_has_approval_true(self) -> None:
        reviews = [
            {"id": 1, "state": "APPROVED", "user": {"login": "reviewer1"}},
        ]
        assert _has_required_approval(reviews) is True

    def test_has_approval_multiple_with_one_approved(self) -> None:
        reviews = [
            {"id": 1, "state": "COMMENTED", "user": {"login": "reviewer1"}},
            {"id": 2, "state": "APPROVED", "user": {"login": "reviewer2"}},
        ]
        assert _has_required_approval(reviews) is True

    def test_has_approval_false_no_reviews(self) -> None:
        assert _has_required_approval([]) is False

    def test_has_approval_false_no_approved(self) -> None:
        reviews = [
            {"id": 1, "state": "COMMENTED", "user": {"login": "reviewer1"}},
            {"id": 2, "state": "CHANGES_REQUESTED", "user": {"login": "reviewer2"}},
        ]
        assert _has_required_approval(reviews) is False


class TestPostPrComment:
    """Tests for _post_pr_comment function."""

    @patch("scripts.gitea_pr_automerge._req_json")
    def test_post_comment_success(self, mock_req: MagicMock) -> None:
        mock_req.return_value = {"id": 1, "body": "Test comment"}
        _post_pr_comment("owner", "repo", "http://test", "token", 42, "Test comment")
        mock_req.assert_called_once()
        call_args = mock_req.call_args
        assert call_args[0][0] == "POST"
        assert "issues/42/comments" in call_args[0][1]
        # The body is passed as a positional argument (4th arg)
        assert call_args[0][3] == {"body": "Test comment"}


class TestCheckMergeConflict:
    """Tests for _check_merge_conflict function (AC6)."""

    @patch("scripts.gitea_pr_automerge._req_json")
    def test_no_conflict_mergeable_true(self, mock_req: MagicMock) -> None:
        mock_req.return_value = {"number": 42, "mergeable": True}
        result = _check_merge_conflict("owner", "repo", "http://test", "token", 42)
        assert result is False

    @patch("scripts.gitea_pr_automerge._req_json")
    def test_has_conflict_mergeable_false(self, mock_req: MagicMock) -> None:
        mock_req.return_value = {"number": 42, "mergeable": False}
        result = _check_merge_conflict("owner", "repo", "http://test", "token", 42)
        assert result is True

    @patch("scripts.gitea_pr_automerge._req_json")
    def test_unknown_mergeable_none(self, mock_req: MagicMock) -> None:
        mock_req.return_value = {"number": 42, "mergeable": None}
        result = _check_merge_conflict("owner", "repo", "http://test", "token", 42)
        assert result is False

    @patch("scripts.gitea_pr_automerge._req_json")
    def test_api_error_returns_false(self, mock_req: MagicMock) -> None:
        mock_req.side_effect = RuntimeError("API error")
        result = _check_merge_conflict("owner", "repo", "http://test", "token", 42)
        assert result is False


class TestMergePr:
    """Tests for _merge_pr function."""

    @patch("scripts.gitea_pr_automerge._req_json")
    def test_merge_pr_success(self, mock_req: MagicMock) -> None:
        mock_req.return_value = {}
        _merge_pr(
            "owner",
            "repo",
            "http://test",
            "token",
            index=42,
            head_sha="abc123",
            merge_when_checks_succeed=False,
            delete_branch_after_merge=True,
        )
        mock_req.assert_called_once()
        call_args = mock_req.call_args
        assert call_args[0][0] == "POST"
        assert "pulls/42/merge" in call_args[0][1]
        # The body is passed as a positional argument (4th arg)
        assert call_args[0][3]["Do"] == "merge"


class TestTryMergeWithRetry:
    """Tests for _try_merge_with_retry function (AC5)."""

    @patch("scripts.gitea_pr_automerge._merge_pr")
    def test_merge_success_first_attempt(self, mock_merge: MagicMock) -> None:
        success, attempts = _try_merge_with_retry(
            "owner", "repo", "http://test", "token", 42, "abc123", True, 3
        )
        assert success is True
        assert attempts == 1
        assert mock_merge.call_count == 1

    @patch("scripts.gitea_pr_automerge._merge_pr")
    @patch("time.sleep")
    def test_merge_success_after_retry(
        self, mock_sleep: MagicMock, mock_merge: MagicMock
    ) -> None:
        # First two calls fail, third succeeds
        mock_merge.side_effect = [RuntimeError("Error"), RuntimeError("Error"), None]
        success, attempts = _try_merge_with_retry(
            "owner", "repo", "http://test", "token", 42, "abc123", True, 3
        )
        assert success is True
        assert attempts == 3
        assert mock_merge.call_count == 3

    @patch("scripts.gitea_pr_automerge._merge_pr")
    @patch("time.sleep")
    def test_merge_failure_all_retries_exhausted(
        self, mock_sleep: MagicMock, mock_merge: MagicMock
    ) -> None:
        mock_merge.side_effect = RuntimeError("Merge failed")
        success, attempts = _try_merge_with_retry(
            "owner", "repo", "http://test", "token", 42, "abc123", True, 3
        )
        assert success is False
        assert attempts == 3
        assert mock_merge.call_count == 3

    @patch("scripts.gitea_pr_automerge._merge_pr")
    def test_retry_count_logged_in_failure(self, mock_merge: MagicMock) -> None:
        """Test that retry count is available on merge failure (AC5)."""
        mock_merge.side_effect = RuntimeError("Merge failed")
        success, attempts = _try_merge_with_retry(
            "owner", "repo", "http://test", "token", 42, "abc123", True, 5
        )
        assert success is False
        assert attempts == 5


class TestEnvironmentVariables:
    """Tests for environment variable configuration."""

    def test_gitea_poll_interval_default(self) -> None:
        """Test GITEA_POLL_INTERVAL default value."""
        # Clear env var to test default
        env_copy = os.environ.copy()
        if "GITEA_POLL_INTERVAL" in os.environ:
            del os.environ["GITEA_POLL_INTERVAL"]

        # Reload to get default values
        importlib.reload(automerge)

        # Restore env
        os.environ.clear()
        os.environ.update(env_copy)

        # Default should be 60
        assert automerge.os.getenv("GITEA_POLL_INTERVAL", "60") == "60"

    def test_gitea_max_retries_default(self) -> None:
        """Test GITEA_MAX_RETRIES default value."""
        # Default should be 3
        assert os.getenv("GITEA_MAX_RETRIES", "3") == "3"

    def test_gitea_poll_interval_custom(self) -> None:
        """Test GITEA_POLL_INTERVAL can be set from env."""
        with patch.dict(os.environ, {"GITEA_POLL_INTERVAL": "120"}):
            default_poll = int(os.getenv("GITEA_POLL_INTERVAL", "60"))
            assert default_poll == 120

    def test_gitea_max_retries_custom(self) -> None:
        """Test GITEA_MAX_RETRIES can be set from env."""
        with patch.dict(os.environ, {"GITEA_MAX_RETRIES": "5"}):
            default_retries = int(os.getenv("GITEA_MAX_RETRIES", "3"))
            assert default_retries == 5


class TestMain:
    """Tests for main function with full mocking."""

    @patch("scripts.gitea_pr_automerge._req_json")
    @patch("scripts.gitea_pr_automerge._merge_pr")
    @patch("scripts.gitea_pr_automerge._check_merge_conflict")
    @patch("scripts.gitea_pr_automerge._get_pr_reviews")
    @patch("scripts.gitea_pr_automerge._get_pr")
    def test_main_non_merlin_agent_blocked(
        self,
        mock_get_pr: MagicMock,
        mock_get_reviews: MagicMock,
        mock_check_conflict: MagicMock,
        mock_merge: MagicMock,
        mock_req_json: MagicMock,
    ) -> None:
        """Test non-merlin agent is blocked from PR submission."""
        with (
            patch.dict(os.environ, {"GITEA_TOKEN": "test-token", "AGENT_ID": "dev"}),
            patch(
                "sys.argv",
                [
                    "script",
                    "--head",
                    "feature-branch",
                    "--story-id",
                    "ST-CI-002",
                ],
            ),
        ):
            result = main()

        assert result == 1
        mock_get_pr.assert_not_called()

    @patch("scripts.gitea_pr_automerge._req_json")
    @patch("scripts.gitea_pr_automerge._merge_pr")
    @patch("scripts.gitea_pr_automerge._check_merge_conflict")
    @patch("scripts.gitea_pr_automerge._get_pr_reviews")
    @patch("scripts.gitea_pr_automerge._get_pr")
    def test_main_non_merlin_override_allowed(
        self,
        mock_get_pr: MagicMock,
        mock_get_reviews: MagicMock,
        mock_check_conflict: MagicMock,
        mock_merge: MagicMock,
        mock_req_json: MagicMock,
    ) -> None:
        """Test explicit override allows non-merlin agent execution."""
        mock_get_pr.return_value = {
            "number": 42,
            "title": "Test PR",
            "head": {"sha": "abc123"},
        }
        mock_get_reviews.return_value = [{"state": "APPROVED"}]
        mock_check_conflict.return_value = False
        mock_merge.return_value = None
        mock_req_json.return_value = {}

        with (
            patch.dict(
                os.environ,
                {
                    "GITEA_TOKEN": "test-token",
                    "AGENT_ID": "dev",
                    "CHISE_ALLOW_NON_MERLIN_PR": "1",
                },
            ),
            patch(
                "sys.argv",
                [
                    "script",
                    "--head",
                    "feature-branch",
                    "--story-id",
                    "ST-CI-002",
                ],
            ),
        ):
            result = main()

        assert result == 0
        mock_get_pr.assert_called_once()

    @patch("scripts.gitea_pr_automerge._req_json")
    @patch("scripts.gitea_pr_automerge._merge_pr")
    @patch("scripts.gitea_pr_automerge._check_merge_conflict")
    @patch("scripts.gitea_pr_automerge._get_pr_reviews")
    @patch("scripts.gitea_pr_automerge._get_pr")
    def test_main_no_wait_enables_automerge(
        self,
        mock_get_pr: MagicMock,
        mock_get_reviews: MagicMock,
        mock_check_conflict: MagicMock,
        mock_merge: MagicMock,
        mock_req_json: MagicMock,
    ) -> None:
        """Test that --wait=false enables server-side automerge."""
        mock_get_pr.return_value = {
            "number": 42,
            "title": "Test PR",
            "head": {"sha": "abc123"},
        }
        mock_get_reviews.return_value = [{"state": "APPROVED"}]
        mock_check_conflict.return_value = False
        mock_merge.return_value = None
        mock_req_json.return_value = {}

        with (
            patch.dict(os.environ, {"GITEA_TOKEN": "test-token"}),
            patch(
                "sys.argv",
                [
                    "script",
                    "--head",
                    "feature-branch",
                    "--story-id",
                    "ST-CI-002",
                ],
            ),
        ):
            result = main()

        assert result == 0
        mock_merge.assert_called_once()
        call_kwargs = mock_merge.call_args[1]
        assert call_kwargs["merge_when_checks_succeed"] is True

    @patch("scripts.gitea_pr_automerge._req_json")
    @patch("scripts.gitea_pr_automerge._try_merge_with_retry")
    @patch("scripts.gitea_pr_automerge._check_merge_conflict")
    @patch("scripts.gitea_pr_automerge._commit_status")
    @patch("scripts.gitea_pr_automerge._get_pr_reviews")
    @patch("scripts.gitea_pr_automerge._get_pr")
    def test_main_wait_merge_on_green(
        self,
        mock_get_pr: MagicMock,
        mock_get_reviews: MagicMock,
        mock_commit_status: MagicMock,
        mock_check_conflict: MagicMock,
        mock_try_merge: MagicMock,
        mock_req_json: MagicMock,
    ) -> None:
        """Test that --wait polls and merges when CI is green."""
        mock_get_pr.return_value = {
            "number": 42,
            "title": "Test PR",
            "head": {"sha": "abc123"},
        }
        mock_get_reviews.return_value = [{"state": "APPROVED"}]
        mock_commit_status.return_value = {
            "state": "success",
            "statuses": [
                {"context": "ci/woodpecker/push/woodpecker", "state": "success"}
            ],
        }
        mock_check_conflict.return_value = False
        mock_try_merge.return_value = (True, 1)
        mock_req_json.return_value = {}

        with (
            patch.dict(os.environ, {"GITEA_TOKEN": "test-token"}),
            patch(
                "sys.argv",
                [
                    "script",
                    "--head",
                    "feature-branch",
                    "--story-id",
                    "ST-CI-002",
                    "--wait",
                    "--poll-sec",
                    "1",
                ],
            ),
        ):
            result = main()

        assert result == 0
        mock_try_merge.assert_called_once()

    @patch("scripts.gitea_pr_automerge._req_json")
    @patch("scripts.gitea_pr_automerge._commit_status")
    @patch("scripts.gitea_pr_automerge._check_merge_conflict")
    @patch("scripts.gitea_pr_automerge._get_pr_reviews")
    @patch("scripts.gitea_pr_automerge._get_pr")
    def test_main_wait_ci_failure(
        self,
        mock_get_pr: MagicMock,
        mock_get_reviews: MagicMock,
        mock_check_conflict: MagicMock,
        mock_commit_status: MagicMock,
        mock_req_json: MagicMock,
    ) -> None:
        """Test that CI failure returns error."""
        mock_get_pr.return_value = {
            "number": 42,
            "title": "Test PR",
            "head": {"sha": "abc123"},
        }
        mock_get_reviews.return_value = [{"state": "APPROVED"}]
        mock_check_conflict.return_value = False
        mock_commit_status.return_value = {
            "state": "failure",
            "statuses": [
                {"context": "ci/woodpecker/push/woodpecker", "state": "failure"}
            ],
        }
        mock_req_json.return_value = {}

        with (
            patch.dict(os.environ, {"GITEA_TOKEN": "test-token"}),
            patch(
                "sys.argv",
                [
                    "script",
                    "--head",
                    "feature-branch",
                    "--story-id",
                    "ST-CI-002",
                    "--wait",
                ],
            ),
        ):
            result = main()

        assert result == 1

    @patch("scripts.gitea_pr_automerge._req_json")
    @patch("scripts.gitea_pr_automerge._post_pr_comment")
    @patch("scripts.gitea_pr_automerge._check_merge_conflict")
    @patch("scripts.gitea_pr_automerge._get_pr_reviews")
    @patch("scripts.gitea_pr_automerge._get_pr")
    def test_main_merge_conflict_skips(
        self,
        mock_get_pr: MagicMock,
        mock_get_reviews: MagicMock,
        mock_check_conflict: MagicMock,
        mock_post_comment: MagicMock,
        mock_req_json: MagicMock,
    ) -> None:
        """Test that merge conflict skips auto-merge and posts comment (AC6)."""
        mock_get_pr.return_value = {
            "number": 42,
            "title": "Test PR",
            "head": {"sha": "abc123"},
        }
        mock_get_reviews.return_value = [{"state": "APPROVED"}]
        mock_check_conflict.return_value = True
        mock_req_json.return_value = {}

        with (
            patch.dict(os.environ, {"GITEA_TOKEN": "test-token"}),
            patch(
                "sys.argv",
                [
                    "script",
                    "--head",
                    "feature-branch",
                    "--story-id",
                    "ST-CI-002",
                ],
            ),
        ):
            result = main()

        assert result == 1
        mock_post_comment.assert_called_once()
        call_args = mock_post_comment.call_args
        assert "merge conflicts" in call_args[0][5].lower()

    @patch("scripts.gitea_pr_automerge._req_json")
    @patch("scripts.gitea_pr_automerge._get_pr_reviews")
    @patch("scripts.gitea_pr_automerge._check_merge_conflict")
    @patch("scripts.gitea_pr_automerge._get_pr")
    def test_main_no_approval_fails(
        self,
        mock_get_pr: MagicMock,
        mock_check_conflict: MagicMock,
        mock_get_reviews: MagicMock,
        mock_req_json: MagicMock,
    ) -> None:
        """Test that missing approval fails (AC4)."""
        mock_get_pr.return_value = {
            "number": 42,
            "title": "Test PR",
            "head": {"sha": "abc123"},
        }
        mock_check_conflict.return_value = False
        mock_get_reviews.return_value = [{"state": "COMMENTED"}]
        mock_req_json.return_value = {}

        with (
            patch.dict(os.environ, {"GITEA_TOKEN": "test-token"}),
            patch(
                "sys.argv",
                [
                    "script",
                    "--head",
                    "feature-branch",
                    "--story-id",
                    "ST-CI-002",
                ],
            ),
        ):
            result = main()

        assert result == 1

    @patch("scripts.gitea_pr_automerge._req_json")
    @patch("scripts.gitea_pr_automerge._try_merge_with_retry")
    @patch("scripts.gitea_pr_automerge._commit_status")
    @patch("scripts.gitea_pr_automerge._check_merge_conflict")
    @patch("scripts.gitea_pr_automerge._get_pr_reviews")
    @patch("scripts.gitea_pr_automerge._get_pr")
    def test_main_retry_count_logged(
        self,
        mock_get_pr: MagicMock,
        mock_get_reviews: MagicMock,
        mock_check_conflict: MagicMock,
        mock_commit_status: MagicMock,
        mock_try_merge: MagicMock,
        mock_req_json: MagicMock,
    ) -> None:
        """Test that retry count is logged on merge failure (AC5)."""
        mock_get_pr.return_value = {
            "number": 42,
            "title": "Test PR",
            "head": {"sha": "abc123"},
        }
        mock_get_reviews.return_value = [{"state": "APPROVED"}]
        mock_check_conflict.return_value = False
        mock_commit_status.return_value = {
            "state": "success",
            "statuses": [
                {"context": "ci/woodpecker/push/woodpecker", "state": "success"}
            ],
        }
        mock_try_merge.return_value = (False, 3)
        mock_req_json.return_value = {}

        with (
            patch.dict(os.environ, {"GITEA_TOKEN": "test-token"}),
            patch(
                "sys.argv",
                [
                    "script",
                    "--head",
                    "feature-branch",
                    "--story-id",
                    "ST-CI-002",
                    "--wait",
                    "--max-retries",
                    "3",
                ],
            ),
        ):
            result = main()

        assert result == 1
        mock_try_merge.assert_called_once()
        # Verify max_retries was passed correctly
        call_args = mock_try_merge.call_args
        assert call_args[0][7] == 3  # max_retries is the 8th positional arg

    @patch("scripts.gitea_pr_automerge._req_json")
    @patch("scripts.gitea_pr_automerge._merge_pr")
    @patch("scripts.gitea_pr_automerge._check_merge_conflict")
    @patch("scripts.gitea_pr_automerge._get_pr_reviews")
    @patch("scripts.gitea_pr_automerge._get_pr")
    def test_main_missing_token_fails(
        self,
        mock_get_pr: MagicMock,
        mock_get_reviews: MagicMock,
        mock_check_conflict: MagicMock,
        mock_merge: MagicMock,
        mock_req_json: MagicMock,
    ) -> None:
        """Test that missing GITEA_TOKEN returns error."""
        with (
            patch.dict(os.environ, {}, clear=True),
            patch(
                "sys.argv",
                [
                    "script",
                    "--head",
                    "feature-branch",
                    "--story-id",
                    "ST-CI-002",
                ],
            ),
        ):
            result = main()

        assert result == 1

    @patch("scripts.gitea_pr_automerge._req_json")
    @patch("scripts.gitea_pr_automerge._merge_pr")
    @patch("scripts.gitea_pr_automerge._check_merge_conflict")
    @patch("scripts.gitea_pr_automerge._get_pr_reviews")
    @patch("scripts.gitea_pr_automerge._get_pr")
    def test_main_empty_story_id_fails(
        self,
        mock_get_pr: MagicMock,
        mock_get_reviews: MagicMock,
        mock_check_conflict: MagicMock,
        mock_merge: MagicMock,
        mock_req_json: MagicMock,
    ) -> None:
        """Test that empty story ID returns error."""
        mock_get_pr.return_value = {
            "number": 42,
            "title": "Test PR",
            "head": {"sha": "abc123"},
        }
        mock_get_reviews.return_value = [{"state": "APPROVED"}]
        mock_check_conflict.return_value = False
        mock_merge.return_value = None
        mock_req_json.return_value = {}

        with (
            patch.dict(os.environ, {"GITEA_TOKEN": "test-token"}),
            patch(
                "sys.argv",
                [
                    "script",
                    "--head",
                    "feature-branch",
                    "--story-id",
                    "   ",  # Empty/whitespace story ID
                ],
            ),
        ):
            result = main()

        assert result == 1

    @patch("scripts.gitea_pr_automerge._req_json")
    @patch("scripts.gitea_pr_automerge._create_pr")
    @patch("scripts.gitea_pr_automerge._get_pr_reviews")
    @patch("scripts.gitea_pr_automerge._check_merge_conflict")
    @patch("scripts.gitea_pr_automerge._get_pr")
    def test_main_creates_pr_when_not_exists(
        self,
        mock_get_pr: MagicMock,
        mock_check_conflict: MagicMock,
        mock_get_reviews: MagicMock,
        mock_create_pr: MagicMock,
        mock_req_json: MagicMock,
    ) -> None:
        """Test that PR is created when it doesn't exist."""
        mock_get_pr.return_value = None
        mock_create_pr.return_value = {
            "number": 42,
            "title": "ST-CI-002 feature-branch",
            "head": {"sha": "abc123"},
        }
        mock_check_conflict.return_value = False
        mock_get_reviews.return_value = [{"state": "APPROVED"}]
        mock_req_json.return_value = {}

        with (
            patch.dict(os.environ, {"GITEA_TOKEN": "test-token"}),
            patch(
                "sys.argv",
                [
                    "script",
                    "--head",
                    "feature-branch",
                    "--story-id",
                    "ST-CI-002",
                ],
            ),
        ):
            result = main()

        assert result == 0
        mock_create_pr.assert_called_once()

    @patch("scripts.gitea_pr_automerge._req_json")
    @patch("scripts.gitea_pr_automerge._merge_pr")
    @patch("scripts.gitea_pr_automerge._check_merge_conflict")
    @patch("scripts.gitea_pr_automerge._get_pr_reviews")
    @patch("scripts.gitea_pr_automerge._get_pr")
    def test_main_updates_pr_title_if_missing_story_id(
        self,
        mock_get_pr: MagicMock,
        mock_get_reviews: MagicMock,
        mock_check_conflict: MagicMock,
        mock_merge: MagicMock,
        mock_req_json: MagicMock,
    ) -> None:
        """Test that PR title is updated if story ID is missing."""
        mock_get_pr.return_value = {
            "number": 42,
            "title": "Old Title Without Story ID",
            "head": {"sha": "abc123"},
        }
        mock_get_reviews.return_value = [{"state": "APPROVED"}]
        mock_check_conflict.return_value = False
        mock_merge.return_value = None
        mock_req_json.return_value = {}

        with (
            patch.dict(os.environ, {"GITEA_TOKEN": "test-token"}),
            patch(
                "sys.argv",
                [
                    "script",
                    "--head",
                    "feature-branch",
                    "--story-id",
                    "ST-CI-002",
                ],
            ),
        ):
            result = main()

        assert result == 0
        # Verify PATCH was called to update title
        patch_calls = [
            call for call in mock_req_json.call_args_list if call[0][0] == "PATCH"
        ]
        assert len(patch_calls) == 1

    @patch("scripts.gitea_pr_automerge._req_json")
    @patch("scripts.gitea_pr_automerge._create_pr")
    @patch("scripts.gitea_pr_automerge._get_pr_reviews")
    @patch("scripts.gitea_pr_automerge._check_merge_conflict")
    @patch("scripts.gitea_pr_automerge._get_pr")
    def test_main_does_not_duplicate_story_id_when_title_already_contains_it(
        self,
        mock_get_pr: MagicMock,
        mock_check_conflict: MagicMock,
        mock_get_reviews: MagicMock,
        mock_create_pr: MagicMock,
        mock_req_json: MagicMock,
    ) -> None:
        mock_get_pr.return_value = None
        mock_create_pr.return_value = {
            "number": 42,
            "title": "PAPER-LOOP-001: Order Simulator",
            "head": {"sha": "abc123"},
        }
        mock_check_conflict.return_value = False
        mock_get_reviews.return_value = [{"state": "APPROVED"}]
        mock_req_json.return_value = {}

        with (
            patch.dict(os.environ, {"GITEA_TOKEN": "test-token"}),
            patch(
                "sys.argv",
                [
                    "script",
                    "--head",
                    "feature/PAPER-LOOP-001-order-simulator",
                    "--story-id",
                    "PAPER-LOOP-001",
                    "--title",
                    "PAPER-LOOP-001: Order Simulator",
                ],
            ),
        ):
            result = main()

        assert result == 0
        call_kwargs = mock_create_pr.call_args.kwargs
        assert call_kwargs["title"] == "PAPER-LOOP-001: Order Simulator"

    @patch("scripts.gitea_pr_automerge._req_json")
    @patch("scripts.gitea_pr_automerge._merge_pr")
    @patch("scripts.gitea_pr_automerge._check_merge_conflict")
    @patch("scripts.gitea_pr_automerge._get_pr_reviews")
    @patch("scripts.gitea_pr_automerge._get_pr")
    def test_main_rejects_invalid_story_id_pattern(
        self,
        mock_get_pr: MagicMock,
        mock_get_reviews: MagicMock,
        mock_check_conflict: MagicMock,
        mock_merge: MagicMock,
        mock_req_json: MagicMock,
    ) -> None:
        mock_get_pr.return_value = {
            "number": 42,
            "title": "Test PR",
            "head": {"sha": "abc123"},
        }
        mock_get_reviews.return_value = [{"state": "APPROVED"}]
        mock_check_conflict.return_value = False
        mock_merge.return_value = None
        mock_req_json.return_value = {}

        with (
            patch.dict(os.environ, {"GITEA_TOKEN": "test-token"}),
            patch(
                "sys.argv",
                [
                    "script",
                    "--head",
                    "feature/whatever",
                    "--story-id",
                    "PAPER-LOOP",
                ],
            ),
        ):
            result = main()

        assert result == 1
