"""Monitoring infrastructure for ML model registry and training."""

from ml.monitoring.alerter import (
    Alert as TrainingAlert,
)
from ml.monitoring.alerter import (
    AlertRule as TrainingAlertRule,
)
from ml.monitoring.alerter import (
    AlertSeverity as TrainingAlertSeverity,
)
from ml.monitoring.alerter import (
    AlertType,
    DiscordNotificationChannel,
    LoggingNotificationChannel,
    NotificationChannel,
    TrainingAlerter,
)
from ml.monitoring.registry_alerts import (
    Alert,
    AlertManager,
    AlertRule,
    AlertSeverity,
    NullAlertManager,
)
from ml.monitoring.registry_metrics import (
    MetricsCollector,
    NullMetricsCollector,
    PrometheusMetricsCollector,
    RegistryMetrics,
    get_metrics_collector,
    sanitize_metric_name,
    set_metrics_collector,
)
from ml.monitoring.registry_monitor import (
    DegradationEvent,
    ModelRegistryMonitor,
    ModelVersionInfo,
    ShadowModeRecord,
    ShadowModeResult,
    ValidationGateRecord,
    ValidationGateStatus,
)
from ml.monitoring.training_metrics import (
    TrainingMetricsCollector,
    TrainingMode,
    TrainingRunMetrics,
    TrainingStatus,
    TrainingSummary,
)

__all__ = [
    # Registry Metrics
    "MetricsCollector",
    "NullMetricsCollector",
    "PrometheusMetricsCollector",
    "RegistryMetrics",
    "get_metrics_collector",
    "sanitize_metric_name",
    "set_metrics_collector",
    # Registry Alerts
    "Alert",
    "AlertManager",
    "AlertRule",
    "AlertSeverity",
    "NullAlertManager",
    # Training Metrics
    "TrainingMetricsCollector",
    "TrainingMode",
    "TrainingRunMetrics",
    "TrainingStatus",
    "TrainingSummary",
    # Registry Monitor
    "DegradationEvent",
    "ModelRegistryMonitor",
    "ModelVersionInfo",
    "ShadowModeRecord",
    "ValidationGateRecord",
    "ValidationGateStatus",
    "ShadowModeResult",
    # Training Alerter
    "TrainingAlerter",
    "TrainingAlert",
    "TrainingAlertRule",
    "TrainingAlertSeverity",
    "AlertType",
    "NotificationChannel",
    "LoggingNotificationChannel",
    "DiscordNotificationChannel",
]
