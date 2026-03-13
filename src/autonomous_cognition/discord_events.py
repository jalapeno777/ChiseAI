"""Discord event helpers for autonomous cognition notifications."""

from __future__ import annotations

from typing import Any

from governance.notifications.discord_notifier import DiscordNotifier


async def emit_autocog_event(
    notifier: DiscordNotifier,
    event_type: str,
    severity: str,
    summary: str,
    impact: str,
    top_metrics: dict[str, Any],
    artifact_path: str | None,
    run_id: str,
) -> bool:
    """Emit a standardized autonomous cognition event."""
    return await notifier.notify_autocog_event(
        event_type=event_type,
        severity=severity,
        summary=summary,
        impact=impact,
        top_metrics=top_metrics,
        artifact_path=artifact_path,
        run_id=run_id,
    )

