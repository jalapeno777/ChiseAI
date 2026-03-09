#!/usr/bin/env python3
"""Autonomy event bus utility (Redis + local JSONL fallback)."""

from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def now_iso() -> str:
    return (
        datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    )


def redis_client():
    try:
        import redis

        port = int(
            os.getenv("REDIS_PORT")
            or os.getenv("CHISE_REDIS_PORT")
            or os.getenv("ACP_REDIS_PORT")
            or "6380"
        )
        db = int(os.getenv("REDIS_DB", "0"))
        hosts = [
            os.getenv("REDIS_HOST"),
            os.getenv("CHISE_REDIS_HOST"),
            os.getenv("ACP_REDIS_HOST"),
            "chiseai-redis",
            "host.docker.internal",
            "localhost",
        ]
        hosts = [h for i, h in enumerate(hosts) if h and h not in hosts[:i]]
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
                return client
            except Exception:
                continue
        return None
    except Exception:
        return None


def build_event(
    *,
    event_type: str,
    producer: str,
    severity: str = "info",
    story_id: str | None = None,
    payload: dict[str, Any] | None = None,
    payload_schema_version: str = "1.0",
) -> dict[str, Any]:
    return {
        "event_id": f"evt-{uuid.uuid4()}",
        "event_type": event_type,
        "story_id": story_id,
        "timestamp_utc": now_iso(),
        "producer": producer,
        "severity": severity,
        "payload_schema_version": payload_schema_version,
        "payload": payload or {},
    }


def publish_event(
    event: dict[str, Any],
    *,
    output_dir: Path = Path("_bmad-output/full-pilot"),
    redis_stream: str = "bmad:chiseai:events:autonomy",
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / "events.jsonl"
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, sort_keys=True) + "\n")

    client = redis_client()
    if client is None:
        return
    try:
        # Keep JSON payload as stream field for simple consumption.
        client.xadd(redis_stream, {"event": json.dumps(event, sort_keys=True)}, maxlen=5000)
    except Exception:
        pass
