#!/usr/bin/env python3
"""Validate docs/metrics/skill-stacks.yaml structure and references."""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml


def load_yaml(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"stack registry not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("stack registry must be a YAML mapping")
    return data


def discover_skills(skills_dir: Path) -> set[str]:
    if not skills_dir.exists():
        return set()
    found: set[str] = set()
    for child in skills_dir.iterdir():
        if child.is_dir() and (child / "SKILL.md").exists():
            found.add(child.name)
    return found


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate skill stack registry")
    ap.add_argument("--stack-map-path", default="docs/metrics/skill-stacks.yaml")
    ap.add_argument("--skills-dir", default=".opencode/skills")
    ap.add_argument(
        "--strict-missing-skills",
        action="store_true",
        help="fail when stack references unknown skills",
    )
    args = ap.parse_args()

    errors: list[str] = []
    warnings: list[str] = []

    try:
        data = load_yaml(Path(args.stack_map_path))
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1

    stacks = data.get("stacks")
    task_class_stacks = data.get("task_class_stacks")
    if not isinstance(stacks, dict):
        errors.append("`stacks` must be a mapping")
        stacks = {}
    if not isinstance(task_class_stacks, dict):
        errors.append("`task_class_stacks` must be a mapping")
        task_class_stacks = {}

    available_skills = discover_skills(Path(args.skills_dir))

    for stack_name, stack in stacks.items():
        if not isinstance(stack, dict):
            errors.append(f"stack '{stack_name}' must be a mapping")
            continue
        skills = stack.get("skills")
        if not isinstance(skills, list) or not skills:
            errors.append(f"stack '{stack_name}' must include a non-empty skills list")
            continue
        for skill in skills:
            skill_name = str(skill).strip()
            if not skill_name:
                errors.append(f"stack '{stack_name}' contains empty skill name")
                continue
            if available_skills and skill_name not in available_skills:
                msg = f"stack '{stack_name}' references unknown skill '{skill_name}'"
                if args.strict_missing_skills:
                    errors.append(msg)
                else:
                    warnings.append(msg)

    for task_class, refs in task_class_stacks.items():
        if not isinstance(refs, list):
            errors.append(f"task_class_stacks['{task_class}'] must be a list")
            continue
        for stack_name in refs:
            sname = str(stack_name).strip()
            if not sname:
                errors.append(
                    f"task_class_stacks['{task_class}'] includes empty stack name"
                )
                continue
            if sname not in stacks:
                errors.append(
                    f"task_class_stacks['{task_class}'] references missing stack '{sname}'"
                )

    if warnings:
        for w in warnings:
            print(f"WARNING: {w}")
    if errors:
        for e in errors:
            print(f"ERROR: {e}")
        return 1

    print("OK: skill stack registry is valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
