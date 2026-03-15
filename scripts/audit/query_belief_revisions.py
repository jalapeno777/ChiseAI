"""Query utility for belief revision artifacts with 7-day audit support.

This module provides functions to query belief revision artifacts by date range,
belief ID, and severity. It supports the 7-day audit pattern required for
traceability and rollback analysis.

Usage:
    # Query last 7 days
    python scripts/audit/query_belief_revisions.py

    # Query specific date range
    python scripts/audit/query_belief_revisions.py --start-date 2026-03-01 --end-date 2026-03-14

    # Filter by belief ID
    python scripts/audit/query_belief_revisions.py --belief-id belief-memory-health

    # Filter by severity
    python scripts/audit/query_belief_revisions.py --severity high
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

DEFAULT_INDEX_PATH = Path("_bmad-output/autocog/belief_revisions/index.json")
DEFAULT_ARTIFACTS_DIR = Path("_bmad-output/autocog/belief_revisions")


@dataclass
class RevisionQueryResult:
    """Result of a belief revision query."""

    query_params: dict[str, Any]
    total_entries: int
    matching_entries: int
    revisions: list[dict[str, Any]] = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        """Convert result to dictionary."""
        return {
            "query_params": self.query_params,
            "total_entries": self.total_entries,
            "matching_entries": self.matching_entries,
            "revisions": self.revisions,
            "generated_at": self.generated_at,
        }


def load_index(index_path: Path | None = None) -> dict[str, Any]:
    """Load the belief revision index.

    Args:
        index_path: Path to index file. Uses default if not provided.

    Returns:
        Index data dictionary with entries list.
    """
    path = index_path or DEFAULT_INDEX_PATH
    if not path.exists():
        return {"schema_version": "1.0", "entries": []}

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"Warning: Could not load index from {path}: {e}", file=sys.stderr)
        return {"schema_version": "1.0", "entries": []}


def parse_iso_timestamp(ts: str) -> datetime:
    """Parse ISO format timestamp string to datetime."""
    # Handle both with and without timezone
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    return datetime.fromisoformat(ts)


def filter_by_date_range(
    entries: list[dict[str, Any]],
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> list[dict[str, Any]]:
    """Filter index entries by date range.

    Args:
        entries: List of index entries.
        start_date: Inclusive start date. If None, no lower bound.
        end_date: Inclusive end date. If None, no upper bound.

    Returns:
        Filtered list of entries.
    """
    filtered = []
    for entry in entries:
        try:
            entry_date = parse_iso_timestamp(entry["generated_at"])
            # Ensure timezone-aware comparison
            if entry_date.tzinfo is None:
                entry_date = entry_date.replace(tzinfo=UTC)

            if start_date and entry_date < start_date:
                continue
            if end_date and entry_date > end_date:
                continue
            filtered.append(entry)
        except (KeyError, ValueError) as e:
            print(f"Warning: Skipping entry with invalid date: {e}", file=sys.stderr)
            continue
    return filtered


def filter_by_belief_id(
    entries: list[dict[str, Any]],
    belief_id: str,
) -> list[dict[str, Any]]:
    """Filter index entries by belief ID.

    Args:
        entries: List of index entries.
        belief_id: Belief ID to filter by.

    Returns:
        Filtered list of entries containing the belief ID.
    """
    return [entry for entry in entries if belief_id in entry.get("belief_ids", [])]


def filter_by_severity(
    entries: list[dict[str, Any]],
    severity: str,
) -> list[dict[str, Any]]:
    """Filter index entries by severity level.

    Args:
        entries: List of index entries.
        severity: Severity level (high, medium, low).

    Returns:
        Filtered list of entries with matching severity.
    """
    return [
        entry
        for entry in entries
        if entry.get("severity_summary", {}).get(severity, 0) > 0
    ]


def load_artifact(artifact_path: str) -> dict[str, Any] | None:
    """Load a belief revision artifact.

    Args:
        artifact_path: Path to artifact file.

    Returns:
        Artifact data or None if loading fails.
    """
    path = Path(artifact_path)
    if not path.exists():
        # Try relative to artifacts dir
        path = DEFAULT_ARTIFACTS_DIR / path.name

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"Warning: Could not load artifact {artifact_path}: {e}", file=sys.stderr)
        return None


def query_revisions(
    *,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    belief_id: str | None = None,
    severity: str | None = None,
    include_details: bool = True,
    index_path: Path | None = None,
) -> RevisionQueryResult:
    """Query belief revisions with filters.

    Args:
        start_date: Inclusive start date for range filter. Defaults to 7 days ago.
        end_date: Inclusive end date for range filter. Defaults to now.
        belief_id: Filter by specific belief ID.
        severity: Filter by severity level (high, medium, low).
        include_details: Whether to include full revision details from artifacts.
        index_path: Custom path to index file.

    Returns:
        RevisionQueryResult with matching revisions.
    """
    # Default to 7-day range if no dates specified
    if start_date is None and end_date is None:
        start_date, end_date = get_default_7_day_range()

    # Load index
    index_data = load_index(index_path)
    all_entries = index_data.get("entries", [])
    total_entries = len(all_entries)

    # Apply filters
    filtered_entries = all_entries

    if start_date or end_date:
        filtered_entries = filter_by_date_range(filtered_entries, start_date, end_date)

    if belief_id:
        filtered_entries = filter_by_belief_id(filtered_entries, belief_id)

    if severity:
        filtered_entries = filter_by_severity(filtered_entries, severity)

    # Build query params record
    query_params: dict[str, Any] = {}
    if start_date:
        query_params["start_date"] = start_date.isoformat()
    if end_date:
        query_params["end_date"] = end_date.isoformat()
    if belief_id:
        query_params["belief_id"] = belief_id
    if severity:
        query_params["severity"] = severity

    # Load full details if requested
    revisions: list[dict[str, Any]] = []
    if include_details:
        for entry in filtered_entries:
            artifact = load_artifact(entry["artifact_path"])
            if artifact:
                # Add index metadata to each revision
                for rev in artifact.get("revisions", []):
                    rev_with_meta = dict(rev)
                    rev_with_meta["run_id"] = artifact.get("run_id")
                    rev_with_meta["artifact_generated_at"] = artifact.get(
                        "generated_at"
                    )
                    revisions.append(rev_with_meta)
    else:
        # Return index entries only
        revisions = filtered_entries

    return RevisionQueryResult(
        query_params=query_params,
        total_entries=total_entries,
        matching_entries=len(filtered_entries),
        revisions=revisions,
    )


def get_default_7_day_range() -> tuple[datetime, datetime]:
    """Get default 7-day date range ending at now.

    Returns:
        Tuple of (start_date, end_date).
    """
    end_date = datetime.now(UTC)
    start_date = end_date - timedelta(days=7)
    return start_date, end_date


def main() -> int:
    """Main entry point for CLI usage."""
    parser = argparse.ArgumentParser(
        description="Query belief revision artifacts for audit and analysis.",
    )
    parser.add_argument(
        "--start-date",
        type=str,
        help="Start date (ISO format, e.g., 2026-03-01). Defaults to 7 days ago.",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        help="End date (ISO format, e.g., 2026-03-14). Defaults to now.",
    )
    parser.add_argument(
        "--belief-id",
        type=str,
        help="Filter by specific belief ID.",
    )
    parser.add_argument(
        "--severity",
        type=str,
        choices=["high", "medium", "low"],
        help="Filter by severity level.",
    )
    parser.add_argument(
        "--index-only",
        action="store_true",
        help="Return index entries only (faster, no full artifact loading).",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Output file path. Defaults to stdout.",
    )
    parser.add_argument(
        "--format",
        type=str,
        choices=["json", "summary"],
        default="json",
        help="Output format.",
    )

    args = parser.parse_args()

    # Parse dates
    if args.start_date:
        start_date = datetime.fromisoformat(args.start_date.replace("Z", "+00:00"))
        if start_date.tzinfo is None:
            start_date = start_date.replace(tzinfo=UTC)
    else:
        start_date = None

    if args.end_date:
        end_date = datetime.fromisoformat(args.end_date.replace("Z", "+00:00"))
        if end_date.tzinfo is None:
            end_date = end_date.replace(tzinfo=UTC)
    else:
        end_date = None

    # Default to 7 days if no dates specified
    if start_date is None and end_date is None:
        start_date, end_date = get_default_7_day_range()

    # Execute query
    result = query_revisions(
        start_date=start_date,
        end_date=end_date,
        belief_id=args.belief_id,
        severity=args.severity,
        include_details=not args.index_only,
    )

    # Output results
    if args.format == "json":
        output = json.dumps(result.to_dict(), indent=2)
    else:
        # Summary format
        lines = [
            "Belief Revision Query Results",
            "============================",
            "",
            "Query Parameters:",
        ]
        for key, value in result.query_params.items():
            lines.append(f"  {key}: {value}")
        lines.extend(
            [
                "",
                f"Total Index Entries: {result.total_entries}",
                f"Matching Entries: {result.matching_entries}",
                f"Revisions Found: {len(result.revisions)}",
                "",
                f"Generated At: {result.generated_at}",
            ]
        )
        output = "\n".join(lines)

    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"Results written to {args.output}")
    else:
        print(output)

    return 0


if __name__ == "__main__":
    sys.exit(main())
