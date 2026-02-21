"""Tests for auto-approval exclusions."""

from unittest.mock import mock_open, patch

from src.autonomous_git.auto_approval.exclusions import ExclusionManager, ExclusionList


class TestExclusionManager:
    """Test cases for ExclusionManager."""

    def test_init_default(self):
        """Test exclusion manager initializes with default values."""
        manager = ExclusionManager()

        assert manager.exclusions.paths == []
        assert manager.exclusions.authors == []
        assert manager.exclusions.title_patterns == []

    def test_init_with_values(self):
        """Test exclusion manager initializes with provided values."""
        manager = ExclusionManager(
            paths=["docs/*.md"],
            authors=["external"],
            title_patterns=["HOTFIX.*"],
        )

        assert "docs/*.md" in manager.exclusions.paths
        assert "external" in manager.exclusions.authors
        assert "HOTFIX.*" in manager.exclusions.title_patterns

    def test_is_path_excluded_exact_match(self):
        """Test exact path exclusion matching."""
        manager = ExclusionManager(paths=["docs/security/policy.md"])

        assert manager.is_path_excluded("docs/security/policy.md") is True
        assert manager.is_path_excluded("docs/other.md") is False

    def test_is_path_excluded_wildcard(self):
        """Test wildcard path exclusion matching."""
        manager = ExclusionManager(paths=["docs/*.md"])

        assert manager.is_path_excluded("docs/file.md") is True
        assert manager.is_path_excluded("docs/nested/file.md") is False

    def test_is_path_excluded_double_wildcard(self):
        """Test double wildcard path exclusion matching."""
        manager = ExclusionManager(paths=["docs/**/*.md"])

        assert manager.is_path_excluded("docs/file.md") is True
        assert manager.is_path_excluded("docs/nested/file.md") is True
        assert manager.is_path_excluded("docs/deep/nested/file.md") is True

    def test_are_files_excluded(self):
        """Test checking multiple files for exclusion."""
        manager = ExclusionManager(paths=["docs/security/*.md"])

        files = [
            "src/main.py",
            "docs/security/policy.md",
            "tests/test.py",
        ]

        is_excluded, excluded_files = manager.are_files_excluded(files)

        assert is_excluded is True
        assert "docs/security/policy.md" in excluded_files
        assert len(excluded_files) == 1

    def test_are_files_excluded_none(self):
        """Test checking files with no exclusions."""
        manager = ExclusionManager(paths=["docs/*.md"])

        files = ["src/main.py", "tests/test.py"]

        is_excluded, excluded_files = manager.are_files_excluded(files)

        assert is_excluded is False
        assert excluded_files == []

    def test_is_author_excluded(self):
        """Test author exclusion."""
        manager = ExclusionManager(authors=["external-contributor", "blocked-user"])

        assert manager.is_author_excluded("external-contributor") is True
        assert manager.is_author_excluded("blocked-user") is True
        assert manager.is_author_excluded("regular-user") is False

    def test_is_title_excluded_regex(self):
        """Test title pattern exclusion with regex."""
        manager = ExclusionManager(title_patterns=["HOTFIX.*manual", "EMERGENCY.*"])

        assert manager.is_title_excluded("HOTFIX: manual intervention") is True
        assert manager.is_title_excluded("EMERGENCY: critical fix") is True
        assert manager.is_title_excluded("Feature: new thing") is False

    def test_is_title_excluded_case_insensitive(self):
        """Test title pattern exclusion is case insensitive."""
        manager = ExclusionManager(title_patterns=["hotfix.*"])

        assert manager.is_title_excluded("HOTFIX: fix") is True
        assert manager.is_title_excluded("hotfix: fix") is True
        assert manager.is_title_excluded("HotFix: fix") is True

    def test_is_pr_excluded_author(self):
        """Test PR exclusion by author."""
        manager = ExclusionManager(authors=["external"])

        is_excluded, reason = manager.is_pr_excluded(
            pr_number=123,
            title="Fix bug",
            author="external",
            files=["src/main.py"],
        )

        assert is_excluded is True
        assert "external" in reason

    def test_is_pr_excluded_title(self):
        """Test PR exclusion by title."""
        manager = ExclusionManager(title_patterns=["HOTFIX.*"])

        is_excluded, reason = manager.is_pr_excluded(
            pr_number=123,
            title="HOTFIX: critical",
            author="dev1",
            files=["src/main.py"],
        )

        assert is_excluded is True
        assert "title" in reason.lower()

    def test_is_pr_excluded_files(self):
        """Test PR exclusion by files."""
        manager = ExclusionManager(paths=["docs/security/*.md"])

        is_excluded, reason = manager.is_pr_excluded(
            pr_number=123,
            title="Fix bug",
            author="dev1",
            files=["src/main.py", "docs/security/policy.md"],
        )

        assert is_excluded is True
        assert "files" in reason.lower()

    def test_is_pr_not_excluded(self):
        """Test PR that is not excluded."""
        manager = ExclusionManager(
            paths=["docs/*.md"],
            authors=["external"],
            title_patterns=["HOTFIX.*"],
        )

        is_excluded, reason = manager.is_pr_excluded(
            pr_number=123,
            title="Feature: new thing",
            author="dev1",
            files=["src/main.py"],
        )

        assert is_excluded is False
        assert reason == ""

    def test_add_path_exclusion(self):
        """Test adding path exclusion."""
        manager = ExclusionManager()

        manager.add_path_exclusion("new/path/*")

        assert "new/path/*" in manager.exclusions.paths

    def test_add_author_exclusion(self):
        """Test adding author exclusion."""
        manager = ExclusionManager()

        manager.add_author_exclusion("new-user")

        assert "new-user" in manager.exclusions.authors

    def test_add_title_pattern(self):
        """Test adding title pattern exclusion."""
        manager = ExclusionManager()

        manager.add_title_pattern("PATTERN.*")

        assert "PATTERN.*" in manager.exclusions.title_patterns
        # Verify pattern was compiled
        assert len(manager._compiled_patterns) == 1

    def test_get_exclusions(self):
        """Test getting exclusion list."""
        manager = ExclusionManager(
            paths=["docs/*.md"],
            authors=["external"],
        )

        exclusions = manager.get_exclusions()

        assert isinstance(exclusions, ExclusionList)
        assert "docs/*.md" in exclusions.paths
        assert "external" in exclusions.authors

    def test_load_from_file(self):
        """Test loading exclusions from YAML file."""
        yaml_content = """
auto_approval:
  exclusions:
    paths:
      - "docs/security/*.md"
      - "infrastructure/**"
    authors:
      - "external"
    title_patterns:
      - "HOTFIX.*"
"""

        with patch("pathlib.Path.exists", return_value=True):
            with patch("builtins.open", mock_open(read_data=yaml_content)):
                manager = ExclusionManager(config_path="config.yaml")

        assert "docs/security/*.md" in manager.exclusions.paths
        assert "external" in manager.exclusions.authors
        assert "HOTFIX.*" in manager.exclusions.title_patterns

    def test_load_from_file_not_found(self):
        """Test loading exclusions when file doesn't exist."""
        manager = ExclusionManager(config_path="nonexistent.yaml")

        # Should not raise, just use defaults
        assert manager.exclusions.paths == []


class TestExclusionList:
    """Test cases for ExclusionList."""

    def test_to_dict(self):
        """Test ExclusionList serialization."""
        exclusion_list = ExclusionList(
            paths=["docs/*.md"],
            authors=["external"],
            title_patterns=["HOTFIX.*"],
        )

        data = exclusion_list.to_dict()

        assert data["paths"] == ["docs/*.md"]
        assert data["authors"] == ["external"]
        assert data["title_patterns"] == ["HOTFIX.*"]
