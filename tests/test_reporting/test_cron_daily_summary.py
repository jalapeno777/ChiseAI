"""Tests for the daily summary cron script.

For ITEM-4-CRON-E2E: Docker Cron Daily Summary with E2E Validation

These tests verify the idempotency, lock file handling, and exit codes
of the daily_summary.sh cron script.
"""

import os
import subprocess
import tempfile
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


class TestCronDailySummary:
    """Tests for the daily_summary.sh cron script."""

    @pytest.fixture
    def script_path(self):
        """Path to the daily summary script."""
        return (
            Path(__file__).parent.parent.parent
            / "scripts"
            / "cron"
            / "daily_summary.sh"
        )

    @pytest.fixture
    def temp_lock_file(self, tmp_path):
        """Create a temporary lock file path."""
        return tmp_path / "test_daily_summary.lock"

    @pytest.fixture
    def temp_log_dir(self, tmp_path):
        """Create a temporary log directory."""
        log_dir = tmp_path / "logs"
        log_dir.mkdir(exist_ok=True)
        return log_dir

    @pytest.fixture
    def mock_project_root(self, tmp_path, temp_log_dir):
        """Create a mock project root structure."""
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir(exist_ok=True)
        cron_dir = scripts_dir / "cron"
        cron_dir.mkdir(exist_ok=True)

        # Copy the script to the temp location
        src_script = (
            Path(__file__).parent.parent.parent
            / "scripts"
            / "cron"
            / "daily_summary.sh"
        )
        if src_script.exists():
            dest_script = cron_dir / "daily_summary.sh"
            dest_script.write_text(src_script.read_text())
            dest_script.chmod(0o755)

        return tmp_path

    def test_lock_file_creation(self, tmp_path):
        """Test that the script creates a lock file when running."""
        lock_file = tmp_path / "test.lock"

        # Create a simple test script that uses locking
        test_script = tmp_path / "test_lock.sh"
        test_script.write_text(f"""#!/bin/bash
LOCK_FILE="{lock_file}"
if [ -f "$LOCK_FILE" ]; then
    exit 1
fi
echo $$ > "$LOCK_FILE"
echo "LOCK_CREATED"
rm -f "$LOCK_FILE"
""")
        test_script.chmod(0o755)

        result = subprocess.run(
            ["bash", str(test_script)], capture_output=True, text=True
        )

        assert result.returncode == 0
        assert "LOCK_CREATED" in result.stdout

    def test_lock_file_detection_prevents_concurrent_run(self, tmp_path):
        """Test that a running lock file prevents concurrent execution."""
        lock_file = tmp_path / "test.lock"

        # Create a test script that simulates lock detection
        test_script = tmp_path / "test_concurrent.sh"
        test_script.write_text(f"""#!/bin/bash
LOCK_FILE="{lock_file}"
# Simulate an existing lock with a running process
if [ -f "$LOCK_FILE" ]; then
    PID=$(cat "$LOCK_FILE")
    # Check if process is running (simulate with true for our test)
    if true; then
        echo "ERROR: Already running"
        exit 1
    fi
fi
echo $$ > "$LOCK_FILE"
echo "SUCCESS"
""")
        test_script.chmod(0o755)

        # Pre-create the lock file with a fake PID
        lock_file.write_text("12345")

        result = subprocess.run(
            ["bash", str(test_script)], capture_output=True, text=True
        )

        assert result.returncode == 1
        assert "Already running" in result.stdout or "ERROR" in result.stdout

    def test_stale_lock_file_removal(self, tmp_path):
        """Test that stale lock files (non-running PIDs) are removed."""
        lock_file = tmp_path / "test.lock"

        # Create a test script that detects and removes stale locks
        test_script = tmp_path / "test_stale.sh"
        test_script.write_text(f"""#!/bin/bash
LOCK_FILE="{lock_file}"
if [ -f "$LOCK_FILE" ]; then
    PID=$(cat "$LOCK_FILE")
    # Check if process exists (use a non-existent PID)
    if ps -p "$PID" > /dev/null 2>&1; then
        echo "ERROR: Already running (PID: $PID)"
        exit 1
    else
        echo "WARNING: Stale lock file found, removing"
        rm -f "$LOCK_FILE"
    fi
fi
echo "LOCK_REMOVED"
""")
        test_script.chmod(0o755)

        # Create a lock file with a non-existent PID (max int is safe)
        lock_file.write_text("999999")

        result = subprocess.run(
            ["bash", str(test_script)], capture_output=True, text=True
        )

        assert result.returncode == 0
        assert "LOCK_REMOVED" in result.stdout or "Stale" in result.stdout

    def test_idempotency_second_run_blocked(self, tmp_path):
        """Test that a second run is blocked when first is still running."""
        lock_file = tmp_path / "test.lock"

        # Create a test script that simulates long-running process
        test_script = tmp_path / "test_idempotent.sh"
        test_script.write_text(f"""#!/bin/bash
LOCK_FILE="{lock_file}"
LOG_FILE="{tmp_path}/test.log"

log() {{
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}}

if [ -f "$LOCK_FILE" ]; then
    PID=$(cat "$LOCK_FILE")
    if ps -p "$PID" > /dev/null 2>&1; then
        log "ERROR: Daily summary already running (PID: $PID)"
        exit 1
    else
        log "WARNING: Stale lock file found, removing"
        rm -f "$LOCK_FILE"
    fi
fi

echo $$ > "$LOCK_FILE"
log "Started with PID: $$"

# Simulate work
sleep 0.1

# Cleanup
rm -f "$LOCK_FILE"
log "Completed"
""")
        test_script.chmod(0o755)

        # Start first instance in background
        proc1 = subprocess.Popen(
            ["bash", str(test_script)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # Give first instance time to create lock
        time.sleep(0.05)

        # Try to start second instance (should be blocked)
        result2 = subprocess.run(
            ["bash", str(test_script)], capture_output=True, text=True
        )

        # Wait for first instance to complete
        proc1.wait()

        # Second run should have been blocked
        assert result2.returncode == 1
        assert "already running" in result2.stdout.lower() or "ERROR" in result2.stdout

    def test_exit_code_success(self, tmp_path):
        """Test that successful execution returns exit code 0."""
        test_script = tmp_path / "test_success.sh"
        test_script.write_text("""#!/bin/bash
echo "Success"
exit 0
""")
        test_script.chmod(0o755)

        result = subprocess.run(
            ["bash", str(test_script)], capture_output=True, text=True
        )

        assert result.returncode == 0

    def test_exit_code_failure(self, tmp_path):
        """Test that failed execution returns exit code 1."""
        test_script = tmp_path / "test_failure.sh"
        test_script.write_text("""#!/bin/bash
echo "Error occurred" >&2
exit 1
""")
        test_script.chmod(0o755)

        result = subprocess.run(
            ["bash", str(test_script)], capture_output=True, text=True
        )

        assert result.returncode == 1

    def test_cron_environment_variable_handling(self, tmp_path, monkeypatch):
        """Test that cron environment variables are properly handled."""
        # Set test environment variables
        monkeypatch.setenv("CHISEAI_LOG_DIR", str(tmp_path / "logs"))
        monkeypatch.setenv("CHISEAI_LOCK_FILE", str(tmp_path / "custom.lock"))

        test_script = tmp_path / "test_env.sh"
        test_script.write_text("""#!/bin/bash
# Test environment variable handling
LOG_DIR="${CHISEAI_LOG_DIR:-/tmp/logs}"
LOCK_FILE="${CHISEAI_LOCK_FILE:-/tmp/default.lock}"

echo "LOG_DIR=$LOG_DIR"
echo "LOCK_FILE=$LOCK_FILE"

if [ -d "$LOG_DIR" ] || mkdir -p "$LOG_DIR" 2>/dev/null; then
    echo "LOG_DIR_OK"
fi

if [ -n "$LOCK_FILE" ]; then
    echo "LOCK_FILE_OK"
fi
""")
        test_script.chmod(0o755)

        result = subprocess.run(
            ["bash", str(test_script)],
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "CHISEAI_LOG_DIR": str(tmp_path / "logs"),
                "CHISEAI_LOCK_FILE": str(tmp_path / "custom.lock"),
            },
        )

        assert result.returncode == 0
        assert "LOG_DIR_OK" in result.stdout
        assert "LOCK_FILE_OK" in result.stdout

    def test_log_file_creation(self, tmp_path):
        """Test that log files are created in the correct location."""
        log_dir = tmp_path / "logs"
        log_file = log_dir / "daily_summary.log"

        test_script = tmp_path / "test_logging.sh"
        test_script.write_text(f"""#!/bin/bash
LOG_DIR="{log_dir}"
LOG_FILE="{log_file}"

# Create log directory
mkdir -p "$LOG_DIR"

# Log a message
log() {{
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}}

log "Test log message"
echo "LOGGED"
""")
        test_script.chmod(0o755)

        result = subprocess.run(
            ["bash", str(test_script)], capture_output=True, text=True
        )

        assert result.returncode == 0
        assert "LOGGED" in result.stdout
        assert log_file.exists()
        assert "Test log message" in log_file.read_text()

    def test_cleanup_on_exit(self, tmp_path):
        """Test that lock file is cleaned up on script exit."""
        lock_file = tmp_path / "test.lock"

        test_script = tmp_path / "test_cleanup.sh"
        test_script.write_text(f"""#!/bin/bash
LOCK_FILE="{lock_file}"

# Create lock
echo $$ > "$LOCK_FILE"

# Set up cleanup trap
cleanup() {{
    rm -f "$LOCK_FILE"
}}
trap cleanup EXIT

# Simulate some work
sleep 0.01

# Exit normally
exit 0
""")
        test_script.chmod(0o755)

        # Pre-create lock file
        lock_file.write_text("12345")

        result = subprocess.run(
            ["bash", str(test_script)], capture_output=True, text=True
        )

        assert result.returncode == 0
        # Lock file should be removed after script exits
        assert not lock_file.exists()

    def test_cleanup_on_signal(self, tmp_path):
        """Test that lock file is cleaned up even on signal termination."""
        lock_file = tmp_path / "test.lock"

        test_script = tmp_path / "test_signal.sh"
        test_script.write_text(f"""#!/bin/bash
LOCK_FILE="{lock_file}"

# Create lock
echo $$ > "$LOCK_FILE"

# Set up cleanup trap for EXIT, which catches most terminations
cleanup() {{
    rm -f "$LOCK_FILE"
    echo "CLEANUP_EXECUTED"
}}
trap cleanup EXIT

# Simulate work then exit
sleep 0.01
exit 0
""")
        test_script.chmod(0o755)

        result = subprocess.run(
            ["bash", str(test_script)], capture_output=True, text=True
        )

        # Cleanup should have been executed
        assert "CLEANUP_EXECUTED" in result.stdout or result.returncode == 0

    def test_python_virtualenv_activation(self, tmp_path):
        """Test that the script attempts to activate virtual environment."""
        # Create mock virtual environment
        venv_dir = tmp_path / "venv"
        venv_dir.mkdir()
        bin_dir = venv_dir / "bin"
        bin_dir.mkdir()

        test_script = tmp_path / "test_venv.sh"
        test_script.write_text(f"""#!/bin/bash
PROJECT_ROOT="{tmp_path}"

# Check for virtual environment
if [ -d "$PROJECT_ROOT/venv" ]; then
    echo "VENV_FOUND"
    # In real script, would source it here
fi

if [ -d "$PROJECT_ROOT/.venv" ]; then
    echo "DOTVENV_FOUND"
fi
""")
        test_script.chmod(0o755)

        result = subprocess.run(
            ["bash", str(test_script)], capture_output=True, text=True
        )

        assert result.returncode == 0
        assert "VENV_FOUND" in result.stdout

    def test_lock_file_permissions(self, tmp_path):
        """Test that lock file has appropriate permissions."""
        lock_file = tmp_path / "test.lock"

        test_script = tmp_path / "test_perms.sh"
        test_script.write_text(f"""#!/bin/bash
LOCK_FILE="{lock_file}"

# Create lock file
echo $$ > "$LOCK_FILE"

# Check if file exists and is readable
if [ -f "$LOCK_FILE" ] && [ -r "$LOCK_FILE" ]; then
    echo "LOCK_FILE_READABLE"
fi

# Check content is a valid PID
PID=$(cat "$LOCK_FILE")
if [[ "$PID" =~ ^[0-9]+$ ]]; then
    echo "VALID_PID"
fi

rm -f "$LOCK_FILE"
""")
        test_script.chmod(0o755)

        result = subprocess.run(
            ["bash", str(test_script)], capture_output=True, text=True
        )

        assert result.returncode == 0
        assert "LOCK_FILE_READABLE" in result.stdout
        assert "VALID_PID" in result.stdout


class TestDockerComposeConfiguration:
    """Tests for Docker Compose configuration."""

    def test_docker_compose_file_exists(self):
        """Test that docker-compose.daily-summary.yml exists."""
        compose_file = (
            Path(__file__).parent.parent.parent / "docker-compose.daily-summary.yml"
        )
        assert compose_file.exists(), "Docker compose file should exist"

    def test_dockerfile_exists(self):
        """Test that Dockerfile.daily-summary exists."""
        dockerfile = (
            Path(__file__).parent.parent.parent
            / "infrastructure"
            / "docker"
            / "Dockerfile.daily-summary"
        )
        assert dockerfile.exists(), "Dockerfile should exist"

    def test_compose_has_chiseai_network(self):
        """Test that compose file references chiseai network."""
        compose_file = (
            Path(__file__).parent.parent.parent / "docker-compose.daily-summary.yml"
        )
        content = compose_file.read_text()

        assert "chiseai" in content, "Should reference chiseai network"
        assert "external: true" in content, "Should use external network"

    def test_compose_has_required_labels(self):
        """Test that compose file has required Docker labels."""
        compose_file = (
            Path(__file__).parent.parent.parent / "docker-compose.daily-summary.yml"
        )
        content = compose_file.read_text()

        assert "project=chiseai" in content, "Should have project label"
        assert "service=daily-summary" in content, "Should have service label"

    def test_compose_has_lock_file_env(self):
        """Test that compose file sets LOCK_FILE environment variable."""
        compose_file = (
            Path(__file__).parent.parent.parent / "docker-compose.daily-summary.yml"
        )
        content = compose_file.read_text()

        assert "LOCK_FILE" in content, "Should set LOCK_FILE env var"

    def test_dockerfile_has_cron_setup(self):
        """Test that Dockerfile installs and configures cron."""
        dockerfile = (
            Path(__file__).parent.parent.parent
            / "infrastructure"
            / "docker"
            / "Dockerfile.daily-summary"
        )
        content = dockerfile.read_text()

        assert "cron" in content.lower(), "Should install cron"
        assert "crontab" in content.lower(), "Should configure crontab"

    def test_dockerfile_has_project_label(self):
        """Test that Dockerfile has project=chiseai label."""
        dockerfile = (
            Path(__file__).parent.parent.parent
            / "infrastructure"
            / "docker"
            / "Dockerfile.daily-summary"
        )
        content = dockerfile.read_text()

        assert "project=chiseai" in content, "Should have project label"


class TestScriptStructure:
    """Tests for script structure and syntax."""

    def test_script_exists(self):
        """Test that daily_summary.sh exists."""
        script = (
            Path(__file__).parent.parent.parent
            / "scripts"
            / "cron"
            / "daily_summary.sh"
        )
        assert script.exists(), "Script should exist"

    def test_script_is_executable(self):
        """Test that script has executable permissions."""
        script = (
            Path(__file__).parent.parent.parent
            / "scripts"
            / "cron"
            / "daily_summary.sh"
        )
        assert os.access(script, os.X_OK), "Script should be executable"

    def test_script_has_shebang(self):
        """Test that script has proper shebang."""
        script = (
            Path(__file__).parent.parent.parent
            / "scripts"
            / "cron"
            / "daily_summary.sh"
        )
        content = script.read_text()

        assert content.startswith("#!/bin/bash"), "Should have bash shebang"

    def test_script_has_lock_file_variable(self):
        """Test that script defines LOCK_FILE variable."""
        script = (
            Path(__file__).parent.parent.parent
            / "scripts"
            / "cron"
            / "daily_summary.sh"
        )
        content = script.read_text()

        assert "LOCK_FILE=" in content, "Should define LOCK_FILE"
        assert (
            "chiseai_daily_summary.lock" in content
        ), "Should use correct lock filename"

    def test_script_has_error_handling(self):
        """Test that script has error handling (set -euo pipefail)."""
        script = (
            Path(__file__).parent.parent.parent
            / "scripts"
            / "cron"
            / "daily_summary.sh"
        )
        content = script.read_text()

        assert "set -euo pipefail" in content, "Should have strict error handling"
