from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "validate_pr_title.py"
SPEC = importlib.util.spec_from_file_location("validate_pr_title", MODULE_PATH)
assert SPEC and SPEC.loader
validate_pr_title = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = validate_pr_title
SPEC.loader.exec_module(validate_pr_title)


def test_contains_valid_story_id_accepts_legacy_and_date_suffix_ids() -> None:
    assert validate_pr_title._contains_valid_story_id("ST-NS-001 improve parser")
    assert validate_pr_title._contains_valid_story_id(
        "ST-CI-HEALTH-20260215F merge reconcile docs"
    )
    assert validate_pr_title._contains_valid_story_id("CH-CI-103 ci tweak")


def test_contains_valid_story_id_rejects_no_digit_tokens() -> None:
    assert not validate_pr_title._contains_valid_story_id("ST-CI-HEALTH improve docs")


def test_non_pr_build_skips() -> None:
    env: dict[str, str] = {}
    assert not validate_pr_title._is_pr_build(env)
