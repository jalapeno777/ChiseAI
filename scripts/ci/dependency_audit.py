#!/usr/bin/env python3
"""Run pip-audit against project dependencies from pyproject.toml."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]


def main() -> int:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    deps = pyproject.get("project", {}).get("dependencies", [])
    if not isinstance(deps, list) or not deps:
        print("dependency-audit: no dependencies found; skipping")
        return 0

    cleaned: list[str] = []
    for dep in deps:
        d = str(dep).strip()
        if not d or d.startswith("-e "):
            continue
        cleaned.append(d)

    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as tmp:
        for dep in cleaned:
            tmp.write(dep + "\n")
        req_path = tmp.name

    cmd = [
        sys.executable,
        "-m",
        "pip_audit",
        "-r",
        req_path,
        "--progress-spinner",
        "off",
        "--descenders",
        "false",
    ]
    proc = subprocess.run(cmd, check=False, timeout=60)
    if proc.returncode == 0:
        print("dependency-audit: OK")
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
