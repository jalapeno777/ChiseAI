"""Monitoring module for data quality and system health.

Provides monitoring capabilities for:
- Data freshness across multiple sources
- Gap detection in time-series data
- Data source health (InfluxDB, PostgreSQL)
- Alert routing to Discord
- Grafana dashboard integration
- Zero-signal metrics and Prometheus exposition

For ST-DATA-004: Data Quality Monitoring - Freshness + Gaps
For ST-OPS-008: Grafana Data Source Health Monitoring
For ST-MVP-006: Zero-Signal Monitoring Alerts
"""

from monitoring.data_quality import (
    AlertSeverity as DataQualityAlertSeverity,
)
from monitoring.data_quality import (
    DataFreshnessMonitor,
    DataQualityAlert,
    DataQualityMonitor,
    DataSource,
    FreshnessMetrics,
    GapAlert,
    GapDetector,
    SourceConfig,
)
from monitoring.data_quality.config import (
    DataQualityConfig,
    FreshnessThresholdConfig,
)
from monitoring.data_quality.discord_sender import (
    DataQualityDiscordFormatter,
    DataQualityDiscordSender,
)
from monitoring.data_quality.discord_sender import (
    create_discord_alert_handler as create_data_quality_alert_handler,
)
from monitoring.data_quality.grafana_integration import (
    GrafanaDashboardConfig,
    GrafanaMetricsExporter,
)
from monitoring.datasource_health import (
    AlertSeverity,
    ConnectionMetrics,
    ConnectionStatus,
    DatasourceConfig,
    DatasourceHealthAlert,
    DataSourceHealthMonitor,
    DataSourceType,
    InfluxDBHealthChecker,
    PostgreSQLHealthChecker,
    create_default_monitor,
    create_influxdb_config,
    create_postgresql_config,
)
from monitoring.datasource_health_discord import (
    DatasourceHealthDiscordFormatter,
    DatasourceHealthDiscordSender,
    create_discord_alert_handler,
)
from monitoring.zero_signal_metrics import (
    DatasourceMetrics,
    ZeroSignalMetrics,
)

__all__ = [
    # Core data quality
    "DataQualityAlertSeverity",
    "DataFreshnessMonitor",
    "DataQualityAlert",
    "DataQualityMonitor",
    "DataSource",
    "FreshnessMetrics",
    "GapAlert",
    "GapDetector",
    "SourceConfig",
    # Data quality Discord integration
    "DataQualityDiscordFormatter",
    "DataQualityDiscordSender",
    "create_data_quality_alert_handler",
    # Grafana integration
    "GrafanaDashboardConfig",
    "GrafanaMetricsExporter",
    # Data quality Configuration
    "DataQualityConfig",
    "FreshnessThresholdConfig",
    # Data source health (ST-OPS-008)
    "AlertSeverity",
    "ConnectionMetrics",
    "ConnectionStatus",
    "DataSourceHealthMonitor",
    "DataSourceType",
    "DatasourceConfig",
    "DatasourceHealthAlert",
    "InfluxDBHealthChecker",
    "PostgreSQLHealthChecker",
    "create_default_monitor",
    "create_influxdb_config",
    "create_postgresql_config",
    # Data source health Discord integration
    "DatasourceHealthDiscordFormatter",
    "DatasourceHealthDiscordSender",
    "create_discord_alert_handler",
    # Zero-signal metrics (ST-MVP-006)
    "DatasourceMetrics",
    "ZeroSignalMetrics",
]
