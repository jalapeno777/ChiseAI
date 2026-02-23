"""
ChiseAI Decision Audit Trail Module.

ST-GOV-009: Decision Audit Trail Export

Provides tamper-evident logging of autonomous agent decisions with:
- Hash chain for integrity verification
- Queryable by agent, time range, decision type, outcome
- Automated daily exports to S3
- 7-year retention for compliance
"""

from src.governance.audit_trail.trail import (
    AuditTrail,
    AuditTrailEntry,
    DecisionContext,
    HashChainState,
)
from src.governance.audit_trail.decision import (
    Decision,
    DecisionOutcome,
    DecisionType,
    ConstitutionPrinciple,
)
from src.governance.audit_trail.query import (
    AuditTrailQuery,
    QueryFilter,
    QueryResult,
)
from src.governance.audit_trail.exporter import (
    AuditTrailExporter,
    ExportConfig,
    ExportResult,
    S3Config,
)

__all__ = [
    # Trail
    "AuditTrail",
    "AuditTrailEntry",
    "DecisionContext",
    "HashChainState",
    # Decision
    "Decision",
    "DecisionOutcome",
    "DecisionType",
    "ConstitutionPrinciple",
    # Query
    "AuditTrailQuery",
    "QueryFilter",
    "QueryResult",
    # Exporter
    "AuditTrailExporter",
    "ExportConfig",
    "ExportResult",
    "S3Config",
]

# Redis key patterns
AUDIT_TRAIL_KEY = "governance:audit_trail:entries"
AUDIT_CHAIN_KEY = "governance:audit_trail:chain_state"
AUDIT_INDEX_AGENT_KEY = "governance:audit_trail:index:agent"
AUDIT_INDEX_TYPE_KEY = "governance:audit_trail:index:type"
AUDIT_INDEX_OUTCOME_KEY = "governance:audit_trail:index:outcome"
AUDIT_INDEX_TIME_KEY = "governance:audit_trail:index:time"

# Retention: 7 years (compliance requirement)
RETENTION_DAYS = 2557  # 7 * 365 + leap days
RETENTION_SECONDS = RETENTION_DAYS * 24 * 60 * 60

# Export schedule
EXPORT_DAILY_SCHEDULE = "0 2 * * *"  # Daily at 2 AM UTC
