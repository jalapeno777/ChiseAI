#!/usr/bin/env python3
"""Fix datetime.now(timezone.utc) to datetime.now(timezone.utc) in scripts directory."""

import re
from pathlib import Path


def fix_file(filepath):
    """Fix a single file."""
    content = filepath.read_text()
    original = content

    # Check if file has datetime.now(timezone.utc)
    if (
        "datetime.now(timezone.utc)" not in content
        and '__import__("datetime").datetime.now(timezone.utc)' not in content
    ):
        return False

    # Replace datetime.now(timezone.utc) with datetime.now(timezone.utc)
    content = re.sub(r"datetime\.utcnow\(\)", "datetime.now(timezone.utc)", content)

    # Replace __import__("datetime").datetime.now(timezone.utc) with datetime.now(timezone.utc)
    content = re.sub(
        r'__import__\("datetime"\)\.datetime\.utcnow\(\)',
        "datetime.now(timezone.utc)",
        content,
    )

    # Add timezone import if needed
    if "datetime.now(timezone.utc)" in content:
        if "from datetime import timezone" not in content:
            # Check if we have "from datetime import datetime"
            if "from datetime import datetime" in content:
                content = content.replace(
                    "from datetime import datetime",
                    "from datetime import datetime, timezone",
                )
            elif "from datetime import (" in content:
                # Multi-line import
                content = re.sub(
                    r"from datetime import \(([^)]+)\)",
                    lambda m: f"from datetime import ({m.group(1).strip()},\n timezone)",
                    content,
                )

    if content != original:
        filepath.write_text(content)
        return True
    return False


def main():
    scripts_dir = Path("/tmp/worktrees/SIG-REM-008/scripts")
    fixed = []

    for py_file in scripts_dir.rglob("*.py"):
        try:
            if fix_file(py_file):
                fixed.append(str(py_file.relative_to(scripts_dir)))
                print(f"Fixed: {py_file}")
        except Exception as e:
            print(f"Error fixing {py_file}: {e}")

    print(f"\nFixed {len(fixed)} files")
    for f in fixed:
        print(f" - {f}")


if __name__ == "__main__":
    main()
