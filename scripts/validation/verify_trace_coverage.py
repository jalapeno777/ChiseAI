#!/usr/bin/env python3
"""
Trace Coverage Verification Script (TEMPO-2026-001, Task 4.6)

Queries Tempo API to verify distributed trace coverage across services.
Generates a coverage report showing:
- Trace counts per service
- Span attribute completeness
- Service coverage percentage
- Trace propagation verification

Usage:
    python scripts/validation/verify_trace_coverage.py [--service SERVICE] [--hours HOURS]

Story: TEMPO-2026-001
Task: 4.6 - Distributed Trace Flow Verification
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import requests

# Ensure src is in path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "src"))

# Default configuration
DEFAULT_TEMPO_ENDPOINT = os.getenv("TEMPO_ENDPOINT", "http://chiseai-tempo:3200")
DEFAULT_TEMPO_QUERY_ENDPOINT = os.getenv(
    "TEMPO_QUERY_ENDPOINT", "http://chiseai-tempo:16686"
)
COVERAGE_THRESHOLD = 0.90  # 90% coverage required

# Services to check for traces
EXPECTED_SERVICES = [
    "chiseai-api",
    "chiseai-strategy",
    "chiseai-ingestion",
    "chiseai-db",
    "chiseai-redis",
]

# Required span attributes
REQUIRED_ATTRIBUTES = [
    "service.name",
    "service.version",
    "deployment.environment",
]

# Recommended span attributes
RECOMMENDED_ATTRIBUTES = [
    "chiseai.service.type",
    "chiseai.service.group",
    "host.name",
    "http.method",
    "http.route",
    "http.status_code",
    "db.system",
    "db.operation",
    "error",
]


class TempoClient:
    """Client for querying Tempo API."""

    def __init__(self, endpoint: str = DEFAULT_TEMPO_ENDPOINT):
        self.endpoint = endpoint.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/json",
            }
        )

    def health_check(self) -> dict[str, Any]:
        """Check Tempo health status."""
        try:
            response = self.session.get(f"{self.endpoint}/ready", timeout=10)
            return {
                "status": (
                    "ready" if response.status_code in [200, 204] else "not_ready"
                ),
                "code": response.status_code,
            }
        except requests.RequestException as e:
            return {
                "status": "error",
                "error": str(e),
            }

    def search_traces(
        self,
        service: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        tags: dict[str, str] | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Search for traces in Tempo."""
        params: dict[str, Any] = {"limit": limit}

        if service:
            params["service"] = service

        if start:
            params["start"] = int(start.timestamp())

        if end:
            params["end"] = int(end.timestamp())

        if tags:
            for key, value in tags.items():
                params[f"tag.{key}"] = value

        url = f"{self.endpoint}/api/search?{urlencode(params)}"

        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            return {"error": str(e), "traces": []}

    def get_trace(self, trace_id: str) -> dict[str, Any]:
        """Get a specific trace by ID."""
        url = f"{self.endpoint}/api/traces/{trace_id}"

        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            return {"error": str(e)}

    def get_services(self) -> list[str]:
        """Get list of services with traces."""
        url = f"{self.endpoint}/api/services"

        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            return data.get("services", [])
        except requests.RequestException:
            return []

    def get_operations(self, service: str) -> list[str]:
        """Get list of operations for a service."""
        url = f"{self.endpoint}/api/operations?service={service}"

        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            return data.get("operations", [])
        except requests.RequestException:
            return []


class CoverageAnalyzer:
    """Analyze trace coverage across services."""

    def __init__(self, tempo_client: TempoClient):
        self.tempo = tempo_client
        self.results: dict[str, Any] = {}

    def analyze_service_coverage(
        self,
        hours: int = 24,
    ) -> dict[str, Any]:
        """Analyze trace coverage for all expected services."""
        end = datetime.now(UTC)
        start = end - timedelta(hours=hours)

        coverage = {
            "period_hours": hours,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "services": {},
            "summary": {
                "total_services": len(EXPECTED_SERVICES),
                "services_with_traces": 0,
                "coverage_percentage": 0.0,
                "passes_threshold": False,
            },
        }

        services_with_traces = 0

        for service in EXPECTED_SERVICES:
            service_coverage = self._analyze_service(service, start, end)
            coverage["services"][service] = service_coverage

            if service_coverage["trace_count"] > 0:
                services_with_traces += 1

        coverage["summary"]["services_with_traces"] = services_with_traces
        coverage["summary"]["coverage_percentage"] = (
            services_with_traces / len(EXPECTED_SERVICES) * 100
        )
        coverage["summary"]["passes_threshold"] = (
            coverage["summary"]["coverage_percentage"] >= COVERAGE_THRESHOLD * 100
        )

        return coverage

    def _analyze_service(
        self,
        service: str,
        start: datetime,
        end: datetime,
    ) -> dict[str, Any]:
        """Analyze coverage for a single service."""
        # Search for traces
        search_result = self.tempo.search_traces(
            service=service,
            start=start,
            end=end,
            limit=100,
        )

        traces = search_result.get("traces", [])
        trace_count = len(traces)

        result = {
            "service": service,
            "trace_count": trace_count,
            "has_traces": trace_count > 0,
            "span_count": 0,
            "attributes": {},
            "operations": [],
        }

        if trace_count == 0:
            return result

        # Get operations for this service
        result["operations"] = self.tempo.get_operations(service)

        # Analyze spans from first trace
        if traces:
            first_trace_id = traces[0].get("traceID", traces[0].get("traceId"))
            if first_trace_id:
                trace_detail = self.tempo.get_trace(first_trace_id)
                spans = self._extract_spans(trace_detail)
                result["span_count"] = len(spans)
                result["attributes"] = self._analyze_span_attributes(spans)

        return result

    def _extract_spans(self, trace_data: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract spans from trace data."""
        spans = []

        # Handle different response formats
        if "batches" in trace_data:
            # OTLP format
            for batch in trace_data["batches"]:
                for span in batch.get("scopeSpans", []):
                    spans.extend(span.get("spans", []))
        elif "data" in trace_data:
            # Jaeger format
            for trace in trace_data["data"]:
                spans.extend(trace.get("spans", []))
        elif "spans" in trace_data:
            spans = trace_data["spans"]

        return spans

    def _analyze_span_attributes(self, spans: list[dict[str, Any]]) -> dict[str, Any]:
        """Analyze attributes across spans."""
        attributes_found = set()
        attribute_values: dict[str, set] = {}

        for span in spans:
            # Handle different attribute formats
            attrs = span.get("attributes", [])
            if isinstance(attrs, dict):
                # Simple key-value format
                for key, value in attrs.items():
                    attributes_found.add(key)
                    if key not in attribute_values:
                        attribute_values[key] = set()
                    attribute_values[key].add(str(value))
            elif isinstance(attrs, list):
                # OTLP format with key-value list
                for attr in attrs:
                    key = attr.get("key", "")
                    if key:
                        attributes_found.add(key)
                        if key not in attribute_values:
                            attribute_values[key] = set()
                        value = attr.get("value", {})
                        if isinstance(value, dict):
                            # Get first non-empty value
                            for v in value.values():
                                if v:
                                    attribute_values[key].add(str(v))
                                    break

        return {
            "required_present": list(attributes_found & set(REQUIRED_ATTRIBUTES)),
            "required_missing": list(set(REQUIRED_ATTRIBUTES) - attributes_found),
            "recommended_present": list(attributes_found & set(RECOMMENDED_ATTRIBUTES)),
            "recommended_missing": list(set(RECOMMENDED_ATTRIBUTES) - attributes_found),
            "total_unique": len(attributes_found),
            "sample_values": {k: list(v)[:3] for k, v in attribute_values.items() if v},
        }

    def analyze_trace_propagation(
        self,
        hours: int = 24,
    ) -> dict[str, Any]:
        """Analyze trace propagation across services."""
        end = datetime.now(UTC)
        start = end - timedelta(hours=hours)

        propagation = {
            "period_hours": hours,
            "cross_service_traces": 0,
            "propagation_chains": [],
        }

        # Search for traces without service filter to find cross-service traces
        search_result = self.tempo.search_traces(
            start=start,
            end=end,
            limit=50,
        )

        traces = search_result.get("traces", [])

        for trace_summary in traces:
            trace_id = trace_summary.get("traceID", trace_summary.get("traceId"))
            if not trace_id:
                continue

            trace_detail = self.tempo.get_trace(trace_id)
            spans = self._extract_spans(trace_detail)

            # Count unique services in this trace
            services_in_trace = set()
            for span in spans:
                service_name = self._get_span_service(span)
                if service_name:
                    services_in_trace.add(service_name)

            if len(services_in_trace) > 1:
                propagation["cross_service_traces"] += 1
                if len(propagation["propagation_chains"]) < 5:
                    propagation["propagation_chains"].append(
                        {
                            "trace_id": trace_id,
                            "services": sorted(services_in_trace),
                            "span_count": len(spans),
                        }
                    )

        return propagation

    def _get_span_service(self, span: dict[str, Any]) -> str | None:
        """Extract service name from span."""
        # Try different attribute formats
        attrs = span.get("attributes", [])

        if isinstance(attrs, dict):
            return attrs.get("service.name")

        if isinstance(attrs, list):
            for attr in attrs:
                if attr.get("key") == "service.name":
                    value = attr.get("value", {})
                    return value.get("stringValue") or value.get("value")

        return None


def generate_report(
    coverage: dict[str, Any],
    propagation: dict[str, Any],
    health: dict[str, Any],
) -> str:
    """Generate human-readable coverage report."""
    lines = [
        "=" * 80,
        "TEMPO-2026-001: Distributed Trace Coverage Report",
        "=" * 80,
        "",
        f"Report Generated: {datetime.now(UTC).isoformat()}",
        f"Tempo Health: {health.get('status', 'unknown')}",
        "",
        "-" * 80,
        "Service Coverage Summary",
        "-" * 80,
        f"Total Services Expected: {coverage['summary']['total_services']}",
        f"Services with Traces: {coverage['summary']['services_with_traces']}",
        f"Coverage: {coverage['summary']['coverage_percentage']:.1f}%",
        f"Threshold: {COVERAGE_THRESHOLD * 100:.0f}%",
        f"Status: {'PASS' if coverage['summary']['passes_threshold'] else 'FAIL'}",
        "",
    ]

    # Service details
    lines.extend(["-" * 80, "Service Details", "-" * 80, ""])

    for service, details in coverage["services"].items():
        status = "✓" if details["has_traces"] else "✗"
        lines.append(f"{status} {service}")
        lines.append(f"  Traces: {details['trace_count']}")
        lines.append(f"  Spans: {details['span_count']}")
        lines.append(f"  Operations: {len(details['operations'])}")

        if details["attributes"]:
            attrs = details["attributes"]
            lines.append(
                f"  Required Attributes: {len(attrs['required_present'])}/{len(REQUIRED_ATTRIBUTES)}"
            )
            if attrs["required_missing"]:
                lines.append(f"    Missing: {', '.join(attrs['required_missing'])}")
            lines.append(
                f"  Recommended Attributes: {len(attrs['recommended_present'])}/{len(RECOMMENDED_ATTRIBUTES)}"
            )

        lines.append("")

    # Propagation summary
    lines.extend(
        [
            "-" * 80,
            "Trace Propagation",
            "-" * 80,
            f"Cross-Service Traces: {propagation['cross_service_traces']}",
            "",
        ]
    )

    if propagation["propagation_chains"]:
        lines.append("Sample Propagation Chains:")
        for chain in propagation["propagation_chains"]:
            lines.append(f"  Trace {chain['trace_id'][:16]}...")
            lines.append(f"    Services: {' → '.join(chain['services'])}")
            lines.append(f"    Spans: {chain['span_count']}")
            lines.append("")

    lines.extend(
        [
            "=" * 80,
            f"Overall Result: {'PASS' if coverage['summary']['passes_threshold'] else 'FAIL'}",
            "=" * 80,
        ]
    )

    return "\n".join(lines)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Verify distributed trace coverage in Tempo"
    )
    parser.add_argument(
        "--endpoint",
        default=DEFAULT_TEMPO_ENDPOINT,
        help=f"Tempo endpoint (default: {DEFAULT_TEMPO_ENDPOINT})",
    )
    parser.add_argument(
        "--hours",
        type=int,
        default=24,
        help="Hours to look back for traces (default: 24)",
    )
    parser.add_argument(
        "--service",
        help="Analyze specific service only",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )
    parser.add_argument(
        "--output",
        help="Write report to file",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=COVERAGE_THRESHOLD * 100,
        help=f"Coverage threshold percentage (default: {COVERAGE_THRESHOLD * 100:.0f})",
    )

    args = parser.parse_args()

    # Create Tempo client
    tempo = TempoClient(args.endpoint)

    # Health check
    health = tempo.health_check()
    if health["status"] != "ready":
        print(f"ERROR: Tempo not ready: {health}", file=sys.stderr)
        if not args.json:
            sys.exit(1)

    # Analyze coverage
    analyzer = CoverageAnalyzer(tempo)

    if args.service:
        # Single service analysis
        end = datetime.now(UTC)
        start = end - timedelta(hours=args.hours)
        coverage = {
            "services": {
                args.service: analyzer._analyze_service(args.service, start, end)
            }
        }
        propagation = {"cross_service_traces": 0, "propagation_chains": []}
    else:
        # Full analysis
        coverage = analyzer.analyze_service_coverage(args.hours)
        propagation = analyzer.analyze_trace_propagation(args.hours)

    # Generate results
    results = {
        "timestamp": datetime.now(UTC).isoformat(),
        "tempo_endpoint": args.endpoint,
        "tempo_health": health,
        "coverage": coverage,
        "propagation": propagation,
    }

    if args.json:
        output = json.dumps(results, indent=2, default=str)
    else:
        output = generate_report(coverage, propagation, health)

    # Output results
    if args.output:
        Path(args.output).write_text(output)
        print(f"Report written to: {args.output}")
    else:
        print(output)

    # Exit with appropriate code
    if not args.json and not args.service:
        if not coverage["summary"]["passes_threshold"]:
            sys.exit(1)

    return 0


if __name__ == "__main__":
    sys.exit(main())
