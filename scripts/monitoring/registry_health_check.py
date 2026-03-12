#!/usr/bin/env python3
"""Health check script for Model Registry.

This script performs comprehensive health checks on the Model Registry
 and returns results in JSON format with proper exit codes.

Usage:
    # Quick health check
    python scripts/monitoring/registry_health_check.py --quick



    # Full health check
    python scripts/monitoring/registry_health_check.py --full

    # JSON output to file
    python scripts/monitoring/registry_health_check.py --output json --output-file health_report.json

    # Prometheus metrics endpoint
    curl http://localhost:9091/metrics
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

# Add src to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from src.ml.model_registry.registry import (
    ModelRegistry,
)
from src.ml.monitoring.registry_metrics import (
    MetricsCollector,
    PrometheusMetricsCollector,
    get_metrics_collector,
    set_metrics_collector,
)
from src.ml.monitoring.registry_alerts import (
    AlertManager,
    AlertRule,
    AlertSeverity,
    DefaultAlertManager,
    create_default_alert_rules,
)

from src.ml.models.model_storage import FilesystemBackend

logger = logging.getLogger(__name__)


@dataclass
class HealthStatus:
    """Health check status enumeration."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    ERROR = "error"


@dataclass
class HealthCheckResult:
    """Result of a single health check.

    Attributes:
        timestamp: ISO 8601 format timestamp
        status: HealthStatus
        message: str
        details: dict[str, Any] = field(default_factory=dict)
        latency_seconds: float = 0.0
        checks: dict[str, Any] = field(default_factory=dict)
        total_issues: int = 0
        critical_issues: int = 0
        warnings: int = 0
    """

    timestamp: str = ""
    status: str = ""
    message: str = ""


class HealthCheck:
    """Orchestrates health checks for the Model Registry."""

    def __init__(
        self,
        registry: Optional[ModelRegistry] = None,
        storage_backend: Optional[FilesystemBackend] = None,
        max_latency_seconds: float = 1.0,
        max_storage_percent: float = 80.0,
        max_failed_ops: int = 5,
        min_cache_hit_rate: float = 50.0,
    ):
        self.registry = registry
        self.storage_backend = storage_backend
        self.max_latency_seconds = max_latency_seconds
        self.max_storage_percent = max_storage_percent
        self.max_failed_ops = max_failed_ops
        self.min_cache_hit_rate = min_cache_hit_rate

        # Initialize alert manager with default rules
        self.alert_manager = DefaultAlertManager()
        for rule in create_default_alert_rules():
            self.alert_manager.add_rule(rule)

    def _get_storage_size(self, path: str) -> int:
        """Calculate total storage size in bytes."""
        total_size = 0
        try:
            for entry in os.scandir(path):
                entry_path = os.path.join(path, entry)
                if os.path.isfile(entry_path):
                    total_size += os.path.getsize(entry_path)
        except Exception as e:
            logger.debug(f"Error scanning {path}: {e}")
        return total_size

    def _connectivity_check(self) -> dict[str, Any]:
        """Run connectivity check."""
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": HealthStatus.DEGRADED.value,
            "message": "Registry not connected",
            "details": {},
            "latency_seconds": 0.0,
            "checks": {
                "connectivity": {
                    "status": "degraded",
                    "message": "Registry not connected",
                }
            },
            "total_issues": 1,
            "critical_issues": 0,
            "warnings": 1,
        }

    def _storage_backend_check(self, error_msg: str) -> dict[str, Any]:
        """Run storage backend check with error."""
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": HealthStatus.DEGRADED.value,
            "message": f"Storage backend error: {error_msg}",
            "details": {},
            "latency_seconds": 0.0,
            "checks": {"storage_backend": {"status": "degraded", "message": error_msg}},
            "total_issues": 1,
            "critical_issues": 0,
            "warnings": 1,
        }

    def _calculate_cache_hit_rate(self, metrics: Any) -> float:
        """Calculate cache hit rate from metrics."""
        try:
            cache_data = metrics.to_dict().get("cache", {})
            return cache_data.get("hit_rate_percent", 0.0)
        except Exception:
            return 0.0

    def run_check(self) -> dict[str, Any]:
        """Run all health checks and return results."""
        results: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": HealthStatus.HEALTHY.value,
            "message": "All checks passed",
            "details": {},
            "latency_seconds": 0.0,
            "checks": {},
            "total_issues": 0,
            "critical_issues": 0,
            "warnings": 0,
        }

        # Check 1: Connectivity
        if not self.registry:
            return self._connectivity_check()

        # Check 2: Storage backend
        if self.storage_backend:
            try:
                models = self.storage_backend.list_models()
                logger.info(f"Storage backend accessible: {len(models)} models")
            except Exception as e:
                return self._storage_backend_check(str(e))

        # Check 3: Recent operations
        try:
            if self.registry:
                versions = self.registry.list_versions()
                recent_count = len(versions)
                results["checks"]["recent_operations"] = {
                    "status": HealthStatus.HEALTHY.value,
                    "message": f"Found {recent_count} recent model operations",
                    "details": {"count": recent_count},
                }
        except Exception as e:
            results["checks"]["recent_operations"] = {
                "status": HealthStatus.DEGRADED.value,
                "message": f"Failed to list versions: {str(e)}",
                "details": {"error": str(e)},
            }
            results["total_issues"] += 1

        # Check 4: Storage usage
        if self.registry:
            try:
                metrics_collector = get_metrics_collector()
                if isinstance(metrics_collector, PrometheusMetricsCollector):
                    metrics = metrics_collector.get_metrics()
                    storage_bytes = getattr(metrics, "storage_usage_bytes", 0)
                    model_count = getattr(metrics, "models_count", 0)
                    cache_hit_rate = self._calculate_cache_hit_rate(metrics)

                    # Check storage percent
                    storage_capacity = 10 * 1024 * 1024 * 1024  # 10GB default
                    storage_percent = (
                        (storage_bytes / storage_capacity) * 100
                        if storage_capacity > 0
                        else 0
                    )
                    if storage_percent > self.max_storage_percent:
                        results["checks"]["storage_usage"] = {
                            "status": HealthStatus.DEGRADED.value,
                            "message": f"Storage usage at {storage_percent:.1f}% exceeds {self.max_storage_percent:.0f}%",
                            "details": {
                                "usage_bytes": storage_bytes,
                                "capacity_bytes": storage_capacity,
                                "percent": storage_percent,
                            },
                        }
                        results["warnings"] += 1
                    else:
                        results["checks"]["storage_usage"] = {
                            "status": HealthStatus.HEALTHY.value,
                            "message": f"Storage usage at {storage_percent:.1f}% ({storage_bytes / 1024 / 1024:.1f} MB)",
                            "details": {
                                "usage_bytes": storage_bytes,
                                "capacity_bytes": storage_capacity,
                                "percent": storage_percent,
                            },
                        }
                else:
                    results["total_issues"] += 1
            except Exception as e:
                results["checks"]["storage_usage"] = {
                    "status": HealthStatus.UNAVAILABLE.value,
                    "message": f"Storage backend not configured",
                    "details": {"error": str(e)},
                }
                results["total_issues"] += 1
                results["critical_issues"] += 1

        # Check 5: Cache performance
        if self.registry:
            try:
                metrics_collector = get_metrics_collector()
                metrics = metrics_collector.get_metrics()
                cache_data = metrics.to_dict().get("cache", {})
                hit_rate = cache_data.get("hit_rate_percent", 0)

                if hit_rate < self.min_cache_hit_rate:
                    results["checks"]["cache_performance"] = {
                        "status": HealthStatus.DEGRADED.value,
                        "message": f"Cache hit rate at {hit_rate:.1f}% is below {self.min_cache_hit_rate:.0f}%",
                        "details": cache_data,
                    }
                    results["warnings"] += 1
                else:
                    results["checks"]["cache_performance"] = {
                        "status": HealthStatus.HEALTHY.value,
                        "message": f"Cache hit rate at {hit_rate:.1f}% is healthy",
                        "details": cache_data,
                    }
            except Exception as e:
                results["checks"]["cache_performance"] = {
                    "status": HealthStatus.UNAVAILABLE.value,
                    "message": f"Failed to get cache metrics: {str(e)}",
                    "details": {"error": str(e)},
                }
                results["total_issues"] += 1

        # Check 6: Model retrieval latency
        if self.registry:
            try:
                metrics_collector = get_metrics_collector()
                metrics = metrics_collector.get_metrics()
                latency_data = metrics.to_dict().get("model_retrieval_latency", {})
                p95 = latency_data.get("p95", 0)

                if p95 > self.max_latency_seconds:
                    results["checks"]["retrieval_latency"] = {
                        "status": HealthStatus.DEGRADED.value,
                        "message": f"P95 latency at {p95:.3f}s exceeds {self.max_latency_seconds:.3f}s threshold",
                        "details": latency_data,
                    }
                    results["critical_issues"] += 1
                else:
                    results["checks"]["retrieval_latency"] = {
                        "status": HealthStatus.HEALTHY.value,
                        "message": f"P95 latency at {p95:.3f}s is within threshold",
                        "details": latency_data,
                    }
            except Exception as e:
                results["checks"]["retrieval_latency"] = {
                    "status": HealthStatus.UNAVAILABLE.value,
                    "message": f"Failed to get retrieval latency: {str(e)}",
                    "details": {"error": str(e)},
                }
                results["total_issues"] += 1
                results["critical_issues"] += 1

        # Check 7: Failed operations
        if self.registry:
            try:
                metrics_collector = get_metrics_collector()
                metrics = metrics_collector.get_metrics()
                ops_data = metrics.to_dict().get("operations", {})
                failed_ops = ops_data.get("failed_total", {})

                total_failed = (
                    sum(failed_ops.values())
                    if isinstance(failed_ops, dict)
                    else failed_ops
                )
                if total_failed > self.max_failed_ops:
                    results["checks"]["failed_operations"] = {
                        "status": HealthStatus.DEGRADED.value,
                        "message": f"Total failed operations in last 5 minutes: {total_failed}. Exceeds threshold of {self.max_failed_ops}",
                        "details": {
                            "total_failed": total_failed,
                            "threshold": self.max_failed_ops,
                            "operations": failed_ops,
                        },
                    }
                    results["warnings"] += 1
                else:
                    results["checks"]["failed_operations"] = {
                        "status": HealthStatus.HEALTHY.value,
                        "message": f"Failed operations in acceptable range: {total_failed} in last 5 minutes",
                        "details": {"total_failed": total_failed},
                    }
            except Exception as e:
                results["checks"]["failed_operations"] = {
                    "status": HealthStatus.UNAVAILABLE.value,
                    "message": f"Failed to get failed operations: {str(e)}",
                    "details": {"error": str(e)},
                }
                results["total_issues"] += 1

        # Check 8: Alert status
        if self.alert_manager:
            try:
                metrics_collector = get_metrics_collector()
                alerts = self.alert_manager.evaluate(metrics_collector.get_metrics())

                if alerts:
                    results["checks"]["alerts"] = {
                        "status": HealthStatus.DEGRADED.value,
                        "message": f"{len(alerts)} active alerts detected",
                        "details": {
                            "active_count": len(alerts),
                            "alerts": [
                                {"name": a.name, "severity": a.severity.value}
                                for a in alerts
                            ],
                        },
                    }
                    results["warnings"] += len(alerts)
                else:
                    results["checks"]["alerts"] = {
                        "status": HealthStatus.HEALTHY.value,
                        "message": "No active alerts",
                        "details": {"active_count": 0, "alerts": []},
                    }
            except Exception as e:
                results["checks"]["alerts"] = {
                    "status": HealthStatus.UNAVAILABLE.value,
                    "message": f"Failed to evaluate alerts: {str(e)}",
                    "details": {"error": str(e)},
                }
                results["total_issues"] += 1
                results["critical_issues"] += 1

        # Check 9: Integrity (integrity failures in failed ops)
        # Integrity failures are tracked as failed operations with "integrity" error type
        if self.registry:
            try:
                metrics_collector = get_metrics_collector()
                metrics = metrics_collector.get_metrics()
                ops_data = metrics.to_dict().get("operations", {})
                failed_ops = ops_data.get("failed_total", {})

                integrity_failures = (
                    sum(
                        v
                        for k, v in failed_ops.items()
                        if isinstance(failed_ops, dict)
                        and k.startswith("integrity_failure")
                    )
                    if isinstance(failed_ops, dict)
                    else 0
                )

                if integrity_failures > 0:
                    results["checks"]["integrity"] = {
                        "status": HealthStatus.DEGRADED.value,
                        "message": f"Integrity failures detected: {integrity_failures} integrity error(s)",
                        "details": {"integrity_failures": integrity_failures},
                    }
                    results["warnings"] += 1
                    results["critical_issues"] += 1
                else:
                    results["checks"]["integrity"] = {
                        "status": HealthStatus.HEALTHY.value,
                        "message": "No integrity failures detected",
                        "details": {"integrity_failures": 0},
                    }
            except Exception as e:
                results["checks"]["integrity"] = {
                    "status": HealthStatus.UNAVAILABLE.value,
                    "message": f"Failed to check integrity: {str(e)}",
                    "details": {"error": str(e)},
                }
                results["total_issues"] += 1

        return results

    def to_json(
        self, results: dict[str, Any], output_file: Optional[str] = None
    ) -> str:
        """Convert results to JSON."""
        json_str = json.dumps(results, indent=2) + "\n"

        if output_file:
            try:
                with open(output_file, "w") as f:
                    f.write(json_str)
                logger.info(f"Results written to {output_file}")
            except Exception as e:
                logger.error(f"Failed to write results to {output_file}: {e}")

        return json_str

    def _print_summary(self, results: dict[str, Any]):
        """Print summary of health check results."""
        timestamp = results.get("timestamp", "")
        print(f"\n{'=' * 60}")
        print(f"Health Check Summary - {timestamp}")
        print(f"{'=' * 60}")

        for check_name, check_result in sorted(results.get("checks", {}).items()):
            status = check_result.get("status", "unknown")
            message = check_result.get("message", "")
            if status == HealthStatus.DEGRADED:
                print(f"  [DEGRADED] {check_name}: {message}")
            elif status == HealthStatus.UNAVAILABLE:
                print(f"  [UNAVAILABLE] {check_name}: {message}")
            else:
                print(f"  [HEALTHY] {check_name}: {message}")

        # Print details
        for check_name, check_result in sorted(results.get("checks", {}).items()):
            if check_name != "summary":
                details = check_result.get("details", {})
                if details:
                    print(f"    Details: {details}")

        # Print warnings
        if results.get("warnings", 0) > 0:
            print(f"\n{'=' * 33} WARNINGS {'=' * 33}")
            print(f"  Total warnings: {results['warnings']}")

        # Print critical issues
        if results.get("critical_issues", 0) > 0:
            print(f"\n{'=' * 31} CRITICAL ISSUES {'=' * 31}")
            print(f"  Total critical issues: {results['critical_issues']}")

        # Print overall status
        status = results.get("status", "unknown")
        print(f"\n{'=' * 60}")
        print(f"Overall Status: {status}")
        print(f"Total Issues: {results.get('total_issues', 0)}")
        print(f"Warnings: {results.get('warnings', 0)}")
        print(f"Critical Issues: {results.get('critical_issues', 0)}")
        print(f"Checks Run: {len(results.get('checks', {}))}")
        print(f"Timestamp: {results.get('timestamp', '')}")
        print(f"{'=' * 60}")

    def _format_prometheus(self, results: dict[str, Any]) -> str:
        """Format results as Prometheus metrics."""
        lines = []
        lines.append(
            "# HELP registry_health_status Overall health status (0=healthy, 1=degraded, 2=unavailable)"
        )
        lines.append("# TYPE registry_health_status gauge")
        status_map = {
            HealthStatus.HEALTHY: 0,
            HealthStatus.DEGRADED: 1,
            HealthStatus.UNAVAILABLE: 2,
        }
        status_val = status_map.get(results.get("status"), 2)
        lines.append(f"registry_health_status {status_val}")

        lines.append("# HELP registry_health_issues_total Total number of issues")
        lines.append("# TYPE registry_health_issues_total gauge")
        lines.append(f"registry_health_issues_total {results.get('total_issues', 0)}")

        lines.append(
            "# HELP registry_health_critical_issues Total number of critical issues"
        )
        lines.append("# TYPE registry_health_critical_issues gauge")
        lines.append(
            f"registry_health_critical_issues {results.get('critical_issues', 0)}"
        )

        lines.append("# HELP registry_health_warnings Total number of warnings")
        lines.append("# TYPE registry_health_warnings gauge")
        lines.append(f"registry_health_warnings {results.get('warnings', 0)}")

        return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Health check for Model Registry")
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Run quick health check (connectivity only)",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Run full health check (all checks)",
    )
    parser.add_argument(
        "--storage-path",
        type=str,
        default="/tmp/model-registry/storage",
        help="Path to model registry storage",
    )
    parser.add_argument(
        "--max-latency",
        type=float,
        default=1.0,
        help="Max retrieval latency in seconds (default: 1.0)",
    )
    parser.add_argument(
        "--max-storage-percent",
        type=float,
        default=80.0,
        help="Max storage usage percentage (default: 80.0)",
    )
    parser.add_argument(
        "--max-failures",
        type=int,
        default=5,
        help="Max failed operations in 5 min window (default: 5)",
    )
    parser.add_argument(
        "--min-cache-hit-rate",
        type=float,
        default=50.0,
        help="Minimum cache hit rate percentage (default: 50.0)",
    )
    parser.add_argument(
        "--output",
        choices=["json", "prometheus"],
        default="json",
        help="Output format",
    )
    parser.add_argument(
        "--output-file",
        type=str,
        default=None,
        help="Output file path (default: stdout)",
    )
    parser.add_argument(
        "--exit-on-error",
        action="store_true",
        help="Exit with code 1 on errors",
    )

    args = parser.parse_args()

    # Run health check
    start_time = time.time()
    checker = HealthCheck(
        max_latency_seconds=args.max_latency,
        max_storage_percent=args.max_storage_percent,
        max_failed_ops=args.max_failures,
        min_cache_hit_rate=args.min_cache_hit_rate,
    )

    results = checker.run_check()

    end_time = time.time()
    duration_seconds = end_time - start_time

    results["duration_seconds"] = round(duration_seconds, 3)

    # Print results
    if args.output == "json":
        output = checker.to_json(results, args.output_file)
        print(output)
    else:
        print(checker._format_prometheus(results))

    # Exit with appropriate code
    if args.exit_on_error:
        if results["status"] == HealthStatus.UNAVAILABLE:
            sys.exit(1)
        elif results["status"] == HealthStatus.DEGRADED:
            sys.exit(1)
        else:
            sys.exit(0)


if __name__ == "__main__":
    main()
