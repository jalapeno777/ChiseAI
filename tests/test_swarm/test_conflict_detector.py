#!/usr/bin/env python3
"""
Tests for conflict_detector.py

Story: ST-AUTO-007
"""

# Add project root to path
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.swarm.conflict_detector import (
    ChangeSet,
    ConflictDetector,
    ConflictReport,
    ConflictSeverity,
    ConflictType,
    FileChange,
)


class TestConflictType(unittest.TestCase):
    """Test ConflictType enum."""

    def test_enum_values(self):
        """Test enum values."""
        self.assertEqual(ConflictType.NONE.value, "none")
        self.assertEqual(ConflictType.FILE_OVERLAP.value, "file_overlap")
        self.assertEqual(ConflictType.SCOPE_OVERLAP.value, "scope_overlap")
        self.assertEqual(ConflictType.MERGE_CONFLICT.value, "merge_conflict")


class TestConflictSeverity(unittest.TestCase):
    """Test ConflictSeverity enum."""

    def test_enum_values(self):
        """Test enum values."""
        self.assertEqual(ConflictSeverity.NONE.value, "none")
        self.assertEqual(ConflictSeverity.LOW.value, "low")
        self.assertEqual(ConflictSeverity.MEDIUM.value, "medium")
        self.assertEqual(ConflictSeverity.HIGH.value, "high")
        self.assertEqual(ConflictSeverity.CRITICAL.value, "critical")


class TestConflictReport(unittest.TestCase):
    """Test ConflictReport dataclass."""

    def test_to_dict(self):
        """Test conversion to dictionary."""
        report = ConflictReport(
            conflict_type=ConflictType.FILE_OVERLAP,
            severity=ConflictSeverity.MEDIUM,
            source_story="ST-001",
            target_story="ST-002",
            source_agent="agent-1",
            target_agent="agent-2",
            conflicting_files=["file1.py", "file2.py"],
            description="Files overlap",
            resolution_strategy="Manual merge",
            auto_resolvable=False,
        )

        data = report.to_dict()

        self.assertEqual(data["conflict_type"], "file_overlap")
        self.assertEqual(data["severity"], "medium")
        self.assertEqual(data["source_story"], "ST-001")
        self.assertEqual(len(data["conflicting_files"]), 2)
        self.assertFalse(data["auto_resolvable"])

    def test_from_dict(self):
        """Test creation from dictionary."""
        data = {
            "conflict_type": "file_overlap",
            "severity": "medium",
            "source_story": "ST-001",
            "target_story": "ST-002",
            "source_agent": "agent-1",
            "target_agent": "agent-2",
            "conflicting_files": ["file1.py"],
            "description": "Test",
            "resolution_strategy": "Merge",
            "auto_resolvable": True,
        }

        report = ConflictReport.from_dict(data)

        self.assertEqual(report.conflict_type, ConflictType.FILE_OVERLAP)
        self.assertEqual(report.severity, ConflictSeverity.MEDIUM)
        self.assertEqual(report.source_story, "ST-001")


class TestFileChange(unittest.TestCase):
    """Test FileChange dataclass."""

    def test_creation(self):
        """Test creating FileChange."""
        change = FileChange(
            path="src/test.py",
            change_type="modified",
            additions=10,
            deletions=5,
            scope="src:test",
        )

        self.assertEqual(change.path, "src/test.py")
        self.assertEqual(change.change_type, "modified")
        self.assertEqual(change.additions, 10)
        self.assertEqual(change.deletions, 5)
        self.assertEqual(change.scope, "src:test")


class TestChangeSet(unittest.TestCase):
    """Test ChangeSet dataclass."""

    def test_to_dict(self):
        """Test conversion to dictionary."""
        change_set = ChangeSet(
            story_id="ST-001",
            agent="agent-1",
            branch="feature/test",
            base_ref="main",
            files=[
                FileChange(path="file1.py", change_type="modified", additions=5),
                FileChange(path="file2.py", change_type="added", additions=10),
            ],
            scopes=["src:test"],
        )

        data = change_set.to_dict()

        self.assertEqual(data["story_id"], "ST-001")
        self.assertEqual(data["agent"], "agent-1")
        self.assertEqual(len(data["files"]), 2)
        self.assertEqual(data["scopes"], ["src:test"])


class TestConflictDetector(unittest.TestCase):
    """Test ConflictDetector class."""

    def setUp(self):
        """Set up test fixtures."""
        self.repo_root = Path(__file__).parent.parent.parent
        self.detector = ConflictDetector(repo_root=self.repo_root)

    def test_init(self):
        """Test initialization."""
        self.assertEqual(self.detector.repo_root, self.repo_root)

    def test_find_repo_root(self):
        """Test finding repository root."""
        root = self.detector._find_repo_root()
        self.assertTrue(root.exists())

    def test_detect_scope(self):
        """Test scope detection."""
        # Test known scopes
        self.assertEqual(
            self.detector._detect_scope("scripts/swarm/test.py"), "scripts:swarm"
        )
        self.assertEqual(
            self.detector._detect_scope("src/strategy/test.py"), "src:strategy"
        )

        # Test unknown scope
        self.assertIsNone(self.detector._detect_scope("unknown/path.py"))

    def test_is_protected_file(self):
        """Test protected file detection."""
        self.assertTrue(self.detector._is_protected_file(".woodpecker.yml"))
        self.assertTrue(self.detector._is_protected_file("pyproject.toml"))
        self.assertTrue(
            self.detector._is_protected_file("docs/bmm-workflow-status.yaml")
        )
        self.assertFalse(self.detector._is_protected_file("src/test.py"))

    @patch("subprocess.run")
    def test_get_changed_files(self, mock_run):
        """Test getting changed files."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="src/file1.py | 10 +++---\nsrc/file2.py | 5 +++++\n"
        )

        files = self.detector.get_changed_files("feature/test", "main")

        self.assertEqual(len(files), 2)
        self.assertEqual(files[0].path, "src/file1.py")
        self.assertEqual(files[0].additions, 3)  # Count of + in "+++---"
        self.assertEqual(files[0].deletions, 3)  # Count of - in "+++---"

    @patch("subprocess.run")
    def test_get_changed_files_failure(self, mock_run):
        """Test getting changed files failure."""
        mock_run.return_value = MagicMock(returncode=1, stderr="error")

        files = self.detector.get_changed_files("feature/test", "main")

        self.assertEqual(len(files), 0)

    def test_detect_scope_overlap(self):
        """Test scope overlap detection."""
        cs1 = ChangeSet(
            story_id="ST-001",
            agent="agent-1",
            branch="feature/test1",
            files=[
                FileChange(
                    path="scripts/swarm/file1.py",
                    change_type="modified",
                    scope="scripts:swarm",
                )
            ],
            scopes=["scripts:swarm"],
        )
        cs2 = ChangeSet(
            story_id="ST-002",
            agent="agent-2",
            branch="feature/test2",
            files=[
                FileChange(
                    path="scripts/swarm/file2.py",
                    change_type="modified",
                    scope="scripts:swarm",
                )
            ],
            scopes=["scripts:swarm"],
        )

        overlap = self.detector.detect_scope_overlap(cs1, cs2)

        self.assertEqual(len(overlap), 1)
        self.assertEqual(overlap[0], "scripts:swarm")

    def test_detect_scope_overlap_none(self):
        """Test scope overlap detection with no overlap."""
        cs1 = ChangeSet(
            story_id="ST-001",
            agent="agent-1",
            branch="feature/test1",
            files=[
                FileChange(
                    path="scripts/swarm/file1.py",
                    change_type="modified",
                    scope="scripts:swarm",
                )
            ],
            scopes=["scripts:swarm"],
        )
        cs2 = ChangeSet(
            story_id="ST-002",
            agent="agent-2",
            branch="feature/test2",
            files=[
                FileChange(
                    path="src/strategy/file2.py",
                    change_type="modified",
                    scope="src:strategy",
                )
            ],
            scopes=["src:strategy"],
        )

        overlap = self.detector.detect_scope_overlap(cs1, cs2)

        self.assertEqual(len(overlap), 0)

    def test_detect_file_overlap(self):
        """Test file overlap detection."""
        cs1 = ChangeSet(
            story_id="ST-001",
            agent="agent-1",
            branch="feature/test1",
            files=[
                FileChange(path="src/file1.py", change_type="modified"),
                FileChange(path="src/file2.py", change_type="modified"),
            ],
        )
        cs2 = ChangeSet(
            story_id="ST-002",
            agent="agent-2",
            branch="feature/test2",
            files=[
                FileChange(path="src/file2.py", change_type="modified"),
                FileChange(path="src/file3.py", change_type="modified"),
            ],
        )

        overlap = self.detector.detect_file_overlap(cs1, cs2)

        self.assertEqual(len(overlap), 1)
        self.assertEqual(overlap[0], "src/file2.py")

    def test_detect_file_overlap_none(self):
        """Test file overlap detection with no overlap."""
        cs1 = ChangeSet(
            story_id="ST-001",
            agent="agent-1",
            branch="feature/test1",
            files=[FileChange(path="src/file1.py", change_type="modified")],
        )
        cs2 = ChangeSet(
            story_id="ST-002",
            agent="agent-2",
            branch="feature/test2",
            files=[FileChange(path="src/file2.py", change_type="modified")],
        )

        overlap = self.detector.detect_file_overlap(cs1, cs2)

        self.assertEqual(len(overlap), 0)

    def test_extract_changed_ranges(self):
        """Test extracting changed line ranges from diff."""
        diff = """@@ -1,5 +1,7 @@
line 1
line 2
@@ -10,3 +12,4 @@
line 10
line 11
"""

        ranges = self.detector._extract_changed_ranges(diff)

        self.assertEqual(len(ranges), 2)
        self.assertEqual(ranges[0], (1, 7))
        self.assertEqual(ranges[1], (12, 15))

    def test_detect_conflicts_no_overlap(self):
        """Test conflict detection with no overlap."""
        cs1 = ChangeSet(
            story_id="ST-001",
            agent="agent-1",
            branch="feature/test1",
            files=[FileChange(path="src/file1.py", change_type="modified")],
        )
        cs2 = ChangeSet(
            story_id="ST-002",
            agent="agent-2",
            branch="feature/test2",
            files=[FileChange(path="src/file2.py", change_type="modified")],
        )

        report = self.detector.detect_conflicts(cs1, cs2)

        self.assertEqual(report.conflict_type, ConflictType.NONE)
        self.assertEqual(report.severity, ConflictSeverity.NONE)
        self.assertTrue(report.auto_resolvable)

    def test_detect_conflicts_protected_file(self):
        """Test conflict detection with protected file."""
        cs1 = ChangeSet(
            story_id="ST-001",
            agent="agent-1",
            branch="feature/test1",
            files=[FileChange(path=".woodpecker.yml", change_type="modified")],
        )
        cs2 = ChangeSet(
            story_id="ST-002",
            agent="agent-2",
            branch="feature/test2",
            files=[FileChange(path=".woodpecker.yml", change_type="modified")],
        )

        report = self.detector.detect_conflicts(cs1, cs2)

        self.assertEqual(report.conflict_type, ConflictType.FILE_OVERLAP)
        self.assertEqual(report.severity, ConflictSeverity.CRITICAL)
        self.assertFalse(report.auto_resolvable)
        self.assertIn(".woodpecker.yml", report.conflicting_files)

    @patch.object(ConflictDetector, "check_merge_conflict_potential")
    def test_detect_conflicts_merge_conflict(self, mock_check):
        """Test conflict detection with merge conflict."""
        mock_check.return_value = (True, ["src/file1.py"])

        cs1 = ChangeSet(
            story_id="ST-001",
            agent="agent-1",
            branch="feature/test1",
            files=[FileChange(path="src/file1.py", change_type="modified")],
        )
        cs2 = ChangeSet(
            story_id="ST-002",
            agent="agent-2",
            branch="feature/test2",
            files=[FileChange(path="src/file1.py", change_type="modified")],
        )

        report = self.detector.detect_conflicts(cs1, cs2)

        self.assertEqual(report.conflict_type, ConflictType.MERGE_CONFLICT)
        self.assertIn(report.severity, [ConflictSeverity.MEDIUM, ConflictSeverity.HIGH])
        self.assertFalse(report.auto_resolvable)

    def test_detect_all_conflicts(self):
        """Test detecting all conflicts among multiple change sets."""
        cs1 = ChangeSet(
            story_id="ST-001",
            agent="agent-1",
            branch="feature/test1",
            files=[FileChange(path="src/file1.py", change_type="modified")],
        )
        cs2 = ChangeSet(
            story_id="ST-002",
            agent="agent-2",
            branch="feature/test2",
            files=[FileChange(path="src/file1.py", change_type="modified")],
        )
        cs3 = ChangeSet(
            story_id="ST-003",
            agent="agent-3",
            branch="feature/test3",
            files=[FileChange(path="src/file2.py", change_type="modified")],
        )

        reports = self.detector.detect_all_conflicts([cs1, cs2, cs3])

        # Should have 1 conflict (between cs1 and cs2)
        self.assertEqual(len(reports), 1)

    def test_generate_conflict_matrix(self):
        """Test generating conflict matrix."""
        cs1 = ChangeSet(
            story_id="ST-001",
            agent="agent-1",
            branch="feature/test1",
            files=[FileChange(path="src/file1.py", change_type="modified")],
        )
        cs2 = ChangeSet(
            story_id="ST-002",
            agent="agent-2",
            branch="feature/test2",
            files=[FileChange(path="src/file1.py", change_type="modified")],
        )

        matrix = self.detector.generate_conflict_matrix([cs1, cs2])

        self.assertEqual(len(matrix["agents"]), 2)
        self.assertEqual(matrix["total_conflicts"], 1)
        self.assertEqual(matrix["auto_resolvable"], 1)

    def test_generate_conflict_matrix_empty(self):
        """Test generating conflict matrix with no conflicts."""
        cs1 = ChangeSet(
            story_id="ST-001",
            agent="agent-1",
            branch="feature/test1",
            files=[FileChange(path="src/file1.py", change_type="modified")],
        )
        cs2 = ChangeSet(
            story_id="ST-002",
            agent="agent-2",
            branch="feature/test2",
            files=[FileChange(path="src/file2.py", change_type="modified")],
        )

        matrix = self.detector.generate_conflict_matrix([cs1, cs2])

        self.assertEqual(matrix["total_conflicts"], 0)
        self.assertEqual(matrix["auto_resolvable"], 0)


class TestConflictDetectorAnalyze(unittest.TestCase):
    """Test ConflictDetector analyze methods."""

    def setUp(self):
        """Set up test fixtures."""
        self.repo_root = Path(__file__).parent.parent.parent

        with patch.object(
            ConflictDetector, "_find_repo_root", return_value=self.repo_root
        ):
            self.detector = ConflictDetector()

    @patch.object(ConflictDetector, "get_changed_files")
    def test_analyze_changes(self, mock_get_files):
        """Test analyzing changes."""
        mock_get_files.return_value = [
            FileChange(
                path="scripts/swarm/test.py",
                change_type="modified",
                scope="scripts:swarm",
            ),
        ]

        change_set = self.detector.analyze_changes(
            story_id="ST-001",
            agent="agent-1",
            branch="feature/test",
        )

        self.assertEqual(change_set.story_id, "ST-001")
        self.assertEqual(change_set.agent, "agent-1")
        self.assertEqual(len(change_set.files), 1)
        self.assertEqual(change_set.scopes, ["scripts:swarm"])


if __name__ == "__main__":
    unittest.main()
