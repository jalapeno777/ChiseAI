"""Monitoring infrastructure for ML model registry."""

from ml.monitoring.registry_metrics import (
    MetricsCollector,
    NullMetricsCollector,
    PrometheusMetricsCollector,
    RegistryMetrics,
    get_metrics_collector,
    set_metrics_collector,
)
from ml.monitoring.registry_alerts import (
    Alert,
    AlertManager,
    AlertRule,
    AlertSeverity,
    NullAlertManager,
)

__all__ = [
    # Metrics
    "MetricsCollector",
    "NullMetricsCollector",
    "PrometheusMetricsCollector",
    "RegistryMetrics",
    "get_metrics_collector",
    "set_metrics_collector",
    # Alerts
    "Alert",
    "AlertManager",
    "AlertRule",
    "AlertSeverity",
    "NullAlertManager",
]
