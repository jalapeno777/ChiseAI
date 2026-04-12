"""Tests for scripts.autocog.monthly_audit module.

Tests the monthly audit script including Redis scanning, lessons normalization,
Qdrant promotion, and deferred item collection.
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Import the module under test
from scripts.autocog.monthly_audit import (
    MonthlyAuditResult,
    NormalizedLesson,
    collect_deferred_items,
    collect_metacog_dimensions,
    fingerprint_lesson,
    normalize_and_dedup_lessons,
    parse_lessons_file,
    promote_to_qdrant,
    run_monthly_audit,
    scan_redis_keys,
    write_audit_result,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_repo_root(tmp_path: Path) -> Path:
    """Create a minimal repo-like directory structure."""
    (tmp_path / "pyproject.toml").write_text("[tool.pytest]\n")
    (tmp_path / "docs" / "tempmemories").mkdir(parents=True)
    (tmp_path / "_bmad-output" / "autocog" / "cycles").mkdir(parents=True)
    return tmp_path


@pytest.fixture
def sample_lessons_file(tmp_repo_root: Path) -> Path:
    """Create a sample lessons.md with multiple LESSON blocks."""
    lessons_path = tmp_repo_root / "docs" / "tempmemories" / "lessons.md"
    lessons_path.write_text(
        """---
type: summary
story_id: LESSONS-001
created: 2026-03-17T00:00:00Z
tags:
  - lessons
---

# Swarm Lessons

## Lessons

```text
LESSON
- id: LESSON-20260329-ci-validator-gap
- context: evidence_validator.py performs file/git verification but only called manually
- trigger: git-audit-20260323 identified this gap
- actionable_rule: When creating validation tools, wire them into CI in the same story
- applies_to:
  - jarvis
  - senior-dev
- expected_outcome: No validation tool exists without being wired into CI pipeline
- evidence_ref: SAFETY-MERGE-AUTHORITY-001
- added_utc: 2026-03-29T00:30:00Z
```

```text
LESSON
- id: LESSON-20260401-completion-fraud-detection
- context: During P0 merge authority fix, Jarvis reported all 4 scripts fixed but one was NOT
- trigger: SAFETY-MERGE-AUTHORITY-001 remediation
- actionable_rule: Aria MUST independently verify every completion claim
- applies_to:
  - aria
- expected_outcome: No false completion claims
- evidence_ref: PR #837
- added_utc: 2026-04-01T12:00:00Z
```

```text
LESSON
- id: LESSON-20260405-duplicate-ci-validator
- context: evidence_validator.py performs file/git verification but only called manually
- trigger: git-audit-20260323 identified this gap
- actionable_rule: When creating validation tools, wire them into CI in the same story
- applies_to:
  - jarvis
- expected_outcome: Same as before
- evidence_ref: DIFFERENT-REF
- added_utc: 2026-04-05T00:00:00Z
```
""",
        encoding="utf-8",
    )
    return lessons_path


@pytest.fixture
def sample_cycle_file(tmp_repo_root: Path) -> Path:
    """Create a sample cycle artifact with deferred items."""
    cycle_path = (
        tmp_repo_root
        / "_bmad-output"
        / "autocog"
        / "cycles"
        / "autocog-20260412-194058-02a127.json"
    )
    cycle_data = {
        "run_id": "autocog-20260412-194058-02a127",
        "started_at": "2026-04-12T19:40:58Z",
        "completed_at": "2026-04-12T19:45:00Z",
        "status": "completed",
        "rejections": [
            {
                "reason": "Insufficient evidence for promotion",
                "candidate": "brain-v2.3",
            },
        ],
        "metrics": {
            "skip_rate_check": {
                "alert_triggered": True,
                "skip_rate": 0.45,
                "threshold": 0.30,
            }
        },
    }
    cycle_path.write_text(json.dumps(cycle_data), encoding="utf-8")
    return cycle_path


# ---------------------------------------------------------------------------
# Tests: fingerprint_lesson
# ---------------------------------------------------------------------------


class TestFingerprintLesson:
    """Tests for lesson fingerprinting."""

    def test_same_content_same_fingerprint(self):
        """Identical lessons produce identical fingerprints."""
        fp1 = fingerprint_lesson("ctx", "trigger", "rule")
        fp2 = fingerprint_lesson("ctx", "trigger", "rule")
        assert fp1 == fp2

    def test_different_content_different_fingerprint(self):
        """Different lessons produce different fingerprints."""
        fp1 = fingerprint_lesson("ctx a", "trigger", "rule")
        fp2 = fingerprint_lesson("ctx b", "trigger", "rule")
        assert fp1 != fp2

    def test_case_insensitive(self):
        """Fingerprinting is case-insensitive."""
        fp1 = fingerprint_lesson("Context", "Trigger", "Rule")
        fp2 = fingerprint_lesson("context", "trigger", "rule")
        assert fp1 == fp2

    def test_whitespace_stripped(self):
        """Leading/trailing whitespace is stripped."""
        fp1 = fingerprint_lesson("  ctx  ", "  trigger  ", "  rule  ")
        fp2 = fingerprint_lesson("ctx", "trigger", "rule")
        assert fp1 == fp2

    def test_fingerprint_is_sha256_prefix(self):
        """Fingerprint is a 16-char hex string."""
        fp = fingerprint_lesson("test", "test", "test")
        assert len(fp) == 16
        int(fp, 16)  # Must be valid hex


# ---------------------------------------------------------------------------
# Tests: parse_lessons_file
# ---------------------------------------------------------------------------


class TestParseLessonsFile:
    """Tests for lessons.md parsing."""

    def test_parse_multiple_lessons(self, sample_lessons_file: Path):
        """Correctly parses multiple LESSON blocks."""
        lessons = parse_lessons_file(sample_lessons_file)
        assert len(lessons) == 3
        assert lessons[0]["id"] == "LESSON-20260329-ci-validator-gap"
        assert lessons[1]["id"] == "LESSON-20260401-completion-fraud-detection"
        assert lessons[2]["id"] == "LESSON-20260405-duplicate-ci-validator"

    def test_parse_applies_to_list(self, sample_lessons_file: Path):
        """Correctly parses multi-value applies_to."""
        lessons = parse_lessons_file(sample_lessons_file)
        first = lessons[0]
        assert isinstance(first["applies_to"], list)
        assert "jarvis" in first["applies_to"]
        assert "senior-dev" in first["applies_to"]

    def test_parse_missing_file(self):
        """Returns empty list for missing file."""
        lessons = parse_lessons_file(Path("/nonexistent/lessons.md"))
        assert lessons == []

    def test_parse_no_lessons(self, tmp_path: Path):
        """Returns empty list for file without LESSON blocks."""
        f = tmp_path / "empty_lessons.md"
        f.write_text("# No lessons here\n", encoding="utf-8")
        lessons = parse_lessons_file(f)
        assert lessons == []

    def test_all_fields_parsed(self, sample_lessons_file: Path):
        """All standard fields are captured."""
        lessons = parse_lessons_file(sample_lessons_file)
        first = lessons[0]
        assert "id" in first
        assert "context" in first
        assert "trigger" in first
        assert "actionable_rule" in first
        assert "expected_outcome" in first
        assert "evidence_ref" in first
        assert "added_utc" in first


# ---------------------------------------------------------------------------
# Tests: normalize_and_dedup_lessons
# ---------------------------------------------------------------------------


class TestNormalizeAndDedupLessons:
    """Tests for lesson normalization and deduplication."""

    def test_dedup_identical_lessons(self, sample_lessons_file: Path):
        """Duplicate lessons (same fingerprint) are merged."""
        raw = parse_lessons_file(sample_lessons_file)
        normalized, dup_count = normalize_and_dedup_lessons(raw)
        # First and third lesson share same context+trigger+actionable_rule
        assert dup_count >= 1
        assert len(normalized) < len(raw)

    def test_occurrence_count_increments(self, sample_lessons_file: Path):
        """Occurrence count reflects duplicates."""
        raw = parse_lessons_file(sample_lessons_file)
        normalized, _ = normalize_and_dedup_lessons(raw)
        # Find the deduplicated one
        for lesson in normalized:
            if lesson.occurrence_count > 1:
                assert lesson.occurrence_count == 2
                break

    def test_unique_lessons_preserved(self, sample_lessons_file: Path):
        """Unique lessons are kept intact."""
        raw = parse_lessons_file(sample_lessons_file)
        normalized, _ = normalize_and_dedup_lessons(raw)
        ids = [l.id for l in normalized]
        assert "LESSON-20260401-completion-fraud-detection" in ids

    def test_empty_input(self):
        """Empty input returns empty results."""
        normalized, dup_count = normalize_and_dedup_lessons([])
        assert normalized == []
        assert dup_count == 0


# ---------------------------------------------------------------------------
# Tests: scan_redis_keys
# ---------------------------------------------------------------------------


class TestScanRedisKeys:
    """Tests for Redis key scanning."""

    @patch("scripts.autocog.monthly_audit.REDIS_AVAILABLE", True)
    @patch("scripts.autocog.monthly_audit.redis")
    def test_scan_returns_keys(self, mock_redis_module: MagicMock):
        """SCAN returns all matching keys."""
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        # SCAN returns (cursor, keys) tuples
        mock_client.scan.side_effect = [
            (1, [b"bmad:chiseai:iterlog:story:ST-001"]),
            (0, [b"bmad:chiseai:metacog:prediction:story:ST-002"]),
        ]
        mock_redis_module.Redis.from_url.return_value = mock_client

        keys = scan_redis_keys("redis://localhost:6379/0")
        assert len(keys) == 2
        assert "bmad:chiseai:iterlog:story:ST-001" in keys
        assert "bmad:chiseai:metacog:prediction:story:ST-002" in keys

    @patch("scripts.autocog.monthly_audit.REDIS_AVAILABLE", False)
    def test_scan_unavailable(self):
        """Returns empty list when Redis unavailable."""
        keys = scan_redis_keys("redis://localhost:6379/0")
        assert keys == []


# ---------------------------------------------------------------------------
# Tests: collect_metacog_dimensions
# ---------------------------------------------------------------------------


class TestCollectMetacogDimensions:
    """Tests for metacog dimension collection."""

    @patch("scripts.autocog.monthly_audit.REDIS_AVAILABLE", True)
    @patch("scripts.autocog.monthly_audit.redis")
    def test_collects_prediction_keys(self, mock_redis_module: MagicMock):
        """Collects prediction dimensions from Redis."""
        mock_client = MagicMock()
        mock_client.type.return_value = b"hash"
        mock_client.hgetall.return_value = {
            b"confidence": b"0.8",
            b"story_id": b"ST-001",
        }
        mock_redis_module.Redis.from_url.return_value = mock_client

        keys = ["bmad:chiseai:metacog:prediction:story:ST-001"]
        dims = collect_metacog_dimensions("redis://localhost:6379/0", keys)

        assert len(dims) == 1
        assert dims[0].key_type == "prediction"
        assert dims[0].story_id == "ST-001"
        assert dims[0].fields["confidence"] == "0.8"

    @patch("scripts.autocog.monthly_audit.REDIS_AVAILABLE", True)
    @patch("scripts.autocog.monthly_audit.redis")
    def test_collects_outcome_keys(self, mock_redis_module: MagicMock):
        """Collects outcome dimensions from Redis."""
        mock_client = MagicMock()
        mock_client.type.return_value = b"hash"
        mock_client.hgetall.return_value = {
            b"actual_outcome": b"success",
            b"story_id": b"ST-002",
        }
        mock_redis_module.Redis.from_url.return_value = mock_client

        keys = ["bmad:chiseai:metacog:outcome:story:ST-002"]
        dims = collect_metacog_dimensions("redis://localhost:6379/0", keys)

        assert len(dims) == 1
        assert dims[0].key_type == "outcome"

    def test_empty_keys(self):
        """Returns empty list for no keys."""
        dims = collect_metacog_dimensions("redis://localhost:6379/0", [])
        assert dims == []

    @patch("scripts.autocog.monthly_audit.REDIS_AVAILABLE", True)
    @patch("scripts.autocog.monthly_audit.redis")
    def test_skips_non_metacog_keys(self, mock_redis_module: MagicMock):
        """Skips keys that don't match metacog pattern."""
        keys = ["bmad:chiseai:iterlog:story:ST-001", "bmad:chiseai:ownership"]
        dims = collect_metacog_dimensions("redis://localhost:6379/0", keys)
        assert dims == []


# ---------------------------------------------------------------------------
# Tests: collect_deferred_items
# ---------------------------------------------------------------------------


class TestCollectDeferredItems:
    """Tests for deferred item collection from cycle artifacts."""

    def test_collects_rejections(self, sample_cycle_file: Path):
        """Collects rejected promotions as deferred items."""
        cycles_dir = sample_cycle_file.parent
        items = collect_deferred_items(cycles_dir)

        rejection_items = [i for i in items if i.item_type == "rejection"]
        assert len(rejection_items) == 1
        assert "Insufficient evidence" in rejection_items[0].description

    def test_collects_skip_rate_alerts(self, sample_cycle_file: Path):
        """Collects skip rate alerts as deferred items."""
        cycles_dir = sample_cycle_file.parent
        items = collect_deferred_items(cycles_dir)

        skip_items = [i for i in items if i.item_type == "skip_rate_alert"]
        assert len(skip_items) == 1
        assert "0.45" in skip_items[0].description

    def test_missing_cycles_dir(self):
        """Returns empty list when cycles dir doesn't exist."""
        items = collect_deferred_items(Path("/nonexistent/cycles"))
        assert items == []

    def test_empty_cycles_dir(self, tmp_path: Path):
        """Returns empty list for empty cycles dir."""
        items = collect_deferred_items(tmp_path)
        assert items == []

    def test_ignores_corrupt_json(self, tmp_repo_root: Path):
        """Skips cycle files with invalid JSON."""
        bad_cycle = (
            tmp_repo_root / "_bmad-output" / "autocog" / "cycles" / "autocog-bad.json"
        )
        bad_cycle.write_text("{invalid json}", encoding="utf-8")
        items = collect_deferred_items(bad_cycle.parent)
        assert items == []


# ---------------------------------------------------------------------------
# Tests: promote_to_qdrant
# ---------------------------------------------------------------------------


class TestPromoteToQdrant:
    """Tests for Qdrant promotion."""

    @patch("scripts.autocog.monthly_audit.QDRANT_AVAILABLE", False)
    def test_unavailable_returns_zero(self):
        """Returns 0 when Qdrant client unavailable."""
        count = promote_to_qdrant([], dry_run=False)
        assert count == 0

    @patch("scripts.autocog.monthly_audit.QDRANT_AVAILABLE", True)
    @patch("scripts.autocog.monthly_audit.QdrantClient")
    def test_dry_run_counts_without_upsert(self, mock_qdrant_cls: MagicMock):
        """Dry run counts promotions without calling upsert."""
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_collection.name = "ChiseAI"
        mock_client.get_collections.return_value.collections = [mock_collection]
        mock_qdrant_cls.return_value = mock_client

        lessons = [
            NormalizedLesson(
                id="LESSON-001",
                fingerprint="abc123",
                context="test context",
                trigger="test trigger",
                actionable_rule="test rule",
                applies_to=["jarvis"],
            )
        ]

        count = promote_to_qdrant(lessons, dry_run=True)
        assert count == 1
        mock_client.upsert.assert_not_called()

    @patch("scripts.autocog.monthly_audit.QDRANT_AVAILABLE", True)
    @patch("scripts.autocog.monthly_audit.QdrantClient")
    def test_skips_superseded_lessons(self, mock_qdrant_cls: MagicMock):
        """Skips lessons that are superseded."""
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_collection.name = "ChiseAI"
        mock_client.get_collections.return_value.collections = [mock_collection]
        mock_qdrant_cls.return_value = mock_client

        lessons = [
            NormalizedLesson(
                id="LESSON-001",
                fingerprint="abc123",
                context="test",
                trigger="test",
                actionable_rule="test rule",
                applies_to=["jarvis"],
                superseded_by="LESSON-002",
            )
        ]

        count = promote_to_qdrant(lessons, dry_run=True)
        assert count == 0

    @patch("scripts.autocog.monthly_audit.QDRANT_AVAILABLE", True)
    @patch("scripts.autocog.monthly_audit.QdrantClient")
    def test_skips_incomplete_lessons(self, mock_qdrant_cls: MagicMock):
        """Skips lessons without actionable_rule or context."""
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_collection.name = "ChiseAI"
        mock_client.get_collections.return_value.collections = [mock_collection]
        mock_qdrant_cls.return_value = mock_client

        lessons = [
            NormalizedLesson(
                id="LESSON-001",
                fingerprint="abc123",
                context="",
                trigger="test",
                actionable_rule="",
                applies_to=[],
            )
        ]

        count = promote_to_qdrant(lessons, dry_run=True)
        assert count == 0

    @patch("scripts.autocog.monthly_audit.QDRANT_AVAILABLE", True)
    @patch("scripts.autocog.monthly_audit.QdrantClient")
    def test_missing_collection_returns_zero(self, mock_qdrant_cls: MagicMock):
        """Returns 0 when ChiseAI collection doesn't exist."""
        mock_client = MagicMock()
        mock_client.get_collections.return_value.collections = []
        mock_qdrant_cls.return_value = mock_client

        count = promote_to_qdrant([], dry_run=False)
        assert count == 0


# ---------------------------------------------------------------------------
# Tests: run_monthly_audit (integration)
# ---------------------------------------------------------------------------


class TestRunMonthlyAudit:
    """Integration tests for the full monthly audit."""

    @patch("scripts.autocog.monthly_audit.REDIS_AVAILABLE", False)
    @patch("scripts.autocog.monthly_audit.QDRANT_AVAILABLE", False)
    def test_audit_without_dependencies(
        self, tmp_repo_root: Path, sample_lessons_file: Path
    ):
        """Audit runs even without Redis/Qdrant, using file-based data."""
        result = run_monthly_audit(
            dry_run=True,
            repo_root=tmp_repo_root,
        )

        assert isinstance(result, MonthlyAuditResult)
        assert result.dry_run is True
        assert result.timestamp != ""
        assert result.redis_available is False
        assert result.qdrant_available is False
        assert len(result.lessons_normalized) == 2  # deduped from 3
        assert result.lessons_duplicate_count >= 1
        assert len(result.warnings) > 0  # Should warn about missing deps

    @patch("scripts.autocog.monthly_audit.REDIS_AVAILABLE", True)
    @patch("scripts.autocog.monthly_audit.redis")
    @patch("scripts.autocog.monthly_audit.QDRANT_AVAILABLE", False)
    def test_audit_with_redis(
        self,
        mock_redis_module: MagicMock,
        tmp_repo_root: Path,
        sample_lessons_file: Path,
    ):
        """Audit collects Redis data when available."""
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.scan.return_value = (
            0,
            [b"bmad:chiseai:metacog:prediction:story:ST-001"],
        )
        mock_client.type.return_value = b"hash"
        mock_client.hgetall.return_value = {b"confidence": b"0.9"}
        mock_redis_module.Redis.from_url.return_value = mock_client

        result = run_monthly_audit(
            dry_run=True,
            repo_root=tmp_repo_root,
            redis_url="redis://localhost:6379/0",
        )

        assert result.redis_available is True
        assert len(result.all_redis_keys) == 1
        assert len(result.all_metacog_dimensions) == 1
        assert result.all_metacog_dimensions[0]["key_type"] == "prediction"

    @patch("scripts.autocog.monthly_audit.REDIS_AVAILABLE", False)
    @patch("scripts.autocog.monthly_audit.QDRANT_AVAILABLE", False)
    def test_audit_collects_deferred_items(
        self,
        tmp_repo_root: Path,
        sample_lessons_file: Path,
        sample_cycle_file: Path,
    ):
        """Audit collects deferred items from cycle artifacts."""
        result = run_monthly_audit(
            dry_run=True,
            repo_root=tmp_repo_root,
        )

        assert len(result.deferred_items_status) == 2  # 1 rejection + 1 skip alert


# ---------------------------------------------------------------------------
# Tests: write_audit_result
# ---------------------------------------------------------------------------


class TestWriteAuditResult:
    """Tests for writing audit result JSON."""

    @patch("scripts.autocog.monthly_audit.REDIS_AVAILABLE", False)
    @patch("scripts.autocog.monthly_audit.QDRANT_AVAILABLE", False)
    def test_write_creates_json_file(
        self, tmp_repo_root: Path, sample_lessons_file: Path
    ):
        """Write creates a valid JSON file in the cycles directory."""
        result = run_monthly_audit(dry_run=False, repo_root=tmp_repo_root)
        output_path = write_audit_result(result, tmp_repo_root)

        assert output_path.exists()
        data = json.loads(output_path.read_text(encoding="utf-8"))
        assert "timestamp" in data
        assert "lessons_normalized" in data
        assert "all_metacog_dimensions" in data
        assert "deferred_items_status" in data
        assert "durable_learnings_promoted" in data

    @patch("scripts.autocog.monthly_audit.REDIS_AVAILABLE", False)
    @patch("scripts.autocog.monthly_audit.QDRANT_AVAILABLE", False)
    def test_write_filename_contains_date(
        self, tmp_repo_root: Path, sample_lessons_file: Path
    ):
        """Output filename includes the current date."""
        result = run_monthly_audit(dry_run=False, repo_root=tmp_repo_root)
        output_path = write_audit_result(result, tmp_repo_root)

        today = datetime.now(UTC).strftime("%Y-%m-%d")
        assert today in output_path.name
        assert output_path.name.endswith("-full-cycle.json")


# ---------------------------------------------------------------------------
# Tests: CLI (--dry-run)
# ---------------------------------------------------------------------------


class TestCLIDryRun:
    """Tests for the CLI --dry-run flag."""

    @patch("scripts.autocog.monthly_audit.REDIS_AVAILABLE", False)
    @patch("scripts.autocog.monthly_audit.QDRANT_AVAILABLE", False)
    def test_dry_run_no_output_file(
        self,
        tmp_repo_root: Path,
        sample_lessons_file: Path,
        capsys: pytest.CaptureFixture,
    ):
        """Dry run does not create output file."""
        with (
            patch(
                "scripts.autocog.monthly_audit.get_repo_root",
                return_value=tmp_repo_root,
            ),
            patch(
                "sys.argv",
                ["monthly_audit.py", "--dry-run", "--repo-root", str(tmp_repo_root)],
            ),
        ):
            from scripts.autocog.monthly_audit import main

            rc = main()

        assert rc == 0

        # Check no output file was created
        cycles_dir = tmp_repo_root / "_bmad-output" / "autocog" / "cycles"
        full_cycle_files = list(cycles_dir.glob("*-full-cycle.json"))
        assert len(full_cycle_files) == 0

        # Check dry run message in output
        captured = capsys.readouterr()
        assert "DRY RUN" in captured.out
