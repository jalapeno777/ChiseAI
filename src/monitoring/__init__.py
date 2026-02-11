"""Monitoring module for data quality and system health.

Provides monitoring capabilities for:
- Data freshness across multiple sources
- Gap detection in time-series data
- Alert routing to Discord
- Grafana dashboard integration

For ST-DATA-004: Data Quality Monitoring - Freshness + Gaps
"""

from monitoring.data_quality.config import (
    DataQualityConfig,
    FreshnessThresholdConfig,
)
from monitoring.data_quality.discord_sender import (
    DataQualityDiscordFormatter,
    DataQualityDiscordSender,
    create_discord_alert_handler,
)
from monitoring.data_quality.grafana_integration import (
    GrafanaDashboardConfig,
    GrafanaMetricsExporter,
)
from monitoring.data_quality import (
    AlertSeverity,
    DataFreshnessMonitor,
    DataQualityAlert,
    DataQualityMonitor,
    DataSource,
    FreshnessMetrics,
    GapAlert,
    GapDetector,
    SourceConfig,
)

__all__ = [
    # Core data quality
    "AlertSeverity",
    "DataFreshnessMonitor",
    "DataQualityAlert",
    "DataQualityMonitor",
    "DataSource",
    "FreshnessMetrics",
    "GapAlert",
    "GapDetector",
    "SourceConfig",
    # Discord integration
    "DataQualityDiscordFormatter",
    "DataQualityDiscordSender",
    "create_discord_alert_handler",
    # Grafana integration
    "GrafanaDashboardConfig",
    "GrafanaMetricsExporter",
    # Configuration
    "DataQualityConfig",
    "FreshnessThresholdConfig",
]
