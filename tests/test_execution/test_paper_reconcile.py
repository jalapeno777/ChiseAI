#!/usr/bin/env python3
"""Tests for paper_reconcile.py script."""

import os
import subprocess
import sys

import pytest


class TestPaperReconcileScript:
    """Tests for the paper_reconcile.py script."""

    def test_script_exists(self):
        """Reconcile script exists."""
        script_path = os.path.join(
            os.path.dirname(__file__), "../../scripts/paper_reconcile.py"
        )
        assert os.path.exists(script_path), f"Script not found at {script_path}"

    def test_help_flag(self):
        """--help works."""
        result = subprocess.run(
            [sys.executable, "scripts/paper_reconcile.py", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "--json" in result.stdout
        assert "--since" in result.stdout

    def test_reconcile_runs(self):
        """Script runs and produces output."""
        result = subprocess.run(
            [sys.executable, "scripts/paper_reconcile.py"],
            capture_output=True,
            text=True,
            cwd=os.path.join(os.path.dirname(__file__), "../.."),
        )
        # Accept: 0=clean, 1=divergence, 2=error
        assert result.returncode in [
            0,
            1,
            2,
        ], f"Unexpected exit code {result.returncode}. stderr={result.stderr!r}"

    def test_json_output_valid(self):
        """--json produces valid JSON."""
        result = subprocess.run(
            [sys.executable, "scripts/paper_reconcile.py", "--json"],
            capture_output=True,
            text=True,
            cwd=os.path.join(os.path.dirname(__file__), "../.."),
        )
        if result.returncode in [0, 1, 2]:
            import json

            try:
                data = json.loads(result.stdout)
                assert "redis_counts" in data or "error" in data
            except json.JSONDecodeError:
                pytest.fail(f"Output not valid JSON: {result.stdout!r}")

    def test_exit_codes_documented(self):
        """Verify exit codes are 0=clean, 1=divergence, 2=error."""
        result = subprocess.run(
            [sys.executable, "scripts/paper_reconcile.py"],
            capture_output=True,
            text=True,
            cwd=os.path.join(os.path.dirname(__file__), "../.."),
        )
        # The script should either exit 0 (clean) or 1 (divergence)
        assert result.returncode in [0, 1], f"Expected 0 or 1, got {result.returncode}"
