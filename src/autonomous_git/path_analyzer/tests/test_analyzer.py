"""Tests for analyzer module."""

import pytest
from autonomous_git.path_analyzer.analyzer import (
    PathAnalyzer,
    analyze_paths,
)
from autonomous_git.path_analyzer.classification import RiskLevel


class TestPathAnalyzer:
    """Test PathAnalyzer class."""

    def test_initialization(self):
        """Test analyzer initialization."""
        analyzer = PathAnalyzer()
        assert analyzer.pattern_matcher is not None
        assert analyzer.semantic_analyzer is not None
        assert analyzer.cache is not None

    def test_analyze_safe_files_only(self):
        """Test analyzing only safe files."""
        analyzer = PathAnalyzer()
        files = ["docs/readme.md", "LICENSE", "CHANGELOG.md"]

        result = analyzer.analyze(files, pr_number=123)

        assert result.risk_level == RiskLevel.SAFE
        assert result.pr_number == 123
        assert len(result.files) == 3
        assert result.confidence > 0.8
        assert "safe" in result.reasoning.lower()

    def test_analyze_complex_files(self):
        """Test analyzing complex files."""
        analyzer = PathAnalyzer()
        files = [".woodpecker.yml", "docs/readme.md"]

        result = analyzer.analyze(files, pr_number=123)

        # Should be COMPLEX due to .woodpecker.yml
        assert result.risk_level == RiskLevel.COMPLEX

    def test_analyze_mixed_files(self):
        """Test analyzing mixed safe and complex files."""
        analyzer = PathAnalyzer()
        files = [
            "docs/readme.md",  # Safe
            ".woodpecker.yml",  # Complex
            "tests/test_foo.py",  # Safe
        ]

        result = analyzer.analyze(files, pr_number=123)

        # Should be COMPLEX due to .woodpecker.yml
        assert result.risk_level == RiskLevel.COMPLEX

    def test_analyze_unknown_files(self):
        """Test analyzing files with no pattern match."""
        analyzer = PathAnalyzer()
        files = ["unknown/file.xyz", "random/path.dat"]

        result = analyzer.analyze(files, pr_number=123)

        # Unknown files default to MEDIUM_RISK
        assert result.risk_level == RiskLevel.MEDIUM_RISK

    def test_analyze_with_cache(self):
        """Test that caching works."""
        analyzer = PathAnalyzer()
        files = ["docs/readme.md"]

        # First analysis
        result1 = analyzer.analyze(files, pr_number=123, commit_sha="abc123")

        # Second analysis should hit cache
        result2 = analyzer.analyze(files, pr_number=123, commit_sha="abc123")

        assert result1.risk_level == result2.risk_level
        assert result1.confidence == result2.confidence

    def test_analyze_without_cache(self):
        """Test analysis without caching."""
        analyzer = PathAnalyzer()
        files = ["docs/readme.md"]

        result = analyzer.analyze(files, pr_number=123, use_cache=False)

        assert result.risk_level == RiskLevel.SAFE

    def test_analyze_empty_files(self):
        """Test analyzing empty file list."""
        analyzer = PathAnalyzer()

        result = analyzer.analyze([], pr_number=123)

        assert result.risk_level == RiskLevel.SAFE
        assert "No files" in result.reasoning or "files" in result.reasoning.lower()

    def test_analyze_with_content(self):
        """Test analysis with file contents."""
        analyzer = PathAnalyzer()
        files = ["config.py"]
        contents = {"config.py": 'password = "secret123"'}

        result = analyzer.analyze(files, pr_number=123, file_contents=contents)

        # Should detect security issue
        assert result.risk_level == RiskLevel.COMPLEX

    def test_file_classifications_populated(self):
        """Test that file classifications are populated."""
        analyzer = PathAnalyzer()
        files = ["docs/readme.md", "tests/test.py"]

        result = analyzer.analyze(files, pr_number=123)

        assert len(result.file_classifications) == 2
        for fc in result.file_classifications:
            assert fc.risk_level == RiskLevel.SAFE

    def test_timestamp_populated(self):
        """Test that timestamp is populated."""
        analyzer = PathAnalyzer()
        files = ["docs/readme.md"]

        result = analyzer.analyze(files, pr_number=123)

        assert result.timestamp is not None
        assert "T" in result.timestamp  # ISO format

    def test_duration_populated(self):
        """Test that analysis duration is populated."""
        analyzer = PathAnalyzer()
        files = ["docs/readme.md"]

        result = analyzer.analyze(files, pr_number=123)

        assert result.analysis_duration_ms is not None
        assert result.analysis_duration_ms >= 0

    def test_reasoning_generated(self):
        """Test that reasoning is generated."""
        analyzer = PathAnalyzer()
        files = ["docs/readme.md", ".woodpecker.yml"]

        result = analyzer.analyze(files, pr_number=123)

        assert len(result.reasoning) > 0
        assert "complex" in result.reasoning.lower()

    def test_to_dict_serialization(self):
        """Test that result can be serialized."""
        analyzer = PathAnalyzer()
        files = ["docs/readme.md"]

        result = analyzer.analyze(files, pr_number=123)
        data = result.to_dict()

        assert data["risk_level"] == "safe"
        assert data["pr_number"] == 123
        assert "file_classifications" in data


class TestAnalyzePathsFunction:
    """Test analyze_paths convenience function."""

    def test_analyze_paths_function(self):
        """Test the convenience function."""
        files = ["docs/readme.md", "tests/test.py"]

        result = analyze_paths(files, pr_number=456)

        assert result.risk_level == RiskLevel.SAFE
        assert result.pr_number == 456

    def test_analyze_paths_with_config(self):
        """Test analyze_paths with custom config."""
        # This will use defaults since config doesn't exist
        files = ["docs/readme.md"]

        result = analyze_paths(files, config_path="/nonexistent/config.yaml")

        assert result.risk_level == RiskLevel.SAFE

    def test_analyze_paths_performance(self):
        """Test that analysis is reasonably fast."""
        import time

        # Generate 100 files
        files = [f"src/module/file_{i}.py" for i in range(100)]

        start = time.time()
        result = analyze_paths(files, pr_number=999)
        duration = time.time() - start

        # Should complete in less than 2 seconds
        assert duration < 2.0
        assert result.risk_level == RiskLevel.MEDIUM_RISK  # Unknown paths


class TestRiskDetermination:
    """Test risk determination logic."""

    def test_highest_risk_wins(self):
        """Test that highest risk level is used."""
        analyzer = PathAnalyzer()
        files = [
            "docs/readme.md",  # SAFE
            ".woodpecker.yml",  # COMPLEX
        ]

        result = analyzer.analyze(files)
        assert result.risk_level == RiskLevel.COMPLEX

    def test_complex_outranks_medium(self):
        """Test COMPLEX outranks MEDIUM_RISK."""
        analyzer = PathAnalyzer()
        files = [
            "unknown/file.xyz",  # MEDIUM_RISK (unknown)
            ".woodpecker.yml",  # COMPLEX
        ]

        result = analyzer.analyze(files)
        assert result.risk_level == RiskLevel.COMPLEX

    def test_medium_outranks_safe(self):
        """Test MEDIUM_RISK outranks SAFE."""
        analyzer = PathAnalyzer()
        files = [
            "docs/readme.md",  # SAFE
            "unknown/file.xyz",  # MEDIUM_RISK
        ]

        result = analyzer.analyze(files)
        assert result.risk_level == RiskLevel.MEDIUM_RISK


class TestConfidenceCalculation:
    """Test confidence calculation."""

    def test_confidence_range(self):
        """Test that confidence is in valid range."""
        analyzer = PathAnalyzer()

        # Various file combinations
        test_cases = [
            ["docs/readme.md"],
            [".woodpecker.yml"],
            ["unknown/file.xyz"],
            ["docs/readme.md", ".woodpecker.yml"],
        ]

        for files in test_cases:
            result = analyzer.analyze(files)
            assert 0.0 <= result.confidence <= 1.0
