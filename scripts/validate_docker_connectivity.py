#!/usr/bin/env python3
"""Compatibility wrapper for Docker connectivity validation.

Delegates to the maintained validator:
`scripts/validation/validate_scheduler_docker_config.py`.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VALIDATOR = (
    PROJECT_ROOT / "scripts" / "validation" / "validate_scheduler_docker_config.py"
)


def main() -> int:
    cmd = [sys.executable, str(VALIDATOR), *sys.argv[1:]]
    return subprocess.run(cmd, cwd=PROJECT_ROOT).returncode


if __name__ == "__main__":
    raise SystemExit(main())
