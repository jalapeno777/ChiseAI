"""Execution incident publishing helpers.

Publishes hard-failure incidents to:
1) Redis stream (for autonomous system consumption)
2) Discord webhook (for operator visibility)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import UTC, datetime
from urllib import request
from urllib.error import HTTPError, URLError

import redis

logger = logging.getLogger(__name__)


def _redis_client() -> redis.Redis:
    host = os.getenv("REDIS_HOST", "host.docker.internal")
    port = int(os.getenv("REDIS_PORT", "6380"))
    db = int(os.getenv("REDIS_DB", "0"))
    return redis.Redis(host=host, port=port, db=db, decode_responses=True)


def _incident_stream_name() -> str:
    return os.getenv("TRADING_INCIDENT_STREAM", "bmad:chiseai:incidents:stream")


def _discord_webhook_url() -> str:
    return os.getenv("DISCORD_TRADING_WEBHOOK_URL", "").strip() or os.getenv(
        "DISCORD_WEBHOOK_URL", ""
    ).strip()


def _publish_to_redis_sync(payload: dict[str, object]) -> None:
    try:
        client = _redis_client()
        client.xadd(
            _incident_stream_name(),
            {
                "event_type": "trading_incident",
                "severity": str(payload.get("severity", "P2")),
                "incident_id": str(payload.get("incident_id", "unknown")),
                "payload": json.dumps(payload, sort_keys=True),
            },
            maxlen=10000,
            approximate=True,
        )
    except Exception:
        logger.exception("Failed to publish trading incident to Redis stream")


def _post_discord_sync(payload: dict[str, object]) -> None:
    webhook = _discord_webhook_url()
    if not webhook:
        return
    text = (
        f"[{payload.get('severity', 'P2')}] {payload.get('title', 'Trading incident')}\n"
        f"{payload.get('message', '')}\n"
        f"incident_id={payload.get('incident_id', 'unknown')}"
    )
    body = json.dumps({"content": text}).encode("utf-8")
    req = request.Request(
        webhook,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=10):
            pass
    except HTTPError as e:
        logger.warning(
            "Discord webhook rejected trading incident (%s): HTTP %s %s",
            payload.get("incident_id", "unknown"),
            e.code,
            e.reason,
        )
    except URLError as e:
        logger.warning(
            "Discord webhook network error for trading incident (%s): %s",
            payload.get("incident_id", "unknown"),
            e.reason,
        )
    except Exception:
        logger.exception(
            "Unexpected error posting trading incident to Discord webhook (%s)",
            payload.get("incident_id", "unknown"),
        )


async def publish_execution_incident(
    incident_type: str,
    severity: str,
    title: str,
    message: str,
    context: dict[str, object] | None = None,
) -> None:
    """Publish execution incident to Redis stream and Discord webhook."""
    incident_id = f"exec-{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}"
    payload: dict[str, object] = {
        "incident_id": incident_id,
        "incident_type": incident_type,
        "severity": severity,
        "title": title,
        "message": message,
        "context": context or {},
        "source": "paper_trading_execution",
        "timestamp": datetime.now(UTC).isoformat(),
    }
    await asyncio.to_thread(_publish_to_redis_sync, payload)
    await asyncio.to_thread(_post_discord_sync, payload)
