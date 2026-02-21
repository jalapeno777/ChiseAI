"""Tests for classification module."""

from autonomous_git.path_analyzer.classification import (
    RiskLevel,
    FileClassification,
    RiskClassification,
)


class TestRiskLevel:
    """Test RiskLevel enum."""

    def test_enum_values(self):
        """Test that enum values are correct."""
        assert RiskLevel.SAFE.value == "safe"
        assert RiskLevel.MEDIUM_RISK.value == "medium_risk"
        assert RiskLevel.COMPLEX.value == "complex"

    def test_str_representation(self):
        """Test string representation."""
        assert str(RiskLevel.SAFE) == "safe"
        assert str(RiskLevel.MEDIUM_RISK) == "medium_risk"
        assert str(RiskLevel.COMPLEX) == "complex"

    def test_priority_ordering(self):
        """Test risk level priority."""
        assert RiskLevel.SAFE.priority == 0
        assert RiskLevel.MEDIUM_RISK.priority == 1
        assert RiskLevel.COMPLEX.priority == 2

    def test_from_highest_with_empty_list(self):
        """Test from_highest with empty list defaults to COMPLEX."""
        result = RiskLevel.from_highest([])
        assert result == RiskLevel.COMPLEX

    def test_from_highest_with_single_item(self):
        """Test from_highest with single item."""
        assert RiskLevel.from_highest([RiskLevel.SAFE]) == RiskLevel.SAFE
        assert RiskLevel.from_highest([RiskLevel.COMPLEX]) == RiskLevel.COMPLEX

    def test_from_highest_returns_highest(self):
        """Test from_highest returns highest risk level."""
        levels = [RiskLevel.SAFE, RiskLevel.MEDIUM_RISK, RiskLevel.SAFE]
        assert RiskLevel.from_highest(levels) == RiskLevel.MEDIUM_RISK

        levels = [RiskLevel.SAFE, RiskLevel.COMPLEX, RiskLevel.MEDIUM_RISK]
        assert RiskLevel.from_highest(levels) == RiskLevel.COMPLEX


class TestFileClassification:
    """Test FileClassification dataclass."""

    def test_basic_creation(self):
        """Test basic FileClassification creation."""
        fc = FileClassification(
            path="docs/readme.md",
            risk_level=RiskLevel.SAFE,
            confidence=0.95,
        )
        assert fc.path == "docs/readme.md"
        assert fc.risk_level == RiskLevel.SAFE
        assert fc.confidence == 0.95
        assert fc.pattern_matched is None
        assert fc.semantic_flags == []

    def test_with_pattern(self):
        """Test FileClassification with pattern match."""
        fc = FileClassification(
            path="docs/readme.md",
            risk_level=RiskLevel.SAFE,
            confidence=0.95,
            pattern_matched="Documentation files",
            semantic_flags=[],
        )
        assert fc.pattern_matched == "Documentation files"

    def test_with_semantic_flags(self):
        """Test FileClassification with semantic flags."""
        fc = FileClassification(
            path="src/main.py",
            risk_level=RiskLevel.COMPLEX,
            confidence=0.8,
            pattern_matched="Package init",
            semantic_flags=["test_deletion", "critical_file"],
        )
        assert len(fc.semantic_flags) == 2
        assert "test_deletion" in fc.semantic_flags


class TestRiskClassification:
    """Test RiskClassification dataclass."""

    def test_basic_creation(self):
        """Test basic RiskClassification creation."""
        rc = RiskClassification(
            risk_level=RiskLevel.SAFE,
            confidence=0.9,
            files=["docs/readme.md"],
            file_classifications=[],
            reasoning="All files are safe",
        )
        assert rc.risk_level == RiskLevel.SAFE
        assert rc.confidence == 0.9
        assert rc.files == ["docs/readme.md"]

    def test_to_dict(self):
        """Test conversion to dictionary."""
        fc = FileClassification(
            path="docs/readme.md",
            risk_level=RiskLevel.SAFE,
            confidence=0.95,
            pattern_matched="Documentation",
        )
        rc = RiskClassification(
            risk_level=RiskLevel.SAFE,
            confidence=0.9,
            files=["docs/readme.md"],
            file_classifications=[fc],
            reasoning="All safe",
            pr_number=123,
            commit_sha="abc123",
        )

        data = rc.to_dict()
        assert data["risk_level"] == "safe"
        assert data["confidence"] == 0.9
        assert data["files"] == ["docs/readme.md"]
        assert data["reasoning"] == "All safe"
        assert data["pr_number"] == 123
        assert data["commit_sha"] == "abc123"
        assert len(data["file_classifications"]) == 1

    def test_from_dict(self):
        """Test creation from dictionary."""
        data = {
            "risk_level": "medium_risk",
            "confidence": 0.75,
            "files": ["src/main.py", "tests/test_main.py"],
            "file_classifications": [
                {
                    "path": "src/main.py",
                    "risk_level": "medium_risk",
                    "confidence": 0.7,
                    "pattern_matched": None,
                    "semantic_flags": ["cross_module_import"],
                }
            ],
            "reasoning": "Some concerns",
            "pr_number": 456,
            "commit_sha": "def456",
        }

        rc = RiskClassification.from_dict(data)
        assert rc.risk_level == RiskLevel.MEDIUM_RISK
        assert rc.confidence == 0.75
        assert len(rc.files) == 2
        assert len(rc.file_classifications) == 1
        assert rc.file_classifications[0].path == "src/main.py"

    def test_roundtrip_serialization(self):
        """Test that to_dict/from_dict is reversible."""
        fc = FileClassification(
            path="docs/readme.md",
            risk_level=RiskLevel.SAFE,
            confidence=0.95,
        )
        original = RiskClassification(
            risk_level=RiskLevel.SAFE,
            confidence=0.9,
            files=["docs/readme.md"],
            file_classifications=[fc],
            reasoning="Safe files",
            pr_number=123,
        )

        data = original.to_dict()
        restored = RiskClassification.from_dict(data)

        assert restored.risk_level == original.risk_level
        assert restored.confidence == original.confidence
        assert restored.files == original.files
        assert restored.reasoning == original.reasoning
        assert restored.pr_number == original.pr_number
