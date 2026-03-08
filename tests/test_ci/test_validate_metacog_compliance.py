from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "validation"
    / "validate_metacog_compliance.py"
)
SPEC = importlib.util.spec_from_file_location("validate_metacog_compliance", MODULE_PATH)
assert SPEC and SPEC.loader
validate_metacog_compliance = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = validate_metacog_compliance
SPEC.loader.exec_module(validate_metacog_compliance)


def _write_iterlog(path: Path, story_id: str, status: str, body: str) -> None:
    text = f"""---
story_id: {story_id}
status: {status}
---

{body}
"""
    path.write_text(text, encoding="utf-8")


def test_strict_mode_fails_when_required_sections_missing(
    tmp_path: Path, monkeypatch
) -> None:
    iterlog_dir = tmp_path / "docs" / "tempmemories"
    iterlog_dir.mkdir(parents=True)
    _write_iterlog(
        iterlog_dir / "iterlog-CH-TEST-001.md",
        "CH-TEST-001",
        "completed",
        "## Decisions\n- done",
    )

    monkeypatch.setattr(validate_metacog_compliance, "ITERLOG_DIR", iterlog_dir)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "validate_metacog_compliance.py",
            "--story-id",
            "CH-TEST-001",
            "--strict",
        ],
    )
    assert validate_metacog_compliance.main() == 1


def test_story_id_filter_is_exact_and_does_not_match_prefix(
    tmp_path: Path, monkeypatch
) -> None:
    iterlog_dir = tmp_path / "docs" / "tempmemories"
    iterlog_dir.mkdir(parents=True)

    good_body = """
## Metacognitive Predictions
predicted_outcome: improve reliability
predicted_risks: [regression]
confidence: 0.8
verification_plan: run precommit
expected_metrics: [reopen_rate]

## Metacognitive Outcomes
actual_outcome: improved reliability
actual_metrics: {reopen_rate: 0.04}
wins: [reduced regressions]
misses: []
new_prevention_rules: [rule-1]

## Metacognitive Calibration
predicted_confidence: 0.8
observed_result: success
calibration_delta: 0.1
confidence_adjustment_recommendation: no_change
"""
    _write_iterlog(
        iterlog_dir / "iterlog-ST-1.md",
        "ST-1",
        "completed",
        good_body,
    )
    _write_iterlog(
        iterlog_dir / "iterlog-ST-10.md",
        "ST-10",
        "completed",
        "## Metacognitive Predictions\npredicted_outcome: nope",
    )

    monkeypatch.setattr(validate_metacog_compliance, "ITERLOG_DIR", iterlog_dir)
    monkeypatch.setattr(
        sys,
        "argv",
        ["validate_metacog_compliance.py", "--story-id", "ST-1", "--strict"],
    )
    assert validate_metacog_compliance.main() == 0


def test_required_key_value_fields_are_enforced(
    tmp_path: Path, monkeypatch
) -> None:
    iterlog_dir = tmp_path / "docs" / "tempmemories"
    iterlog_dir.mkdir(parents=True)

    # Missing expected_metrics and new_prevention_rules should fail strict mode.
    body = """
## Metacognitive Predictions
predicted_outcome: improve throughput
predicted_risks: [merge_conflict]
confidence: 0.7
verification_plan: run ci

## Metacognitive Outcomes
actual_outcome: neutral
actual_metrics: {cycle_time_hours: 5}
wins: []
misses: [underestimated dependency]

## Metacognitive Calibration
predicted_confidence: 0.7
observed_result: partial
calibration_delta: 0.2
confidence_adjustment_recommendation: lower_confidence
"""
    _write_iterlog(
        iterlog_dir / "iterlog-CH-META-001.md",
        "CH-META-001",
        "completed",
        body,
    )

    monkeypatch.setattr(validate_metacog_compliance, "ITERLOG_DIR", iterlog_dir)
    monkeypatch.setattr(
        sys,
        "argv",
        ["validate_metacog_compliance.py", "--story-id", "CH-META-001", "--strict"],
    )
    assert validate_metacog_compliance.main() == 1


def test_invalid_story_id_fails_in_strict_mode(
    tmp_path: Path, monkeypatch
) -> None:
    iterlog_dir = tmp_path / "docs" / "tempmemories"
    iterlog_dir.mkdir(parents=True)
    body = """
## Metacognitive Predictions
predicted_outcome: improve reliability
predicted_risks: [regression]
confidence: 0.8
verification_plan: run precommit
expected_metrics: [reopen_rate <= 0.05]

## Metacognitive Outcomes
actual_outcome: improved reliability
actual_metrics: {reopen_rate: 0.04}
wins: [reduced regressions]
misses: []
new_prevention_rules: [rule-1]

## Metacognitive Calibration
predicted_confidence: 0.8
observed_result: success
calibration_delta: 0.1
confidence_adjustment_recommendation: no_change
"""
    _write_iterlog(
        iterlog_dir / "iterlog-BAD-STORY.md",
        "BAD-STORY",
        "completed",
        body,
    )

    monkeypatch.setattr(validate_metacog_compliance, "ITERLOG_DIR", iterlog_dir)
    monkeypatch.setattr(
        sys,
        "argv",
        ["validate_metacog_compliance.py", "--story-id", "BAD-STORY", "--strict"],
    )
    assert validate_metacog_compliance.main() == 1


def test_semantic_bounds_are_enforced(
    tmp_path: Path, monkeypatch
) -> None:
    iterlog_dir = tmp_path / "docs" / "tempmemories"
    iterlog_dir.mkdir(parents=True)
    body = """
## Metacognitive Predictions
predicted_outcome: improve reliability
predicted_risks: [regression]
confidence: 1.7
verification_plan: run precommit
expected_metrics: [reopen_rate <= 0.05]

## Metacognitive Outcomes
actual_outcome: improved reliability
actual_metrics: {reopen_rate: 0.04}
wins: [reduced regressions]
misses: []
new_prevention_rules: [rule-1]

## Metacognitive Calibration
predicted_confidence: 0.8
observed_result: maybe
calibration_delta: 0.1
confidence_adjustment_recommendation: no_change
"""
    _write_iterlog(
        iterlog_dir / "iterlog-CH-META-002.md",
        "CH-META-002",
        "completed",
        body,
    )

    monkeypatch.setattr(validate_metacog_compliance, "ITERLOG_DIR", iterlog_dir)
    monkeypatch.setattr(
        sys,
        "argv",
        ["validate_metacog_compliance.py", "--story-id", "CH-META-002", "--strict"],
    )
    assert validate_metacog_compliance.main() == 1


def test_require_artifacts_fails_when_redis_unavailable(
    tmp_path: Path, monkeypatch
) -> None:
    iterlog_dir = tmp_path / "docs" / "tempmemories"
    iterlog_dir.mkdir(parents=True)
    body = """
## Metacognitive Predictions
predicted_outcome: improve reliability
predicted_risks: [regression]
confidence: 0.8
verification_plan: run precommit
expected_metrics: [reopen_rate <= 0.05]

## Metacognitive Outcomes
actual_outcome: improved reliability
actual_metrics: {reopen_rate: 0.04}
wins: [reduced regressions]
misses: []
new_prevention_rules: [rule-1]

## Metacognitive Calibration
predicted_confidence: 0.8
observed_result: success
calibration_delta: 0.1
confidence_adjustment_recommendation: no_change
"""
    _write_iterlog(
        iterlog_dir / "iterlog-CH-META-003.md",
        "CH-META-003",
        "completed",
        body,
    )

    monkeypatch.setattr(validate_metacog_compliance, "ITERLOG_DIR", iterlog_dir)
    monkeypatch.setattr(validate_metacog_compliance, "_get_redis_client", lambda: None)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "validate_metacog_compliance.py",
            "--story-id",
            "CH-META-003",
            "--strict",
            "--require-artifacts",
        ],
    )
    assert validate_metacog_compliance.main() == 1


def test_require_artifacts_passes_when_redis_keys_exist(
    tmp_path: Path, monkeypatch
) -> None:
    iterlog_dir = tmp_path / "docs" / "tempmemories"
    iterlog_dir.mkdir(parents=True)
    body = """
## Metacognitive Predictions
predicted_outcome: improve reliability
predicted_risks: [regression]
confidence: 0.8
verification_plan: run precommit
expected_metrics: [reopen_rate <= 0.05]

## Metacognitive Outcomes
actual_outcome: improved reliability
actual_metrics: {reopen_rate: 0.04}
wins: [reduced regressions]
misses: []
new_prevention_rules: [rule-1]

## Metacognitive Calibration
predicted_confidence: 0.8
observed_result: success
calibration_delta: 0.1
confidence_adjustment_recommendation: no_change
"""
    _write_iterlog(
        iterlog_dir / "iterlog-CH-META-004.md",
        "CH-META-004",
        "completed",
        body,
    )

    class _FakeRedis:
        def exists(self, key: str) -> int:  # noqa: ARG002
            return 1

    monkeypatch.setattr(validate_metacog_compliance, "ITERLOG_DIR", iterlog_dir)
    monkeypatch.setattr(
        validate_metacog_compliance,
        "_get_redis_client",
        lambda: {0: _FakeRedis()},
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "validate_metacog_compliance.py",
            "--story-id",
            "CH-META-004",
            "--strict",
            "--require-artifacts",
        ],
    )
    assert validate_metacog_compliance.main() == 0


def test_markdown_bold_key_fields_are_accepted(
    tmp_path: Path, monkeypatch
) -> None:
    iterlog_dir = tmp_path / "docs" / "tempmemories"
    iterlog_dir.mkdir(parents=True)
    body = """
## Metacognitive Predictions
**predicted_outcome**: improve reliability
**predicted_risks**: [regression]
**confidence**: 0.8
**verification_plan**: run precommit
**expected_metrics**: [reopen_rate <= 0.05]

## Metacognitive Outcomes
**actual_outcome**: improved reliability
**actual_metrics**: {reopen_rate: 0.04}
**wins**: [reduced regressions]
**misses**: []
**new_prevention_rules**: [rule-1]

## Metacognitive Calibration
**predicted_confidence**: 0.8
**observed_result**: success
**calibration_delta**: 0.1
**confidence_adjustment_recommendation**: no_change
"""
    _write_iterlog(
        iterlog_dir / "iterlog-CH-META-005.md",
        "CH-META-005",
        "completed",
        body,
    )

    monkeypatch.setattr(validate_metacog_compliance, "ITERLOG_DIR", iterlog_dir)
    monkeypatch.setattr(
        sys,
        "argv",
        ["validate_metacog_compliance.py", "--story-id", "CH-META-005", "--strict"],
    )
    assert validate_metacog_compliance.main() == 0


def test_require_artifacts_falls_back_to_db0_when_env_db_mismatch(
    tmp_path: Path, monkeypatch
) -> None:
    iterlog_dir = tmp_path / "docs" / "tempmemories"
    iterlog_dir.mkdir(parents=True)
    body = """
## Metacognitive Predictions
predicted_outcome: improve reliability
predicted_risks: [regression]
confidence: 0.8
verification_plan: run precommit
expected_metrics: [reopen_rate <= 0.05]

## Metacognitive Outcomes
actual_outcome: improved reliability
actual_metrics: {reopen_rate: 0.04}
wins: [reduced regressions]
misses: []
new_prevention_rules: [rule-1]

## Metacognitive Calibration
predicted_confidence: 0.8
observed_result: success
calibration_delta: 0.1
confidence_adjustment_recommendation: no_change
"""
    _write_iterlog(
        iterlog_dir / "iterlog-CH-META-006.md",
        "CH-META-006",
        "completed",
        body,
    )

    class _MissingRedis:
        def exists(self, key: str) -> int:  # noqa: ARG002
            return 0

    class _PresentRedis:
        def exists(self, key: str) -> int:  # noqa: ARG002
            return 1

    monkeypatch.setattr(validate_metacog_compliance, "ITERLOG_DIR", iterlog_dir)
    monkeypatch.setattr(
        validate_metacog_compliance,
        "_get_redis_client",
        lambda: {1: _MissingRedis(), 0: _PresentRedis()},
    )
    monkeypatch.setenv("REDIS_DB", "1")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "validate_metacog_compliance.py",
            "--story-id",
            "CH-META-006",
            "--strict",
            "--require-artifacts",
        ],
    )
    assert validate_metacog_compliance.main() == 0


def test_observed_result_aliases_are_accepted(
    tmp_path: Path, monkeypatch
) -> None:
    iterlog_dir = tmp_path / "docs" / "tempmemories"
    iterlog_dir.mkdir(parents=True)
    body = """
## Metacognitive Predictions
predicted_outcome: improve reliability
predicted_risks: [regression]
confidence: 0.8
verification_plan: run precommit
expected_metrics: [reopen_rate <= 0.05]

## Metacognitive Outcomes
actual_outcome: improved reliability
actual_metrics: {reopen_rate: 0.04}
wins: [reduced regressions]
misses: []
new_prevention_rules: [rule-1]

## Metacognitive Calibration
predicted_confidence: 0.8
observed_result: PARTIAL_PASS
calibration_delta: 0.1
confidence_adjustment_recommendation: no_change
"""
    _write_iterlog(
        iterlog_dir / "iterlog-CH-META-007.md",
        "CH-META-007",
        "completed",
        body,
    )

    monkeypatch.setattr(validate_metacog_compliance, "ITERLOG_DIR", iterlog_dir)
    monkeypatch.setattr(
        sys,
        "argv",
        ["validate_metacog_compliance.py", "--story-id", "CH-META-007", "--strict"],
    )
    assert validate_metacog_compliance.main() == 0
