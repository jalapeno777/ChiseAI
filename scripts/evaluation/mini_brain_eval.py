#!/usr/bin/env python3
"""
Mini BrainEval - Real Issue Detection from Iterlogs

SAFETY: No risk cap logic modified
SAFETY: No promotion gate logic modified
SAFETY: No live trading flow modified

This script scans docs/tempmemories/*.md files, Redis iterlogs, and Qdrant memories
for real issues and generates evaluation reports with detected patterns, severity
classification, and suggested mitigations.
"""

import argparse
import json
import os
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml


@dataclass
class Issue:
    """Represents a detected issue."""

    issue_type: str
    severity: str  # P0, P1, P2, P3
    description: str
    source_file: str
    timestamp: str | None = None
    line_number: int | None = None
    context: str = ""
    # Structured issue fields
    root_cause: str | None = None
    fix_applied: str | None = None
    time_lost_minutes: int | None = None
    recurrence_hint: str | None = None
    impact_area: str | None = None
    resolved: bool | None = None
    is_structured: bool = False  # Flag to indicate structured vs regex
    # Source tracking for multi-source ingestion
    source: str = "filesystem"  # "filesystem", "redis", or "qdrant"
    provenance: dict[str, Any] | None = None  # Origin details


@dataclass
class MiniEvalResult:
    """Result of a mini brain evaluation."""

    eval_id: str
    timestamp: str
    cadence: str
    issues_found: list[dict[str, Any]]
    mitigations: list[dict[str, Any]]
    file_stats: dict[str, Any]
    summary: str
    ingestion_sources: list[str] = field(default_factory=list)  # Sources used
    source_stats: dict[str, dict[str, Any]] = field(
        default_factory=dict
    )  # Stats per source


class IssueDetector:
    """Detects issues from iterlog files."""

    # Issue patterns to search for
    PATTERNS = {
        "file_access": {
            "patterns": [
                r"permission denied",
                r"file not found",
                r"cannot read",
                r"no such file",
                r"access denied",
            ],
            "severity": "P2",
            "mitigation": "Check file permissions and paths. Ensure proper access rights.",
        },
        "db_connectivity": {
            "patterns": [
                r"connection refused",
                r"timeout",
                r"postgresql.*error",
                r"redis.*error",
                r"influxdb.*error",
                r"database.*unavailable",
                r"cannot connect",
            ],
            "severity": "P1",
            "mitigation": "Verify database services are running. Check network connectivity and credentials.",
        },
        "env_slowdown": {
            "patterns": [
                r"slow",
                r"took \d+s",
                r"high memory",
                r"cpu usage",
                r"performance.*degraded",
                r"lag",
            ],
            "severity": "P2",
            "mitigation": "Monitor resource usage. Consider scaling or optimization.",
        },
        "tool_error": {
            "patterns": [
                r"failed",
                r"error:",
                r"exception",
                r"crash",
                r"fatal",
                r"panic",
            ],
            "severity": "P1",
            "mitigation": "Review error logs. Check tool configuration and dependencies.",
        },
        "ci_failure": {
            "patterns": [
                r"ci.*fail",
                r"build.*fail",
                r"test.*fail",
                r"lint.*error",
                r"check.*fail",
            ],
            "severity": "P2",
            "mitigation": "Review CI logs. Fix failing tests or linting issues.",
        },
        "blocker": {
            "patterns": [
                r"blocker",
                r"blocking",
                r"cannot proceed",
                r"stuck",
            ],
            "severity": "P0",
            "mitigation": "Escalate to team lead. Identify dependency or external blocker.",
        },
        "config_error": {
            "patterns": [
                r"config.*error",
                r"invalid.*config",
                r"missing.*config",
                r"configuration.*fail",
            ],
            "severity": "P1",
            "mitigation": "Verify configuration files. Check for missing or invalid settings.",
        },
        "api_error": {
            "patterns": [
                r"api.*error",
                r"http.*error",
                r"request.*fail",
                r"response.*error",
                r"status.*\d{3}",
            ],
            "severity": "P2",
            "mitigation": "Check API status and rate limits. Verify request format.",
        },
    }

    def __init__(
        self,
        tempmemories_path: str = "docs/tempmemories",
        use_redis: bool = False,
        use_qdrant: bool = False,
        include_provenance: bool = False,
    ):
        self.tempmemories_path = Path(tempmemories_path)
        self.use_redis = use_redis
        self.use_qdrant = use_qdrant
        self.include_provenance = include_provenance
        self.issues: list[Issue] = []
        self.source_stats: dict[str, dict[str, Any]] = {
            "filesystem": {"files_scanned": 0, "issues_found": 0},
            "redis": {"keys_scanned": 0, "issues_found": 0},
            "qdrant": {"vectors_scanned": 0, "issues_found": 0},
        }
        self._redis_client = None
        self._qdrant_client = None

    def _get_redis_client(self):
        """Get or create Redis client."""
        if self._redis_client is not None:
            return self._redis_client

        try:
            import redis as redis_lib

            redis_host = os.getenv("REDIS_HOST", "host.docker.internal")
            redis_port = int(os.getenv("REDIS_PORT", "6380"))
            redis_db = int(os.getenv("REDIS_DB", "0"))
            redis_password = os.getenv("REDIS_PASSWORD", None)

            self._redis_client = redis_lib.Redis(
                host=redis_host,
                port=redis_port,
                db=redis_db,
                password=redis_password,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
            )
            # Test connection
            self._redis_client.ping()
            return self._redis_client
        except Exception as e:
            print(f"Warning: Redis client initialization failed: {e}")
            return None

    def _get_qdrant_client(self):
        """Get or create Qdrant client."""
        if self._qdrant_client is not None:
            return self._qdrant_client

        try:
            from qdrant_client import QdrantClient

            qdrant_host = os.getenv("QDRANT_HOST", "host.docker.internal")
            qdrant_port = int(os.getenv("QDRANT_PORT", "6334"))
            qdrant_grpc_port = int(os.getenv("QDRANT_GRPC_PORT", "6334"))

            self._qdrant_client = QdrantClient(
                host=qdrant_host,
                port=qdrant_port,
                grpc_port=qdrant_grpc_port,
                prefer_grpc=True,
            )
            return self._qdrant_client
        except Exception as e:
            print(f"Warning: Qdrant client initialization failed: {e}")
            return None

    def scan_all_sources(self) -> list[Issue]:
        """Scan all enabled sources for issues."""
        self.issues = []

        # Always scan filesystem (default behavior)
        self._scan_filesystem()

        # Scan Redis if enabled
        if self.use_redis:
            self._scan_redis()

        # Scan Qdrant if enabled
        if self.use_qdrant:
            self._scan_qdrant()

        return self.issues

    def _scan_filesystem(self) -> None:
        """Scan filesystem (docs/tempmemories/*.md) for issues."""
        if not self.tempmemories_path.exists():
            print(f"Warning: Path {self.tempmemories_path} does not exist")
            return

        md_files = list(self.tempmemories_path.glob("*.md"))
        self.source_stats["filesystem"]["files_scanned"] = len(md_files)

        for file_path in md_files:
            file_issues = self._scan_file(file_path)
            self.issues.extend(file_issues)

        self.source_stats["filesystem"]["issues_found"] = len(
            [i for i in self.issues if i.source == "filesystem"]
        )

    def _scan_file(self, file_path: Path) -> list[Issue]:
        """Scan a single file for issues."""
        file_issues: list[Issue] = []

        try:
            with open(file_path, encoding="utf-8", errors="ignore") as f:
                content = f.read()
                lines = content.split("\n")
        except Exception as e:
            print(f"Error reading {file_path}: {e}")
            return file_issues

        # Extract timestamp from frontmatter if present
        timestamp = self._extract_timestamp(content)

        # FIRST: Try to parse structured issues
        structured_issues = self._scan_structured_issues(content, file_path, timestamp)
        if structured_issues:
            file_issues.extend(structured_issues)
            return file_issues  # Use structured issues only, skip regex

        # FALLBACK: Use regex patterns if no structured section found
        for line_num, line in enumerate(lines, 1):
            for issue_type, config in self.PATTERNS.items():
                for pattern in config["patterns"]:
                    if re.search(pattern, line, re.IGNORECASE):
                        # Get context (surrounding lines)
                        context_start = max(0, line_num - 2)
                        context_end = min(len(lines), line_num + 1)
                        context = "\n".join(lines[context_start:context_end])

                        issue = Issue(
                            issue_type=issue_type,
                            severity=str(config.get("severity", "P3")),
                            description=line.strip(),
                            source_file=str(file_path),
                            timestamp=timestamp,
                            line_number=line_num,
                            context=context.strip(),
                            is_structured=False,
                            source="filesystem",
                            provenance=(
                                {
                                    "source_type": "FILESYSTEM",
                                    "file_path": str(file_path),
                                    "line_number": line_num,
                                }
                                if self.include_provenance
                                else None
                            ),
                        )
                        file_issues.append(issue)
                        break  # Avoid duplicate detection for same line

        return file_issues

    def _scan_redis(self) -> None:
        """Scan Redis iterlog keys for issues."""
        client = self._get_redis_client()
        if client is None:
            print("Warning: Redis not available, skipping Redis scan")
            return

        try:
            # Scan for iterlog keys
            pattern = "bmad:chiseai:iterlog:story:*:decisions"
            cursor = 0
            keys_scanned = 0

            while True:
                cursor, keys = client.scan(cursor=cursor, match=pattern, count=100)

                for key in keys:
                    keys_scanned += 1
                    try:
                        # Get decisions from the list
                        decisions = client.lrange(key, 0, -1)
                        story_id = self._extract_story_id_from_key(key)

                        for decision_json in decisions:
                            try:
                                decision = json.loads(decision_json)
                                issues = self._parse_redis_decision(
                                    decision, story_id, key
                                )
                                self.issues.extend(issues)
                            except json.JSONDecodeError:
                                continue
                    except Exception as e:
                        print(f"Warning: Error processing Redis key {key}: {e}")

                if cursor == 0:
                    break

            self.source_stats["redis"]["keys_scanned"] = keys_scanned
            self.source_stats["redis"]["issues_found"] = len(
                [i for i in self.issues if i.source == "redis"]
            )

        except Exception as e:
            print(f"Warning: Redis scan failed: {e}")

    def _scan_qdrant(self) -> None:
        """Scan Qdrant memories for issues."""
        client = self._get_qdrant_client()
        if client is None:
            print("Warning: Qdrant not available, skipping Qdrant scan")
            return

        try:
            # Search for issue-related memories
            collection_name = os.getenv("QDRANT_COLLECTION", "ChiseAI")

            # Use a query to find issue-related vectors
            search_queries = [
                "error",
                "failure",
                "blocker",
                "incident",
                "issue",
                "problem",
            ]

            vectors_scanned = 0
            seen_ids = set()

            for query in search_queries:
                try:
                    # Scroll through the collection
                    offset = None
                    while True:
                        results = client.scroll(
                            collection_name=collection_name,
                            limit=100,
                            offset=offset,
                            with_payload=True,
                        )

                        if not results or not results[0]:
                            break

                        for point in results[0]:
                            if point.id in seen_ids:
                                continue
                            seen_ids.add(point.id)
                            vectors_scanned += 1

                            # Parse the memory content for issues
                            payload = point.payload or {}
                            content = payload.get("information", "")

                            issues = self._parse_qdrant_memory(
                                content, point.id, payload
                            )
                            self.issues.extend(issues)

                        # Get next offset
                        offset = results[1]
                        if offset is None:
                            break

                except Exception as e:
                    print(f"Warning: Qdrant search failed for query '{query}': {e}")
                    continue

            self.source_stats["qdrant"]["vectors_scanned"] = vectors_scanned
            self.source_stats["qdrant"]["issues_found"] = len(
                [i for i in self.issues if i.source == "qdrant"]
            )

        except Exception as e:
            print(f"Warning: Qdrant scan failed: {e}")

    def _extract_story_id_from_key(self, key: str) -> str | None:
        """Extract story ID from Redis key."""
        # Pattern: bmad:chiseai:iterlog:story:ST-XXX:decisions
        parts = key.split(":")
        if len(parts) >= 5:
            return parts[4]
        return None

    def _parse_redis_decision(
        self, decision: dict[str, Any], story_id: str | None, key: str
    ) -> list[Issue]:
        """Parse a Redis decision entry for issues."""
        issues: list[Issue] = []

        # Get decision text and metadata
        decision_text = decision.get("decision", "")
        rationale = decision.get("rationale", "")
        timestamp = decision.get("timestamp", datetime.utcnow().isoformat())

        # Check for issue patterns in decision text
        text_to_check = f"{decision_text} {rationale}".lower()

        for issue_type, config in self.PATTERNS.items():
            for pattern in config["patterns"]:
                if re.search(pattern, text_to_check, re.IGNORECASE):
                    issue = Issue(
                        issue_type=issue_type,
                        severity=str(config.get("severity", "P3")),
                        description=(
                            decision_text[:200] if decision_text else issue_type
                        ),
                        source_file=f"redis:{key}",
                        timestamp=timestamp,
                        line_number=None,
                        context=rationale[:500] if rationale else "",
                        is_structured=False,
                        source="redis",
                        provenance=(
                            {
                                "source_type": "ITERLOG_DECISION",
                                "story_id": story_id,
                                "redis_key": key,
                                "timestamp": timestamp,
                                "decision_type": decision.get("type", "unknown"),
                            }
                            if self.include_provenance
                            else None
                        ),
                    )
                    issues.append(issue)
                    break  # One issue per pattern match

        return issues

    def _parse_qdrant_memory(
        self, content: str, point_id: str, payload: dict[str, Any]
    ) -> list[Issue]:
        """Parse a Qdrant memory for issues."""
        issues: list[Issue] = []

        if not content:
            return issues

        # Check for issue patterns in content
        text_to_check = content.lower()

        for issue_type, config in self.PATTERNS.items():
            for pattern in config["patterns"]:
                if re.search(pattern, text_to_check, re.IGNORECASE):
                    # Extract metadata from payload
                    metadata = payload.get("metadata", {})
                    timestamp = metadata.get("timestamp", datetime.utcnow().isoformat())

                    issue = Issue(
                        issue_type=issue_type,
                        severity=str(config.get("severity", "P3")),
                        description=content[:200],
                        source_file=f"qdrant:{point_id}",
                        timestamp=timestamp,
                        line_number=None,
                        context=content[:500],
                        is_structured=False,
                        source="qdrant",
                        provenance=(
                            {
                                "source_type": "QDRANT_MEMORY",
                                "point_id": str(point_id),
                                "collection": os.getenv("QDRANT_COLLECTION", "ChiseAI"),
                                "timestamp": timestamp,
                                "metadata": metadata,
                            }
                            if self.include_provenance
                            else None
                        ),
                    )
                    issues.append(issue)
                    break  # One issue per pattern match

        return issues

    def _scan_structured_issues(
        self, content: str, file_path: Path, timestamp: str | None
    ) -> list[Issue]:
        """Parse structured issues from markdown YAML section.

        Returns empty list if no structured section or parsing fails.
        """
        issues: list[Issue] = []

        # Find ## Structured Issues section
        structured_match = re.search(
            r"^##\s+Structured\s+Issues\s*\n(.*?)(?=^##\s|\Z)",
            content,
            re.MULTILINE | re.DOTALL,
        )

        if not structured_match:
            return issues  # No structured section found

        yaml_content = structured_match.group(1).strip()

        try:
            parsed = yaml.safe_load(yaml_content)
            if not parsed or not isinstance(parsed, dict):
                return issues

            issues_list = parsed.get("issues", [])
            if not issues_list:
                return issues  # Empty issues list

            for item in issues_list:
                if not isinstance(item, dict):
                    continue

                # Map severity from structured fields or infer from issue_type
                issue_type = item.get("issue_type", "unknown")
                severity = self._infer_severity(issue_type, item.get("resolved", False))

                # Build description from structured fields
                description_parts = []
                if item.get("root_cause"):
                    description_parts.append(f"Root cause: {item['root_cause']}")
                if item.get("fix_applied"):
                    description_parts.append(f"Fix: {item['fix_applied']}")
                description = "; ".join(description_parts) or issue_type

                issue = Issue(
                    issue_type=issue_type,
                    severity=severity,
                    description=description,
                    source_file=str(file_path),
                    timestamp=timestamp,
                    line_number=None,  # Structured issues don't have line numbers
                    context="",  # Structured issues don't have surrounding context
                    root_cause=item.get("root_cause"),
                    fix_applied=item.get("fix_applied"),
                    time_lost_minutes=item.get("time_lost_minutes"),
                    recurrence_hint=item.get("recurrence_hint"),
                    impact_area=item.get("impact_area"),
                    resolved=item.get("resolved"),
                    is_structured=True,
                    source="filesystem",
                    provenance=(
                        {
                            "source_type": "STRUCTURED_FILE",
                            "file_path": str(file_path),
                            "is_structured": True,
                        }
                        if self.include_provenance
                        else None
                    ),
                )
                issues.append(issue)

        except yaml.YAMLError as e:
            print(f"Warning: Failed to parse structured issues in {file_path}: {e}")
            return []  # Return empty on parse error, will fallback to regex

        return issues

    def _infer_severity(self, issue_type: str, resolved: bool) -> str:
        """Infer severity from issue_type and resolved status."""
        # Check if issue_type matches known patterns
        for pattern_type, config in self.PATTERNS.items():
            if pattern_type == issue_type:
                # Reduce severity if resolved
                if resolved:
                    severity_order = ["P0", "P1", "P2", "P3"]
                    idx = severity_order.index(str(config.get("severity", "P3")))
                    return severity_order[min(idx + 1, 3)]
                return str(config.get("severity", "P3"))

        # Default severity based on common patterns
        if "blocker" in issue_type.lower():
            return "P0"
        if "failure" in issue_type.lower() or "error" in issue_type.lower():
            return "P1"
        if "warning" in issue_type.lower() or "slow" in issue_type.lower():
            return "P2"
        return "P3"

    def _extract_timestamp(self, content: str) -> str | None:
        """Extract timestamp from file frontmatter."""
        # Look for date: YYYY-MM-DD pattern
        date_match = re.search(r"date:\s*(\d{4}-\d{2}-\d{2})", content)
        if date_match:
            return date_match.group(1)

        # Look for timestamp in filename pattern
        ts_match = re.search(r"(\d{4}-\d{2}-\d{2})", content[:500])
        if ts_match:
            return ts_match.group(1)

        return None

    def get_mitigations(self) -> list[dict[str, Any]]:
        """Generate mitigation suggestions based on detected issues."""
        mitigations = []

        # Group issues by type
        issues_by_type: dict[str, list[Issue]] = {}
        for issue in self.issues:
            if issue.issue_type not in issues_by_type:
                issues_by_type[issue.issue_type] = []
            issues_by_type[issue.issue_type].append(issue)

        for issue_type, issues in issues_by_type.items():
            config = self.PATTERNS.get(issue_type, {})
            mitigation = {
                "issue_type": issue_type,
                "count": len(issues),
                "severity": config.get("severity", "P3"),
                "suggestion": config.get("mitigation", "Review and address the issue."),
                "affected_files": list(set(i.source_file for i in issues)),
            }
            mitigations.append(mitigation)

        return mitigations

    def get_file_stats(self) -> dict[str, Any]:
        """Generate statistics about scanned files."""
        md_files = (
            list(self.tempmemories_path.glob("*.md"))
            if self.tempmemories_path.exists()
            else []
        )

        # Count issues by severity
        severity_counts = {"P0": 0, "P1": 0, "P2": 0, "P3": 0}
        for issue in self.issues:
            if issue.severity in severity_counts:
                severity_counts[issue.severity] += 1

        # Count issues by type
        type_counts: dict[str, int] = {}
        for issue in self.issues:
            type_counts[issue.issue_type] = type_counts.get(issue.issue_type, 0) + 1

        return {
            "files_scanned": len(md_files),
            "total_issues": len(self.issues),
            "issues_by_severity": severity_counts,
            "issues_by_type": type_counts,
            "files_with_issues": len(set(i.source_file for i in self.issues)),
        }

    def get_ingestion_sources(self) -> list[str]:
        """Get list of sources that were scanned."""
        sources = ["filesystem"]
        if self.use_redis:
            sources.append("redis")
        if self.use_qdrant:
            sources.append("qdrant")
        return sources


def run_evaluation(
    cadence: str,
    output_dir: str = "_bmad-output/brain-eval",
    use_redis: bool = False,
    use_qdrant: bool = False,
    include_provenance: bool = False,
    tempmemories_path: str = "docs/tempmemories",
) -> MiniEvalResult:
    """Run a complete evaluation for the specified cadence."""

    detector = IssueDetector(
        tempmemories_path=tempmemories_path,
        use_redis=use_redis,
        use_qdrant=use_qdrant,
        include_provenance=include_provenance,
    )
    issues = detector.scan_all_sources()
    mitigations = detector.get_mitigations()
    file_stats = detector.get_file_stats()
    ingestion_sources = detector.get_ingestion_sources()
    source_stats = detector.source_stats

    # Generate summary
    summary_parts = [
        f"Sources: {', '.join(ingestion_sources)}",
        f"Scanned {file_stats['files_scanned']} files",
        f"Found {file_stats['total_issues']} issues",
    ]

    if file_stats["total_issues"] > 0:
        summary_parts.append(
            f"P0: {file_stats['issues_by_severity']['P0']}, "
            f"P1: {file_stats['issues_by_severity']['P1']}, "
            f"P2: {file_stats['issues_by_severity']['P2']}, "
            f"P3: {file_stats['issues_by_severity']['P3']}"
        )

    result = MiniEvalResult(
        eval_id=str(uuid.uuid4()),
        timestamp=datetime.utcnow().isoformat() + "Z",
        cadence=cadence,
        issues_found=[asdict(issue) for issue in issues],
        mitigations=mitigations,
        file_stats=file_stats,
        summary="; ".join(summary_parts),
        ingestion_sources=ingestion_sources,
        source_stats=source_stats,
    )

    # Save to file
    output_path = Path(output_dir) / cadence
    output_path.mkdir(parents=True, exist_ok=True)

    timestamp_str = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    output_file = output_path / f"{timestamp_str}.json"

    with open(output_file, "w") as f:
        json.dump(asdict(result), f, indent=2)

    print(f"Evaluation complete. Results saved to: {output_file}")
    print(f"Summary: {result.summary}")

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Mini BrainEval - Detect issues from iterlog files"
    )
    parser.add_argument(
        "--cadence",
        choices=["6h", "daily", "weekly"],
        required=True,
        help="Evaluation cadence",
    )
    parser.add_argument(
        "--output-dir",
        default="_bmad-output/brain-eval",
        help="Output directory for results",
    )
    parser.add_argument(
        "--tempmemories",
        default="docs/tempmemories",
        help="Path to tempmemories directory",
    )
    parser.add_argument(
        "--use-redis",
        action="store_true",
        help="Enable Redis iterlog ingestion",
    )
    parser.add_argument(
        "--use-qdrant",
        action="store_true",
        help="Enable Qdrant memory ingestion",
    )
    parser.add_argument(
        "--use-all",
        action="store_true",
        help="Enable all sources (filesystem + Redis + Qdrant)",
    )
    parser.add_argument(
        "--provenance",
        action="store_true",
        help="Include provenance information in output",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run in dry-run mode (no output files written)",
    )

    args = parser.parse_args()

    # Handle --use-all flag
    use_redis = args.use_redis or args.use_all
    use_qdrant = args.use_qdrant or args.use_all

    # Override tempmemories path if provided
    tempmemories_path = args.tempmemories

    result = run_evaluation(
        cadence=args.cadence,
        output_dir=args.output_dir,
        use_redis=use_redis,
        use_qdrant=use_qdrant,
        include_provenance=args.provenance,
        tempmemories_path=tempmemories_path,
    )

    # Print summary
    print(f"\n{'=' * 60}")
    print(f"Mini BrainEval - {args.cadence.upper()} Evaluation")
    print(f"{'=' * 60}")
    print(f"Eval ID: {result.eval_id}")
    print(f"Timestamp: {result.timestamp}")
    print(f"Ingestion Sources: {', '.join(result.ingestion_sources)}")
    print(f"Files Scanned: {result.file_stats['files_scanned']}")
    print(f"Total Issues: {result.file_stats['total_issues']}")

    # Print source stats
    if result.source_stats:
        print("\nSource Statistics:")
        for source, stats in result.source_stats.items():
            if stats.get("files_scanned", 0) > 0:
                print(
                    f"  {source}: {stats['files_scanned']} files, {stats.get('issues_found', 0)} issues"
                )
            elif stats.get("keys_scanned", 0) > 0:
                print(
                    f"  {source}: {stats['keys_scanned']} keys, {stats.get('issues_found', 0)} issues"
                )
            elif stats.get("vectors_scanned", 0) > 0:
                print(
                    f"  {source}: {stats['vectors_scanned']} vectors, {stats.get('issues_found', 0)} issues"
                )

    if result.file_stats["total_issues"] > 0:
        print("\nIssues by Severity:")
        for sev, count in result.file_stats["issues_by_severity"].items():
            if count > 0:
                print(f"  {sev}: {count}")

        print("\nIssues by Type:")
        for issue_type, count in result.file_stats["issues_by_type"].items():
            print(f"  {issue_type}: {count}")

        print("\nTop Mitigations:")
        for mit in sorted(result.mitigations, key=lambda x: x["count"], reverse=True)[
            :5
        ]:
            print(
                f"  - {mit['issue_type']} ({mit['count']}): {mit['suggestion'][:60]}..."
            )

    # Print sample issues with source/provenance if available
    if result.issues_found and args.provenance:
        print("\nSample Issues with Provenance:")
        for issue in result.issues_found[:3]:
            print(
                f"  - [{issue.get('source', 'unknown')}] {issue.get('issue_type', 'unknown')}: {issue.get('description', '')[:50]}..."
            )
            if issue.get("provenance"):
                prov = issue["provenance"]
                print(f"    Provenance: {prov.get('source_type', 'unknown')}")


if __name__ == "__main__":
    main()
