"""Skip rate monitoring for autonomous cognition candidates."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class SkipRateMonitor:
    """Monitors candidate skip rate and alerts if threshold exceeded."""

    DEFAULT_WINDOW_DAYS = 7
    DEFAULT_ALERT_THRESHOLD = 0.20  # 20%

    def __init__(
        self,
        window_days: int = DEFAULT_WINDOW_DAYS,
        alert_threshold: float = DEFAULT_ALERT_THRESHOLD,
        cycles_dir: str | Path = "_bmad-output/autocog/cycles",
    ):
        self._window_days = window_days
        self._alert_threshold = alert_threshold
        self._cycles_dir = Path(cycles_dir)

    def check_skip_rate(self) -> dict[str, Any]:
        """Check skip rate over the configured window and return status."""
        skip_data = self._collect_skip_data()

        if not skip_data:
            return {
                "skip_rate": 0.0,
                "total_candidates": 0,
                "skipped_candidates": 0,
                "alert_triggered": False,
                "window_days": self._window_days,
                "message": "No data available in window",
            }

        total_candidates = sum(d["total"] for d in skip_data)
        total_skipped = sum(d["skipped"] for d in skip_data)

        skip_rate = total_skipped / total_candidates if total_candidates > 0 else 0.0
        alert_triggered = skip_rate > self._alert_threshold

        result = {
            "skip_rate": round(skip_rate, 4),
            "total_candidates": total_candidates,
            "skipped_candidates": total_skipped,
            "alert_triggered": alert_triggered,
            "window_days": self._window_days,
            "threshold": self._alert_threshold,
            "data_points": len(skip_data),
        }

        if alert_triggered:
            result["alert_message"] = (
                f"SKIP RATE ALERT: {skip_rate:.1%} skip rate exceeds "
                f"threshold of {self._alert_threshold:.1%} over "
                f"{self._window_days} days"
            )
            logger.warning(result["alert_message"])

        return result

    def _collect_skip_data(self) -> list[dict[str, int]]:
        """Collect skip data from cycle artifacts within window."""
        if not self._cycles_dir.exists():
            return []

        cutoff_date = datetime.now(UTC) - timedelta(days=self._window_days)
        skip_data: list[dict[str, int]] = []

        for cycle_file in self._cycles_dir.glob("autocog-*.json"):
            try:
                stat = cycle_file.stat()
                file_mtime = datetime.fromtimestamp(stat.st_mtime, UTC)

                if file_mtime < cutoff_date:
                    continue

                data = json.loads(cycle_file.read_text(encoding="utf-8"))
                metrics = data.get("metrics", {})
                candidate_skips = metrics.get("candidate_skips", [])

                # Count candidates from hypotheses generated
                experiments_run = data.get("experiments_run", 0)
                total_candidates = experiments_run + len(candidate_skips)

                if total_candidates > 0:
                    skip_data.append(
                        {
                            "total": total_candidates,
                            "skipped": len(candidate_skips),
                            "timestamp": file_mtime.isoformat(),
                        }
                    )

            except (OSError, json.JSONDecodeError) as e:
                logger.debug("Failed reading cycle file %s: %s", cycle_file, e)
                continue

        return skip_data

    def record_skip_metric(
        self, run_id: str, total_candidates: int, skipped_candidates: int
    ) -> None:
        """Record skip metric to Redis for real-time monitoring."""
        try:
            from tools.redis_state import redis_state_lpush

            metric = {
                "run_id": run_id,
                "timestamp": datetime.now(UTC).isoformat(),
                "total_candidates": total_candidates,
                "skipped_candidates": skipped_candidates,
                "skip_rate": (
                    skipped_candidates / total_candidates
                    if total_candidates > 0
                    else 0.0
                ),
            }

            redis_state_lpush(
                "bmad:chiseai:autocog:skip_rate:history",
                json.dumps(metric),
                expire=86400 * 30,  # 30 days
            )
        except Exception as e:
            logger.debug("Failed recording skip metric to Redis: %s", e)
