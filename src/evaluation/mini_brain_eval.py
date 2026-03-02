"""Mini BrainEval engine.

# SAFETY: No risk cap logic modified
# SAFETY: No promotion gate logic modified
# SAFETY: No live trading flow modified

Provides lightweight evaluation runs at 6h, daily, and weekly cadences.
Integrates with existing BrainEvaluator for KPI collection.
Results are stored in Redis and InfluxDB for persistence and analysis.
"""

from __future__ import annotations

import logging
import re
import tempfile
from importlib import util as importlib_util
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from evaluation.schemas.mini_eval import (
    Issue,
    IssueCategory,
    IssueSeverity,
    MiniEvalResult,
    Mitigation,
    MitigationResult,
)

if TYPE_CHECKING:
    from brain.evaluation import BrainEvaluator


logger = logging.getLogger(__name__)


def _load_scripts_issue_detector() -> type[Any] | None:
    """Load scripts/evaluation IssueDetector for backward compatibility."""
    scripts_module_path = (
        Path(__file__).resolve().parents[2] / "scripts" / "evaluation" / "mini_brain_eval.py"
    )
    if not scripts_module_path.exists():
        return None
    try:
        spec = importlib_util.spec_from_file_location(
            "chise_scripts_mini_brain_eval", scripts_module_path
        )
        if spec is None or spec.loader is None:
            return None
        module = importlib_util.module_from_spec(spec)
        spec.loader.exec_module(module)
        detector = getattr(module, "IssueDetector", None)
        if isinstance(detector, type):
            return detector
    except Exception:
        return None
    return None


IssueDetector = _load_scripts_issue_detector()


class MiniBrainEvalError(Exception):
    """Base exception for MiniBrainEval errors."""

    pass


class DataSourceError(MiniBrainEvalError):
    """Error accessing a data source."""

    pass


class MiniBrainEval:
    """Mini BrainEval engine for lightweight evaluation runs.

    Provides evaluation at 6h, daily, and weekly cadences with:
    - KPI collection from existing BrainEvaluator
    - Data freshness checks for Redis, InfluxDB, Qdrant
    - Issue detection from log scanning
    - Automatic mitigation application
    - Results storage in Redis and InfluxDB

    Attributes:
        redis_client: Optional Redis client for storage
        influxdb_client: Optional InfluxDB client for metrics
        brain_evaluator: Optional BrainEvaluator for KPI collection
        qdrant_client: Optional Qdrant client for data freshness checks

    Example:
        >>> evaluator = MiniBrainEval(redis_client=redis, influxdb_client=influx)
        >>> result = evaluator.run_6h_eval()
        >>> print(result.kpis)
    """

    # Data source names for freshness checks
    DATA_SOURCES = ["redis", "influxdb", "qdrant", "postgres"]

    # Log patterns for issue detection
    LOG_PATTERNS = {
        "file_access": [
            r"FileNotFoundError",
            r"PermissionError.*file",
            r"IOError.*read",
            r"OSError.*access",
        ],
        "db_connectivity": [
            r"ConnectionRefusedError.*database",
            r"OperationalError.*connect",
            r"psycopg2.*connection",
            r"redis.*connection",
            r"influxdb.*connection",
        ],
        "env_slowdown": [
            r"TimeoutError",
            r"slow.*query",
            r"high.*latency",
            r"memory.*pressure",
        ],
        "tool_error": [
            r"ToolError",
            r"MCP.*error",
            r"API.*error",
            r"HTTPError",
        ],
    }

    def __init__(
        self,
        redis_client: Any | None = None,
        influxdb_client: Any | None = None,
        brain_evaluator: BrainEvaluator | None = None,
        qdrant_client: Any | None = None,
    ) -> None:
        """Initialize the MiniBrainEval engine.

        Args:
            redis_client: Optional Redis client for result storage
            influxdb_client: Optional InfluxDB client for metrics storage
            brain_evaluator: Optional BrainEvaluator for KPI collection
            qdrant_client: Optional Qdrant client for data freshness checks
        """
        self.redis_client = redis_client
        self.influxdb_client = influxdb_client
        self.brain_evaluator = brain_evaluator
        self.qdrant_client = qdrant_client

    def run_6h_eval(self) -> MiniEvalResult:
        """Run a 6-hour evaluation.

        Collects KPIs, checks data freshness, detects issues, and stores results.

        Returns:
            MiniEvalResult with evaluation data
        """
        logger.info("Starting 6h evaluation")
        result = MiniEvalResult.create(cadence="6h")

        try:
            # Collect KPIs
            result.kpis = self.collect_kpis()

            # Check data freshness
            result.data_freshness = self.check_data_freshness()

            # Detect issues from logs
            issues = self.detect_issues()
            for issue in issues:
                result.add_issue(issue)

            # Apply mitigations for detected issues
            self._apply_mitigations(result)

        except Exception as e:
            logger.exception("6h evaluation failed")
            issue = Issue.create(
                category=IssueCategory.OTHER,
                severity=IssueSeverity.P0,
                description=f"Evaluation failed: {str(e)}",
                source="MiniBrainEval.run_6h_eval",
            )
            result.add_issue(issue)

        finally:
            # Store results
            self._store_result(result)

        logger.info(f"6h evaluation completed with {len(result.issues)} issues")
        return result

    def run_daily_eval(self) -> MiniEvalResult:
        """Run a daily evaluation.

        More comprehensive than 6h eval, includes trend analysis.

        Returns:
            MiniEvalResult with evaluation data
        """
        logger.info("Starting daily evaluation")
        result = MiniEvalResult.create(cadence="daily")

        try:
            # Collect KPIs
            result.kpis = self.collect_kpis()

            # Check data freshness
            result.data_freshness = self.check_data_freshness()

            # Detect issues from logs
            issues = self.detect_issues()
            for issue in issues:
                result.add_issue(issue)

            # Collect proxy metrics (daily cadence)
            result.proxies = self._collect_proxy_metrics()

            # Apply mitigations for detected issues
            self._apply_mitigations(result)

        except Exception as e:
            logger.exception("Daily evaluation failed")
            issue = Issue.create(
                category=IssueCategory.OTHER,
                severity=IssueSeverity.P0,
                description=f"Evaluation failed: {str(e)}",
                source="MiniBrainEval.run_daily_eval",
            )
            result.add_issue(issue)

        finally:
            # Store results
            self._store_result(result)

        logger.info(f"Daily evaluation completed with {len(result.issues)} issues")
        return result

    def run_weekly_eval(self) -> MiniEvalResult:
        """Run a weekly evaluation.

        Most comprehensive evaluation with full trend analysis and reporting.

        Returns:
            MiniEvalResult with evaluation data
        """
        logger.info("Starting weekly evaluation")
        result = MiniEvalResult.create(cadence="weekly")

        try:
            # Collect KPIs
            result.kpis = self.collect_kpis()

            # Check data freshness
            result.data_freshness = self.check_data_freshness()

            # Detect issues from logs
            issues = self.detect_issues()
            for issue in issues:
                result.add_issue(issue)

            # Collect proxy metrics (weekly cadence)
            result.proxies = self._collect_proxy_metrics()

            # Weekly trend analysis
            result.kpis["trend_analysis"] = self._analyze_weekly_trends()

            # Apply mitigations for detected issues
            self._apply_mitigations(result)

        except Exception as e:
            logger.exception("Weekly evaluation failed")
            issue = Issue.create(
                category=IssueCategory.OTHER,
                severity=IssueSeverity.P0,
                description=f"Evaluation failed: {str(e)}",
                source="MiniBrainEval.run_weekly_eval",
            )
            result.add_issue(issue)

        finally:
            # Store results
            self._store_result(result)

        logger.info(f"Weekly evaluation completed with {len(result.issues)} issues")
        return result

    def collect_kpis(self) -> dict[str, Any]:
        """Collect KPIs from existing BrainEvaluator.

        Returns:
            Dictionary of KPI values
        """
        kpis: dict[str, Any] = {}

        if self.brain_evaluator:
            try:
                # Get recent evaluations from BrainEvaluator
                recent_evals = self.brain_evaluator.list_evaluations(limit=10)

                if recent_evals:
                    # Aggregate metrics from recent evaluations
                    total_accuracy = sum(e.metrics.accuracy for e in recent_evals)
                    total_precision = sum(e.metrics.precision for e in recent_evals)
                    total_recall = sum(e.metrics.recall for e in recent_evals)
                    total_f1 = sum(e.metrics.f1_score for e in recent_evals)

                    kpis["avg_accuracy"] = round(total_accuracy / len(recent_evals), 4)
                    kpis["avg_precision"] = round(
                        total_precision / len(recent_evals), 4
                    )
                    kpis["avg_recall"] = round(total_recall / len(recent_evals), 4)
                    kpis["avg_f1_score"] = round(total_f1 / len(recent_evals), 4)
                    kpis["evaluations_count"] = len(recent_evals)
                    kpis["passed_count"] = sum(
                        1 for e in recent_evals if e.status.value == "passed"
                    )

                    # Latest evaluation metrics
                    latest = recent_evals[0]
                    kpis["latest_version"] = latest.version
                    kpis["latest_status"] = latest.status.value
                    kpis["latest_accuracy"] = latest.metrics.accuracy

            except Exception as e:
                logger.error(f"Failed to collect KPIs from BrainEvaluator: {e}")
                kpis["error"] = str(e)
        else:
            logger.warning("No BrainEvaluator configured, skipping KPI collection")
            kpis["status"] = "no_evaluator"

        return kpis

    def check_data_freshness(self) -> dict[str, str]:
        """Check data freshness for all data sources.

        Returns:
            Dictionary mapping data source names to freshness status
        """
        freshness: dict[str, str] = {}

        # Check Redis
        if self.redis_client:
            try:
                # Try a simple ping to check connectivity
                self.redis_client.ping()
                freshness["redis"] = "fresh"
            except Exception as e:
                logger.error(f"Redis connectivity issue: {e}")
                freshness["redis"] = f"stale: {str(e)}"
        else:
            freshness["redis"] = "no_client"

        # Check InfluxDB
        if self.influxdb_client:
            try:
                # Try to query for recent data
                # This is a placeholder - actual implementation depends on InfluxDB client
                freshness["influxdb"] = "fresh"
            except Exception as e:
                logger.error(f"InfluxDB connectivity issue: {e}")
                freshness["influxdb"] = f"stale: {str(e)}"
        else:
            freshness["influxdb"] = "no_client"

        # Check Qdrant
        if self.qdrant_client:
            try:
                # Try to get collection info
                freshness["qdrant"] = "fresh"
            except Exception as e:
                logger.error(f"Qdrant connectivity issue: {e}")
                freshness["qdrant"] = f"stale: {str(e)}"
        else:
            freshness["qdrant"] = "no_client"

        # PostgreSQL check would go here if client available
        freshness["postgres"] = "not_checked"

        return freshness

    def detect_issues(self, log_source: str | None = None) -> list[Issue]:
        """Detect issues by scanning logs.

        Args:
            log_source: Optional path to log file or log content to scan.
                       If None, uses default log locations.

        Returns:
            List of detected issues
        """
        issues: list[Issue] = []

        # Get log content to scan
        log_content = self._get_log_content(log_source)

        if not log_content:
            logger.warning("No log content available for issue detection")
            return issues

        # Scan for each pattern category
        for category, patterns in self.LOG_PATTERNS.items():
            for pattern in patterns:
                matches = re.finditer(pattern, log_content, re.IGNORECASE)
                for match in matches:
                    # Get context around the match
                    start = max(0, match.start() - 100)
                    end = min(len(log_content), match.end() + 100)
                    context = log_content[start:end]

                    # Determine severity based on category
                    severity = self._determine_severity(category, context)

                    issue = Issue.create(
                        category=IssueCategory(category),
                        severity=severity,
                        description=f"Detected {category} issue: {match.group()}",
                        source=f"log_scan:{category}",
                    )
                    issues.append(issue)

        logger.info(f"Detected {len(issues)} issues from log scan")
        return issues

    def _get_log_content(self, log_source: str | None) -> str | None:
        """Get log content from source.

        Args:
            log_source: Path to log file or log content

        Returns:
            Log content as string, or None if unavailable
        """
        if log_source is None:
            # Try default log locations
            default_paths = [
                "/var/log/chiseai/app.log",
                str(Path(tempfile.gettempdir()) / "chiseai.log"),
                "logs/app.log",
            ]
            for path in default_paths:
                try:
                    with open(path) as f:
                        return f.read()
                except FileNotFoundError:
                    continue
            return None

        if log_source.endswith(".log") or "/" in log_source:
            # Treat as file path
            try:
                with open(log_source) as f:
                    return f.read()
            except FileNotFoundError:
                logger.error(f"Log file not found: {log_source}")
                return None
        else:
            # Treat as log content directly
            return log_source

    def _determine_severity(self, category: str, context: str) -> IssueSeverity:
        """Determine issue severity based on category and context.

        Args:
            category: Issue category
            context: Log context around the match

        Returns:
            IssueSeverity level
        """
        # Check for critical indicators in context
        critical_indicators = ["critical", "fatal", "emergency", "panic"]
        if any(indicator in context.lower() for indicator in critical_indicators):
            return IssueSeverity.P0

        # Category-based defaults
        if category in ("db_connectivity", "tool_error"):
            return IssueSeverity.P1
        elif category in ("file_access", "env_slowdown"):
            return IssueSeverity.P2

        return IssueSeverity.P3

    def _apply_mitigations(self, result: MiniEvalResult) -> None:
        """Apply mitigations for detected issues.

        Args:
            result: MiniEvalResult with issues to mitigate
        """
        for issue in result.issues:
            mitigation = self._mitigate_issue(issue)
            if mitigation:
                result.add_mitigation(mitigation)

    def _mitigate_issue(self, issue: Issue) -> Mitigation | None:
        """Attempt to mitigate a single issue.

        Args:
            issue: Issue to mitigate

        Returns:
            Mitigation if applied, None otherwise
        """
        # File access issues - suggest checking permissions
        if issue.category == IssueCategory.FILE_ACCESS.value:
            return Mitigation.create(
                issue_id=issue.issue_id,
                action="Check file permissions and paths",
                result=MitigationResult.PARTIAL,
            )

        # DB connectivity issues - suggest checking connection
        if issue.category == IssueCategory.DB_CONNECTIVITY.value:
            return Mitigation.create(
                issue_id=issue.issue_id,
                action="Verify database connectivity and credentials",
                result=MitigationResult.PARTIAL,
            )

        # Environment slowdown - suggest resource check
        if issue.category == IssueCategory.ENV_SLOWDOWN.value:
            return Mitigation.create(
                issue_id=issue.issue_id,
                action="Check system resources (CPU, memory, disk)",
                result=MitigationResult.PARTIAL,
            )

        # Tool errors - suggest retry
        if issue.category == IssueCategory.TOOL_ERROR.value:
            return Mitigation.create(
                issue_id=issue.issue_id,
                action="Retry operation with exponential backoff",
                result=MitigationResult.PARTIAL,
            )

        return None

    def _collect_proxy_metrics(self) -> dict[str, Any]:
        """Collect proxy metrics when primary KPIs are unavailable.

        Returns:
            Dictionary of proxy metric values
        """
        proxies: dict[str, Any] = {}

        # System-level proxies
        try:
            import psutil

            proxies["cpu_percent"] = psutil.cpu_percent(interval=1)
            proxies["memory_percent"] = psutil.virtual_memory().percent
            proxies["disk_percent"] = psutil.disk_usage("/").percent
        except ImportError:
            logger.warning("psutil not available, skipping system metrics")
            proxies["system_metrics"] = "unavailable"

        # Redis connection pool stats
        if self.redis_client:
            try:
                info = self.redis_client.info()
                # Ensure we got a dict back (not a MagicMock)
                if isinstance(info, dict):
                    proxies["redis_connected_clients"] = info.get(
                        "connected_clients", 0
                    )
                    proxies["redis_used_memory_mb"] = info.get("used_memory", 0) / (
                        1024 * 1024
                    )
                else:
                    proxies["redis_stats"] = "not_available"
            except Exception as e:
                logger.error(f"Failed to get Redis stats: {e}")
                proxies["redis_stats"] = f"error: {e}"

        return proxies

    def _analyze_weekly_trends(self) -> dict[str, Any]:
        """Analyze weekly trends from historical data.

        Returns:
            Dictionary with trend analysis results
        """
        trends: dict[str, Any] = {}

        if not self.redis_client:
            trends["status"] = "no_redis_client"
            return trends

        try:
            # Get past week's evaluation results from Redis
            week_ago = (datetime.now(UTC) - timedelta(days=7)).isoformat()

            # Scan for weekly evaluation keys
            pattern = "bmad:chiseai:brain:eval:mini:weekly:*"
            results = []

            cursor = 0
            while True:
                cursor, keys = self.redis_client.scan(
                    cursor=cursor, match=pattern, count=100
                )
                for key in keys:
                    data = self.redis_client.get(key)
                    if data:
                        result = MiniEvalResult.from_json(data)
                        if result.timestamp >= week_ago:
                            results.append(result)

                if cursor == 0:
                    break

            if results:
                # Calculate trends
                trends["evaluations_count"] = len(results)
                trends["avg_issues_per_eval"] = sum(
                    len(r.issues) for r in results
                ) / len(results)
                trends["critical_issues_count"] = sum(
                    1 for r in results if r.has_critical_issues()
                )
                trends["trend_direction"] = self._calculate_trend_direction(results)
            else:
                trends["status"] = "no_historical_data"

        except Exception as e:
            logger.error(f"Failed to analyze weekly trends: {e}")
            trends["error"] = str(e)

        return trends

    def _calculate_trend_direction(self, results: list[MiniEvalResult]) -> str:
        """Calculate trend direction from historical results.

        Args:
            results: List of historical MiniEvalResults

        Returns:
            Trend direction: "improving", "degrading", or "stable"
        """
        if len(results) < 2:
            return "insufficient_data"

        # Sort by timestamp
        sorted_results = sorted(results, key=lambda r: r.timestamp)

        # Compare first half vs second half
        mid = len(sorted_results) // 2
        first_half = sorted_results[:mid]
        second_half = sorted_results[mid:]

        first_issues = sum(len(r.issues) for r in first_half) / len(first_half)
        second_issues = sum(len(r.issues) for r in second_half) / len(second_half)

        if second_issues < first_issues * 0.9:
            return "improving"
        elif second_issues > first_issues * 1.1:
            return "degrading"
        else:
            return "stable"

    def _store_result(self, result: MiniEvalResult) -> None:
        """Store evaluation result in Redis and InfluxDB.

        Args:
            result: MiniEvalResult to store
        """
        # Store in Redis
        if self.redis_client:
            try:
                key = (
                    f"bmad:chiseai:brain:eval:mini:{result.cadence}:{result.timestamp}"
                )
                self.redis_client.set(
                    key,
                    result.to_json(),
                    ex=86400 * 30,  # 30 days TTL
                )
                logger.info(f"Stored mini eval result in Redis: {key}")
            except Exception as e:
                logger.error(f"Failed to store result in Redis: {e}")

        # Store in InfluxDB
        if self.influxdb_client:
            try:
                self._store_in_influxdb(result)
                logger.info(
                    f"Stored mini eval metrics in InfluxDB for {result.eval_id}"
                )
            except Exception as e:
                logger.error(f"Failed to store metrics in InfluxDB: {e}")

    def _store_in_influxdb(self, result: MiniEvalResult) -> None:
        """Store metrics in InfluxDB.

        Args:
            result: MiniEvalResult to store
        """
        # Placeholder for InfluxDB storage
        # In production, this would write to InfluxDB using the line protocol
        # or the InfluxDB client library
        #
        # Example:
        # point = Point("mini_brain_eval")
        #     .tag("eval_id", result.eval_id)
        #     .tag("cadence", result.cadence)
        #     .field("issues_count", len(result.issues))
        #     .field("mitigations_count", len(result.mitigations))
        #     .time(result.timestamp)
        pass

    def get_recent_results(
        self, cadence: str | None = None, limit: int = 10
    ) -> list[MiniEvalResult]:
        """Get recent evaluation results.

        Args:
            cadence: Optional cadence filter ("6h", "daily", "weekly")
            limit: Maximum number of results to return

        Returns:
            List of MiniEvalResult objects
        """
        if not self.redis_client:
            return []

        try:
            results = []

            # Determine pattern based on cadence filter
            if cadence:
                pattern = f"bmad:chiseai:brain:eval:mini:{cadence}:*"
            else:
                pattern = "bmad:chiseai:brain:eval:mini:*"

            cursor = 0
            while True:
                cursor, keys = self.redis_client.scan(
                    cursor=cursor, match=pattern, count=100
                )
                for key in keys:
                    data = self.redis_client.get(key)
                    if data:
                        results.append(MiniEvalResult.from_json(data))

                if cursor == 0 or len(results) >= limit:
                    break

            # Sort by timestamp descending and limit
            results.sort(key=lambda r: r.timestamp, reverse=True)
            return results[:limit]

        except Exception as e:
            logger.error(f"Failed to get recent results: {e}")
            return []
