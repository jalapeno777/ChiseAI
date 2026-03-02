#!/usr/bin/env python3
"""Static Docker governance checks for compose files.

Checks:
- services with name starting `chiseai` must attach to `chiseai` network
- services with name starting `chiseai` must include label `project=chiseai`
"""

from __future__ import annotations

from pathlib import Path

import yaml

COMPOSE_GLOBS = [
    "docker-compose*.yml",
    "docker-compose*.yaml",
    "**/docker-compose*.yml",
    "**/docker-compose*.yaml",
]


def _collect_compose_files() -> list[Path]:
    root = Path(".")
    found: set[Path] = set()
    for pat in COMPOSE_GLOBS:
        for p in root.glob(pat):
            if p.is_file() and ".venv" not in p.parts:
                found.add(p)
    return sorted(found)


def _has_project_label(labels: object) -> bool:
    if isinstance(labels, list):
        return any(str(x).strip() == "project=chiseai" for x in labels)
    if isinstance(labels, dict):
        return str(labels.get("project", "")).strip() == "chiseai"
    return False


def main() -> int:
    issues: list[str] = []
    files = _collect_compose_files()

    for file in files:
        try:
            doc = yaml.safe_load(file.read_text(encoding="utf-8")) or {}
        except Exception as exc:  # noqa: BLE001
            issues.append(f"{file}: failed to parse YAML ({exc})")
            continue

        services = doc.get("services", {})
        if not isinstance(services, dict):
            continue

        for svc_name, svc in services.items():
            if not str(svc_name).startswith("chiseai"):
                continue
            if not isinstance(svc, dict):
                continue

            nets = svc.get("networks", [])
            net_names: set[str] = set()
            if isinstance(nets, (list, dict)):
                net_names = {str(x) for x in nets}

            if "chiseai" not in net_names:
                issues.append(f"{file}: service '{svc_name}' missing 'chiseai' network")

            if not _has_project_label(svc.get("labels")):
                issues.append(
                    f"{file}: service '{svc_name}' missing label 'project=chiseai'"
                )

    if issues:
        print("docker-governance: FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1

    print("docker-governance: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
