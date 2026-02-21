"""Tests for Gitea client."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from autonomous_git.gitreviewbot.gitea_client import GiteaClient
from autonomous_git.gitreviewbot.models import Decision, DecisionType


class TestGiteaClient:
    """Test GiteaClient."""

    def test_init_with_defaults(self, monkeypatch):
        """Test initialization with default values."""
        # Clear env vars that might affect defaults
        monkeypatch.delenv("GITEA_TOKEN", raising=False)
        monkeypatch.delenv("GITEA_URL", raising=False)
        monkeypatch.delenv("GITEA_OWNER", raising=False)
        monkeypatch.delenv("GITEA_REPO", raising=False)

        client = GiteaClient()

        assert client.base_url == "http://localhost:3000"
        assert client.token == ""
        assert client.owner == "chiseai"
        assert client.repo == "chiseai"

    def test_init_with_params(self):
        """Test initialization with custom values."""
        client = GiteaClient(
            base_url="https://gitea.example.com",
            token="test-token",
            owner="test-owner",
            repo="test-repo",
        )

        assert client.base_url == "https://gitea.example.com"
        assert client.token == "test-token"
        assert client.owner == "test-owner"
        assert client.repo == "test-repo"

    def test_init_from_env(self, monkeypatch):
        """Test initialization from environment variables."""
        monkeypatch.setenv("GITEA_URL", "https://env-gitea.com")
        monkeypatch.setenv("GITEA_TOKEN", "env-token")
        monkeypatch.setenv("GITEA_OWNER", "env-owner")
        monkeypatch.setenv("GITEA_REPO", "env-repo")

        client = GiteaClient()

        assert client.base_url == "https://env-gitea.com"
        assert client.token == "env-token"
        assert client.owner == "env-owner"
        assert client.repo == "env-repo"


class TestExtractStoryId:
    """Test story ID extraction."""

    def test_extract_st_id(self):
        """Test extracting ST-* ID."""
        client = GiteaClient()

        assert client.extract_story_id("ST-123: Add feature") == "ST-123"
        assert client.extract_story_id("st-456: Fix bug") == "ST-456"

    def test_extract_ch_id(self):
        """Test extracting CH-* ID."""
        client = GiteaClient()

        assert client.extract_story_id("CH-789: Refactor") == "CH-789"

    def test_extract_ft_id(self):
        """Test extracting FT-* ID."""
        client = GiteaClient()

        assert client.extract_story_id("FT-001: New feature") == "FT-001"

    def test_extract_reward_id(self):
        """Test extracting REWARD-* ID."""
        client = GiteaClient()

        assert client.extract_story_id("REWARD-123: Update") == "REWARD-123"

    def test_extract_repo_id(self):
        """Test extracting REPO-* ID."""
        client = GiteaClient()

        assert client.extract_story_id("REPO-456: Cleanup") == "REPO-456"

    def test_extract_safety_id(self):
        """Test extracting SAFETY-* ID."""
        client = GiteaClient()

        assert client.extract_story_id("SAFETY-789: Fix") == "SAFETY-789"

    def test_extract_branch_id(self):
        """Test extracting BRANCH-* ID."""
        client = GiteaClient()

        assert client.extract_story_id("BRANCH-001: Sync") == "BRANCH-001"

    def test_extract_paper_id(self):
        """Test extracting PAPER-* ID."""
        client = GiteaClient()

        assert client.extract_story_id("PAPER-123: Trading") == "PAPER-123"

    def test_extract_recon_id(self):
        """Test extracting RECON-* ID."""
        client = GiteaClient()

        assert client.extract_story_id("RECON-456: Reconcile") == "RECON-456"

    def test_no_story_id(self):
        """Test when no story ID present."""
        client = GiteaClient()

        assert client.extract_story_id("Add feature") is None
        assert client.extract_story_id("Fix bug in parser") is None


class TestFormatReviewBody:
    """Test review body formatting."""

    def test_format_approve(self):
        """Test formatting APPROVE decision."""
        client = GiteaClient()

        decision = Decision(
            decision=DecisionType.APPROVE,
            confidence=95.0,
            senior_dev_confidence=92.0,
            critic_confidence=93.0,
            summary="LGTM",
            pr_number=123,
            pr_title="Test",
        )

        body = client._format_review_body(decision)

        assert "APPROVE" in body
        assert "95.0%" in body
        assert "LGTM" in body

    def test_format_with_blockers(self):
        """Test formatting with blockers."""
        client = GiteaClient()

        decision = Decision(
            decision=DecisionType.REQUEST_CHANGES,
            confidence=60.0,
            senior_dev_confidence=65.0,
            critic_confidence=55.0,
            summary="Needs work",
            pr_number=123,
            pr_title="Test",
            blockers=["Missing tests", "Security issue"],
        )

        body = client._format_review_body(decision)

        assert "Blockers" in body
        assert "Missing tests" in body
        assert "Security issue" in body

    def test_format_with_findings(self):
        """Test formatting with findings."""
        from autonomous_git.gitreviewbot.models import Finding, Severity

        client = GiteaClient()

        decision = Decision(
            decision=DecisionType.COMMENT,
            confidence=80.0,
            senior_dev_confidence=82.0,
            critic_confidence=78.0,
            summary="Review recommended",
            pr_number=123,
            pr_title="Test",
            findings=[
                Finding(
                    file="src/test.py",
                    line=10,
                    severity=Severity.WARNING,
                    message="Consider refactoring",
                    suggestion="Use list comprehension",
                ),
            ],
        )

        body = client._format_review_body(decision)

        assert "Findings" in body
        assert "src/test.py" in body
        assert "Consider refactoring" in body

    def test_format_with_violations(self):
        """Test formatting with violations."""
        from autonomous_git.gitreviewbot.models import Violation, Severity

        client = GiteaClient()

        decision = Decision(
            decision=DecisionType.REQUEST_CHANGES,
            confidence=70.0,
            senior_dev_confidence=75.0,
            critic_confidence=65.0,
            summary="Issues found",
            pr_number=123,
            pr_title="Test",
            violations=[
                Violation(
                    rule="missing_story_id",
                    severity=Severity.ERROR,
                    message="PR title missing story ID",
                ),
            ],
        )

        body = client._format_review_body(decision)

        assert "Violations" in body
        assert "missing_story_id" in body

    def test_format_auto_merge_eligible(self):
        """Test formatting auto-merge eligible."""
        client = GiteaClient()

        decision = Decision(
            decision=DecisionType.APPROVE,
            confidence=96.0,
            senior_dev_confidence=95.0,
            critic_confidence=95.0,
            summary="LGTM",
            pr_number=123,
            pr_title="Test",
            auto_merge_eligible=True,
        )

        body = client._format_review_body(decision)

        assert "Auto-merge eligible" in body


class TestBuildFileComments:
    """Test file comment building."""

    def test_build_comments_for_errors(self):
        """Test building comments for error findings."""
        from autonomous_git.gitreviewbot.models import Finding, Severity

        client = GiteaClient()

        decision = Decision(
            decision=DecisionType.REQUEST_CHANGES,
            confidence=70.0,
            senior_dev_confidence=75.0,
            critic_confidence=65.0,
            summary="Issues",
            pr_number=123,
            pr_title="Test",
            findings=[
                Finding(
                    file="src/test.py",
                    line=10,
                    severity=Severity.ERROR,
                    message="Bug here",
                ),
            ],
        )

        comments = client._build_file_comments(decision)

        assert len(comments) == 1
        assert comments[0]["path"] == "src/test.py"
        assert comments[0]["position"] == 10

    def test_no_comments_for_info(self):
        """Test no comments for info findings."""
        from autonomous_git.gitreviewbot.models import Finding, Severity

        client = GiteaClient()

        decision = Decision(
            decision=DecisionType.APPROVE,
            confidence=95.0,
            senior_dev_confidence=92.0,
            critic_confidence=93.0,
            summary="LGTM",
            pr_number=123,
            pr_title="Test",
            findings=[
                Finding(
                    file="src/test.py",
                    line=10,
                    severity=Severity.INFO,
                    message="Suggestion",
                ),
            ],
        )

        comments = client._build_file_comments(decision)

        assert len(comments) == 0

    def test_no_comments_without_line(self):
        """Test no comments for findings without line number."""
        from autonomous_git.gitreviewbot.models import Finding, Severity

        client = GiteaClient()

        decision = Decision(
            decision=DecisionType.REQUEST_CHANGES,
            confidence=70.0,
            senior_dev_confidence=75.0,
            critic_confidence=65.0,
            summary="Issues",
            pr_number=123,
            pr_title="Test",
            findings=[
                Finding(
                    file="src/test.py",
                    line=None,
                    severity=Severity.ERROR,
                    message="General issue",
                ),
            ],
        )

        comments = client._build_file_comments(decision)

        assert len(comments) == 0
