#!/usr/bin/env python3
"""Compatibility wrapper: CI root-cause triage.

Routes legacy `scripts/swarm/ci_root_cause.py` calls to the canonical
`scripts/ci/woodpecker_triage.py diagnose` command.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TRIAGE_SCRIPT = PROJECT_ROOT / "scripts" / "ci" / "woodpecker_triage.py"


def main() -> int:
    cmd = [sys.executable, str(TRIAGE_SCRIPT), "diagnose", *sys.argv[1:]]
    return subprocess.run(cmd, cwd=PROJECT_ROOT).returncode


if __name__ == "__main__":
    raise SystemExit(main())
