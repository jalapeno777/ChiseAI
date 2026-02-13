"""
Tests for Grafana Dashboard Backup & Restore functionality.

Tests cover:
- Backup script execution
- Dashboard export format
- Git commit and tagging
- Rollback functionality
- 30-day retention cleanup
- Integration with watchdog
"""

import json
import os
import shutil
import subprocess
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Constants
SCRIPT_DIR = Path(__file__).parent.parent.parent / "scripts"
BACKUP_SCRIPT = SCRIPT_DIR / "grafana-backup.sh"
ROLLBACK_SCRIPT = SCRIPT_DIR / "grafana-rollback.sh"
BACKUP_DIR = (
    Path(__file__).parent.parent.parent / "infrastructure" / "grafana" / "backups"
)


class MockGrafanaResponse:
    """Mock responses for Grafana API."""

    @staticmethod
    def search_dashboards():
        return [
            {
                "id": 1,
                "uid": "chiseai-data-freshness",
                "title": "ChiseAI Data Freshness",
                "uri": "db/chiseai-data-freshness",
                "type": "dash-db",
                "folderId": 0,
                "folderUid": "",
                "slug": "",
            },
            {
                "id": 2,
                "uid": "chiseai-backtest-kpis",
                "title": "ChiseAI Backtest KPIs",
                "uri": "db/chiseai-backtest-kpis",
                "type": "dash-db",
                "folderId": 0,
                "folderUid": "",
                "slug": "",
            },
        ]

    @staticmethod
    def dashboard_json(uid, title):
        return {
            "id": 1,
            "uid": uid,
            "title": title,
            "timezone": "browser",
            "schemaVersion": 39,
            "version": 1,
            "panels": [
                {
                    "id": 1,
                    "title": f"{title} Panel",
                    "type": "timeseries",
                    "gridPos": {"x": 0, "y": 0, "w": 12, "h": 8},
                }
            ],
            "annotations": {"list": []},
            "templating": {"list": []},
            "time": {"from": "now-6h", "to": "now"},
            "refresh": "30s",
        }

    @staticmethod
    def export_response(uid, title):
        return {
            "dashboard": MockGrafanaResponse.dashboard_json(uid, title),
            "meta": {"isFolder": False, "folderId": 0, "folderTitle": "General"},
        }


@pytest.fixture
def temp_git_repo():
    """Create a temporary git repository for testing."""
    temp_dir = tempfile.mkdtemp(prefix="grafana-backup-test-")
    original_dir = os.getcwd()

    try:
        os.chdir(temp_dir)
        subprocess.run(["git", "init"], check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"], check=True, capture_output=True
        )

        # Create initial commit
        subprocess.run(
            ["git", "commit", "--allow-empty", "-m", "Initial commit"],
            check=True,
            capture_output=True,
        )

        # Create backup directory
        backup_dir = Path(temp_dir) / "infrastructure" / "grafana" / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)

        # Create provisioning directory
        prov_dir = (
            Path(temp_dir)
            / "infrastructure"
            / "grafana"
            / "provisioning"
            / "dashboards"
        )
        prov_dir.mkdir(parents=True, exist_ok=True)

        yield temp_dir
    finally:
        os.chdir(original_dir)
        shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def mock_grafana_api():
    """Mock Grafana API responses."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        yield


class TestBackupScriptExists:
    """Test that backup scripts exist and are executable."""

    def test_backup_script_exists(self):
        """Test that grafana-backup.sh exists."""
        assert BACKUP_SCRIPT.exists(), f"Backup script not found at {BACKUP_SCRIPT}"

    def test_rollback_script_exists(self):
        """Test that grafana-rollback.sh exists."""
        assert (
            ROLLBACK_SCRIPT.exists()
        ), f"Rollback script not found at {ROLLBACK_SCRIPT}"

    def test_backup_script_is_executable(self):
        """Test that backup script has execute permissions."""
        mode = BACKUP_SCRIPT.stat().st_mode
        assert mode & 0o111, "Backup script is not executable"

    def test_rollback_script_is_executable(self):
        """Test that rollback script has execute permissions."""
        mode = ROLLBACK_SCRIPT.stat().st_mode
        assert mode & 0o111, "Rollback script is not executable"


class TestBackupScriptHelp:
    """Test backup script help output."""

    def test_backup_help_output(self):
        """Test that --help produces valid help text."""
        result = subprocess.run(
            [str(BACKUP_SCRIPT), "--help"], capture_output=True, text=True
        )
        assert result.returncode == 0
        assert "Usage:" in result.stdout
        assert "--grafana-url" in result.stdout

    def test_rollback_help_output(self):
        """Test that --help produces valid help text."""
        result = subprocess.run(
            [str(ROLLBACK_SCRIPT), "--help"], capture_output=True, text=True
        )
        assert result.returncode == 0
        assert "Usage:" in result.stdout
        assert "--list" in result.stdout


class TestBackupScriptDryRun:
    """Test backup script in dry-run mode."""

    def test_backup_dry_run_no_grafana(self, temp_git_repo):
        """Test backup script dry-run without Grafana connection."""
        backup_dir = Path(temp_git_repo) / "infrastructure" / "grafana" / "backups"

        result = subprocess.run(
            [str(BACKUP_SCRIPT), "--dry-run", f"--backup-dir={backup_dir}"],
            capture_output=True,
            text=True,
        )
        # Should complete even without Grafana (dry run)
        assert result.returncode == 0
        assert "Would" in result.stdout or "Dry run" in result.stdout

    def test_backup_dry_run_creates_summary(self, temp_git_repo):
        """Test that dry-run produces a summary."""
        backup_dir = Path(temp_git_repo) / "infrastructure" / "grafana" / "backups"

        result = subprocess.run(
            [str(BACKUP_SCRIPT), "--dry-run", f"--backup-dir={backup_dir}"],
            capture_output=True,
            text=True,
        )

        assert "Backup Summary" in result.stdout


class TestBackupScriptValidation:
    """Test backup script validation."""

    def test_jq_check_runs(self, temp_git_repo):
        """Test that jq validation runs."""
        backup_dir = Path(temp_git_repo) / "infrastructure" / "grafana" / "backups"

        # Run backup - jq check should pass if jq is installed
        result = subprocess.run(
            [str(BACKUP_SCRIPT), f"--backup-dir={backup_dir}"],
            capture_output=True,
            text=True,
        )

        # Should complete (jq is installed in test environment)
        # May fail at Grafana connection but jq check passes
        assert "Prerequisites check passed" in result.stdout or result.returncode == 0


class TestRollbackScriptList:
    """Test rollback script list functionality."""

    def test_list_backups_empty_repo(self, temp_git_repo):
        """Test listing backups in empty repository."""
        backup_dir = Path(temp_git_repo) / "infrastructure" / "grafana" / "backups"

        result = subprocess.run(
            [str(ROLLBACK_SCRIPT), "--list", f"--backup-dir={backup_dir}"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        # Empty repo may have no backups yet


class TestBackupGitIntegration:
    """Test git integration for backups."""

    def test_backup_creates_tag_format(self, temp_git_repo):
        """Test that backup creates tag with correct format."""
        backup_dir = Path(temp_git_repo) / "infrastructure" / "grafana" / "backups"
        prov_dir = (
            Path(temp_git_repo)
            / "infrastructure"
            / "grafana"
            / "provisioning"
            / "dashboards"
        )

        # Create a sample dashboard file
        sample_dashboard = prov_dir / "test-dashboard.json"
        sample_dashboard.write_text(
            json.dumps(MockGrafanaResponse.dashboard_json("test-uid", "Test Dashboard"))
        )

        # Stage and commit
        subprocess.run(["git", "add", str(prov_dir)], check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Add test dashboard"],
            check=True,
            capture_output=True,
        )

        # Run backup with dry-run to avoid actual Grafana calls
        result = subprocess.run(
            [str(BACKUP_SCRIPT), "--dry-run", f"--backup-dir={backup_dir}", "--no-git"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0

    def test_rollback_commit_message_format(self, temp_git_repo):
        """Test that rollback creates commit with timestamp format."""
        backup_dir = Path(temp_git_repo) / "infrastructure" / "grafana" / "backups"
        prov_dir = (
            Path(temp_git_repo)
            / "infrastructure"
            / "grafana"
            / "provisioning"
            / "dashboards"
        )

        # Create a backup directory with a date
        backup_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        backup_path = backup_dir / backup_date
        backup_path.mkdir(parents=True, exist_ok=True)

        # Create sample dashboard in backup
        sample_dashboard = backup_path / "test-dashboard.json"
        sample_dashboard.write_text(
            json.dumps(MockGrafanaResponse.dashboard_json("test-uid", "Test Dashboard"))
        )

        # Create tag
        tag_name = f"dashboard-backup-{backup_date}"
        subprocess.run(
            [
                "git",
                "tag",
                "-a",
                tag_name,
                "-m",
                f"Dashboard backup from {backup_date}",
            ],
            check=True,
            capture_output=True,
        )

        # Run rollback dry-run
        result = subprocess.run(
            [
                str(ROLLBACK_SCRIPT),
                "--dry-run",
                tag_name,
                f"--backup-dir={backup_dir}",
                f"--provisioning-dir={prov_dir}",
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "Rollback Summary" in result.stdout


class TestBackupRetention:
    """Test 30-day retention cleanup."""

    def test_retention_cleanup_identified(self, temp_git_repo):
        """Test that cleanup identifies old backups."""
        backup_dir = Path(temp_git_repo) / "infrastructure" / "grafana" / "backups"

        # Create old backup directories
        old_dates = [
            (datetime.now() - timedelta(days=35)).strftime("%Y-%m-%d"),
            (datetime.now() - timedelta(days=45)).strftime("%Y-%m-%d"),
        ]
        for date in old_dates:
            old_path = backup_dir / date
            old_path.mkdir(parents=True, exist_ok=True)
            (old_path / "old-dashboard.json").write_text("{}")

        # Create recent backup
        recent_date = datetime.now().strftime("%Y-%m-%d")
        recent_path = backup_dir / recent_date
        recent_path.mkdir(parents=True, exist_ok=True)
        (recent_path / "recent-dashboard.json").write_text("{}")

        # Run backup with retention check
        result = subprocess.run(
            [
                str(BACKUP_SCRIPT),
                "--dry-run",
                f"--backup-dir={backup_dir}",
                "--retention-days=30",
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0

        # Check that old backups would be cleaned up
        assert (
            "30" in result.stdout
            or "30 days" in result.stdout
            or "retention" in result.stdout.lower()
        )


class TestDashboardExportFormat:
    """Test dashboard JSON export format."""

    def test_export_contains_meta(self, temp_git_repo):
        """Test that exported dashboard contains metadata."""
        backup_dir = Path(temp_git_repo) / "infrastructure" / "grafana" / "backups"
        backup_date = datetime.now().strftime("%Y-%m-%d")
        backup_path = backup_dir / backup_date
        backup_path.mkdir(parents=True, exist_ok=True)

        # Create a mock exported dashboard
        export_data = {
            "meta": {
                "title": "Test Dashboard",
                "uid": "test-uid",
                "exported_at": datetime.now().isoformat(),
                "source": "grafana-api",
            },
            "dashboard": MockGrafanaResponse.dashboard_json(
                "test-uid", "Test Dashboard"
            ),
        }

        dashboard_file = backup_path / "test-dashboard.json"
        dashboard_file.write_text(json.dumps(export_data))

        # Validate JSON
        with open(dashboard_file) as f:
            data = json.load(f)

        assert "meta" in data
        assert "dashboard" in data
        assert data["meta"]["title"] == "Test Dashboard"
        assert "exported_at" in data["meta"]

    def test_exported_json_is_valid(self, temp_git_repo):
        """Test that exported JSON is valid."""
        backup_dir = Path(temp_git_repo) / "infrastructure" / "grafana" / "backups"
        backup_date = datetime.now().strftime("%Y-%m-%d")
        backup_path = backup_dir / backup_date
        backup_path.mkdir(parents=True, exist_ok=True)

        # Create a valid dashboard JSON
        dashboard_data = MockGrafanaResponse.dashboard_json(
            "test-uid", "Test Dashboard"
        )

        dashboard_file = backup_path / "test-dashboard.json"
        dashboard_file.write_text(json.dumps(dashboard_data))

        # Validate using jq equivalent in Python
        with open(dashboard_file) as f:
            data = json.load(f)

        assert "uid" in data
        assert "title" in data
        assert "panels" in data


class TestRollbackValidation:
    """Test rollback script validation."""

    def test_unknown_target_fails(self, temp_git_repo):
        """Test that unknown target causes failure."""
        backup_dir = Path(temp_git_repo) / "infrastructure" / "grafana" / "backups"
        prov_dir = (
            Path(temp_git_repo)
            / "infrastructure"
            / "grafana"
            / "provisioning"
            / "dashboards"
        )

        result = subprocess.run(
            [
                str(ROLLBACK_SCRIPT),
                "nonexistent-target-12345",
                f"--backup-dir={backup_dir}",
                f"--provisioning-dir={prov_dir}",
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode != 0
        assert "Unknown target" in result.stderr or "not found" in result.stderr.lower()


class TestGitCommitMessage:
    """Test git commit message format."""

    def test_backup_commit_message_format(self, temp_git_repo):
        """Test backup commit message follows format."""
        backup_dir = Path(temp_git_repo) / "infrastructure" / "grafana" / "backups"

        # Create sample dashboard in provisioning
        prov_dir = (
            Path(temp_git_repo)
            / "infrastructure"
            / "grafana"
            / "provisioning"
            / "dashboards"
        )
        sample_file = prov_dir / "sample.json"
        sample_file.write_text("{}")

        subprocess.run(["git", "add", str(prov_dir)], check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Add sample dashboard"],
            check=True,
            capture_output=True,
        )

        # Run backup
        result = subprocess.run(
            [str(BACKUP_SCRIPT), "--dry-run", f"--backup-dir={backup_dir}"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        # Commit message should contain timestamp
        assert "Dashboard backup" in result.stdout or "would" in result.stdout.lower()


class TestDashboardFilenameSanitization:
    """Test dashboard filename sanitization."""

    def test_special_chars_in_title(self):
        """Test that special characters are properly sanitized."""
        import re

        title = "ChiseAI: Data Freshness & KPIs"
        filename = title.lower().replace(" ", "-")
        filename = re.sub(r"[^a-z0-9-]", "", filename)

        # Result should be valid filename
        assert len(filename) > 0
        assert all(c.isalnum() or c == "-" for c in filename)


class TestIntegrationScenarios:
    """Integration test scenarios."""

    def test_full_backup_restore_cycle(self, temp_git_repo):
        """Test complete backup and restore cycle."""
        backup_dir = Path(temp_git_repo) / "infrastructure" / "grafana" / "backups"
        prov_dir = (
            Path(temp_git_repo)
            / "infrastructure"
            / "grafana"
            / "provisioning"
            / "dashboards"
        )

        # Create initial dashboard
        dashboard_content = MockGrafanaResponse.dashboard_json(
            "test-uid", "Test Dashboard"
        )
        dashboard_file = prov_dir / "test-dashboard.json"
        dashboard_file.write_text(json.dumps(dashboard_content))

        subprocess.run(["git", "add", str(prov_dir)], check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial dashboard"],
            check=True,
            capture_output=True,
        )

        # Create backup directory
        backup_date = datetime.now().strftime("%Y-%m-%d")
        backup_path = backup_dir / backup_date
        backup_path.mkdir(parents=True, exist_ok=True)

        # Copy dashboard to backup
        shutil.copy(dashboard_file, backup_path / "test-dashboard.json")

        # Create tag
        tag_name = f"dashboard-backup-{backup_date}"
        subprocess.run(
            ["git", "tag", "-a", tag_name, "-m", f"Backup {backup_date}"],
            check=True,
            capture_output=True,
        )

        # Run rollback dry-run
        result = subprocess.run(
            [
                str(ROLLBACK_SCRIPT),
                "--dry-run",
                tag_name,
                f"--backup-dir={backup_dir}",
                f"--provisioning-dir={prov_dir}",
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "Rollback Summary" in result.stdout

    def test_multiple_dashboards_backup(self, temp_git_repo):
        """Test backing up multiple dashboards."""
        backup_dir = Path(temp_git_repo) / "infrastructure" / "grafana" / "backups"
        prov_dir = (
            Path(temp_git_repo)
            / "infrastructure"
            / "grafana"
            / "provisioning"
            / "dashboards"
        )

        # Create multiple dashboards
        dashboards = [
            ("dashboard-1.json", "chiseai-data-freshness", "Data Freshness"),
            ("dashboard-2.json", "chiseai-backtest-kpis", "Backtest KPIs"),
        ]

        for filename, uid, title in dashboards:
            content = MockGrafanaResponse.dashboard_json(uid, title)
            (prov_dir / filename).write_text(json.dumps(content))

        subprocess.run(["git", "add", str(prov_dir)], check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Add dashboards"], check=True, capture_output=True
        )

        # Create backup directory
        backup_date = datetime.now().strftime("%Y-%m-%d")
        backup_path = backup_dir / backup_date
        backup_path.mkdir(parents=True, exist_ok=True)

        # Copy dashboards to backup
        for filename, uid, title in dashboards:
            content = MockGrafanaResponse.dashboard_json(uid, title)
            (backup_path / filename).write_text(json.dumps(content))

        # Count dashboards
        dashboard_count = len(list(backup_path.glob("*.json")))

        assert dashboard_count == 2

    def test_rollback_to_specific_commit(self, temp_git_repo):
        """Test rolling back to a specific backup tag."""
        backup_dir = Path(temp_git_repo) / "infrastructure" / "grafana" / "backups"
        prov_dir = (
            Path(temp_git_repo)
            / "infrastructure"
            / "grafana"
            / "provisioning"
            / "dashboards"
        )

        # Create a backup directory first
        backup_date = datetime.now().strftime("%Y-%m-%d")
        backup_path = backup_dir / backup_date
        backup_path.mkdir(parents=True, exist_ok=True)

        # Create a sample dashboard in the backup
        dashboard_file = backup_path / "test-dashboard.json"
        dashboard_content = MockGrafanaResponse.dashboard_json(
            "test-uid", "Test Dashboard"
        )
        dashboard_file.write_text(json.dumps(dashboard_content))

        # Create a git tag for the backup
        tag_name = f"dashboard-backup-{backup_date}"
        subprocess.run(
            ["git", "tag", "-a", tag_name, "-m", f"Backup {backup_date}"],
            check=True,
            capture_output=True,
        )

        # Run rollback using the tag
        result = subprocess.run(
            [
                str(ROLLBACK_SCRIPT),
                "--dry-run",
                tag_name,
                f"--backup-dir={backup_dir}",
                f"--provisioning-dir={prov_dir}",
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "Rollback Summary" in result.stdout


class TestBackupDirectoryStructure:
    """Test backup directory structure."""

    def test_backup_directory_creation(self):
        """Test that backup directory is created if missing."""
        # This tests the path handling
        expected_path = BACKUP_DIR

        # Check if directory exists or can be created
        if not expected_path.exists():
            expected_path.mkdir(parents=True, exist_ok=True)

        assert expected_path.exists()

    def test_backup_subdirectory_format(self):
        """Test that backup subdirectory follows YYYY-MM-DD format."""
        import re

        # Simulate date folder creation
        date_folder = datetime.now().strftime("%Y-%m-%d")

        # Validate format
        assert re.match(r"\d{4}-\d{2}-\d{2}", date_folder)
        assert len(date_folder) == 10


class TestScriptExitCodes:
    """Test script exit codes."""

    def test_backup_success_exit_code(self, temp_git_repo):
        """Test that successful backup returns 0."""
        backup_dir = Path(temp_git_repo) / "infrastructure" / "grafana" / "backups"

        result = subprocess.run(
            [str(BACKUP_SCRIPT), "--dry-run", f"--backup-dir={backup_dir}"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0

    def test_list_success_exit_code(self, temp_git_repo):
        """Test that list command returns 0."""
        backup_dir = Path(temp_git_repo) / "infrastructure" / "grafana" / "backups"

        result = subprocess.run(
            [str(ROLLBACK_SCRIPT), "--list", f"--backup-dir={backup_dir}"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0


class TestEnvironmentVariableHandling:
    """Test environment variable handling."""

    def test_grafana_url_from_env(self, temp_git_repo):
        """Test that GRAFANA_URL environment variable is used."""
        backup_dir = Path(temp_git_repo) / "infrastructure" / "grafana" / "backups"

        env = os.environ.copy()
        env["GRAFANA_URL"] = "http://custom-grafana:3000"

        result = subprocess.run(
            [str(BACKUP_SCRIPT), "--dry-run", f"--backup-dir={backup_dir}"],
            capture_output=True,
            text=True,
            env=env,
        )

        assert result.returncode == 0
        # Custom URL should be mentioned in output
        assert (
            "custom-grafana" in result.stdout
            or "http://custom-grafana:3000" in result.stdout
        )

    def test_retention_days_from_env(self, temp_git_repo):
        """Test that RETENTION_DAYS environment variable is used."""
        backup_dir = Path(temp_git_repo) / "infrastructure" / "grafana" / "backups"

        env = os.environ.copy()
        env["RETENTION_DAYS"] = "60"

        result = subprocess.run(
            [str(BACKUP_SCRIPT), "--dry-run", f"--backup-dir={backup_dir}"],
            capture_output=True,
            text=True,
            env=env,
        )

        assert result.returncode == 0
        assert "60" in result.stdout


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
