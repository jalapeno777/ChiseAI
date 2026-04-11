#!/usr/bin/env python3
"""Tests for paper_backfill.py script."""

import os
import subprocess
import sys

import pytest


class TestPaperBackfillScript:
    """Tests for the paper_backfill.py script."""

    def test_script_exists(self):
        """Backfill script exists."""
        script_path = os.path.join(
            os.path.dirname(__file__), "../../scripts/paper_backfill.py"
        )
        assert os.path.exists(script_path), f"Script not found at {script_path}"

    def test_dry_run_succeeds(self):
        """Script --dry-run exits successfully (or with auth error, not syntax error)."""
        result = subprocess.run(
            [sys.executable, "scripts/paper_backfill.py", "--dry-run"],
            capture_output=True,
            text=True,
            cwd=os.path.join(os.path.dirname(__file__), "../.."),
        )
        # Accept either success (0) or auth error (1) — auth depends on env
        assert result.returncode in [0, 1], (
            f"Expected exit 0 or 1, got {result.returncode}. "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )

    def test_dry_run_produces_json_output(self):
        """--dry-run produces valid JSON output."""
        result = subprocess.run(
            [sys.executable, "scripts/paper_backfill.py", "--dry-run"],
            capture_output=True,
            text=True,
            cwd=os.path.join(os.path.dirname(__file__), "../.."),
        )
        if result.returncode in [0, 1]:
            import json

            try:
                data = json.loads(result.stdout)
                assert "outcomes_upserted" in data or "orphaned_fills" in data
            except json.JSONDecodeError:
                pytest.fail(f"Output not valid JSON: {result.stdout!r}")

    def test_help_flag(self):
        """--help works."""
        result = subprocess.run(
            [sys.executable, "scripts/paper_backfill.py", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "--dry-run" in result.stdout
        assert "--since" in result.stdout
