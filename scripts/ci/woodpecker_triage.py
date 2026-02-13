#!/usr/bin/env python3
"""Root-cause-first Woodpecker CI triage.

Capabilities:
- Query Woodpecker API for pipeline/step status and logs
- Diagnose exact CI failures (rule/file/line/test where possible)
- Emit machine-readable + markdown artifacts for swarm handoffs

Fallback:
- If API/token is unavailable, parse local `_bmad-output/ci` logs/status files.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import textwrap
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

DEFAULT_BASE_URL = "http://host.docker.internal:8012"
DEFAULT_OUT_DIR = Path("_bmad-output/ci/woodpecker")

SUCCESS_STATUSES = {"success", "passing", "passed", "complete", "skipped"}
FAILED_STATUSES = {"failure", "failed", "error", "killed", "blocked"}


@dataclass
class RootCause:
    tool: str
    kind: str
    message: str
    evidence: str
    confidence: str = "medium"
    file: str | None = None
    line: int | None = None
    column: int | None = None
    rule: str | None = None
    test: str | None = None

    def key(self) -> tuple[Any, ...]:
        return (
            self.tool,
            self.kind,
            self.file,
            self.line,
            self.column,
            self.rule,
            self.test,
            self.message,
        )

    def to_dict(self, idx: int) -> dict[str, Any]:
        return {
            "id": f"rc-{idx:03d}",
            "tool": self.tool,
            "kind": self.kind,
            "message": self.message,
            "file": self.file,
            "line": self.line,
            "column": self.column,
            "rule": self.rule,
            "test": self.test,
            "evidence": self.evidence,
            "confidence": self.confidence,
        }


class WoodpeckerClient:
    def __init__(self, base_url: str, token: str | None):
        self.base_url = base_url.rstrip("/")
        self.token = (token or "").strip()

    def _headers(self, mode: str) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.token:
            if mode == "bearer":
                headers["Authorization"] = f"Bearer {self.token}"
            elif mode == "token":
                headers["Authorization"] = f"token {self.token}"
            else:
                headers["X-WOODPECKER-TOKEN"] = self.token
        return headers

    def _request(self, method: str, path: str, *, expect_json: bool = True) -> Any:
        url = f"{self.base_url}{path}"
        errors: list[str] = []
        for mode in ("bearer", "token", "x-token"):
            req = Request(url=url, method=method, headers=self._headers(mode))
            try:
                with urlopen(req, timeout=20) as resp:  # noqa: S310
                    data = resp.read().decode("utf-8", errors="replace")
                    if expect_json:
                        return json.loads(data)
                    return data
            except HTTPError as exc:
                errors.append(f"{mode}:{exc.code}")
                if exc.code in {401, 403}:
                    continue
                raise
            except URLError as exc:
                raise RuntimeError(f"Cannot reach Woodpecker at {url}: {exc}") from exc
        raise RuntimeError(
            f"Woodpecker request failed at {url}. Tried auth headers: {', '.join(errors)}"
        )

    def get_json(self, path: str) -> Any:
        return self._request("GET", path, expect_json=True)

    def get_text(self, path: str) -> str:
        return self._request("GET", path, expect_json=False)


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _repo_context(args: argparse.Namespace) -> tuple[str, str]:
    owner = (
        args.owner
        or os.getenv("WOODPECKER_REPO_OWNER")
        or os.getenv("CI_REPO_OWNER")
        or os.getenv("GITEA_OWNER")
    )
    repo = (
        args.repo
        or os.getenv("WOODPECKER_REPO_NAME")
        or os.getenv("CI_REPO_NAME")
        or os.getenv("GITEA_REPO")
        or "ChiseAI"
    )
    if not owner:
        raise SystemExit(
            "Missing repo owner. Set --owner or WOODPECKER_REPO_OWNER/CI_REPO_OWNER/GITEA_OWNER"
        )
    return owner, repo


def _normalize_pipeline(data: dict[str, Any]) -> dict[str, Any]:
    number = data.get("number") or data.get("id") or data.get("build_number")
    status = (
        str(data.get("status") or data.get("state") or data.get("result") or "unknown")
        .strip()
        .lower()
    )
    return {
        "number": number,
        "id": data.get("id"),
        "status": status,
        "event": data.get("event") or data.get("hook_event"),
        "ref": data.get("ref") or data.get("commit") or data.get("branch"),
        "title": data.get("title") or data.get("message") or "",
        "author": data.get("author") or data.get("sender") or "",
        "created": data.get("created") or data.get("created_at"),
        "updated": data.get("updated") or data.get("updated_at"),
        "raw": data,
    }


def _normalize_step(data: dict[str, Any]) -> dict[str, Any]:
    status = (
        str(data.get("status") or data.get("state") or data.get("result") or "unknown")
        .strip()
        .lower()
    )
    return {
        "id": data.get("id"),
        "number": data.get("number") or data.get("position") or data.get("index"),
        "name": data.get("name") or data.get("step") or "unknown-step",
        "status": status,
        "exit_code": data.get("exit_code") or data.get("exitCode") or data.get("code"),
        "started": data.get("started") or data.get("started_at"),
        "stopped": data.get("stopped")
        or data.get("finished")
        or data.get("finished_at"),
        "raw": data,
    }


def _pr_candidates(text: str) -> set[int]:
    hits: set[int] = set()
    for pat in (
        r"refs/pull/(\d+)/",
        r"\bPR[ #](\d+)\b",
        r"\bpull[ _-]?request[ #]?(\d+)\b",
    ):
        for m in re.finditer(pat, text, flags=re.IGNORECASE):
            try:
                hits.add(int(m.group(1)))
            except ValueError:
                continue
    return hits


def _extract_pipeline_pr(pipeline: dict[str, Any]) -> set[int]:
    raw = pipeline.get("raw", {})
    values = [
        raw.get("pull_request"),
        raw.get("pullRequest"),
        raw.get("pull_request_number"),
        pipeline.get("ref"),
        pipeline.get("title"),
    ]
    out: set[int] = set()
    for value in values:
        if value is None:
            continue
        if isinstance(value, int):
            out.add(value)
            continue
        s = str(value)
        if s.isdigit():
            out.add(int(s))
        out.update(_pr_candidates(s))
    return out


def _list_pipelines(
    client: WoodpeckerClient, owner: str, repo: str
) -> list[dict[str, Any]]:
    candidates = [
        f"/api/repos/{owner}/{repo}/pipelines?{urlencode({'per_page': 50})}",
        f"/api/repos/{owner}/{repo}/builds?{urlencode({'per_page': 50})}",
        f"/api/repos/{owner}/{repo}/pipelines",
    ]
    for path in candidates:
        try:
            data = client.get_json(path)
            if isinstance(data, list):
                return [
                    _normalize_pipeline(item) for item in data if isinstance(item, dict)
                ]
        except Exception:
            continue
    raise RuntimeError(
        "Unable to list pipelines from Woodpecker API. Verify base URL, token, owner, and repo."
    )


def _fetch_pipeline_steps(
    client: WoodpeckerClient, owner: str, repo: str, pipeline_number: int
) -> list[dict[str, Any]]:
    candidates = [
        f"/api/repos/{owner}/{repo}/pipelines/{pipeline_number}/steps",
        f"/api/repos/{owner}/{repo}/builds/{pipeline_number}",
        f"/api/repos/{owner}/{repo}/pipelines/{pipeline_number}",
    ]
    for path in candidates:
        try:
            data = client.get_json(path)
            if isinstance(data, list):
                return [
                    _normalize_step(step) for step in data if isinstance(step, dict)
                ]
            if isinstance(data, dict):
                if isinstance(data.get("steps"), list):
                    return [
                        _normalize_step(step)
                        for step in data["steps"]
                        if isinstance(step, dict)
                    ]
                if isinstance(data.get("stages"), list):
                    return [
                        _normalize_step(step)
                        for step in data["stages"]
                        if isinstance(step, dict)
                    ]
        except Exception:
            continue
    return []


def _fetch_step_log(
    client: WoodpeckerClient,
    owner: str,
    repo: str,
    pipeline_number: int,
    step: dict[str, Any],
) -> str:
    step_id = step.get("id")
    step_number = step.get("number")
    candidates = [
        f"/api/repos/{owner}/{repo}/pipelines/{pipeline_number}/steps/{step_number}/logs",
        f"/api/repos/{owner}/{repo}/pipelines/{pipeline_number}/steps/{step_number}/log",
        f"/api/repos/{owner}/{repo}/pipelines/{pipeline_number}/steps/{step_id}/logs",
        f"/api/repos/{owner}/{repo}/pipelines/{pipeline_number}/logs/{step_id}",
    ]
    for path in candidates:
        if "None" in path:
            continue
        try:
            data = client.get_json(path)
            if isinstance(data, str):
                return data
            if isinstance(data, list):
                return "\n".join(str(x) for x in data)
            if isinstance(data, dict):
                for key in ("logs", "log", "output", "stdout"):
                    value = data.get(key)
                    if isinstance(value, str):
                        return value
                return json.dumps(data, indent=2)
        except Exception:
            try:
                return client.get_text(path)
            except Exception:
                continue
    return ""


def _is_failed_status(status: str) -> bool:
    s = status.lower()
    if s in FAILED_STATUSES:
        return True
    if s in SUCCESS_STATUSES:
        return False
    return s not in {"", "unknown", "running", "pending"}


def _detect_tool(step_name: str, log_text: str) -> str:
    name = step_name.lower()
    text = log_text.lower()
    if "black" in text or "would reformat" in text:
        return "black"
    if "ruff" in text or re.search(r"\b[A-Z]\d{3}\b", log_text):
        return "ruff"
    if "mypy" in text or " error:" in text and "[" in text:
        return "mypy"
    if "bandit" in text or "issue:" in text and "b" in text:
        return "bandit"
    if "pytest" in text or "===" in text and "failed" in text:
        return "pytest"
    if "validate_status_sync.py" in text:
        return "validate_status_sync"
    if "validate_iterloop_compliance.py" in text:
        return "validate_iterloop_compliance"
    if "validate_pr_title.py" in text:
        return "validate_pr_title"
    if "lint" in name:
        return "lint"
    if "security" in name:
        return "bandit"
    if "local-ci" in name:
        return "local-ci"
    return "generic"


def _parse_black(log_text: str) -> list[RootCause]:
    out: list[RootCause] = []
    for line in log_text.splitlines():
        m = re.search(r"would reformat\s+(.+)$", line)
        if not m:
            continue
        path = m.group(1).strip()
        out.append(
            RootCause(
                tool="black",
                kind="format",
                message=f"black formatting required: {path}",
                file=path,
                evidence=line.strip(),
                confidence="high",
            )
        )
    return out


def _parse_ruff(log_text: str) -> list[RootCause]:
    out: list[RootCause] = []
    pat = re.compile(r"^(.+?):(\d+):(\d+):\s+([A-Z]\d+)\s+(.+)$")
    for line in log_text.splitlines():
        m = pat.match(line.strip())
        if not m:
            continue
        out.append(
            RootCause(
                tool="ruff",
                kind="lint",
                file=m.group(1),
                line=int(m.group(2)),
                column=int(m.group(3)),
                rule=m.group(4),
                message=m.group(5),
                evidence=line.strip(),
                confidence="high",
            )
        )
    return out


def _parse_mypy(log_text: str) -> list[RootCause]:
    out: list[RootCause] = []
    pat = re.compile(
        r"^(.+?):(\d+):\s+(error|note):\s+(.+?)(?:\s+\[([\w\-\.]+)\])?$",
        flags=re.IGNORECASE,
    )
    for line in log_text.splitlines():
        m = pat.match(line.strip())
        if not m or m.group(3).lower() != "error":
            continue
        out.append(
            RootCause(
                tool="mypy",
                kind="type",
                file=m.group(1),
                line=int(m.group(2)),
                rule=m.group(5),
                message=m.group(4),
                evidence=line.strip(),
                confidence="high",
            )
        )
    return out


def _parse_pytest(log_text: str) -> list[RootCause]:
    out: list[RootCause] = []
    failing_tests: list[str] = []
    for line in log_text.splitlines():
        m = re.match(r"FAILED\s+(.+?)\s+-\s+(.+)$", line.strip())
        if m:
            failing_tests.append(m.group(1).strip())
            out.append(
                RootCause(
                    tool="pytest",
                    kind="test",
                    test=m.group(1).strip(),
                    message=m.group(2).strip(),
                    evidence=line.strip(),
                    confidence="high",
                )
            )
    if not out and "assert" in log_text:
        evidence = ""
        for line in log_text.splitlines():
            if line.strip().startswith("E   "):
                evidence = line.strip()
                break
        out.append(
            RootCause(
                tool="pytest",
                kind="test",
                message="pytest assertion or runtime failure",
                evidence=evidence or "assertion failure present in traceback",
                confidence="medium",
            )
        )
    if not out and failing_tests:
        for test in failing_tests:
            out.append(
                RootCause(
                    tool="pytest",
                    kind="test",
                    test=test,
                    message="test failed",
                    evidence=f"FAILED {test}",
                )
            )
    return out


def _parse_bandit(log_text: str) -> list[RootCause]:
    out: list[RootCause] = []
    issue_pat = re.compile(r"Issue:\s+\[(B\d+):[^\]]*\]\s+(.+)$")
    loc_pat = re.compile(r"Location:\s+(.+?):(\d+)(?::\d+)?")

    lines = log_text.splitlines()
    for idx, line in enumerate(lines):
        m = issue_pat.search(line)
        if not m:
            continue
        rule = m.group(1)
        msg = m.group(2).strip()
        file = None
        line_no = None
        evidence = line.strip()
        for j in range(idx + 1, min(idx + 7, len(lines))):
            mloc = loc_pat.search(lines[j])
            if mloc:
                file = mloc.group(1)
                line_no = int(mloc.group(2))
                evidence = f"{evidence} | {lines[j].strip()}"
                break
        out.append(
            RootCause(
                tool="bandit",
                kind="security",
                file=file,
                line=line_no,
                rule=rule,
                message=msg,
                evidence=evidence,
                confidence="high",
            )
        )
    return out


def _parse_validator(log_text: str, tool: str) -> list[RootCause]:
    out: list[RootCause] = []
    patterns = [
        re.compile(r"^ERROR:\s+(.+)$"),
        re.compile(r"^\s*Missing\s+.+$", flags=re.IGNORECASE),
        re.compile(r"^\s*Invalid\s+.+$", flags=re.IGNORECASE),
    ]
    for line in log_text.splitlines():
        stripped = line.strip()
        for pat in patterns:
            m = pat.match(stripped)
            if not m:
                continue
            msg = m.group(1) if m.groups() else stripped
            out.append(
                RootCause(
                    tool=tool,
                    kind="validation",
                    message=msg,
                    evidence=stripped,
                    confidence="high" if stripped.startswith("ERROR:") else "medium",
                )
            )
            break
    return out


def _parse_generic(log_text: str, step_name: str) -> list[RootCause]:
    lines = [line.strip() for line in log_text.splitlines() if line.strip()]
    tail = "\n".join(lines[-5:]) if lines else "no log output"
    return [
        RootCause(
            tool="generic",
            kind="step_failure",
            message=f"step '{step_name}' failed without structured parser match",
            evidence=tail,
            confidence="low",
        )
    ]


def parse_root_causes(step_name: str, log_text: str) -> list[RootCause]:
    tool = _detect_tool(step_name, log_text)
    parsers = {
        "black": _parse_black,
        "ruff": _parse_ruff,
        "mypy": _parse_mypy,
        "pytest": _parse_pytest,
        "bandit": _parse_bandit,
    }

    parsed: list[RootCause] = []
    if tool in parsers:
        parsed.extend(parsers[tool](log_text))
    elif tool in {
        "validate_status_sync",
        "validate_iterloop_compliance",
        "validate_pr_title",
        "lint",
        "local-ci",
    }:
        parsed.extend(_parse_validator(log_text, tool))

    if not parsed:
        if tool != "generic":
            parsed.extend(_parse_validator(log_text, tool))
    if not parsed:
        parsed.extend(_parse_generic(log_text, step_name))

    # De-duplicate
    dedup: list[RootCause] = []
    seen: set[tuple[Any, ...]] = set()
    for rc in parsed:
        key = rc.key()
        if key in seen:
            continue
        seen.add(key)
        dedup.append(rc)
    return dedup


def _select_pipeline(
    pipelines: list[dict[str, Any]], pipeline_number: int | None, pr_number: int | None
) -> dict[str, Any]:
    if pipeline_number is not None:
        for p in pipelines:
            if int(p.get("number") or -1) == pipeline_number:
                return p
        raise SystemExit(f"Pipeline #{pipeline_number} not found")

    filtered = pipelines
    if pr_number is not None:
        filtered = [p for p in pipelines if pr_number in _extract_pipeline_pr(p)]

    # Prefer latest failure, else latest run.
    for p in filtered:
        if _is_failed_status(p.get("status", "")):
            return p
    if filtered:
        return filtered[0]

    raise SystemExit("No matching pipelines found")


def _collect_local_ci(local_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    statuses: dict[str, int] = {}
    for p in sorted(local_dir.glob("*.status")):
        try:
            statuses[p.stem] = int(p.read_text(encoding="utf-8").strip())
        except Exception:
            statuses[p.stem] = 99

    pipeline = {
        "number": 0,
        "status": "failure" if any(v != 0 for v in statuses.values()) else "success",
        "event": "local",
        "ref": "local",
        "title": "local-ci-artifacts",
        "created": None,
        "updated": None,
        "source": "local",
    }

    steps: list[dict[str, Any]] = []
    for name, code in statuses.items():
        step = {
            "id": None,
            "number": None,
            "name": name,
            "status": "success" if code == 0 else "failure",
            "exit_code": code,
            "started": None,
            "stopped": None,
            "log": "",
        }
        candidate_logs = [
            local_dir / f"{name}.log",
            local_dir / f"{name}-full.log",
            local_dir / "local-ci-full.log" if name == "local-ci" else None,
        ]
        for log_path in candidate_logs:
            if log_path and log_path.exists():
                step["log"] = log_path.read_text(encoding="utf-8", errors="replace")
                break
        steps.append(step)

    return pipeline, steps


def _repro_for_tool(tool: str) -> str:
    mapping = {
        "black": "black --check .",
        "ruff": "ruff check .",
        "mypy": "mypy src scripts",
        "pytest": "pytest -q",
        "bandit": "bandit -q -r src -s B311,B107",
        "validate_status_sync": "python3 scripts/validate_status_sync.py",
        "validate_iterloop_compliance": "python3 scripts/validate_iterloop_compliance.py --story-id=<story_id>",
        "validate_pr_title": "python3 scripts/validate_pr_title.py",
        "local-ci": "./scripts/local-ci-checks.sh",
        "lint": "bash scripts/ci/swarm_triage.sh",
        "generic": "bash scripts/ci/swarm_triage.sh",
    }
    return mapping.get(tool, "bash scripts/ci/swarm_triage.sh")


def _render_markdown(result: dict[str, Any]) -> str:
    pipeline = result["pipeline"]
    lines: list[str] = []
    lines.append("## Woodpecker CI Root Cause")
    lines.append("")
    lines.append(f"- Pipeline: `{pipeline['number']}`")
    lines.append(f"- Status: `{pipeline['status']}`")
    lines.append(f"- Source: `{result['source']}`")
    lines.append("")
    lines.append("### Failed Steps")
    lines.append("")
    if not result["failed_steps"]:
        lines.append("No failed steps detected.")
        return "\n".join(lines) + "\n"

    for step in result["failed_steps"]:
        lines.append(
            f"- `{step['name']}` status=`{step['status']}` exit=`{step.get('exit_code')}`"
        )
    lines.append("")

    lines.append("### Root Causes")
    lines.append("")
    if not result["root_causes"]:
        lines.append("No root causes extracted.")
    else:
        for rc in result["root_causes"]:
            loc = ""
            if rc.get("file"):
                loc = f" ({rc['file']}:{rc.get('line') or 1})"
            rule = f" [{rc['rule']}]" if rc.get("rule") else ""
            test = f" test={rc['test']}" if rc.get("test") else ""
            lines.append(
                f"- `{rc['id']}` `{rc['tool']}`{rule}{test}: {rc['message']}{loc}"
            )
            lines.append(f"  - evidence: `{rc['evidence'][:180]}`")
    lines.append("")
    lines.append("### Repro Commands")
    lines.append("")
    for cmd in result.get("repro_commands", []):
        lines.append(f"- `{cmd}`")
    lines.append("")
    return "\n".join(lines)


def diagnose(args: argparse.Namespace) -> dict[str, Any]:
    owner = args.owner
    repo = args.repo
    source = "woodpecker-api"

    pipeline: dict[str, Any]
    steps: list[dict[str, Any]]

    if args.from_local_dir:
        source = "local-artifacts"
        pipeline, steps = _collect_local_ci(Path(args.from_local_dir))
    else:
        owner, repo = _repo_context(args)
        token = args.token or os.getenv("WOODPECKER_TOKEN")
        if not token:
            raise SystemExit(
                "Missing WOODPECKER_TOKEN. Set token or use --from-local-dir _bmad-output/ci"
            )
        client = WoodpeckerClient(args.base_url, token)
        pipelines = _list_pipelines(client, owner, repo)
        chosen = _select_pipeline(pipelines, args.pipeline, args.pr)
        pipeline_number = int(chosen["number"])
        steps = _fetch_pipeline_steps(client, owner, repo, pipeline_number)
        for step in steps:
            step["log"] = _fetch_step_log(client, owner, repo, pipeline_number, step)
        pipeline = {**chosen, "source": source}

    failed_steps = [step for step in steps if _is_failed_status(step.get("status", ""))]

    root_causes: list[dict[str, Any]] = []
    repro_commands: set[str] = set()
    idx = 1
    for step in failed_steps:
        parsed = parse_root_causes(
            step.get("name", "unknown-step"), step.get("log", "")
        )
        step_root_causes = []
        for rc in parsed:
            rc_dict = rc.to_dict(idx)
            idx += 1
            step_root_causes.append(rc_dict)
            root_causes.append(rc_dict)
            repro_commands.add(_repro_for_tool(rc.tool))
        step["root_causes"] = step_root_causes

    result = {
        "generated_at": _now_iso(),
        "source": source,
        "repo": {
            "owner": owner,
            "name": repo,
        },
        "pipeline": {
            "number": pipeline.get("number"),
            "status": pipeline.get("status"),
            "event": pipeline.get("event"),
            "ref": pipeline.get("ref"),
            "title": pipeline.get("title"),
            "created": pipeline.get("created"),
            "updated": pipeline.get("updated"),
        },
        "failed_steps": [
            {
                "name": s.get("name"),
                "status": s.get("status"),
                "exit_code": s.get("exit_code"),
                "number": s.get("number"),
                "id": s.get("id"),
                "root_causes": s.get("root_causes", []),
            }
            for s in failed_steps
        ],
        "root_causes": root_causes,
        "repro_commands": sorted(repro_commands),
    }

    if args.write_artifacts:
        pipeline_num = int(result["pipeline"].get("number") or 0)
        out_dir = Path(args.out_dir) / str(pipeline_num)
        raw_dir = out_dir / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)

        # Write raw logs
        for step in failed_steps:
            safe = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(step.get("name", "step")))
            (raw_dir / f"{safe}.log").write_text(step.get("log", ""), encoding="utf-8")

        (out_dir / "pipeline.json").write_text(
            json.dumps(result, indent=2), encoding="utf-8"
        )

        md = _render_markdown(result)
        (out_dir / "root-cause.md").write_text(md, encoding="utf-8")
        (out_dir / "root-cause.json").write_text(
            json.dumps(result.get("root_causes", []), indent=2), encoding="utf-8"
        )

        repro = ["#!/usr/bin/env bash", "set -euo pipefail", ""]
        for cmd in sorted(repro_commands):
            repro.append(cmd)
        (out_dir / "repro.sh").write_text("\n".join(repro) + "\n", encoding="utf-8")
        os.chmod(out_dir / "repro.sh", 0o755)
        result["artifact_dir"] = str(out_dir)

    return result


def status(args: argparse.Namespace) -> dict[str, Any]:
    owner, repo = _repo_context(args)
    token = args.token or os.getenv("WOODPECKER_TOKEN")
    if not token:
        raise SystemExit("Missing WOODPECKER_TOKEN")
    client = WoodpeckerClient(args.base_url, token)

    pipelines = _list_pipelines(client, owner, repo)
    if args.pr is not None:
        pipelines = [p for p in pipelines if args.pr in _extract_pipeline_pr(p)]

    if args.limit and args.limit > 0:
        pipelines = pipelines[: args.limit]

    rows = []
    for p in pipelines:
        rows.append(
            {
                "number": p.get("number"),
                "status": p.get("status"),
                "event": p.get("event"),
                "ref": p.get("ref"),
                "title": p.get("title"),
                "pr_candidates": sorted(_extract_pipeline_pr(p)),
            }
        )

    return {
        "generated_at": _now_iso(),
        "repo": {"owner": owner, "name": repo},
        "count": len(rows),
        "pipelines": rows,
    }


def _print_status_human(result: dict[str, Any]) -> None:
    print(f"Pipelines: {result['count']}")
    for row in result["pipelines"]:
        print(
            f"- #{row['number']} status={row['status']} event={row['event']} "
            f"ref={row['ref']} prs={row['pr_candidates']}"
        )


def _print_diagnose_human(result: dict[str, Any]) -> None:
    print(_render_markdown(result))
    if result.get("artifact_dir"):
        print(f"Artifacts: {result['artifact_dir']}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Woodpecker CI triage")
    p.add_argument(
        "--base-url", default=os.getenv("WOODPECKER_BASE_URL", DEFAULT_BASE_URL)
    )
    p.add_argument("--token", default=None)
    p.add_argument("--owner", default=None)
    p.add_argument("--repo", default=None)

    sub = p.add_subparsers(dest="cmd", required=True)

    p_status = sub.add_parser("status", help="Show pipeline status overview")
    p_status.add_argument("--pr", type=int, default=None)
    p_status.add_argument("--limit", type=int, default=10)
    p_status.add_argument("--format", choices=["human", "json"], default="human")

    p_diag = sub.add_parser("diagnose", help="Diagnose root causes for failed pipeline")
    p_diag.add_argument("--pr", type=int, default=None)
    p_diag.add_argument("--pipeline", type=int, default=None)
    p_diag.add_argument("--from-local-dir", default=None)
    p_diag.add_argument("--write-artifacts", action="store_true")
    p_diag.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    p_diag.add_argument("--format", choices=["human", "json"], default="human")

    p_bundle = sub.add_parser("bundle", help="Create triage artifact bundle")
    p_bundle.add_argument("--pr", type=int, default=None)
    p_bundle.add_argument("--pipeline", type=int, default=None)
    p_bundle.add_argument("--from-local-dir", default=None)
    p_bundle.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    p_bundle.add_argument("--format", choices=["human", "json"], default="human")

    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.cmd == "status":
        result = status(args)
        if args.format == "json":
            print(json.dumps(result, indent=2))
        else:
            _print_status_human(result)
        return 0

    if args.cmd in {"diagnose", "bundle"}:
        if args.cmd == "bundle":
            args.write_artifacts = True
        result = diagnose(args)
        if args.format == "json":
            print(json.dumps(result, indent=2))
        else:
            _print_diagnose_human(result)
        return 1 if result.get("failed_steps") else 0

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
