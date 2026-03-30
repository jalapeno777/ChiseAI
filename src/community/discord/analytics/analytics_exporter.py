"""Analytics exporter for community Discord."""

import csv
import io
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class TimeSeriesDataPoint:
    """A single time-series data point."""

    timestamp: datetime
    metric_name: str
    value: float
    labels: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "metric_name": self.metric_name,
            "value": self.value,
            "labels": self.labels,
        }


class AnalyticsExporter:
    """Export community analytics for dashboard integration.

    Provides time-series data, JSON/CSV export options,
    and API endpoint format for dashboard consumption.
    """

    def __init__(
        self,
        redis_client: Any = None,
        metrics_reporter: Any = None,
    ):
        """Initialize AnalyticsExporter.

        Args:
            redis_client: Redis client for data access
            metrics_reporter: MetricsReporter instance
        """
        self._redis = redis_client
        self._metrics_reporter = metrics_reporter

    async def export_metrics_json(
        self,
        start_time: datetime,
        end_time: datetime,
        metrics: list[str] | None = None,
    ) -> str:
        """Export metrics as JSON.

        Args:
            start_time: Start of time range
            end_time: End of time range
            metrics: List of metric names to include (None for all)

        Returns:
            JSON string
        """
        data: dict[str, Any] = {
            "export_time": datetime.now().isoformat(),
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "data": [],
        }

        if not self._metrics_reporter:
            return json.dumps(data, indent=2)

        metric_list = metrics or [
            "active_users",
            "messages_sent",
            "reactions_added",
            "threads_created",
            "engagement_score",
        ]

        for metric_name in metric_list:
            series = await self._metrics_reporter.export_time_series(
                metric_name=metric_name,
                start_time=start_time,
                end_time=end_time,
            )
            data["data"].extend(series)

        return json.dumps(data, indent=2)

    async def export_metrics_csv(
        self,
        start_time: datetime,
        end_time: datetime,
        metrics: list[str] | None = None,
    ) -> str:
        """Export metrics as CSV.

        Args:
            start_time: Start of time range
            end_time: End of time range
            metrics: List of metric names to include

        Returns:
            CSV string
        """
        output = io.StringIO()
        writer = csv.writer(output)

        # Write header
        writer.writerow(["timestamp", "metric_name", "value", "labels_json"])

        if self._metrics_reporter:
            metric_list = metrics or [
                "active_users",
                "messages_sent",
                "reactions_added",
                "threads_created",
            ]

            for metric_name in metric_list:
                series = await self._metrics_reporter.export_time_series(
                    metric_name=metric_name,
                    start_time=start_time,
                    end_time=end_time,
                )

                for point in series:
                    writer.writerow(
                        [
                            point["timestamp"],
                            metric_name,
                            point.get("value", 0),
                            json.dumps(point.get("metadata", {})),
                        ]
                    )

        return output.getvalue()

    async def get_dashboard_summary(
        self,
        hours: int = 24,
    ) -> dict[str, Any]:
        """Get dashboard summary data.

        Args:
            hours: Number of hours to look back

        Returns:
            Dashboard summary dictionary
        """
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=hours)

        summary: dict[str, Any] = {
            "generated_at": datetime.now().isoformat(),
            "period": {
                "start": start_time.isoformat(),
                "end": end_time.isoformat(),
                "hours": hours,
            },
            "active_users": {
                "current": 0,
                "change_percent": 0.0,
            },
            "engagement": {
                "messages": 0,
                "reactions": 0,
                "threads": 0,
            },
            "top_commands": [],
            "alerts": [],
        }

        if self._metrics_reporter:
            # Get active users
            from .community_metrics import CommunityMetrics

            metrics = CommunityMetrics(redis_client=self._redis)
            active = await metrics.get_active_users("daily")

            summary["active_users"]["current"] = active.daily

            # Get engagement
            engagement = await metrics.get_engagement_metrics()
            summary["engagement"] = {
                "messages": engagement.messages_sent,
                "reactions": engagement.reactions_added,
                "threads": engagement.threads_created,
            }

            # Get top commands
            commands = await metrics.get_command_usage(limit=5)
            summary["top_commands"] = [
                {"name": c.command_name, "usage": c.usage_count} for c in commands
            ]

            # Get recent alerts
            alerts = await self._metrics_reporter.get_recent_alerts(limit=5)
            summary["alerts"] = [a.to_dict() for a in alerts]

        return summary

    async def get_time_series_api_format(
        self,
        metric_name: str,
        start_time: datetime,
        end_time: datetime,
        interval_minutes: int = 60,
    ) -> dict[str, Any]:
        """Get time-series data in API endpoint format.

        Args:
            metric_name: Name of the metric
            start_time: Start of time range
            end_time: End of time range
            interval_minutes: Bucket interval

        Returns:
            API format dictionary
        """
        data_points: list[TimeSeriesDataPoint] = []

        if self._metrics_reporter:
            raw_series = await self._metrics_reporter.export_time_series(
                metric_name=metric_name,
                start_time=start_time,
                end_time=end_time,
                interval_minutes=interval_minutes,
            )

            for point in raw_series:
                ts = point.get("timestamp")
                if isinstance(ts, str):
                    ts = datetime.fromisoformat(ts)

                data_points.append(
                    TimeSeriesDataPoint(
                        timestamp=ts or datetime.now(),
                        metric_name=metric_name,
                        value=float(point.get("value", 0)),
                        labels=point.get("metadata", {}),
                    )
                )

        return {
            "metric": metric_name,
            "interval_minutes": interval_minutes,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "data_points": [dp.to_dict() for dp in data_points],
            "count": len(data_points),
        }

    def format_for_grafana(
        self,
        time_series: list[TimeSeriesDataPoint],
    ) -> dict[str, Any]:
        """Format time-series data for Grafana.

        Args:
            time_series: List of data points

        Returns:
            Grafana-compatible format
        """
        if not time_series:
            return {"targets": [], "labels": {}}

        datapoints = [
            [ds.value, int(ds.timestamp.timestamp() * 1000)] for ds in time_series
        ]

        return {
            "targets": [
                {
                    "target": time_series[0].label,
                    "datapoints": datapoints,
                }
            ],
            "labels": getattr(time_series[0], "labels", {}),
        }

    async def export_user_leaderboard(
        self,
        metric: str = "engagement",
        limit: int = 20,
        period_days: int = 7,
    ) -> list[dict[str, Any]]:
        """Export user leaderboard data.

        Args:
            metric: Metric to rank by ('engagement', 'messages', 'reactions')
            limit: Number of users to return
            period_days: Days to analyze

        Returns:
            List of user rankings
        """
        # This would query user engagement data
        # For now, return placeholder structure
        leaderboard: list[dict[str, Any]] = []

        if self._redis:
            try:
                from tools.redis_state import redis_state_get, redis_state_scan_keys

                pattern = f"community:discord:user:*:{metric}"
                keys = redis_state_scan_keys(pattern, count=limit * 2)

                user_scores: list[tuple[str, float]] = []

                for key in keys:
                    data = redis_state_get(key)
                    if data:
                        try:
                            parsed = json.loads(data)
                            score = float(parsed.get("count", 0))
                            user_id = key.split(":")[4]  # Extract user ID from key
                            user_scores.append((user_id, score))
                        except (json.JSONDecodeError, ValueError):
                            continue

                # Sort by score
                user_scores.sort(key=lambda x: x[1], reverse=True)

                for rank, (user_id, score) in enumerate(user_scores[:limit], 1):
                    leaderboard.append(
                        {
                            "rank": rank,
                            "user_id": user_id,
                            "score": score,
                            "metric": metric,
                        }
                    )

            except Exception as e:
                logger.warning(f"Failed to get leaderboard from Redis: {e}")

        return leaderboard
