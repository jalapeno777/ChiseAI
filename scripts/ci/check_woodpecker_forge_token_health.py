#!/usr/bin/env python3
"""Validate Woodpecker forge token health from Postgres user records.

Why this exists:
- Woodpecker can fail pre-step with opaque forge/config errors when stored OAuth
  access tokens expire or when DB `users.expiry` drifts from JWT `exp`.
- This script provides a deterministic preflight check for ops/local CI.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
from config.bootstrap import bootstrap


@dataclass
class TokenHealth:
    user_id: int
    login: str
    db_expiry: int
    jwt_exp: int
    seconds_left: int
    token_prefix: str


def _rewrite_dsn_host(dsn: str, new_host: str) -> str:
    parsed = urlparse(dsn)
    if not parsed.hostname:
        return dsn
    netloc = parsed.netloc
    userinfo = ""
    if "@" in netloc:
        userinfo, _ = netloc.rsplit("@", 1)
    port = f":{parsed.port}" if parsed.port else ""
    new_netloc = f"{userinfo + '@' if userinfo else ''}{new_host}{port}"
    return urlunparse(parsed._replace(netloc=new_netloc))


def _dsn_candidates(base_dsn: str) -> list[str]:
    host = (urlparse(base_dsn).hostname or "").strip().lower()
    candidates = [base_dsn]
    if host in {"chiseai-postgres", "postgres", "localhost", "127.0.0.1"}:
        candidates.append(_rewrite_dsn_host(base_dsn, "host.docker.internal"))
    if host != "localhost":
        candidates.append(_rewrite_dsn_host(base_dsn, "localhost"))
    dedup: list[str] = []
    for dsn in candidates:
        if dsn not in dedup:
            dedup.append(dsn)
    return dedup


def _decode_jwt_exp(jwt: str) -> int:
    parts = jwt.split(".")
    if len(parts) != 3:
        raise ValueError("token is not a JWT (3-part token expected)")
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    data = json.loads(base64.urlsafe_b64decode(payload.encode("utf-8")))
    exp = data.get("exp")
    if not isinstance(exp, int):
        raise ValueError("JWT payload missing integer exp")
    return exp


def _query_users(dsn: str) -> list[dict[str, Any]]:
    sql = (
        "select id,login,coalesce(expiry,0),coalesce(token,'') from users order by id;"
    )
    proc = subprocess.run(
        ["psql", dsn, "-At", "-q", "-F", "|", "-c", sql],
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "psql query failed")

    rows: list[dict[str, Any]] = []
    for line in (proc.stdout or "").splitlines():
        if not line.strip():
            continue
        user_id_s, login, expiry_s, token = line.split("|", 3)
        rows.append(
            {
                "id": int(user_id_s),
                "login": login,
                "expiry": int(expiry_s or "0"),
                "token": token,
            }
        )
    return rows


def _discover_dsn(explicit_dsn: str | None) -> str:
    if explicit_dsn:
        return explicit_dsn

    env_dsn = os.getenv("WOODPECKER_DATABASE_DATASOURCE", "").strip()
    if env_dsn:
        return env_dsn

    if shutil.which("docker"):
        proc = subprocess.run(
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
        if proc.returncode == 0:
            try:
                envs = json.loads(proc.stdout.strip())
                if isinstance(envs, list):
                    for item in envs:
                        if isinstance(item, str) and item.startswith(
                            "WOODPECKER_DATABASE_DATASOURCE="
                        ):
                            return item.split("=", 1)[1]
            except Exception:
                pass

    raise SystemExit(
        "Could not determine DSN. Pass --dsn or set WOODPECKER_DATABASE_DATASOURCE."
    )


def _collect_health(
    dsn: str, require_logins: set[str]
) -> tuple[list[TokenHealth], str]:
    last_error = ""
    for candidate in _dsn_candidates(dsn):
        try:
            rows = _query_users(candidate)
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            continue

        now = int(time.time())
        health: list[TokenHealth] = []
        for row in rows:
            login = row["login"]
            if require_logins and login not in require_logins:
                continue
            token = row["token"]
            if not token:
                continue
            jwt_exp = _decode_jwt_exp(token)
            health.append(
                TokenHealth(
                    user_id=row["id"],
                    login=login,
                    db_expiry=row["expiry"],
                    jwt_exp=jwt_exp,
                    seconds_left=jwt_exp - now,
                    token_prefix=token[:16],
                )
            )
        return health, candidate

    raise SystemExit(f"Failed querying users via DSN candidates: {last_error}")


def main() -> int:
    bootstrap(load_env=True)

    parser = argparse.ArgumentParser(
        description="Check Woodpecker forge token expiry drift and near-expiry risk"
    )
    parser.add_argument(
        "--dsn",
        default=None,
        help="Postgres DSN for Woodpecker DB. Defaults from env/docker inspect.",
    )
    parser.add_argument(
        "--warn-seconds",
        type=int,
        default=900,
        help="Warn/fail when token expires within this many seconds (default: 900).",
    )
    parser.add_argument(
        "--drift-seconds",
        type=int,
        default=60,
        help="Allowable absolute delta between users.expiry and JWT exp.",
    )
    parser.add_argument(
        "--require-user",
        action="append",
        default=[],
        help="Restrict checks to one or more specific user logins.",
    )
    parser.add_argument(
        "--warn-only",
        action="store_true",
        help="Never return non-zero; print WARN messages instead.",
    )
    args = parser.parse_args()

    dsn = _discover_dsn(args.dsn)
    require_logins = {u.strip() for u in args.require_user if u.strip()}
    health, used_dsn = _collect_health(dsn, require_logins)

    if not health:
        print("WARN: No Woodpecker users with tokens matched the query scope.")
        return 0

    failures: list[str] = []
    warnings: list[str] = []
    for item in health:
        drift = abs(item.db_expiry - item.jwt_exp)
        base = (
            f"user={item.login} id={item.user_id} "
            f"db_expiry={item.db_expiry} jwt_exp={item.jwt_exp} "
            f"seconds_left={item.seconds_left} token_prefix={item.token_prefix}"
        )
        if drift > args.drift_seconds:
            failures.append(f"expiry drift exceeds threshold: {base}")
        if item.seconds_left <= 0:
            failures.append(f"token already expired: {base}")
        elif item.seconds_left <= args.warn_seconds:
            warnings.append(f"token near expiry: {base}")

    print(
        f"INFO: checked {len(health)} user token(s) using DSN {shlex.quote(used_dsn)}"
    )
    for msg in warnings:
        print(f"WARN: {msg}")

    if failures:
        if args.warn_only:
            for msg in failures:
                print(f"WARN: {msg}")
            print("WARN: token health violations detected (warn-only mode)")
            return 0
        for msg in failures:
            print(f"ERROR: {msg}")
        return 1

    print("OK: Woodpecker forge token health is within configured thresholds")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
