#!/usr/bin/env python3
"""Root-cause-first Woodpecker CI triage.

Priority order for failure evidence:
1. Woodpecker API (pipeline + workflow/task metadata + step logs)
2. Woodpecker DB log_entries (authoritative fallback)
3. Local captured artifacts under `_bmad-output/ci`
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

# Allow direct script execution from any worktree by exposing repo root + src.
_REPO_ROOT = Path(__file__).resolve().parents[2]
for _path in (str(_REPO_ROOT), str(_REPO_ROOT / "src")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

try:
    from config.bootstrap import bootstrap
except ModuleNotFoundError:
    from src.config.bootstrap import bootstrap

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

    def _request(self, path: str) -> tuple[dict[str, str], str]:
        url = f"{self.base_url}{path}"
        errors: list[str] = []
        for mode in ("bearer", "token", "x-token"):
            req = Request(url=url, method="GET", headers=self._headers(mode))
            try:
                with urlopen(req, timeout=20) as resp:  # nosec B310  # noqa: S310
                    headers = {k.lower(): v for k, v in dict(resp.headers).items()}
                    body = resp.read().decode("utf-8", errors="replace")
                    return headers, body
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{mode}:{exc}")
                continue
        raise RuntimeError(f"Woodpecker request failed for {url}: {' | '.join(errors)}")

    def get_json(self, path: str) -> Any:
        headers, body = self._request(path)
        ctype = headers.get("content-type", "")
        if "json" not in ctype.lower():
            raise RuntimeError(
                f"Non-JSON response for {path} (content-type={ctype}): {body[:120]}"
            )
        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid JSON from {path}: {exc}") from exc

    def get_text(self, path: str) -> str:
        _headers, body = self._request(path)
        return body


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _looks_like_html(text: str) -> bool:
    low = text.lower().lstrip()
    return low.startswith("<!doctype html") or low.startswith("<html")


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


def _resolve_repo_id(client: WoodpeckerClient, owner: str, repo: str) -> int:
    # This endpoint is reliable in this deployment.
    data = client.get_json("/api/user/repos")
    if not isinstance(data, list):
        raise RuntimeError("/api/user/repos did not return a list")
    needle = f"{owner}/{repo}".lower()
    for item in data:
        if not isinstance(item, dict):
            continue
        full_name = str(item.get("full_name") or "").lower()
        if full_name == needle:
            rid = item.get("id")
            if isinstance(rid, int):
                return rid
    raise RuntimeError(f"Unable to resolve Woodpecker repo id for {owner}/{repo}")


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
        "number": data.get("number")
        or data.get("position")
        or data.get("index")
        or data.get("pid"),
        "name": data.get("name") or data.get("step") or "unknown-step",
        "status": status,
        "exit_code": data.get("exit_code") or data.get("exitCode") or data.get("code"),
        "started": data.get("started")
        or data.get("started_at")
        or data.get("start_time"),
        "stopped": data.get("stopped")
        or data.get("finished")
        or data.get("finished_at")
        or data.get("end_time"),
        "raw": data,
    }


def _extract_steps_from_workflows(
    pipeline_detail: dict[str, Any],
) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    workflows = pipeline_detail.get("workflows")
    if not isinstance(workflows, list):
        return steps
    for workflow in workflows:
        if not isinstance(workflow, dict):
            continue
        children = workflow.get("children")
        if not isinstance(children, list):
            continue
        for child in children:
            if not isinstance(child, dict):
                continue
            steps.append(_normalize_step(child))
    return steps


def _pr_candidates(text: str) -> set[int]:
    hits: set[int] = set()
    patterns = (
        r"refs/pull/(\d+)/",
        r"\bPR[ #](\d+)\b",
        r"\bpull[ _-]?request[ #]?(\d+)\b",
    )
    for pat in patterns:
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


def _list_pipelines(client: WoodpeckerClient, repo_id: int) -> list[dict[str, Any]]:
    path = f"/api/repos/{repo_id}/pipelines?{urlencode({'per_page': 50})}"
    data = client.get_json(path)
    if not isinstance(data, list):
        raise RuntimeError(f"Unexpected response for {path}")
    return [_normalize_pipeline(item) for item in data if isinstance(item, dict)]


def _fetch_pipeline_detail(
    client: WoodpeckerClient, repo_id: int, pipeline_number: int
) -> dict[str, Any]:
    path = f"/api/repos/{repo_id}/pipelines/{pipeline_number}"
    data = client.get_json(path)
    if not isinstance(data, dict):
        raise RuntimeError(f"Unexpected response for {path}")
    return data


def _fetch_step_log_from_api(
    client: WoodpeckerClient, repo_id: int, pipeline_number: int, step: dict[str, Any]
) -> str:
    step_id = step.get("id")
    step_number = step.get("number")
    candidates = [
        f"/api/repos/{repo_id}/pipelines/{pipeline_number}/steps/{step_number}/logs",
        f"/api/repos/{repo_id}/pipelines/{pipeline_number}/steps/{step_number}/log",
        f"/api/repos/{repo_id}/pipelines/{pipeline_number}/steps/{step_id}/logs",
        f"/api/repos/{repo_id}/pipelines/{pipeline_number}/logs/{step_id}",
        f"/api/repos/{repo_id}/logs/{step_id}",
    ]
    for path in candidates:
        if "None" in path:
            continue
        try:
            # Try JSON log surfaces first.
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
        except Exception:
            pass
        try:
            text = client.get_text(path)
            if text and not _looks_like_html(text):
                return text
        except Exception:  # nosec B112
            continue
    return ""


def _is_failed_status(status: str) -> bool:
    s = str(status).lower().strip()
    if s in FAILED_STATUSES:
        return True
    if s in SUCCESS_STATUSES:
        return False
    return s not in {"", "unknown", "running", "pending"}


def _detect_tool(step_name: str, log_text: str) -> str:
    name = step_name.lower()
    text = log_text.lower()
    if name == "ci-gate" or "ci-gate: fail" in text:
        return "ci_gate"
    if "black" in text or "would reformat" in text:
        return "black"
    if "ruff" in text or re.search(r"\b[A-Z]\d{3}\b", log_text):
        return "ruff"
    if "mypy" in text or (" error:" in text and "[" in text):
        return "mypy"
    if "bandit" in text or ("issue:" in text and "b" in text):
        return "bandit"
    if "pytest" in text or ("===" in text and "failed" in text):
        return "pytest"
    if "validate_status_sync.py" in text:
        return "validate_status_sync"
    if "validate_iterloop_compliance.py" in text:
        return "validate_iterloop_compliance"
    if "validate_metacog_compliance.py" in text:
        return "validate_metacog_compliance"
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
        if m:
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
        if m:
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
        if m and m.group(3).lower() == "error":
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
    for line in log_text.splitlines():
        m = re.match(r"FAILED\s+(.+?)\s+-\s+(.+)$", line.strip())
        if m:
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
        evidence = next(
            (
                line.strip()
                for line in log_text.splitlines()
                if line.strip().startswith("E   ")
            ),
            "assertion failure present in traceback",
        )
        out.append(
            RootCause(
                tool="pytest",
                kind="test",
                message="pytest assertion or runtime failure",
                evidence=evidence,
                confidence="medium",
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
            loc = loc_pat.search(lines[j])
            if loc:
                file = loc.group(1)
                line_no = int(loc.group(2))
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
            if m:
                msg = m.group(1) if m.groups() else stripped
                out.append(
                    RootCause(
                        tool=tool,
                        kind="validation",
                        message=msg,
                        evidence=stripped,
                        confidence=(
                            "high" if stripped.startswith("ERROR:") else "medium"
                        ),
                    )
                )
                break
    return out


def _parse_ci_gate(log_text: str) -> list[RootCause]:
    out: list[RootCause] = []
    for line in log_text.splitlines():
        stripped = line.strip()
        m = re.match(r"-\s+([\w.-]+\.status):\s*(\d+)$", stripped)
        if m:
            out.append(
                RootCause(
                    tool="ci_gate",
                    kind="status_file",
                    message=f"captured step failed: {m.group(1)}={m.group(2)}",
                    evidence=stripped,
                    confidence="high",
                )
            )
            continue
        if stripped.startswith("ERROR:"):
            out.append(
                RootCause(
                    tool="ci_gate",
                    kind="validator_error",
                    message=stripped[6:].strip(),
                    evidence=stripped,
                    confidence="high",
                )
            )
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
        "ci_gate": _parse_ci_gate,
    }

    parsed: list[RootCause] = []
    if tool in parsers:
        parsed.extend(parsers[tool](log_text))
    elif tool in {
        "validate_status_sync",
        "validate_iterloop_compliance",
        "validate_metacog_compliance",
        "validate_pr_title",
        "lint",
        "local-ci",
    }:
        parsed.extend(_parse_validator(log_text, tool))

    if not parsed and tool != "generic":
        parsed.extend(_parse_validator(log_text, tool))
    if not parsed:
        parsed.extend(_parse_generic(log_text, step_name))

    dedup: list[RootCause] = []
    seen: set[tuple[Any, ...]] = set()
    for rc in parsed:
        key = rc.key()
        if key not in seen:
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
        "id": 0,
        "status": "failure" if any(v != 0 for v in statuses.values()) else "success",
        "event": "local",
        "ref": "local",
        "title": "local-ci-artifacts",
        "created": None,
        "updated": None,
    }

    steps: list[dict[str, Any]] = []
    for name, code in statuses.items():
        step: dict[str, Any] = {
            "id": None,
            "number": None,
            "name": name,
            "status": "success" if code == 0 else "failure",
            "exit_code": code,
            "started": None,
            "stopped": None,
            "log": "",
            "raw": {},
        }
        candidates = [
            local_dir / f"{name}.log",
            local_dir / f"{name}-full.log",
            local_dir / "local-ci-full.log" if name == "local-ci" else None,
        ]
        for log_path in candidates:
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
        "validate_iterloop_compliance": (
            "python3 scripts/validate_iterloop_compliance.py --story-id=<story_id>"
        ),
        "validate_metacog_compliance": (
            "python3 scripts/validation/validate_metacog_compliance.py --story-id=<story_id> --strict"
        ),
        "validate_pr_title": "python3 scripts/validate_pr_title.py",
        "local-ci": "./scripts/local-ci-checks.sh",
        "lint": "bash scripts/ci/swarm_triage.sh",
        "generic": "bash scripts/ci/swarm_triage.sh",
    }
    return mapping.get(tool, "bash scripts/ci/swarm_triage.sh")


def _render_markdown(result: dict[str, Any]) -> str:
    p = result["pipeline"]
    lines = [
        "## Woodpecker CI Root Cause",
        "",
        f"- Pipeline: `{p['number']}`",
        f"- Status: `{p['status']}`",
        f"- Source: `{result['source']}`",
        "",
        "### Failed Steps",
        "",
    ]
    if not result["failed_steps"]:
        lines.append("No failed steps detected.")
        return "\n".join(lines) + "\n"

    for step in result["failed_steps"]:
        lines.append(
            f"- `{step['name']}` status=`{step['status']}` exit=`{step.get('exit_code')}`"
        )

    lines.extend(["", "### Root Causes", ""])
    if not result["root_causes"]:
        lines.append("No root causes extracted.")
    else:
        for rc in result["root_causes"]:
            loc = f" ({rc['file']}:{rc.get('line') or 1})" if rc.get("file") else ""
            rule = f" [{rc['rule']}]" if rc.get("rule") else ""
            test = f" test={rc['test']}" if rc.get("test") else ""
            lines.append(
                f"- `{rc['id']}` `{rc['tool']}`{rule}{test}: {rc['message']}{loc}"
            )
            lines.append(f"  - evidence: `{rc['evidence'][:180]}`")

    lines.extend(["", "### Repro Commands", ""])
    for cmd in result.get("repro_commands", []):
        lines.append(f"- `{cmd}`")
    lines.append("")
    return "\n".join(lines)


def _detect_db_dsn(args: argparse.Namespace) -> str | None:
    if args.db_dsn:
        return args.db_dsn
    for key in ("WOODPECKER_DB_DSN", "WOODPECKER_DATABASE_DATASOURCE"):
        val = os.getenv(key)
        if val:
            return val

    if not shutil.which("docker"):
        return None
    try:
        proc = subprocess.run(  # nosec B607
            [
                "docker",
                "inspect",
                "woodpecker-server",
                "--format",
                "{{json .Config.Env}}",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        if proc.returncode != 0:
            return None
        envs = json.loads(proc.stdout.strip())
        if not isinstance(envs, list):
            return None
        for item in envs:
            if isinstance(item, str) and item.startswith(
                "WOODPECKER_DATABASE_DATASOURCE="
            ):
                return item.split("=", 1)[1]
    except Exception:
        return None
    return None


def _rewrite_dsn_host(dsn: str, new_host: str) -> str:
    parsed = urlparse(dsn)
    if not parsed.hostname:
        return dsn
    netloc = parsed.netloc
    userinfo = ""
    if "@" in netloc:
        userinfo, hostport = netloc.rsplit("@", 1)
    else:
        pass
    port = f":{parsed.port}" if parsed.port else ""
    new_netloc = f"{userinfo + '@' if userinfo else ''}{new_host}{port}"
    return urlunparse(parsed._replace(netloc=new_netloc))


def _dsn_candidates(base_dsn: str) -> list[str]:
    dsn_list = [base_dsn]
    host = urlparse(base_dsn).hostname or ""
    if host in {"chiseai-postgres", "postgres", "localhost", "127.0.0.1"}:
        dsn_list.append(_rewrite_dsn_host(base_dsn, "host.docker.internal"))
    if host != "localhost":
        dsn_list.append(_rewrite_dsn_host(base_dsn, "localhost"))
    dedup: list[str] = []
    for dsn in dsn_list:
        if dsn not in dedup:
            dedup.append(dsn)
    return dedup


def _fetch_db_logs(
    pipeline_id: int, step_ids: list[int], db_dsn: str | None
) -> tuple[dict[int, str], str | None]:
    if not db_dsn or not shutil.which("psql"):
        return {}, None

    for candidate_dsn in _dsn_candidates(db_dsn):
        logs: dict[int, str] = {}
        ok = True
        for step_id in step_ids:
            sql = (
                "select convert_from(data,'UTF8') "
                "from log_entries "
                f"where step_id={step_id} "
                "order by line;"
            )
            proc = subprocess.run(  # nosec B607
                ["psql", candidate_dsn, "-At", "-q", "-c", sql],
                capture_output=True,
                text=True,
                check=False,
                timeout=15,
            )
            if proc.returncode != 0:
                ok = False
                break
            text = proc.stdout or ""
            if text.strip():
                logs[step_id] = text

        if ok:
            # verify we queried correct pipeline by checking step ids exist
            verify_sql = (
                "select count(*) from steps "
                f"where pipeline_id={pipeline_id} "
                f"and id in ({','.join(str(i) for i in step_ids)});"
            )
            verify = subprocess.run(  # nosec B607
                ["psql", candidate_dsn, "-At", "-q", "-c", verify_sql],
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
            if verify.returncode == 0:
                try:
                    count = int((verify.stdout or "0").strip() or "0")
                    if count > 0:
                        return logs, candidate_dsn
                except ValueError:
                    pass
    return {}, None


def _finalize_result(
    result_source: str,
    owner: str | None,
    repo: str | None,
    pipeline: dict[str, Any],
    steps: list[dict[str, Any]],
) -> dict[str, Any]:
    failed_steps = [step for step in steps if _is_failed_status(step.get("status", ""))]

    root_causes: list[dict[str, Any]] = []
    repro_commands: set[str] = set()
    idx = 1

    for step in failed_steps:
        parsed = parse_root_causes(
            step.get("name", "unknown-step"), step.get("log", "")
        )
        step_causes: list[dict[str, Any]] = []
        for rc in parsed:
            rc_dict = rc.to_dict(idx)
            idx += 1
            step_causes.append(rc_dict)
            root_causes.append(rc_dict)
            repro_commands.add(_repro_for_tool(rc.tool))
        step["root_causes"] = step_causes

    return {
        "generated_at": _now_iso(),
        "source": result_source,
        "repo": {"owner": owner, "name": repo},
        "pipeline": {
            "number": pipeline.get("number"),
            "id": pipeline.get("id"),
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


def diagnose(args: argparse.Namespace) -> dict[str, Any]:
    if args.from_local_dir:
        pipeline, steps = _collect_local_ci(Path(args.from_local_dir))
        result = _finalize_result("local-artifacts", None, None, pipeline, steps)
        return _write_artifacts_if_needed(result, steps, args)

    owner, repo = _repo_context(args)
    token = args.token or os.getenv("WOODPECKER_TOKEN")
    if not token:
        raise SystemExit(
            "Missing WOODPECKER_TOKEN. Set token or use --from-local-dir _bmad-output/ci"
        )

    client = WoodpeckerClient(args.base_url, token)
    repo_id = _resolve_repo_id(client, owner, repo)
    pipelines = _list_pipelines(client, repo_id)
    chosen = _select_pipeline(pipelines, args.pipeline, args.pr)

    pipeline_number = int(chosen["number"])
    detail = _fetch_pipeline_detail(client, repo_id, pipeline_number)
    detail_norm = _normalize_pipeline(detail)

    steps = _extract_steps_from_workflows(detail)
    for step in steps:
        step["log"] = _fetch_step_log_from_api(client, repo_id, pipeline_number, step)

    source_parts = ["woodpecker-api"]

    missing_failed = [
        s
        for s in steps
        if _is_failed_status(s.get("status", "")) and not (s.get("log") or "").strip()
    ]
    if missing_failed:
        db_dsn = _detect_db_dsn(args)
        step_ids = [
            int(s["id"]) for s in missing_failed if isinstance(s.get("id"), int)
        ]
        db_logs, used_dsn = _fetch_db_logs(
            int(detail_norm.get("id") or 0), step_ids, db_dsn
        )
        if used_dsn:
            source_parts.append("woodpecker-db")
        for step in missing_failed:
            sid = step.get("id")
            if isinstance(sid, int) and sid in db_logs and db_logs[sid].strip():
                step["log"] = db_logs[sid]

    result = _finalize_result("+".join(source_parts), owner, repo, detail_norm, steps)
    return _write_artifacts_if_needed(result, steps, args)


def _write_artifacts_if_needed(
    result: dict[str, Any], steps: list[dict[str, Any]], args: argparse.Namespace
) -> dict[str, Any]:
    if not args.write_artifacts:
        return result

    pipeline_num = int(result["pipeline"].get("number") or 0)
    out_dir = Path(args.out_dir) / str(pipeline_num)
    raw_dir = out_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    failed_ids = {(s.get("id"), s.get("name")) for s in result.get("failed_steps", [])}
    for step in steps:
        key = (step.get("id"), step.get("name"))
        if key not in failed_ids:
            continue
        safe_name = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(step.get("name", "step")))
        (raw_dir / f"{safe_name}.log").write_text(step.get("log", ""), encoding="utf-8")

    (out_dir / "pipeline.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    (out_dir / "root-cause.json").write_text(
        json.dumps(result.get("root_causes", []), indent=2), encoding="utf-8"
    )
    (out_dir / "root-cause.md").write_text(_render_markdown(result), encoding="utf-8")

    repro = ["#!/usr/bin/env bash", "set -euo pipefail", ""]
    for cmd in result.get("repro_commands", []):
        repro.append(cmd)
    (out_dir / "repro.sh").write_text("\n".join(repro) + "\n", encoding="utf-8")
    os.chmod(out_dir / "repro.sh", 0o700)
    result["artifact_dir"] = str(out_dir)
    return result


def status(args: argparse.Namespace) -> dict[str, Any]:
    owner, repo = _repo_context(args)
    token = args.token or os.getenv("WOODPECKER_TOKEN")
    if not token:
        raise SystemExit("Missing WOODPECKER_TOKEN")

    client = WoodpeckerClient(args.base_url, token)
    repo_id = _resolve_repo_id(client, owner, repo)
    pipelines = _list_pipelines(client, repo_id)

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
        "repo": {"owner": owner, "name": repo, "repo_id": repo_id},
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
    parser = argparse.ArgumentParser(description="Woodpecker CI triage")
    parser.add_argument(
        "--base-url", default=os.getenv("WOODPECKER_BASE_URL", DEFAULT_BASE_URL)
    )
    parser.add_argument("--token", default=None)
    parser.add_argument("--owner", default=None)
    parser.add_argument("--repo", default=None)
    parser.add_argument(
        "--db-dsn",
        default=None,
        help="Optional Woodpecker Postgres DSN for step-log fallback",
    )

    sub = parser.add_subparsers(dest="cmd", required=True)

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

    return parser


def main() -> int:
    # Bootstrap environment first
    bootstrap(load_env=True)
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
