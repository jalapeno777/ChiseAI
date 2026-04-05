#!/usr/bin/env python3
"""Compute stale push failure KPI from recent Woodpecker pipelines.

A stale push failure is counted when:
- pipeline event is push
- ref targets feature/*
- step `pre-pr-merge-check` failed
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

DEFAULT_BASE_URL = "http://host.docker.internal:8012"


@dataclass
class KPI:
    timestamp_utc: str
    total_push_feature: int
    stale_push_failures: int
    ratio: float
    threshold: float
    alert: bool
    sampled_pipelines: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp_utc": self.timestamp_utc,
            "total_push_feature": self.total_push_feature,
            "stale_push_failures": self.stale_push_failures,
            "ratio": self.ratio,
            "threshold": self.threshold,
            "alert": self.alert,
            "sampled_pipelines": self.sampled_pipelines,
        }


class WoodpeckerClient:
    def __init__(self, base_url: str, token: str | None):
        self.base_url = base_url.rstrip("/")
        self.token = (token or "").strip()
        self._preferred_auth_mode: str | None = None

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

    def _request_json(self, path: str) -> Any:
        url = f"{self.base_url}{path}"
        modes: list[str] = []
        if self._preferred_auth_mode in {"bearer", "token", "x-token"}:
            modes.append(self._preferred_auth_mode)
        for mode in ("bearer", "token", "x-token"):
            if mode not in modes:
                modes.append(mode)
        errors: list[str] = []
        for mode in modes:
            req = Request(url, headers=self._headers(mode), method="GET")
            try:
                with urlopen(req, timeout=20) as resp:  # nosec B310
                    body = resp.read().decode("utf-8", errors="replace")
                    self._preferred_auth_mode = mode
                    return json.loads(body)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{mode}:{exc}")
                continue
        raise RuntimeError(f"Woodpecker request failed for {url}: {' | '.join(errors)}")

    def repo_id(self, owner: str, repo: str) -> int:
        rows = self._request_json("/api/user/repos")
        if not isinstance(rows, list):
            raise RuntimeError("Unexpected /api/user/repos payload")
        needle = f"{owner}/{repo}".lower()
        for row in rows:
            if not isinstance(row, dict):
                continue
            if str(row.get("full_name", "")).lower() == needle:
                rid = row.get("id")
                if isinstance(rid, int):
                    return rid
        raise RuntimeError(f"Unable to resolve repo id for {owner}/{repo}")

    def list_pipelines(self, repo_id: int, limit: int) -> list[dict[str, Any]]:
        rows = self._request_json(f"/api/repos/{repo_id}/pipelines?per_page={limit}")
        if not isinstance(rows, list):
            return []
        return [row for row in rows if isinstance(row, dict)]

    def pipeline_detail(self, repo_id: int, number: int) -> dict[str, Any]:
        row = self._request_json(f"/api/repos/{repo_id}/pipelines/{number}")
        if not isinstance(row, dict):
            return {}
        return row


def _is_failed(status: str) -> bool:
    return status.strip().lower() in {"failure", "failed", "error", "killed", "blocked"}


def _extract_steps(detail: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    workflows = detail.get("workflows")
    if not isinstance(workflows, list):
        return out
    for wf in workflows:
        if not isinstance(wf, dict):
            continue
        children = wf.get("children")
        if not isinstance(children, list):
            continue
        for c in children:
            if isinstance(c, dict):
                out.append(c)
    return out


def _is_stale_push_failure(detail: dict[str, Any]) -> bool:
    for step in _extract_steps(detail):
        name = str(step.get("name") or "").strip().lower()
        status = str(step.get("status") or step.get("state") or "").strip().lower()
        if name == "pre-pr-merge-check" and _is_failed(status):
            return True
    return False


def _send_alert(webhook_url: str, payload: dict[str, Any]) -> None:
    content = (
        "🚨 Stale push KPI exceeded threshold: "
        f"{payload['stale_push_failures']}/{payload['total_push_feature']} "
        f"({payload['ratio']:.2%}, threshold={payload['threshold']:.2%})"
    )
    body = json.dumps({"content": content}).encode("utf-8")
    req = Request(
        webhook_url,
        method="POST",
        headers={"Content-Type": "application/json"},
        data=body,
    )
    with urlopen(req, timeout=15):  # nosec B310
        pass


def _write_redis(payload: dict[str, Any]) -> None:
    host = os.getenv("CHISE_REDIS_HOST", "host.docker.internal")
    port = os.getenv("CHISE_REDIS_PORT", "6380")
    db = os.getenv("CHISE_REDIS_DB", "0")
    cmd = [
        "redis-cli",
        "-h",
        host,
        "-p",
        str(port),
        "-n",
        str(db),
        "SET",
        "bmad:chiseai:kpi:stale-push:last",
        json.dumps(payload),
    ]
    subprocess.run(cmd, check=False, capture_output=True, text=True)


def run(args: argparse.Namespace) -> int:
    owner = os.getenv("GITEA_OWNER", "craig")
    repo = os.getenv("GITEA_REPO", "ChiseAI")
    base_url = os.getenv("WOODPECKER_BASE_URL", DEFAULT_BASE_URL)
    token = os.getenv("WOODPECKER_TOKEN", "")
    if not token:
        print("WOODPECKER_TOKEN is required", file=sys.stderr)
        return 2

    client = WoodpeckerClient(base_url, token)
    repo_id = client.repo_id(owner, repo)
    pipelines = client.list_pipelines(repo_id, args.limit)

    total_push_feature = 0
    stale_push_failures = 0

    for row in pipelines:
        event = str(row.get("event") or "").strip().lower()
        ref = str(row.get("ref") or "").strip()
        number = row.get("number")
        if event != "push":
            continue
        if not ref.startswith("refs/heads/feature/"):
            continue
        if not isinstance(number, int):
            continue
        total_push_feature += 1
        detail = client.pipeline_detail(repo_id, number)
        if _is_stale_push_failure(detail):
            stale_push_failures += 1

    ratio = (
        float(stale_push_failures) / float(total_push_feature)
        if total_push_feature
        else 0.0
    )
    payload = KPI(
        timestamp_utc=datetime.now(UTC).replace(microsecond=0).isoformat(),
        total_push_feature=total_push_feature,
        stale_push_failures=stale_push_failures,
        ratio=ratio,
        threshold=args.threshold,
        alert=ratio >= args.threshold and total_push_feature > 0,
        sampled_pipelines=len(pipelines),
    ).to_dict()

    if args.output_json:
        out_path = Path(args.output_json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    if args.write_redis:
        _write_redis(payload)

    print(json.dumps(payload, indent=2))

    webhook = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
    if payload["alert"] and webhook:
        try:
            _send_alert(webhook, payload)
        except Exception as exc:  # noqa: BLE001
            print(f"WARN: failed to send stale-push KPI alert: {exc}", file=sys.stderr)

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Stale push KPI from Woodpecker")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--threshold", type=float, default=0.30)
    parser.add_argument("--output-json", type=str, default="")
    parser.add_argument("--write-redis", action="store_true")
    args = parser.parse_args()
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
