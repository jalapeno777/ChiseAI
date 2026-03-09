"""
Tempmemory Governance Module for ChiseAI.

Provides functionality for managing temporary memory files including:
- Migration from docs/tempmemories/ to Redis and Qdrant
- Tracking migration status
- Archiving migrated files
- Reconciliation and issue detection
- CI integration for pipeline ingestion

This module is part of Phase 1 of the Tempmemory Migration story (ST-MEMORY-003).
"""

from governance.tempmemory.archive_reconcile import (
    ArchiveResult,
    ReconciliationIssue,
    ReconciliationReport,
    TempmemoryArchiveReconciler,
)
from governance.tempmemory.ci_integration import (
    CIIngestionReport,
    cache_ingested_memories,
    cache_ingestion_report,
    format_report_for_logs,
    get_cached_memories,
    get_ingestion_report,
    is_ingestion_enabled,
    is_memory_ingested,
    run_pre_eval_ingestion,
    should_fail_ci,
    validate_ingestion_success,
)
from governance.tempmemory.ingestion_runner import (
    FileIngestionResult,
    IngestionStatus,
    TempmemoryIngestionRunner,
)
from governance.tempmemory.migration import (
    MigrationReport,
    MigrationResult,
    MigrationStatus,
    MigrationTarget,
    TempmemoryFile,
    TempmemoryMigrationEngine,
)
from governance.tempmemory.tracking import (
    FileTrackingRecord,
    TempmemoryTracker,
    TrackingReportType,
    TrackingSummary,
)

__all__ = [
    # Migration
    "MigrationResult",
    "MigrationStatus",
    "MigrationTarget",
    "MigrationReport",
    "TempmemoryFile",
    "TempmemoryMigrationEngine",
    # Tracking
    "FileTrackingRecord",
    "TempmemoryTracker",
    "TrackingReportType",
    "TrackingSummary",
    # Archive/Reconcile
    "ArchiveResult",
    "ReconciliationIssue",
    "ReconciliationReport",
    "TempmemoryArchiveReconciler",
    # Ingestion Runner
    "FileIngestionResult",
    "IngestionStatus",
    "TempmemoryIngestionRunner",
    # CI Integration
    "CIIngestionReport",
    "is_ingestion_enabled",
    "run_pre_eval_ingestion",
    "validate_ingestion_success",
    "cache_ingestion_report",
    "cache_ingested_memories",
    "get_ingestion_report",
    "get_cached_memories",
    "is_memory_ingested",
    "format_report_for_logs",
    "should_fail_ci",
]
