from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "validation"
    / "validate_insight_governance.py"
)
SPEC = importlib.util.spec_from_file_location("validate_insight_governance", MODULE_PATH)
assert SPEC and SPEC.loader
validate_insight_governance = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = validate_insight_governance
SPEC.loader.exec_module(validate_insight_governance)


def _write_iterlog(path: Path, story_id: str, status: str, body: str) -> None:
    text = f"""---
story_id: {story_id}
status: {status}
---

{body}
"""
    path.write_text(text, encoding="utf-8")


def test_strict_fails_without_thinking_partner_status_fields(
    tmp_path: Path, monkeypatch
) -> None:
    iterlog_dir = tmp_path / "docs" / "tempmemories"
    iterlog_dir.mkdir(parents=True)
    body = """
## Insights Sent To Aria
```text
INSIGHT_PACKET
- insight_packet_id: IP-CH-TP-001-20260308T000000Z-abc123
- story_id: CH-TP-001
- detected_at_utc: 2026-03-08T00:00:00Z
- context: test
- issues:
  - issue: missing checks
    impact_if_ignored: drift
    suggested_improvement: enforce checks
    reason: test
    urgency: high
    confidence: 0.9
    evidence: validator output
    evidence_signature: sig-1
```

## Aria Decisions
```text
ARIA_DECISION
- aria_decision_id: AD-CH-TP-001-20260308T000100Z-def456
- decision: ACCEPT
- scope_update: enforce checks
- scope_impact: MINOR
- prd_scope_change: false
- craig_approval_required: false
- rationale: test
- expected_outcome: improved compliance
- follow_up_actions: add gates
```

## Rejected Insight Signatures
- none
"""
    _write_iterlog(iterlog_dir / "iterlog-CH-TP-001.md", "CH-TP-001", "completed", body)

    monkeypatch.setattr(validate_insight_governance, "ITERLOG_DIR", iterlog_dir)
    monkeypatch.setattr(
        sys,
        "argv",
        ["validate_insight_governance.py", "--story-id", "CH-TP-001", "--strict"],
    )
    assert validate_insight_governance.main() == 1


def test_strict_passes_with_no_issues_packet_and_tp_proof(
    tmp_path: Path, monkeypatch
) -> None:
    iterlog_dir = tmp_path / "docs" / "tempmemories"
    iterlog_dir.mkdir(parents=True)
    body = """
## Thinking Partner Status
- **tp_session_id**: TPS-20260308T000000Z-aaa111

## Insights Sent To Aria
```text
NO_ISSUES_PACKET
- packet_id: NIP-CH-TP-002-20260308T000000Z-bbb222
- story_id: CH-TP-002
- reviewed_at_utc: 2026-03-08T00:00:00Z
- context: no material issues
- checks_run: validators
- evidence: local checks all pass
- evidence_signature: sig-2
```

## Aria Decisions
```text
ARIA_DECISION
- aria_decision_id: AD-CH-TP-002-20260308T000100Z-ccc333
- decision: ACCEPT
- scope_update: no changes
- scope_impact: NONE
- prd_scope_change: false
- craig_approval_required: false
- rationale: no issues found
- expected_outcome: proceed
- follow_up_actions: none
```

## Rejected Insight Signatures
- none

Thinking Partner Proof: ACTIVE | CH-TP-002 | IP:none | AD:AD-CH-TP-002-20260308T000100Z-ccc333 | Risks:0
"""
    _write_iterlog(iterlog_dir / "iterlog-CH-TP-002.md", "CH-TP-002", "completed", body)

    monkeypatch.setattr(validate_insight_governance, "ITERLOG_DIR", iterlog_dir)
    monkeypatch.setattr(
        sys,
        "argv",
        ["validate_insight_governance.py", "--story-id", "CH-TP-002", "--strict"],
    )
    assert validate_insight_governance.main() == 0


def test_tp_session_artifact_strict_fails_when_missing(
    tmp_path: Path, monkeypatch
) -> None:
    iterlog_dir = tmp_path / "docs" / "tempmemories"
    iterlog_dir.mkdir(parents=True)
    body = """
## Thinking Partner Status
- tp_session_id: TPS-20260308T000000Z-zzz999

## Insights Sent To Aria
```text
NO_ISSUES_PACKET
- packet_id: NIP-CH-TP-003-20260308T000000Z-bbb222
- story_id: CH-TP-003
- reviewed_at_utc: 2026-03-08T00:00:00Z
- context: no material issues
- checks_run: validators
- evidence: local checks all pass
- evidence_signature: sig-2
```

## Aria Decisions
```text
ARIA_DECISION
- aria_decision_id: AD-CH-TP-003-20260308T000100Z-ccc333
- decision: ACCEPT
- scope_update: no changes
- scope_impact: NONE
- prd_scope_change: false
- craig_approval_required: false
- rationale: no issues found
- expected_outcome: proceed
- follow_up_actions: none
```

## Rejected Insight Signatures
- none

Thinking Partner Proof: ACTIVE | CH-TP-003 | IP:none | AD:AD-CH-TP-003-20260308T000100Z-ccc333 | Risks:0
"""
    _write_iterlog(iterlog_dir / "iterlog-CH-TP-003.md", "CH-TP-003", "completed", body)

    class _MissingRedis:
        def exists(self, key: str) -> int:  # noqa: ARG002
            return 0

    monkeypatch.setattr(validate_insight_governance, "ITERLOG_DIR", iterlog_dir)
    monkeypatch.setattr(
        validate_insight_governance,
        "_get_redis_clients",
        lambda: {0: _MissingRedis()},
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "validate_insight_governance.py",
            "--story-id",
            "CH-TP-003",
            "--strict",
            "--tp-session-artifact-mode",
            "strict",
        ],
    )
    assert validate_insight_governance.main() == 1


def test_tp_session_artifact_warn_mode_does_not_fail(
    tmp_path: Path, monkeypatch
) -> None:
    iterlog_dir = tmp_path / "docs" / "tempmemories"
    iterlog_dir.mkdir(parents=True)
    body = """
## Thinking Partner Status
- tp_session_id: TPS-20260308T000000Z-yyy888

## Insights Sent To Aria
```text
NO_ISSUES_PACKET
- packet_id: NIP-CH-TP-004-20260308T000000Z-bbb222
- story_id: CH-TP-004
- reviewed_at_utc: 2026-03-08T00:00:00Z
- context: no material issues
- checks_run: validators
- evidence: local checks all pass
- evidence_signature: sig-2
```

## Aria Decisions
```text
ARIA_DECISION
- aria_decision_id: AD-CH-TP-004-20260308T000100Z-ccc333
- decision: ACCEPT
- scope_update: no changes
- scope_impact: NONE
- prd_scope_change: false
- craig_approval_required: false
- rationale: no issues found
- expected_outcome: proceed
- follow_up_actions: none
```

## Rejected Insight Signatures
- none

Thinking Partner Proof: ACTIVE | CH-TP-004 | IP:none | AD:AD-CH-TP-004-20260308T000100Z-ccc333 | Risks:0
"""
    _write_iterlog(iterlog_dir / "iterlog-CH-TP-004.md", "CH-TP-004", "completed", body)

    class _MissingRedis:
        def exists(self, key: str) -> int:  # noqa: ARG002
            return 0

    monkeypatch.setattr(validate_insight_governance, "ITERLOG_DIR", iterlog_dir)
    monkeypatch.setattr(
        validate_insight_governance,
        "_get_redis_clients",
        lambda: {0: _MissingRedis()},
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "validate_insight_governance.py",
            "--story-id",
            "CH-TP-004",
            "--strict",
            "--tp-session-artifact-mode",
            "warn",
        ],
    )
    assert validate_insight_governance.main() == 0


def test_tp_session_self_heal_recovers_missing_artifact(
    tmp_path: Path, monkeypatch
) -> None:
    iterlog_dir = tmp_path / "docs" / "tempmemories"
    iterlog_dir.mkdir(parents=True)
    body = """
## Thinking Partner Status
- tp_session_id: TPS-20260308T000000Z-xxx777

## Insights Sent To Aria
```text
NO_ISSUES_PACKET
- packet_id: NIP-CH-TP-005-20260308T000000Z-bbb222
- story_id: CH-TP-005
- reviewed_at_utc: 2026-03-08T00:00:00Z
- context: no material issues
- checks_run: validators
- evidence: local checks all pass
- evidence_signature: sig-2
```

## Aria Decisions
```text
ARIA_DECISION
- aria_decision_id: AD-CH-TP-005-20260308T000100Z-ccc333
- decision: ACCEPT
- scope_update: no changes
- scope_impact: NONE
- prd_scope_change: false
- craig_approval_required: false
- rationale: no issues found
- expected_outcome: proceed
- follow_up_actions: none
```

## Rejected Insight Signatures
- none

Thinking Partner Proof: ACTIVE | CH-TP-005 | IP:none | AD:AD-CH-TP-005-20260308T000100Z-ccc333 | Risks:0
"""
    _write_iterlog(iterlog_dir / "iterlog-CH-TP-005.md", "CH-TP-005", "completed", body)

    class _HealingRedis:
        def __init__(self) -> None:
            self._store: dict[str, dict[str, str]] = {}

        def exists(self, key: str) -> int:
            return 1 if key in self._store else 0

        def hset(self, key: str, mapping: dict[str, str]) -> int:
            self._store[key] = dict(mapping)
            return 1

        def expire(self, key: str, ttl: int) -> int:  # noqa: ARG002
            return 1 if key in self._store else 0

    fake_redis = _HealingRedis()
    monkeypatch.setattr(validate_insight_governance, "ITERLOG_DIR", iterlog_dir)
    monkeypatch.setattr(
        validate_insight_governance,
        "_get_redis_clients",
        lambda: {0: fake_redis},
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "validate_insight_governance.py",
            "--story-id",
            "CH-TP-005",
            "--strict",
            "--tp-session-artifact-mode",
            "strict",
            "--tp-session-self-heal",
        ],
    )
    assert validate_insight_governance.main() == 0
