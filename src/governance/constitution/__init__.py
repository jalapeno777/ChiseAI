"""
Constitution module for ChiseAI governance.

This module provides constitution artifact management including:
- Versioned constitution document loading
- JSON schema validation
- API endpoints for constitution access
- Violation detection and alerting
- Human override capability with audit logging
- Metrics export for governance dashboards

For ST-GOV-002: Agent Constitution Artifact
For ST-GOV-004: Meta-KPI Dashboard
"""

from src.governance.constitution.artifact import (
    ConstitutionArtifact,
    ConstitutionLoader,
    ConstitutionVersion,
)
from src.governance.constitution.audit_logger import (
    AuditLogger,
    OverrideRequest,
    OverrideStatus,
)
from src.governance.constitution.metrics_exporter import ConstitutionMetricsExporter
from src.governance.constitution.violation_detector import (
    Violation,
    ViolationDetector,
    ViolationSeverity,
)

__all__ = [
    # Artifact
    "ConstitutionArtifact",
    "ConstitutionLoader",
    "ConstitutionVersion",
    # Violation Detection
    "Violation",
    "ViolationDetector",
    "ViolationSeverity",
    # Audit Logging
    "AuditLogger",
    "OverrideRequest",
    "OverrideStatus",
    # Metrics
    "ConstitutionMetricsExporter",
]
