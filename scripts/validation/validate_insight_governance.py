#!/usr/bin/env python3
"""
Validate insight-governance conformance in iterlog markdown artifacts.

Purpose:
- Ensure INSIGHT_PACKET / ARIA_DECISION structure is present and complete.
- Enforce no-silent-scope-drift fields in ARIA_DECISION.
- Verify fallback sections exist for markdown-mode operation.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

ITERLOG_DIR = Path("docs/tempmemories")
ITERLOG_GLOB = "iterlog-*.md"
LEGACY_EXEMPTIONS_PATH = Path("docs/governance/legacy-exemptions.yaml")

REQUIRED_INSIGHT_FIELDS = {
    "insight_packet_id:",
    "story_id:",
    "detected_at_utc:",
    "context:",
}

REQUIRED_ISSUE_FIELDS = {
    "issue:",
    "impact_if_ignored:",
    "suggested_improvement:",
    "reason:",
    "urgency:",
    "confidence:",
    "evidence:",
    "evidence_signature:",
}

REQUIRED_DECISION_FIELDS = {
    "aria_decision_id:",
    "decision:",
    "scope_update:",
    "scope_impact:",
    "prd_scope_change:",
    "craig_approval_required:",
    "rationale:",
    "expected_outcome:",
    "follow_up_actions:",
}

FALLBACK_SECTIONS = {
    "## Thinking Partner Status",
    "## Insights Sent To Aria",
    "## Aria Decisions",
    "## Rejected Insight Signatures",
}


@dataclass
class Result:
    errors: list[str]
    warnings: list[str]

    def __init__(self) -> None:
        self.errors = []
        self.warnings = []

    def err(self, msg: str) -> None:
        self.errors.append(f"ERROR: {msg}")

    def warn(self, msg: str) -> None:
        self.warnings.append(f"WARNING: {msg}")


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _read_frontmatter(path: Path) -> dict[str, Any]:
    text = _read_text(path)
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}
    raw_yaml = text[4:end]
    data = yaml.safe_load(raw_yaml) or {}
    return data if isinstance(data, dict) else {}


def _read_body(path: Path) -> str:
    text = _read_text(path)
    if not text.startswith("---\n"):
        return text
    end = text.find("\n---\n", 4)
    if end == -1:
        return text
    return text[end + 5 :]


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _is_legacy_exempt(path: Path, fm: dict[str, Any], include_archived: bool) -> bool:
    if _to_bool(fm.get("legacy_exempt")):
        return True
    if str(fm.get("compliance_mode", "")).strip().lower() == "legacy_exempt":
        return True
    return include_archived and "docs/tempmemories/archived/" in str(path).replace(
        "\\", "/"
    )


def _load_legacy_exemptions() -> set[str]:
    if not LEGACY_EXEMPTIONS_PATH.exists():
        return set()
    try:
        data = yaml.safe_load(LEGACY_EXEMPTIONS_PATH.read_text(encoding="utf-8")) or {}
        story_ids = data.get("iterlog_story_ids", [])
        if not isinstance(story_ids, list):
            return set()
        return {str(s).strip() for s in story_ids if str(s).strip()}
    except Exception:
        return set()


def _extract_tp_session_ids(body: str) -> list[str]:
    pattern = r"(?im)^\s*(?:[-*]\s*)?(?:\*\*|`)?tp_session_id(?:\*\*|`)?\s*:\s*([A-Za-z0-9._:-]+)\s*$"
    ids: list[str] = []
    seen: set[str] = set()
    for m in re.findall(pattern, body):
        sid = m.strip()
        if sid and sid not in seen:
            seen.add(sid)
            ids.append(sid)
    return ids


def _extract_story_id(path: Path, fm: dict[str, Any], body: str) -> str:
    if "story_id" in fm:
        return str(fm.get("story_id", "")).strip()
    stem = path.stem
    if stem.startswith("iterlog-"):
        return stem.replace("iterlog-", "", 1)
    match = re.search(
        r"(?im)^\s*(?:[-*]\s*)?(?:\*\*|`)?story_id(?:\*\*|`)?\s*:\s*([A-Za-z0-9_-]+)\s*$",
        body,
    )
    if match:
        return match.group(1).strip()
    return ""


def _get_redis_clients():
    try:
        import redis

        port = int(
            os.getenv("REDIS_PORT")
            or os.getenv("CHISE_REDIS_PORT")
            or os.getenv("ACP_REDIS_PORT")
            or "6380"
        )
        primary_db = int(os.getenv("REDIS_DB", "0"))
        db_candidates = [primary_db] if primary_db == 0 else [primary_db, 0]
        hosts = [
            os.getenv("REDIS_HOST"),
            os.getenv("CHISE_REDIS_HOST"),
            os.getenv("ACP_REDIS_HOST"),
            "chiseai-redis",
            "host.docker.internal",
            "localhost",
        ]
        hosts = [h for i, h in enumerate(hosts) if h and h not in hosts[:i]]
        clients: dict[int, redis.Redis] = {}
        for db in db_candidates:
            for host in hosts:
                try:
                    client = redis.Redis(
                        host=host,
                        port=port,
                        db=db,
                        decode_responses=True,
                        socket_connect_timeout=3,
                        socket_timeout=3,
                    )
                    client.ping()
                    clients[db] = client
                    break
                except Exception:
                    continue
        return clients
    except Exception:
        return None


def _enforce_tp_session_artifacts(
    path: Path,
    fm: dict[str, Any],
    body: str,
    mode: str,
    self_heal: bool,
    result: Result,
) -> None:
    if mode == "off":
        return

    session_ids = _extract_tp_session_ids(body)
    if not session_ids:
        # Handled by structural field checks above.
        return

    clients = _get_redis_clients()
    if clients is None:
        msg = f"{path}: Redis unavailable; cannot validate tp session artifact(s)"
        if mode == "strict":
            result.err(msg)
        else:
            result.warn(msg)
        return

    story_id = _extract_story_id(path, fm, body) or "unknown"
    primary_db = int(os.getenv("REDIS_DB", "0"))
    now_utc = str(fm.get("updated", "")).strip()
    if not now_utc:
        now_utc = "unknown"

    for session_id in session_ids:
        key = f"bmad:chiseai:tp:session:{session_id}"
        found_db = next(
            (db for db, client in clients.items() if client.exists(key) == 1), None
        )
        if found_db is None and self_heal:
            client0 = clients.get(0) or next(iter(clients.values()))
            try:
                client0.hset(
                    key,
                    mapping={
                        "story_id": story_id,
                        "tp_mode": "DEGRADED",
                        "scope": story_id,
                        "created_at": now_utc,
                        "source": "insight_validator_self_heal",
                    },
                )
                client0.expire(key, 432000)
                if client0.exists(key) == 1:
                    found_db = 0
                    result.warn(
                        f"{path}: self-healed missing tp session artifact {key} in Redis DB 0"
                    )
            except Exception:
                pass

        if found_db is None:
            msg = f"{path}: missing tp session artifact {key}"
            if mode == "strict":
                result.err(msg)
            else:
                result.warn(msg)
        elif found_db != primary_db:
            result.warn(
                f"{path}: found tp session artifact {key} in Redis DB {found_db} (REDIS_DB={primary_db})"
            )


def _extract_blocks(body: str, tag: str) -> list[str]:
    """Extract governance blocks from text or yaml fences.

    Supports:
    - ```text ... TAG ... ```
    - ```yaml ... TAG: ... ```
    - ```yaml ... tag_specific_fields ... ``` (when heading announces the tag)
    """
    blocks: list[str] = []

    # Case 1: collect all text/yaml fenced blocks and filter by tag semantics.
    fenced_blocks = re.findall(
        r"```(?:text|yaml)\s*(.*?)```", body, flags=re.DOTALL | re.IGNORECASE
    )
    tag_lower = tag.lower()
    for b in fenced_blocks:
        b_low = b.lower()
        if tag_lower == "insight_packet":
            if "insight_packet_id:" in b_low or re.search(
                r"(?im)^\s*insight_packet\b", b_low
            ):
                blocks.append(b)
        elif tag_lower == "aria_decision":
            if "aria_decision_id:" in b_low or re.search(
                r"(?im)^\s*aria_decision\b", b_low
            ):
                blocks.append(b)
        elif tag_lower == "no_issues_packet":
            if "packet_id:" in b_low and re.search(
                r"(?im)^\s*no_issues_packet\b", b_low
            ):
                blocks.append(b)

    # Case 2: markdown heading announces block type followed by fenced payload.
    heading_pattern = (
        rf"(?is)(?:^|\n)\s*#+\s*{re.escape(tag)}\s*\n+```(?:text|yaml)\s*(.*?)```"
    )
    blocks.extend(re.findall(heading_pattern, body, flags=re.DOTALL | re.IGNORECASE))

    # De-duplicate while preserving order.
    seen: set[str] = set()
    unique: list[str] = []
    for b in blocks:
        key = b.strip()
        if key and key not in seen:
            seen.add(key)
            unique.append(key)
    return unique


def _contains_no_issues_fields(block: str) -> bool:
    required = (
        "packet_id:",
        "story_id:",
        "reviewed_at_utc:",
        "context:",
        "checks_run:",
        "evidence:",
        "evidence_signature:",
    )
    return all(field in block for field in required)


def _validate_insight_packet(block: str, path: Path, idx: int, result: Result) -> None:
    for field in REQUIRED_INSIGHT_FIELDS:
        if field not in block:
            result.err(f"{path}: INSIGHT_PACKET #{idx} missing field {field}")
    for field in REQUIRED_ISSUE_FIELDS:
        if field not in block:
            result.err(f"{path}: INSIGHT_PACKET #{idx} missing issue field {field}")


def _validate_aria_decision(block: str, path: Path, idx: int, result: Result) -> None:
    for field in REQUIRED_DECISION_FIELDS:
        if field not in block:
            result.err(f"{path}: ARIA_DECISION #{idx} missing field {field}")

    scope_impact_match = re.search(r"scope_impact:\s*([A-Z]+)", block)
    if scope_impact_match and scope_impact_match.group(1) not in {
        "NONE",
        "MINOR",
        "MAJOR",
    }:
        result.err(
            f"{path}: ARIA_DECISION #{idx} invalid scope_impact={scope_impact_match.group(1)!r}"
        )

    prd_change_match = re.search(
        r"prd_scope_change:\s*(true|false)", block, flags=re.IGNORECASE
    )
    if not prd_change_match:
        result.err(
            f"{path}: ARIA_DECISION #{idx} missing/invalid prd_scope_change boolean"
        )


def _validate_file(
    path: Path,
    require_for_completed: bool,
    strict: bool,
    tp_session_artifact_mode: str,
    tp_session_self_heal: bool,
    result: Result,
) -> None:
    fm = _read_frontmatter(path)
    status = str(fm.get("status", "")).strip()
    body = _read_body(path)

    should_require = status == "completed" if require_for_completed else True

    if should_require:
        for section in FALLBACK_SECTIONS:
            if section not in body:
                msg = f"{path}: missing fallback section {section}"
                if strict:
                    result.err(msg)
                else:
                    result.warn(msg)

    insight_blocks = _extract_blocks(body, "INSIGHT_PACKET")
    no_issues_blocks = _extract_blocks(body, "NO_ISSUES_PACKET")
    decision_blocks = _extract_blocks(body, "ARIA_DECISION")

    # If parser extracted content by heading fallback, ensure it is the right payload.
    no_issues_blocks = [b for b in no_issues_blocks if _contains_no_issues_fields(b)]

    if should_require and not insight_blocks and not no_issues_blocks:
        msg = f"{path}: no INSIGHT_PACKET or NO_ISSUES_PACKET blocks found"
        if strict:
            result.err(msg)
        else:
            result.warn(msg)
    if should_require and not decision_blocks:
        msg = f"{path}: no ARIA_DECISION blocks found"
        if strict:
            result.err(msg)
        else:
            result.warn(msg)
    tp_session_pattern = r"(?im)^\s*(?:[-*]\s*)?(?:\*\*|`)?tp_session_id(?:\*\*|`)?\s*:"
    if should_require and not re.search(tp_session_pattern, body):
        msg = f"{path}: missing tp_session_id in Thinking Partner status"
        if strict:
            result.err(msg)
        else:
            result.warn(msg)
    if (
        should_require
        and "Thinking Partner Proof:" not in body
        and "## Thinking Partner Proof" not in body
    ):
        msg = f"{path}: missing Thinking Partner Proof line"
        if strict:
            result.err(msg)
        else:
            result.warn(msg)

    for i, block in enumerate(insight_blocks, start=1):
        _validate_insight_packet(block, path, i, result)
    for i, block in enumerate(decision_blocks, start=1):
        _validate_aria_decision(block, path, i, result)
    if should_require:
        _enforce_tp_session_artifacts(
            path=path,
            fm=fm,
            body=body,
            mode=tp_session_artifact_mode,
            self_heal=tp_session_self_heal,
            result=result,
        )


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate insight-governance conformance")
    ap.add_argument("--story-id", help="Validate only iterlog for this story id")
    ap.add_argument(
        "--require-for-completed-only",
        action="store_true",
        help="Require sections/fields only for iterlogs with status=completed",
    )
    ap.add_argument(
        "--strict",
        action="store_true",
        help="Treat missing sections/blocks as errors (CI gate mode)",
    )
    ap.add_argument(
        "--tp-session-artifact-mode",
        choices=["off", "warn", "strict"],
        default=os.getenv("TP_SESSION_ARTIFACT_MODE", "off"),
        help="Redis tp:session artifact enforcement mode (default: off)",
    )
    ap.add_argument(
        "--tp-session-self-heal",
        action="store_true",
        help="Attempt to backfill missing tp:session artifacts in Redis DB0",
    )
    ap.add_argument(
        "--include-legacy",
        action="store_true",
        help="Include legacy-exempt iterlogs (default: skip legacy-exempt files).",
    )
    ap.add_argument(
        "--legacy-archive-exempt",
        action="store_true",
        default=True,
        help="Treat docs/tempmemories/archived/* iterlogs as legacy-exempt (default: true).",
    )
    ap.add_argument(
        "--no-legacy-archive-exempt",
        dest="legacy_archive_exempt",
        action="store_false",
        help="Do not auto-exempt archived iterlogs.",
    )
    args = ap.parse_args()

    paths = sorted(ITERLOG_DIR.glob(ITERLOG_GLOB))
    if args.story_id:
        paths = [p for p in paths if args.story_id in p.name]

    exempt_story_ids = _load_legacy_exemptions()
    skipped_legacy = 0
    if not args.include_legacy:
        filtered = []
        for path in paths:
            fm = _read_frontmatter(path)
            body = _read_body(path)
            story_id = _extract_story_id(path, fm, body)
            if story_id in exempt_story_ids:
                skipped_legacy += 1
                continue
            if _is_legacy_exempt(path, fm, include_archived=args.legacy_archive_exempt):
                skipped_legacy += 1
                continue
            filtered.append(path)
        paths = filtered

    result = Result()
    if not paths:
        if args.story_id:
            result.err(
                f"No eligible iterlog files found in {ITERLOG_DIR}/ for story_id={args.story_id}"
            )
        else:
            result.warn(
                f"No eligible iterlog files found in {ITERLOG_DIR}/ "
                "(legacy exemptions and/or archive filters may have excluded all files)"
            )
    else:
        for path in paths:
            _validate_file(
                path,
                args.require_for_completed_only,
                args.strict,
                args.tp_session_artifact_mode,
                args.tp_session_self_heal,
                result,
            )

    for w in result.warnings:
        print(w)
    for e in result.errors:
        print(e, file=sys.stderr)
    if skipped_legacy:
        print(
            f"INFO: skipped {skipped_legacy} legacy-exempt iterlog file(s) "
            "(use --include-legacy to include)"
        )

    return 1 if result.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
