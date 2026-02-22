"""Core analysis engine."""

import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .cache import PathAnalysisCache
from .classification import FileClassification, RiskClassification, RiskLevel
from .patterns import PathPatternMatcher, PatternType
from .semantic import SemanticAnalyzer


class PathAnalyzer:
    """Main path analysis engine."""

    def __init__(
        self,
        config_path: Optional[str] = None,
        cache: Optional[PathAnalysisCache] = None,
        pattern_matcher: Optional[PathPatternMatcher] = None,
    ):
        """
        Initialize the path analyzer.

        Args:
            config_path: Optional path to pattern config YAML
            cache: Optional cache instance
            pattern_matcher: Optional pattern matcher instance
        """
        self.pattern_matcher = pattern_matcher or PathPatternMatcher(config_path)
        self.semantic_analyzer = SemanticAnalyzer(self.pattern_matcher)
        self.cache = cache or PathAnalysisCache()

    def analyze(
        self,
        files: List[str],
        pr_number: Optional[int] = None,
        commit_sha: Optional[str] = None,
        file_contents: Optional[Dict[str, str]] = None,
        use_cache: bool = True,
    ) -> RiskClassification:
        """
        Analyze a list of file paths and classify the PR risk.

        Args:
            files: List of file paths to analyze
            pr_number: Optional PR number for caching
            commit_sha: Optional commit SHA for caching
            file_contents: Optional dict of path -> content for semantic analysis
            use_cache: Whether to use caching

        Returns:
            RiskClassification result
        """
        start_time = time.time()

        # Check cache first
        if use_cache and pr_number is not None:
            cached = self.cache.get(pr_number, commit_sha, files)
            if cached:
                cached["_from_cache"] = True
                return RiskClassification.from_dict(cached)

        # Analyze each file
        file_classifications = self._analyze_files(files, file_contents)

        # Determine overall risk level
        risk_level = self._determine_overall_risk(file_classifications)

        # Calculate confidence
        confidence = self._calculate_confidence(file_classifications)

        # Generate reasoning
        reasoning = self._generate_reasoning(file_classifications, risk_level)

        # Build result
        duration_ms = (time.time() - start_time) * 1000
        result = RiskClassification(
            risk_level=risk_level,
            confidence=confidence,
            files=files,
            file_classifications=file_classifications,
            reasoning=reasoning,
            pr_number=pr_number,
            commit_sha=commit_sha,
            timestamp=datetime.now(timezone.utc).isoformat(),
            analysis_duration_ms=duration_ms,
        )

        # Cache the result
        if use_cache and pr_number is not None:
            self.cache.set(pr_number, commit_sha, files, result.to_dict())

        return result

    def _analyze_files(
        self, files: List[str], file_contents: Optional[Dict[str, str]] = None
    ) -> List[FileClassification]:
        """Analyze each file and create classifications."""
        classifications = []

        # Get semantic analysis for all files
        semantic_results = {}
        if file_contents:
            semantic_results = self.semantic_analyzer.analyze_batch(
                files, file_contents
            )

        for file_path in files:
            classification = self._classify_single_file(
                file_path, semantic_results.get(file_path, [])
            )
            classifications.append(classification)

        return classifications

    def _classify_single_file(
        self, path: str, semantic_flags: List[Any]
    ) -> FileClassification:
        """Classify a single file."""
        # Check pattern matching
        pattern_type, matched_pattern = self.pattern_matcher.classify_path(path)

        # Determine base risk from patterns
        if pattern_type == PatternType.COMPLEX:
            return FileClassification(
                path=path,
                risk_level=RiskLevel.COMPLEX,
                confidence=0.9,
                pattern_matched=(
                    matched_pattern.description if matched_pattern else None
                ),
                semantic_flags=[f.rule_name for f in semantic_flags],
            )

        if pattern_type == PatternType.SAFE:
            # Even safe patterns can be elevated by semantic flags
            if semantic_flags:
                risk, conf, _ = self.semantic_analyzer.assess_risk_from_flags(
                    semantic_flags
                )
                return FileClassification(
                    path=path,
                    risk_level=risk,
                    confidence=conf * 0.9,
                    pattern_matched=(
                        matched_pattern.description if matched_pattern else None
                    ),
                    semantic_flags=[f.rule_name for f in semantic_flags],
                )

            return FileClassification(
                path=path,
                risk_level=RiskLevel.SAFE,
                confidence=0.95,
                pattern_matched=(
                    matched_pattern.description if matched_pattern else None
                ),
                semantic_flags=[],
            )

        # No pattern match - default to medium risk with semantic analysis
        if semantic_flags:
            risk, conf, _ = self.semantic_analyzer.assess_risk_from_flags(
                semantic_flags
            )
            return FileClassification(
                path=path,
                risk_level=risk,
                confidence=conf,
                semantic_flags=[f.rule_name for f in semantic_flags],
            )

        # Unknown path with no semantic flags - medium risk as default
        return FileClassification(
            path=path,
            risk_level=RiskLevel.MEDIUM_RISK,
            confidence=0.6,
            semantic_flags=[],
        )

    def _determine_overall_risk(
        self, file_classifications: List[FileClassification]
    ) -> RiskLevel:
        """Determine the overall risk level from all file classifications."""
        if not file_classifications:
            return RiskLevel.SAFE

        # Use highest risk level across all files
        risk_levels = [fc.risk_level for fc in file_classifications]
        return RiskLevel.from_highest(risk_levels)

    def _calculate_confidence(
        self, file_classifications: List[FileClassification]
    ) -> float:
        """Calculate overall confidence score."""
        if not file_classifications:
            return 0.9

        # Average confidence, weighted by risk level
        total_weight = 0
        weighted_sum = 0

        for fc in file_classifications:
            weight = fc.risk_level.priority + 1
            weighted_sum += fc.confidence * weight
            total_weight += weight

        return round(weighted_sum / total_weight, 2) if total_weight > 0 else 0.5

    def _generate_reasoning(
        self, file_classifications: List[FileClassification], overall_risk: RiskLevel
    ) -> str:
        """Generate human-readable reasoning for the classification."""
        if not file_classifications:
            return "No files to analyze"

        # Count files by risk level
        risk_counts = {}
        for fc in file_classifications:
            risk_counts[fc.risk_level] = risk_counts.get(fc.risk_level, 0) + 1

        # Build reasoning
        parts = [f"Overall risk: {overall_risk.value}"]

        if RiskLevel.COMPLEX in risk_counts:
            parts.append(f"{risk_counts[RiskLevel.COMPLEX]} complex file(s)")

        if RiskLevel.MEDIUM_RISK in risk_counts:
            parts.append(f"{risk_counts[RiskLevel.MEDIUM_RISK]} medium-risk file(s)")

        if RiskLevel.SAFE in risk_counts:
            parts.append(f"{risk_counts[RiskLevel.SAFE]} safe file(s)")

        # Add notes about specific concerns
        complex_files = [
            fc for fc in file_classifications if fc.risk_level == RiskLevel.COMPLEX
        ]
        if complex_files:
            patterns = set()
            for fc in complex_files:
                if fc.pattern_matched:
                    patterns.add(fc.pattern_matched)
                if fc.semantic_flags:
                    patterns.update(fc.semantic_flags)

            if patterns:
                parts.append(f"Concerns: {', '.join(sorted(patterns)[:3])}")

        return "; ".join(parts)


# Convenience function for API
def analyze_paths(
    files: List[str],
    pr_number: Optional[int] = None,
    commit_sha: Optional[str] = None,
    file_contents: Optional[Dict[str, str]] = None,
    config_path: Optional[str] = None,
    use_cache: bool = True,
) -> RiskClassification:
    """
    Analyze file paths and return risk classification.

    This is the main API entry point for path analysis.

    Args:
        files: List of file paths to analyze
        pr_number: Optional PR number for caching
        commit_sha: Optional commit SHA for caching
        file_contents: Optional dict of path -> content for semantic analysis
        config_path: Optional path to pattern config YAML
        use_cache: Whether to use caching

    Returns:
        RiskClassification result
    """
    analyzer = PathAnalyzer(config_path=config_path)
    return analyzer.analyze(
        files=files,
        pr_number=pr_number,
        commit_sha=commit_sha,
        file_contents=file_contents,
        use_cache=use_cache,
    )
