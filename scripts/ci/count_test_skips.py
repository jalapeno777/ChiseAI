#!/usr/bin/env python3
"""
Count pytest skip and xfail markers in tests/ directory.
Exits 0 if total <= 75, exits 1 if total > 75.
"""

import contextlib
import json
import subprocess
import sys
from pathlib import Path


def count_patterns(pattern: str) -> int:
    """Count occurrences of a regex pattern in tests/ directory."""
    try:
        result = subprocess.run(
            ["grep", "-r", "-c", pattern, "tests/", "--include=*.py"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent,
        )
        if result.returncode not in (0, 1):
            return 0

        total = 0
        for line in result.stdout.strip().split("\n"):
            if ":" in line:
                parts = line.rsplit(":", 1)
                with contextlib.suppress(ValueError):
                    total += int(parts[-1])
        return total
    except Exception:
        return 0


def main() -> int:
    skip_count = count_patterns(r"@pytest\.mark\.skip\b")
    skipif_count = count_patterns(r"@pytest\.mark\.skipif\b")
    xfail_count = count_patterns(r"@pytest\.mark\.xfail\b")

    total = skip_count + skipif_count + xfail_count

    output = {
        "total": total,
        "skip": skip_count,
        "skipif": skipif_count,
        "xfail": xfail_count,
    }

    print(json.dumps(output, indent=2))

    if total > 75:
        print(
            f"FAIL: Total skip/xfail count ({total}) exceeds threshold of 75",
            file=sys.stderr,
        )
        return 1

    print(f"PASS: Total skip/xfail count ({total}) is within threshold of 75")
    return 0


if __name__ == "__main__":
    sys.exit(main())
