"""Opportunity detection engine for autonomous cognition.

Identifies improvement opportunities from system metrics, logs, and code
analysis. Each opportunity type has configurable enablement, scoring, and
async detection capabilities.

Opportunity types (minimum 10):
  1. Low test coverage areas
  2. Slow API endpoints
  3. High error rate patterns
  4. Unused code detection
  5. Configuration drift
  6. Memory usage anomalies
  7. CI pipeline bottlenecks
  8. Documentation gaps
  9. Dependency vulnerabilities
  10. Performance regression patterns
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, ClassVar

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------


class OpportunitySeverity(Enum):
    """Severity level for detected opportunities."""

    LOW = auto()
    MEDIUM = auto()
    HIGH = auto()
    CRITICAL = auto()


class OpportunityCategory(Enum):
    """Category grouping for opportunity types."""

    TESTING = "testing"
    PERFORMANCE = "performance"
    RELIABILITY = "reliability"
    CODE_QUALITY = "code_quality"
    INFRASTRUCTURE = "infrastructure"
    SECURITY = "security"
    DOCUMENTATION = "documentation"
    OPERATIONS = "operations"


@dataclass
class Opportunity:
    """A single detected improvement opportunity.

    Attributes:
        id: Unique identifier for this opportunity
        type: The specific opportunity type that was detected
        title: Human-readable title
        description: Detailed description of the opportunity
        severity: How impactful fixing this would be
        category: Which category this belongs to
        confidence: Detection confidence 0.0-1.0
        score: Overall importance score 0.0-1.0
        source: Where this opportunity was detected from
        metadata: Additional context about the opportunity
        timestamp: When this opportunity was detected (epoch seconds)
        file_path: Relevant file path if applicable
        suggestion: Suggested remediation action
    """

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    type: str = ""
    title: str = ""
    description: str = ""
    severity: OpportunitySeverity = OpportunitySeverity.MEDIUM
    category: OpportunityCategory = OpportunityCategory.CODE_QUALITY
    confidence: float = 0.5
    score: float = 0.5
    source: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    file_path: str = ""
    suggestion: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "type": self.type,
            "title": self.title,
            "description": self.description,
            "severity": self.severity.name,
            "category": self.category.value,
            "confidence": self.confidence,
            "score": self.score,
            "source": self.source,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
            "file_path": self.file_path,
            "suggestion": self.suggestion,
        }


@dataclass
class DetectionConfig:
    """Configuration for the opportunity detector.

    Attributes:
        enabled_types: Set of opportunity type names that are enabled.
                       Empty set means all types enabled.
        min_confidence: Minimum confidence threshold for reported opportunities.
        max_opportunities_per_run: Cap on opportunities returned per detection run.
        scan_timeout_seconds: Timeout for individual opportunity scans.
    """

    enabled_types: set[str] = field(default_factory=set)
    min_confidence: float = 0.3
    max_opportunities_per_run: int = 100
    scan_timeout_seconds: float = 30.0


@dataclass
class DetectionResult:
    """Result of an opportunity detection run.

    Attributes:
        opportunities: List of detected opportunities.
        scan_duration_seconds: Total time for the scan.
        types_scanned: Which opportunity types were scanned.
        errors: Any errors encountered during scanning.
    """

    opportunities: list[Opportunity] = field(default_factory=list)
    scan_duration_seconds: float = 0.0
    types_scanned: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Base opportunity detector
# ---------------------------------------------------------------------------


class BaseOpportunityDetector(ABC):
    """Abstract base class for individual opportunity type detectors."""

    type_name: ClassVar[str] = "base"
    category: ClassVar[OpportunityCategory] = OpportunityCategory.CODE_QUALITY

    def __init__(self, config: DetectionConfig | None = None) -> None:
        self._config = config or DetectionConfig()

    @abstractmethod
    async def detect(self, context: dict[str, Any]) -> list[Opportunity]:
        """Detect opportunities of this type.

        Args:
            context: Detection context containing metrics, logs, code data.

        Returns:
            List of detected opportunities.
        """

    @abstractmethod
    def score(self, opportunity: Opportunity) -> float:
        """Score an opportunity's importance.

        Args:
            opportunity: The opportunity to score.

        Returns:
            Score between 0.0 and 1.0.
        """

    def is_enabled(self) -> bool:
        """Check if this detector type is enabled in config."""
        if not self._config.enabled_types:
            return True
        return self.type_name in self._config.enabled_types


# ---------------------------------------------------------------------------
# Concrete opportunity detectors
# ---------------------------------------------------------------------------


class LowTestCoverageDetector(BaseOpportunityDetector):
    """Detects modules and files with low test coverage."""

    type_name: ClassVar[str] = "low_test_coverage"
    category: ClassVar[OpportunityCategory] = OpportunityCategory.TESTING

    async def detect(self, context: dict[str, Any]) -> list[Opportunity]:
        """Detect files with coverage below threshold.

        Expects context key 'coverage_data': dict mapping file paths to coverage %.
        """
        if not self.is_enabled():
            return []

        coverage_data: dict[str, float] = context.get("coverage_data", {})
        threshold = context.get("coverage_threshold", 80.0)
        opportunities: list[Opportunity] = []

        for file_path, pct in coverage_data.items():
            if pct < threshold:
                severity = (
                    OpportunitySeverity.CRITICAL
                    if pct < 30
                    else (
                        OpportunitySeverity.HIGH
                        if pct < 50
                        else OpportunitySeverity.MEDIUM
                    )
                )
                opp = Opportunity(
                    type=self.type_name,
                    title=f"Low test coverage: {file_path}",
                    description=f"File {file_path} has {pct:.1f}% coverage, below {threshold}% threshold.",
                    severity=severity,
                    category=self.category,
                    confidence=0.9,
                    file_path=file_path,
                    metadata={"coverage_percent": pct, "threshold": threshold},
                    source="coverage_report",
                    suggestion=f"Add tests to increase coverage of {file_path} above {threshold}%.",
                )
                opp.score = self.score(opp)
                opportunities.append(opp)

        return opportunities

    def score(self, opportunity: Opportunity) -> float:
        """Lower coverage = higher score."""
        pct = opportunity.metadata.get("coverage_percent", 100.0)
        # Score inversely proportional to coverage: 0% -> 1.0, 100% -> 0.0
        return round(max(0.0, min(1.0, 1.0 - pct / 100.0)), 3)


class SlowApiEndpointDetector(BaseOpportunityDetector):
    """Detects API endpoints with high response times."""

    type_name: ClassVar[str] = "slow_api_endpoint"
    category: ClassVar[OpportunityCategory] = OpportunityCategory.PERFORMANCE

    async def detect(self, context: dict[str, Any]) -> list[Opportunity]:
        """Detect endpoints exceeding latency threshold.

        Expects context key 'endpoint_metrics': list of dicts with
        'path', 'method', 'avg_latency_ms', 'p95_latency_ms'.
        """
        if not self.is_enabled():
            return []

        endpoint_metrics: list[dict[str, Any]] = context.get("endpoint_metrics", [])
        threshold_ms = context.get("latency_threshold_ms", 1000.0)
        opportunities: list[Opportunity] = []

        for ep in endpoint_metrics:
            p95 = ep.get("p95_latency_ms", ep.get("avg_latency_ms", 0))
            if p95 > threshold_ms:
                severity = (
                    OpportunitySeverity.CRITICAL
                    if p95 > threshold_ms * 5
                    else (
                        OpportunitySeverity.HIGH
                        if p95 > threshold_ms * 3
                        else OpportunitySeverity.MEDIUM
                    )
                )
                opp = Opportunity(
                    type=self.type_name,
                    title=f"Slow endpoint: {ep.get('method', 'GET')} {ep.get('path', '?')}",
                    description=(
                        f"Endpoint {ep.get('method', 'GET')} {ep.get('path', '?')} "
                        f"has p95 latency of {p95:.0f}ms, exceeding {threshold_ms:.0f}ms threshold."
                    ),
                    severity=severity,
                    category=self.category,
                    confidence=0.85,
                    metadata={
                        "avg_latency_ms": ep.get("avg_latency_ms", 0),
                        "p95_latency_ms": p95,
                        "threshold_ms": threshold_ms,
                    },
                    source="api_metrics",
                    suggestion=f"Profile and optimize {ep.get('path', '?')} endpoint latency.",
                )
                opp.score = self.score(opp)
                opportunities.append(opp)

        return opportunities

    def score(self, opportunity: Opportunity) -> float:
        """Higher latency ratio over threshold = higher score."""
        p95 = opportunity.metadata.get("p95_latency_ms", 0)
        threshold = opportunity.metadata.get("threshold_ms", 1000.0)
        ratio = p95 / threshold if threshold > 0 else 1.0
        return round(min(1.0, ratio / 10.0), 3)


class HighErrorRateDetector(BaseOpportunityDetector):
    """Detects patterns of high error rates in services."""

    type_name: ClassVar[str] = "high_error_rate"
    category: ClassVar[OpportunityCategory] = OpportunityCategory.RELIABILITY

    async def detect(self, context: dict[str, Any]) -> list[Opportunity]:
        """Detect services with error rates above threshold.

        Expects context key 'error_metrics': list of dicts with
        'service', 'error_rate', 'total_requests', 'error_types'.
        """
        if not self.is_enabled():
            return []

        error_metrics: list[dict[str, Any]] = context.get("error_metrics", [])
        threshold = context.get("error_rate_threshold", 0.05)
        opportunities: list[Opportunity] = []

        for svc in error_metrics:
            rate = svc.get("error_rate", 0)
            if rate > threshold:
                severity = (
                    OpportunitySeverity.CRITICAL
                    if rate > 0.2
                    else (
                        OpportunitySeverity.HIGH
                        if rate > 0.1
                        else OpportunitySeverity.MEDIUM
                    )
                )
                opp = Opportunity(
                    type=self.type_name,
                    title=f"High error rate: {svc.get('service', '?')}",
                    description=(
                        f"Service {svc.get('service', '?')} has error rate of "
                        f"{rate:.2%}, above {threshold:.2%} threshold. "
                        f"Error types: {svc.get('error_types', [])}"
                    ),
                    severity=severity,
                    category=self.category,
                    confidence=0.9,
                    metadata={
                        "error_rate": rate,
                        "total_requests": svc.get("total_requests", 0),
                        "error_types": svc.get("error_types", []),
                        "threshold": threshold,
                    },
                    source="error_monitoring",
                    suggestion=f"Investigate and fix top error types in {svc.get('service', '?')}.",
                )
                opp.score = self.score(opp)
                opportunities.append(opp)

        return opportunities

    def score(self, opportunity: Opportunity) -> float:
        """Higher error rate = higher score."""
        rate = opportunity.metadata.get("error_rate", 0)
        return round(min(1.0, rate * 5), 3)


class UnusedCodeDetector(BaseOpportunityDetector):
    """Detects potentially unused code modules, functions, and classes."""

    type_name: ClassVar[str] = "unused_code"
    category: ClassVar[OpportunityCategory] = OpportunityCategory.CODE_QUALITY

    async def detect(self, context: dict[str, Any]) -> list[Opportunity]:
        """Detect unused code elements.

        Expects context key 'code_references': dict mapping symbol names to
        reference counts.
        """
        if not self.is_enabled():
            return []

        code_references: dict[str, int] = context.get("code_references", {})
        min_references = context.get("min_references_threshold", 1)
        opportunities: list[Opportunity] = []

        for symbol, refs in code_references.items():
            if refs <= min_references:
                opp = Opportunity(
                    type=self.type_name,
                    title=f"Potentially unused: {symbol}",
                    description=(
                        f"Symbol '{symbol}' has only {refs} reference(s), "
                        f"below threshold of {min_references + 1}. "
                        f"Consider removal or verification."
                    ),
                    severity=OpportunitySeverity.LOW,
                    category=self.category,
                    confidence=0.6,
                    metadata={"symbol": symbol, "reference_count": refs},
                    source="static_analysis",
                    suggestion=f"Verify usage of {symbol} and remove if truly unused.",
                )
                opp.score = self.score(opp)
                opportunities.append(opp)

        return opportunities

    def score(self, opportunity: Opportunity) -> float:
        """Fewer references = higher score."""
        refs = opportunity.metadata.get("reference_count", 1)
        return round(max(0.0, min(1.0, 1.0 - refs / 5.0)), 3)


class ConfigurationDriftDetector(BaseOpportunityDetector):
    """Detects configuration drift between environments."""

    type_name: ClassVar[str] = "configuration_drift"
    category: ClassVar[OpportunityCategory] = OpportunityCategory.INFRASTRUCTURE

    async def detect(self, context: dict[str, Any]) -> list[Opportunity]:
        """Detect configuration differences between environments.

        Expects context key 'config_diffs': list of dicts with
        'key', 'env_a', 'env_b', 'value_a', 'value_b'.
        """
        if not self.is_enabled():
            return []

        config_diffs: list[dict[str, Any]] = context.get("config_diffs", [])
        opportunities: list[Opportunity] = []

        for diff in config_diffs:
            opp = Opportunity(
                type=self.type_name,
                title=f"Config drift: {diff.get('key', '?')}",
                description=(
                    f"Configuration key '{diff.get('key', '?')}' differs between "
                    f"{diff.get('env_a', 'env-a')} ({diff.get('value_a', '?')}) "
                    f"and {diff.get('env_b', 'env-b')} ({diff.get('value_b', '?')})."
                ),
                severity=OpportunitySeverity.MEDIUM,
                category=self.category,
                confidence=0.85,
                metadata={
                    "key": diff.get("key"),
                    "env_a": diff.get("env_a"),
                    "env_b": diff.get("env_b"),
                    "value_a": diff.get("value_a"),
                    "value_b": diff.get("value_b"),
                },
                source="config_audit",
                suggestion=f"Align {diff.get('key', '?')} across environments.",
            )
            opp.score = self.score(opp)
            opportunities.append(opp)

        return opportunities

    def score(self, opportunity: Opportunity) -> float:
        """Fixed score for config drift (medium-high)."""
        return 0.6


class MemoryAnomalyDetector(BaseOpportunityDetector):
    """Detects memory usage anomalies and potential leaks."""

    type_name: ClassVar[str] = "memory_anomaly"
    category: ClassVar[OpportunityCategory] = OpportunityCategory.PERFORMANCE

    async def detect(self, context: dict[str, Any]) -> list[Opportunity]:
        """Detect memory anomalies.

        Expects context key 'memory_metrics': list of dicts with
        'service', 'current_mb', 'peak_mb', 'limit_mb', 'growth_rate_mb_per_hr'.
        """
        if not self.is_enabled():
            return []

        memory_metrics: list[dict[str, Any]] = context.get("memory_metrics", [])
        usage_threshold = context.get("memory_usage_threshold", 0.8)
        growth_threshold = context.get("memory_growth_threshold_mb_hr", 100.0)
        opportunities: list[Opportunity] = []

        for mem in memory_metrics:
            current = mem.get("current_mb", 0)
            limit = mem.get("limit_mb", 1)
            usage_ratio = current / limit if limit > 0 else 0
            growth = mem.get("growth_rate_mb_per_hr", 0)

            if usage_ratio > usage_threshold or growth > growth_threshold:
                reasons = []
                if usage_ratio > usage_threshold:
                    reasons.append(f"usage at {usage_ratio:.0%} of limit")
                if growth > growth_threshold:
                    reasons.append(f"growing at {growth:.0f} MB/hr")

                severity = (
                    OpportunitySeverity.CRITICAL
                    if usage_ratio > 0.95
                    else (
                        OpportunitySeverity.HIGH
                        if usage_ratio > usage_threshold
                        else OpportunitySeverity.MEDIUM
                    )
                )
                opp = Opportunity(
                    type=self.type_name,
                    title=f"Memory anomaly: {mem.get('service', '?')}",
                    description=(
                        f"Service {mem.get('service', '?')} shows memory anomaly: "
                        f"{', '.join(reasons)}. "
                        f"Current: {current:.0f}MB, Peak: {mem.get('peak_mb', 0):.0f}MB, "
                        f"Limit: {limit:.0f}MB."
                    ),
                    severity=severity,
                    category=self.category,
                    confidence=0.8,
                    metadata={
                        "service": mem.get("service"),
                        "current_mb": current,
                        "peak_mb": mem.get("peak_mb", 0),
                        "limit_mb": limit,
                        "growth_rate_mb_per_hr": growth,
                        "usage_ratio": usage_ratio,
                    },
                    source="memory_monitoring",
                    suggestion=f"Investigate memory usage in {mem.get('service', '?')} for potential leaks.",
                )
                opp.score = self.score(opp)
                opportunities.append(opp)

        return opportunities

    def score(self, opportunity: Opportunity) -> float:
        """Higher usage ratio = higher score."""
        ratio = opportunity.metadata.get("usage_ratio", 0)
        growth = opportunity.metadata.get("growth_rate_mb_per_hr", 0)
        usage_score = min(1.0, ratio)
        growth_score = min(0.3, growth / 500.0)
        return round(min(1.0, usage_score + growth_score), 3)


class CIBottleneckDetector(BaseOpportunityDetector):
    """Detects CI pipeline bottlenecks."""

    type_name: ClassVar[str] = "ci_bottleneck"
    category: ClassVar[OpportunityCategory] = OpportunityCategory.OPERATIONS

    async def detect(self, context: dict[str, Any]) -> list[Opportunity]:
        """Detect slow CI stages and frequent failures.

        Expects context key 'ci_stages': list of dicts with
        'name', 'avg_duration_seconds', 'failure_rate', 'run_count'.
        """
        if not self.is_enabled():
            return []

        ci_stages: list[dict[str, Any]] = context.get("ci_stages", [])
        duration_threshold = context.get("ci_duration_threshold_seconds", 300.0)
        failure_threshold = context.get("ci_failure_threshold", 0.1)
        opportunities: list[Opportunity] = []

        for stage in ci_stages:
            avg_dur = stage.get("avg_duration_seconds", 0)
            fail_rate = stage.get("failure_rate", 0)
            issues = []

            if avg_dur > duration_threshold:
                issues.append(f"slow ({avg_dur:.0f}s avg)")
            if fail_rate > failure_threshold:
                issues.append(f"flaky ({fail_rate:.1%} failure rate)")

            if issues:
                severity = (
                    OpportunitySeverity.HIGH
                    if avg_dur > duration_threshold * 3 or fail_rate > 0.3
                    else OpportunitySeverity.MEDIUM
                )
                opp = Opportunity(
                    type=self.type_name,
                    title=f"CI bottleneck: {stage.get('name', '?')}",
                    description=(
                        f"CI stage '{stage.get('name', '?')}' has issues: "
                        f"{', '.join(issues)}. "
                        f"Avg duration: {avg_dur:.0f}s, Failure rate: {fail_rate:.1%}, "
                        f"Runs: {stage.get('run_count', 0)}."
                    ),
                    severity=severity,
                    category=self.category,
                    confidence=0.85,
                    metadata={
                        "stage_name": stage.get("name"),
                        "avg_duration_seconds": avg_dur,
                        "failure_rate": fail_rate,
                        "run_count": stage.get("run_count", 0),
                    },
                    source="ci_monitoring",
                    suggestion=f"Optimize or parallelize CI stage '{stage.get('name', '?')}'.",
                )
                opp.score = self.score(opp)
                opportunities.append(opp)

        return opportunities

    def score(self, opportunity: Opportunity) -> float:
        """Higher duration and failure rate = higher score."""
        dur = opportunity.metadata.get("avg_duration_seconds", 0)
        fail = opportunity.metadata.get("failure_rate", 0)
        dur_score = min(0.5, dur / 600.0)
        fail_score = min(0.5, fail * 2)
        return round(min(1.0, dur_score + fail_score), 3)


class DocumentationGapDetector(BaseOpportunityDetector):
    """Detects documentation gaps in the codebase."""

    type_name: ClassVar[str] = "documentation_gap"
    category: ClassVar[OpportunityCategory] = OpportunityCategory.DOCUMENTATION

    async def detect(self, context: dict[str, Any]) -> list[Opportunity]:
        """Detect modules and public APIs missing documentation.

        Expects context key 'doc_coverage': dict mapping file paths to
        {'docstring_ratio': float, 'public_undocumented': int, 'total_public': int}.
        """
        if not self.is_enabled():
            return []

        doc_coverage: dict[str, dict[str, Any]] = context.get("doc_coverage", {})
        min_docstring_ratio = context.get("min_docstring_ratio", 0.5)
        opportunities: list[Opportunity] = []

        for file_path, info in doc_coverage.items():
            ratio = info.get("docstring_ratio", 1.0)
            undocumented = info.get("public_undocumented", 0)
            if ratio < min_docstring_ratio and undocumented > 0:
                opp = Opportunity(
                    type=self.type_name,
                    title=f"Documentation gap: {file_path}",
                    description=(
                        f"File {file_path} has {ratio:.0%} docstring coverage "
                        f"({undocumented}/{info.get('total_public', 0)} public symbols undocumented)."
                    ),
                    severity=OpportunitySeverity.LOW,
                    category=self.category,
                    confidence=0.8,
                    metadata={
                        "file_path": file_path,
                        "docstring_ratio": ratio,
                        "public_undocumented": undocumented,
                        "total_public": info.get("total_public", 0),
                    },
                    source="doc_analysis",
                    file_path=file_path,
                    suggestion=f"Add docstrings to {undocumented} undocumented public symbols in {file_path}.",
                )
                opp.score = self.score(opp)
                opportunities.append(opp)

        return opportunities

    def score(self, opportunity: Opportunity) -> float:
        """Lower doc ratio and more undocumented symbols = higher score."""
        ratio = opportunity.metadata.get("docstring_ratio", 1.0)
        undocumented = opportunity.metadata.get("public_undocumented", 0)
        ratio_score = 1.0 - ratio
        count_score = min(0.3, undocumented / 20.0)
        return round(min(1.0, ratio_score * 0.7 + count_score), 3)


class DependencyVulnerabilityDetector(BaseOpportunityDetector):
    """Detects known vulnerabilities in project dependencies."""

    type_name: ClassVar[str] = "dependency_vulnerability"
    category: ClassVar[OpportunityCategory] = OpportunityCategory.SECURITY

    async def detect(self, context: dict[str, Any]) -> list[Opportunity]:
        """Detect vulnerable dependencies.

        Expects context key 'vulnerabilities': list of dicts with
        'package', 'version', 'cve_id', 'severity', 'description'.
        """
        if not self.is_enabled():
            return []

        vulnerabilities: list[dict[str, Any]] = context.get("vulnerabilities", [])
        opportunities: list[Opportunity] = []

        for vuln in vulnerabilities:
            vuln_sev = vuln.get("severity", "MEDIUM").upper()
            severity_map = {
                "CRITICAL": OpportunitySeverity.CRITICAL,
                "HIGH": OpportunitySeverity.HIGH,
                "MEDIUM": OpportunitySeverity.MEDIUM,
                "LOW": OpportunitySeverity.LOW,
            }
            severity = severity_map.get(vuln_sev, OpportunitySeverity.MEDIUM)

            opp = Opportunity(
                type=self.type_name,
                title=f"Vulnerability: {vuln.get('package', '?')} ({vuln.get('cve_id', '?')})",
                description=(
                    f"Package {vuln.get('package', '?')} v{vuln.get('version', '?')} "
                    f"has vulnerability {vuln.get('cve_id', '?')} ({vuln_sev}): "
                    f"{vuln.get('description', 'No description')}"
                ),
                severity=severity,
                category=self.category,
                confidence=0.95,
                metadata={
                    "package": vuln.get("package"),
                    "version": vuln.get("version"),
                    "cve_id": vuln.get("cve_id"),
                    "vulnerability_severity": vuln_sev,
                },
                source="dependency_audit",
                suggestion=f"Update {vuln.get('package', '?')} to a patched version.",
            )
            opp.score = self.score(opp)
            opportunities.append(opp)

        return opportunities

    def score(self, opportunity: Opportunity) -> float:
        """Higher severity vulnerability = higher score."""
        sev = opportunity.metadata.get("vulnerability_severity", "MEDIUM")
        severity_scores = {"CRITICAL": 1.0, "HIGH": 0.8, "MEDIUM": 0.5, "LOW": 0.2}
        return severity_scores.get(sev, 0.5)


class PerformanceRegressionDetector(BaseOpportunityDetector):
    """Detects performance regressions compared to historical baselines."""

    type_name: ClassVar[str] = "performance_regression"
    category: ClassVar[OpportunityCategory] = OpportunityCategory.PERFORMANCE

    async def detect(self, context: dict[str, Any]) -> list[Opportunity]:
        """Detect performance regressions.

        Expects context key 'performance_baselines': list of dicts with
        'metric_name', 'baseline_value', 'current_value', 'unit', 'direction'
        (where direction is 'lower_is_better' or 'higher_is_better').
        """
        if not self.is_enabled():
            return []

        baselines: list[dict[str, Any]] = context.get("performance_baselines", [])
        regression_threshold = context.get("regression_threshold", 0.2)
        opportunities: list[Opportunity] = []

        for bl in baselines:
            baseline = bl.get("baseline_value", 0)
            current = bl.get("current_value", 0)
            direction = bl.get("direction", "lower_is_better")

            if baseline == 0:
                continue

            if direction == "lower_is_better":
                regression_pct = (current - baseline) / abs(baseline)
            else:
                regression_pct = (baseline - current) / abs(baseline)

            if regression_pct > regression_threshold:
                severity = (
                    OpportunitySeverity.CRITICAL
                    if regression_pct > 1.0
                    else (
                        OpportunitySeverity.HIGH
                        if regression_pct > 0.5
                        else OpportunitySeverity.MEDIUM
                    )
                )
                opp = Opportunity(
                    type=self.type_name,
                    title=f"Performance regression: {bl.get('metric_name', '?')}",
                    description=(
                        f"Metric '{bl.get('metric_name', '?')}' shows "
                        f"{regression_pct:.0%} regression. "
                        f"Baseline: {baseline:.2f} {bl.get('unit', '')} -> "
                        f"Current: {current:.2f} {bl.get('unit', '')} "
                        f"({direction})."
                    ),
                    severity=severity,
                    category=self.category,
                    confidence=0.8,
                    metadata={
                        "metric_name": bl.get("metric_name"),
                        "baseline_value": baseline,
                        "current_value": current,
                        "unit": bl.get("unit", ""),
                        "direction": direction,
                        "regression_pct": regression_pct,
                    },
                    source="performance_monitoring",
                    suggestion=f"Investigate regression in {bl.get('metric_name', '?')} and restore baseline.",
                )
                opp.score = self.score(opp)
                opportunities.append(opp)

        return opportunities

    def score(self, opportunity: Opportunity) -> float:
        """Higher regression percentage = higher score."""
        pct = opportunity.metadata.get("regression_pct", 0)
        return round(min(1.0, pct), 3)


# ---------------------------------------------------------------------------
# Main OpportunityDetector orchestrator
# ---------------------------------------------------------------------------


class OpportunityDetector:
    """Orchestrates all opportunity detectors.

    Manages a collection of individual opportunity type detectors,
    runs them concurrently, filters results, and returns a unified
    detection result.

    Attributes:
        config: Detection configuration controlling enablement and thresholds.
    """

    # Registry of all available detector classes
    DETECTOR_REGISTRY: ClassVar[list[type[BaseOpportunityDetector]]] = [
        LowTestCoverageDetector,
        SlowApiEndpointDetector,
        HighErrorRateDetector,
        UnusedCodeDetector,
        ConfigurationDriftDetector,
        MemoryAnomalyDetector,
        CIBottleneckDetector,
        DocumentationGapDetector,
        DependencyVulnerabilityDetector,
        PerformanceRegressionDetector,
    ]

    def __init__(self, config: DetectionConfig | None = None) -> None:
        self.config = config or DetectionConfig()
        self._detectors: list[BaseOpportunityDetector] = [
            cls(self.config) for cls in self.DETECTOR_REGISTRY
        ]

    def get_available_types(self) -> list[str]:
        """Return list of all registered opportunity type names."""
        return [cls.type_name for cls in self.DETECTOR_REGISTRY]

    def get_enabled_types(self) -> list[str]:
        """Return list of currently enabled opportunity type names."""
        return [d.type_name for d in self._detectors if d.is_enabled()]

    async def detect_all(
        self, context: dict[str, Any] | None = None
    ) -> DetectionResult:
        """Run all enabled detectors concurrently.

        Args:
            context: Detection context with metrics, logs, and code data.
                     Passed to each detector.

        Returns:
            DetectionResult with all found opportunities.
        """
        context = context or {}
        start = time.time()
        enabled_detectors = [d for d in self._detectors if d.is_enabled()]

        logger.info(
            "Starting opportunity detection with %d enabled types: %s",
            len(enabled_detectors),
            [d.type_name for d in enabled_detectors],
        )

        # Run all detectors concurrently
        tasks = []
        for detector in enabled_detectors:
            coro = self._run_detector_with_timeout(detector, context)
            tasks.append(coro)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_opportunities: list[Opportunity] = []
        errors: list[str] = []
        types_scanned: list[str] = []

        for i, result in enumerate(results):
            detector = enabled_detectors[i]
            types_scanned.append(detector.type_name)

            if isinstance(result, Exception):
                error_msg = f"Detector {detector.type_name} failed: {result}"
                logger.error(error_msg)
                errors.append(error_msg)
            elif isinstance(result, list):
                all_opportunities.extend(result)

        # Filter by minimum confidence
        filtered = [
            opp
            for opp in all_opportunities
            if opp.confidence >= self.config.min_confidence
        ]

        # Sort by score descending, cap at max
        filtered.sort(key=lambda o: o.score, reverse=True)
        capped = filtered[: self.config.max_opportunities_per_run]

        duration = time.time() - start

        logger.info(
            "Opportunity detection complete: %d found, %d after filtering, "
            "%d returned in %.2fs, %d errors",
            len(all_opportunities),
            len(filtered),
            len(capped),
            duration,
            len(errors),
        )

        return DetectionResult(
            opportunities=capped,
            scan_duration_seconds=duration,
            types_scanned=types_scanned,
            errors=errors,
        )

    async def detect_single(
        self, type_name: str, context: dict[str, Any] | None = None
    ) -> DetectionResult:
        """Run a single detector by type name.

        Args:
            type_name: The opportunity type to detect.
            context: Detection context.

        Returns:
            DetectionResult with findings from the single detector.
        """
        context = context or {}
        start = time.time()

        detector_map = {d.type_name: d for d in self._detectors}
        detector = detector_map.get(type_name)

        if detector is None:
            return DetectionResult(
                errors=[f"Unknown opportunity type: {type_name}"],
                scan_duration_seconds=time.time() - start,
            )

        try:
            opportunities = await self._run_detector_with_timeout(detector, context)
        except Exception as exc:
            return DetectionResult(
                errors=[f"Detector {type_name} failed: {exc}"],
                scan_duration_seconds=time.time() - start,
            )

        filtered = [
            opp for opp in opportunities if opp.confidence >= self.config.min_confidence
        ]
        filtered.sort(key=lambda o: o.score, reverse=True)

        return DetectionResult(
            opportunities=filtered[: self.config.max_opportunities_per_run],
            scan_duration_seconds=time.time() - start,
            types_scanned=[type_name],
        )

    async def _run_detector_with_timeout(
        self, detector: BaseOpportunityDetector, context: dict[str, Any]
    ) -> list[Opportunity]:
        """Run a single detector with timeout protection."""
        return await asyncio.wait_for(
            detector.detect(context),
            timeout=self.config.scan_timeout_seconds,
        )

    def summary_stats(self, result: DetectionResult) -> dict[str, Any]:
        """Generate summary statistics from a detection result.

        Args:
            result: DetectionResult to summarize.

        Returns:
            Dictionary with summary statistics.
        """
        opps = result.opportunities
        if not opps:
            return {
                "total_opportunities": 0,
                "by_severity": {},
                "by_category": {},
                "avg_score": 0.0,
                "avg_confidence": 0.0,
            }

        severity_counts: dict[str, int] = {}
        category_counts: dict[str, int] = {}
        total_score = 0.0
        total_confidence = 0.0

        for opp in opps:
            sev = opp.severity.name
            cat = opp.category.value
            severity_counts[sev] = severity_counts.get(sev, 0) + 1
            category_counts[cat] = category_counts.get(cat, 0) + 1
            total_score += opp.score
            total_confidence += opp.confidence

        return {
            "total_opportunities": len(opps),
            "by_severity": severity_counts,
            "by_category": category_counts,
            "avg_score": round(total_score / len(opps), 3),
            "avg_confidence": round(total_confidence / len(opps), 3),
        }
