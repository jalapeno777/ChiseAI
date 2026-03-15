"""Tests for belief revision auditability pipeline.

Tests cover:
- Artifact serialization/deserialization
- 7-day query returns correct data
- Filter by belief_id works
- Filter by severity works
"""

from __future__ import annotations

import json
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from scripts.audit.query_belief_revisions import (
    DEFAULT_ARTIFACTS_DIR,
    DEFAULT_INDEX_PATH,
    RevisionQueryResult,
    filter_by_belief_id,
    filter_by_date_range,
    filter_by_severity,
    get_default_7_day_range,
    load_artifact,
    load_index,
    parse_iso_timestamp,
    query_revisions,
)


class TestArtifactSerialization:
    """Test artifact serialization and deserialization."""

    def test_artifact_schema_includes_required_fields(self, tmp_path: Path) -> None:
        """Artifact must include all required schema fields."""
        artifact = {
            "run_id": "test-run-001",
            "generated_at": datetime.now(UTC).isoformat(),
            "revision_count": 2,
            "revisions": [
                {
                    "revision_id": "rev-001",
                    "old_belief_id": "belief-old-001",
                    "new_belief_id": "belief-new-001",
                    "old_belief_statement": "Old statement",
                    "new_belief_statement": "New statement",
                    "old_belief_domain": "test",
                    "new_belief_domain": "test",
                    "confidence_before": 0.5,
                    "confidence_after": 0.8,
                    "confidence_delta": 0.3,
                    "reason": "Test reason",
                    "evidence_refs": ["ref1", "ref2"],
                    "applied_at": datetime.now(UTC).isoformat(),
                }
            ],
            "schema_version": "1.0",
            "artifact_type": "belief_revision_audit",
        }

        # Serialize
        artifact_path = tmp_path / "test_artifact.json"
        artifact_path.write_text(json.dumps(artifact, indent=2))

        # Deserialize
        loaded = load_artifact(str(artifact_path))

        assert loaded is not None
        assert loaded["run_id"] == "test-run-001"
        assert loaded["schema_version"] == "1.0"
        assert loaded["artifact_type"] == "belief_revision_audit"
        assert len(loaded["revisions"]) == 1

        # Check revision has all required fields
        rev = loaded["revisions"][0]
        assert "revision_id" in rev
        assert "old_belief_id" in rev
        assert "new_belief_id" in rev
        assert "old_belief_statement" in rev
        assert "new_belief_statement" in rev
        assert "confidence_before" in rev
        assert "confidence_after" in rev
        assert "confidence_delta" in rev
        assert "reason" in rev
        assert "evidence_refs" in rev
        assert "applied_at" in rev

    def test_artifact_handles_missing_file(self, tmp_path: Path) -> None:
        """Loading missing artifact returns None gracefully."""
        missing_path = tmp_path / "nonexistent.json"
        result = load_artifact(str(missing_path))
        assert result is None

    def test_artifact_handles_invalid_json(self, tmp_path: Path) -> None:
        """Loading invalid JSON returns None gracefully."""
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("not valid json")
        result = load_artifact(str(bad_file))
        assert result is None


class TestSevenDayQuery:
    """Test 7-day query functionality."""

    def test_default_7_day_range(self) -> None:
        """Default range should be exactly 7 days ending at now."""
        start, end = get_default_7_day_range()

        # Should be timezone-aware
        assert start.tzinfo is not None
        assert end.tzinfo is not None

        # Should be exactly 7 days apart
        delta = end - start
        assert delta.days == 7

        # End should be close to now
        now = datetime.now(UTC)
        assert abs((end - now).total_seconds()) < 5

    def test_filter_by_date_range_inclusive(self) -> None:
        """Date range filter should be inclusive."""
        now = datetime.now(UTC)

        entries = [
            {"generated_at": (now - timedelta(days=10)).isoformat(), "run_id": "old"},
            {"generated_at": (now - timedelta(days=5)).isoformat(), "run_id": "within"},
            {"generated_at": now.isoformat(), "run_id": "now"},
            {"generated_at": (now + timedelta(days=1)).isoformat(), "run_id": "future"},
        ]

        start = now - timedelta(days=7)
        end = now

        filtered = filter_by_date_range(entries, start, end)
        run_ids = {e["run_id"] for e in filtered}

        assert "within" in run_ids
        assert "now" in run_ids
        assert "old" not in run_ids
        assert "future" not in run_ids

    def test_query_revisions_7_day_default(self, tmp_path: Path) -> None:
        """Query with no dates should default to 7 days."""
        now = datetime.now(UTC)

        # Create test index
        index_data = {
            "schema_version": "1.0",
            "entries": [
                {
                    "run_id": "recent-run",
                    "generated_at": now.isoformat(),
                    "revision_count": 1,
                    "artifact_path": str(tmp_path / "recent.json"),
                    "belief_ids": ["belief-001"],
                    "severity_summary": {"low": 1},
                },
                {
                    "run_id": "old-run",
                    "generated_at": (now - timedelta(days=10)).isoformat(),
                    "revision_count": 1,
                    "artifact_path": str(tmp_path / "old.json"),
                    "belief_ids": ["belief-002"],
                    "severity_summary": {"low": 1},
                },
            ],
        }

        index_path = tmp_path / "index.json"
        index_path.write_text(json.dumps(index_data))

        # Create artifact files - use absolute paths to avoid fallback to default dir
        recent_artifact = tmp_path / "recent.json"
        old_artifact = tmp_path / "old.json"
        recent_artifact.write_text(
            json.dumps(
                {
                    "run_id": "recent-run",
                    "revisions": [{"revision_id": "rev-001"}],
                }
            )
        )
        old_artifact.write_text(
            json.dumps(
                {
                    "run_id": "old-run",
                    "revisions": [{"revision_id": "rev-002"}],
                }
            )
        )

        # Update index with absolute paths
        index_data["entries"][0]["artifact_path"] = str(recent_artifact)
        index_data["entries"][1]["artifact_path"] = str(old_artifact)
        index_path.write_text(json.dumps(index_data))

        # Query without dates (should default to 7 days)
        result = query_revisions(index_path=index_path)

        assert result.matching_entries == 1
        assert len(result.revisions) == 1
        assert result.revisions[0]["revision_id"] == "rev-001"


class TestFilterByBeliefId:
    """Test filtering by belief ID."""

    def test_filter_by_belief_id_exact_match(self) -> None:
        """Filter should match exact belief ID."""
        entries = [
            {"belief_ids": ["belief-001", "belief-002"], "run_id": "run-1"},
            {"belief_ids": ["belief-003"], "run_id": "run-2"},
            {"belief_ids": ["belief-001"], "run_id": "run-3"},
        ]

        filtered = filter_by_belief_id(entries, "belief-001")
        run_ids = {e["run_id"] for e in filtered}

        assert "run-1" in run_ids
        assert "run-3" in run_ids
        assert "run-2" not in run_ids

    def test_filter_by_belief_id_no_match(self) -> None:
        """Filter with non-existent ID returns empty list."""
        entries = [
            {"belief_ids": ["belief-001"], "run_id": "run-1"},
        ]

        filtered = filter_by_belief_id(entries, "belief-999")
        assert len(filtered) == 0

    def test_filter_by_belief_id_empty_belief_ids(self) -> None:
        """Filter handles entries with empty belief_ids."""
        entries = [
            {"belief_ids": [], "run_id": "run-1"},
            {"run_id": "run-2"},  # Missing belief_ids key
        ]

        filtered = filter_by_belief_id(entries, "belief-001")
        assert len(filtered) == 0

    def test_query_revisions_with_belief_id_filter(self, tmp_path: Path) -> None:
        """Full query with belief_id filter works correctly."""
        now = datetime.now(UTC)

        index_data = {
            "schema_version": "1.0",
            "entries": [
                {
                    "run_id": "run-1",
                    "generated_at": now.isoformat(),
                    "revision_count": 1,
                    "artifact_path": str(tmp_path / "run1.json"),
                    "belief_ids": ["belief-memory-health"],
                    "severity_summary": {"low": 1},
                },
                {
                    "run_id": "run-2",
                    "generated_at": now.isoformat(),
                    "revision_count": 1,
                    "artifact_path": str(tmp_path / "run2.json"),
                    "belief_ids": ["belief-other"],
                    "severity_summary": {"low": 1},
                },
            ],
        }

        index_path = tmp_path / "index.json"
        index_path.write_text(json.dumps(index_data))

        (tmp_path / "run1.json").write_text(
            json.dumps(
                {
                    "run_id": "run-1",
                    "revisions": [
                        {
                            "revision_id": "rev-001",
                            "old_belief_id": "belief-memory-health",
                        }
                    ],
                }
            )
        )
        (tmp_path / "run2.json").write_text(
            json.dumps(
                {
                    "run_id": "run-2",
                    "revisions": [
                        {"revision_id": "rev-002", "old_belief_id": "belief-other"}
                    ],
                }
            )
        )

        result = query_revisions(
            belief_id="belief-memory-health",
            index_path=index_path,
        )

        assert result.matching_entries == 1
        assert len(result.revisions) == 1
        assert result.revisions[0]["old_belief_id"] == "belief-memory-health"


class TestFilterBySeverity:
    """Test filtering by severity."""

    def test_filter_by_severity_high(self) -> None:
        """Filter should match entries with high severity revisions."""
        entries = [
            {"severity_summary": {"high": 2, "low": 1}, "run_id": "run-1"},
            {"severity_summary": {"medium": 1}, "run_id": "run-2"},
            {"severity_summary": {"high": 1}, "run_id": "run-3"},
        ]

        filtered = filter_by_severity(entries, "high")
        run_ids = {e["run_id"] for e in filtered}

        assert "run-1" in run_ids
        assert "run-3" in run_ids
        assert "run-2" not in run_ids

    def test_filter_by_severity_no_match(self) -> None:
        """Filter with non-matching severity returns empty list."""
        entries = [
            {"severity_summary": {"low": 1}, "run_id": "run-1"},
        ]

        filtered = filter_by_severity(entries, "high")
        assert len(filtered) == 0

    def test_filter_by_severity_missing_summary(self) -> None:
        """Filter handles entries with missing severity_summary."""
        entries = [
            {"run_id": "run-1"},  # Missing severity_summary
            {"severity_summary": {}, "run_id": "run-2"},  # Empty summary
        ]

        filtered = filter_by_severity(entries, "high")
        assert len(filtered) == 0

    def test_query_revisions_with_severity_filter(self, tmp_path: Path) -> None:
        """Full query with severity filter works correctly."""
        now = datetime.now(UTC)

        index_data = {
            "schema_version": "1.0",
            "entries": [
                {
                    "run_id": "run-high",
                    "generated_at": now.isoformat(),
                    "revision_count": 1,
                    "artifact_path": str(tmp_path / "high.json"),
                    "belief_ids": ["belief-001"],
                    "severity_summary": {"high": 1},
                },
                {
                    "run_id": "run-low",
                    "generated_at": now.isoformat(),
                    "revision_count": 1,
                    "artifact_path": str(tmp_path / "low.json"),
                    "belief_ids": ["belief-002"],
                    "severity_summary": {"low": 1},
                },
            ],
        }

        index_path = tmp_path / "index.json"
        index_path.write_text(json.dumps(index_data))

        (tmp_path / "high.json").write_text(
            json.dumps(
                {
                    "run_id": "run-high",
                    "revisions": [{"revision_id": "rev-high"}],
                }
            )
        )
        (tmp_path / "low.json").write_text(
            json.dumps(
                {
                    "run_id": "run-low",
                    "revisions": [{"revision_id": "rev-low"}],
                }
            )
        )

        result = query_revisions(
            severity="high",
            index_path=index_path,
        )

        assert result.matching_entries == 1
        assert len(result.revisions) == 1
        assert result.revisions[0]["revision_id"] == "rev-high"


class TestIndexLoading:
    """Test index loading functionality."""

    def test_load_existing_index(self, tmp_path: Path) -> None:
        """Loading existing index returns correct data."""
        index_data = {
            "schema_version": "1.0",
            "entries": [{"run_id": "test"}],
        }
        index_path = tmp_path / "index.json"
        index_path.write_text(json.dumps(index_data))

        loaded = load_index(index_path)
        assert loaded["schema_version"] == "1.0"
        assert len(loaded["entries"]) == 1

    def test_load_missing_index_returns_empty(self, tmp_path: Path) -> None:
        """Loading missing index returns empty structure."""
        index_path = tmp_path / "nonexistent.json"
        loaded = load_index(index_path)
        assert loaded["entries"] == []

    def test_load_invalid_index_returns_empty(self, tmp_path: Path) -> None:
        """Loading invalid JSON returns empty structure."""
        index_path = tmp_path / "bad.json"
        index_path.write_text("not json")
        loaded = load_index(index_path)
        assert loaded["entries"] == []


class TestTimestampParsing:
    """Test ISO timestamp parsing."""

    def test_parse_iso_timestamp_with_z(self) -> None:
        """Parsing timestamp with Z suffix works."""
        ts = "2026-03-14T12:00:00Z"
        dt = parse_iso_timestamp(ts)
        assert dt.year == 2026
        assert dt.month == 3
        assert dt.day == 14
        assert dt.hour == 12

    def test_parse_iso_timestamp_with_offset(self) -> None:
        """Parsing timestamp with timezone offset works."""
        ts = "2026-03-14T12:00:00+00:00"
        dt = parse_iso_timestamp(ts)
        assert dt.year == 2026
        assert dt.month == 3
        assert dt.day == 14


class TestRevisionQueryResult:
    """Test RevisionQueryResult dataclass."""

    def test_to_dict_includes_all_fields(self) -> None:
        """to_dict includes all result fields."""
        result = RevisionQueryResult(
            query_params={"start_date": "2026-01-01"},
            total_entries=10,
            matching_entries=5,
            revisions=[{"revision_id": "rev-001"}],
        )

        data = result.to_dict()
        assert data["query_params"] == {"start_date": "2026-01-01"}
        assert data["total_entries"] == 10
        assert data["matching_entries"] == 5
        assert len(data["revisions"]) == 1
        assert "generated_at" in data


class TestCombinedFilters:
    """Test combining multiple filters."""

    def test_combined_date_and_belief_id_filter(self, tmp_path: Path) -> None:
        """Combining date and belief_id filters works correctly."""
        now = datetime.now(UTC)

        index_data = {
            "schema_version": "1.0",
            "entries": [
                {
                    "run_id": "run-1",
                    "generated_at": now.isoformat(),
                    "artifact_path": str(tmp_path / "run1.json"),
                    "belief_ids": ["belief-target"],
                },
                {
                    "run_id": "run-2",
                    "generated_at": (now - timedelta(days=10)).isoformat(),
                    "artifact_path": str(tmp_path / "run2.json"),
                    "belief_ids": ["belief-target"],  # Right belief, wrong date
                },
                {
                    "run_id": "run-3",
                    "generated_at": now.isoformat(),
                    "artifact_path": str(tmp_path / "run3.json"),
                    "belief_ids": ["belief-other"],  # Right date, wrong belief
                },
            ],
        }

        index_path = tmp_path / "index.json"
        index_path.write_text(json.dumps(index_data))

        # Create artifacts with actual revisions
        for i in range(1, 4):
            (tmp_path / f"run{i}.json").write_text(
                json.dumps(
                    {
                        "run_id": f"run-{i}",
                        "revisions": [
                            {"revision_id": f"rev-{i}", "run_id": f"run-{i}"}
                        ],
                    }
                )
            )

        result = query_revisions(
            start_date=now - timedelta(days=7),
            end_date=now,
            belief_id="belief-target",
            index_path=index_path,
        )

        assert result.matching_entries == 1
        assert len(result.revisions) == 1
        assert result.revisions[0]["run_id"] == "run-1"

    def test_combined_all_filters(self, tmp_path: Path) -> None:
        """Combining all filter types works correctly."""
        now = datetime.now(UTC)

        index_data = {
            "schema_version": "1.0",
            "entries": [
                {
                    "run_id": "match",
                    "generated_at": now.isoformat(),
                    "artifact_path": str(tmp_path / "match.json"),
                    "belief_ids": ["belief-target"],
                    "severity_summary": {"high": 1},
                },
                {
                    "run_id": "wrong-severity",
                    "generated_at": now.isoformat(),
                    "artifact_path": str(tmp_path / "wrong-severity.json"),
                    "belief_ids": ["belief-target"],
                    "severity_summary": {"low": 1},
                },
            ],
        }

        index_path = tmp_path / "index.json"
        index_path.write_text(json.dumps(index_data))

        (tmp_path / "match.json").write_text(
            json.dumps(
                {
                    "run_id": "match",
                    "revisions": [{"revision_id": "rev-match"}],
                }
            )
        )
        (tmp_path / "wrong-severity.json").write_text(
            json.dumps(
                {
                    "run_id": "wrong-severity",
                    "revisions": [{"revision_id": "rev-wrong"}],
                }
            )
        )

        result = query_revisions(
            start_date=now - timedelta(days=7),
            end_date=now,
            belief_id="belief-target",
            severity="high",
            index_path=index_path,
        )

        assert result.matching_entries == 1
        assert result.revisions[0]["revision_id"] == "rev-match"
