"""Semantic analysis logic for path classification."""

import re
from dataclasses import dataclass

from .classification import RiskLevel
from .patterns import PathPatternMatcher


@dataclass
class SemanticFlag:
    """A semantic analysis flag for a file."""

    rule_name: str
    message: str
    severity: str = "info"  # info, warning, critical
    details: dict = None

    def __post_init__(self):
        if self.details is None:
            self.details = {}


class SemanticAnalyzer:
    """Performs semantic analysis on file changes."""

    def __init__(self, pattern_matcher: PathPatternMatcher | None = None):
        """Initialize with optional pattern matcher."""
        self.pattern_matcher = pattern_matcher or PathPatternMatcher()

    def analyze_file(self, path: str, content: str | None = None) -> list[SemanticFlag]:
        """
        Analyze a single file for semantic issues.

        Args:
            path: File path
            content: Optional file content for analysis

        Returns:
            List of semantic flags
        """
        flags = []

        # Check for test file deletions
        if self._is_test_deletion(path, content):
            flags.append(
                SemanticFlag(
                    rule_name="test_deletion",
                    message=f"Test file deletion detected: {path}",
                    severity="warning",
                    details={"path": path},
                )
            )

        # Check for critical file modifications
        if self._is_critical_modification(path):
            flags.append(
                SemanticFlag(
                    rule_name="critical_file",
                    message=f"Critical file modification: {path}",
                    severity="critical",
                    details={"path": path},
                )
            )

        # Analyze content if provided
        if content:
            content_flags = self._analyze_content(path, content)
            flags.extend(content_flags)

        return flags

    def analyze_cross_module_imports(
        self, paths: list[str], contents: dict[str, str] | None = None
    ) -> list[SemanticFlag]:
        """
        Analyze for cross-module imports across multiple files.

        Args:
            paths: List of file paths
            contents: Optional dict of path -> content

        Returns:
            List of semantic flags
        """
        flags = []
        module_imports: dict[str, set[str]] = {}

        if contents is None:
            contents = {}

        for path in paths:
            if path not in contents:
                continue

            content = contents[path]
            imports = self._extract_imports(content)

            for module in imports:
                if module not in module_imports:
                    module_imports[module] = set()
                module_imports[module].add(path)

        # Check for cross-module imports
        threshold = 2
        for rule in self.pattern_matcher.get_semantic_rules():
            if rule.name == "cross_module_import" and rule.threshold:
                threshold = rule.threshold

        # If importing from more than threshold modules, flag it
        if len(module_imports) > threshold:
            flags.append(
                SemanticFlag(
                    rule_name="cross_module_import",
                    message=f"Cross-module imports detected: importing from {len(module_imports)} modules",
                    severity="warning",
                    details={
                        "module_count": len(module_imports),
                        "modules": list(module_imports.keys()),
                        "threshold": threshold,
                    },
                )
            )

        return flags

    def analyze_batch(
        self, paths: list[str], contents: dict[str, str] | None = None
    ) -> dict[str, list[SemanticFlag]]:
        """
        Analyze multiple files.

        Args:
            paths: List of file paths
            contents: Optional dict of path -> content

        Returns:
            Dict mapping path to list of flags
        """
        results = {}

        # Analyze each file individually
        for path in paths:
            content = contents.get(path) if contents else None
            results[path] = self.analyze_file(path, content)

        # Analyze cross-module patterns
        cross_module_flags = self.analyze_cross_module_imports(paths, contents)

        # Add cross-module flags to all affected files
        for flag in cross_module_flags:
            for path in paths:
                if path not in results:
                    results[path] = []
                results[path].append(flag)

        return results

    def _is_test_deletion(self, path: str, content: str | None) -> bool:
        """Check if this is a test file deletion."""
        # If content is None/empty and path looks like a test file, it's likely deleted
        if content is None or content == "":
            return self._is_test_file(path)
        return False

    def _is_test_file(self, path: str) -> bool:
        """Check if path looks like a test file."""
        test_patterns = [
            r".*_test\.py$",
            r".*_tests?\.py$",
            r"^tests?/.*",
            r".*/test_.*\.py$",
        ]
        return any(re.match(pattern, path) for pattern in test_patterns)

    def _is_critical_modification(self, path: str) -> bool:
        """Check if path is a critical file."""
        critical_patterns = [
            r"^\.woodpecker\.yml$",
            r"^docs/bmm-workflow-status\.yaml$",
            r"^AGENTS\.md$",
            r"^\.opencode/agent/.*",
            r"^infrastructure/terraform/.*",
        ]
        return any(re.match(pattern, path) for pattern in critical_patterns)

    def _analyze_content(self, path: str, content: str) -> list[SemanticFlag]:
        """Analyze file content for semantic issues."""
        flags = []

        # Check for security-sensitive patterns
        security_flags = self._check_security_patterns(path, content)
        flags.extend(security_flags)

        # Check for architectural concerns
        arch_flags = self._check_architectural_patterns(path, content)
        flags.extend(arch_flags)

        return flags

    def _check_security_patterns(self, path: str, content: str) -> list[SemanticFlag]:
        """Check for security-sensitive code patterns."""
        flags = []

        # Check for hardcoded secrets (basic patterns)
        secret_patterns = [
            (
                r"(password|passwd|pwd)\s*=\s*['\"][^'\"]+['\"]",
                "possible hardcoded password",
            ),
            (r"api[_-]?key\s*=\s*['\"][^'\"]+['\"]", "possible hardcoded API key"),
            (r"secret\s*=\s*['\"][^'\"]+['\"]", "possible hardcoded secret"),
            (r"token\s*=\s*['\"][^'\"]+['\"]", "possible hardcoded token"),
        ]

        for pattern, message in secret_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                flags.append(
                    SemanticFlag(
                        rule_name="security_sensitive",
                        message=f"Potential {message} in {path}",
                        severity="critical",
                        details={"pattern": pattern, "path": path},
                    )
                )

        return flags

    def _check_architectural_patterns(
        self, path: str, content: str
    ) -> list[SemanticFlag]:
        """Check for architectural concerns."""
        flags = []

        # Check for circular imports
        imports = self._extract_imports(content)

        # Check for package init modifications with complex imports
        if "__init__.py" in path and len(imports) > 5:
            flags.append(
                SemanticFlag(
                    rule_name="complex_init",
                    message=f"Complex __init__.py with {len(imports)} imports: {path}",
                    severity="warning",
                    details={"import_count": len(imports), "path": path},
                )
            )

        return flags

    def _extract_imports(self, content: str) -> set[str]:
        """Extract module imports from Python content."""
        imports = set()

        # Match 'import X' and 'from X import Y'
        import_pattern = r"^\s*import\s+([\w.]+)"
        from_pattern = r"^\s*from\s+([\w.]+)\s+import"

        for match in re.finditer(import_pattern, content, re.MULTILINE):
            module = match.group(1).split(".")[0]
            imports.add(module)

        for match in re.finditer(from_pattern, content, re.MULTILINE):
            module = match.group(1).split(".")[0]
            imports.add(module)

        return imports

    def assess_risk_from_flags(
        self, flags: list[SemanticFlag]
    ) -> tuple[RiskLevel, float, str]:
        """
        Assess overall risk from semantic flags.

        Returns:
            Tuple of (risk_level, confidence, reasoning)
        """
        if not flags:
            return RiskLevel.SAFE, 0.9, "No semantic concerns detected"

        critical_count = sum(1 for f in flags if f.severity == "critical")
        warning_count = sum(1 for f in flags if f.severity == "warning")

        if critical_count > 0:
            return (
                RiskLevel.COMPLEX,
                0.85,
                f"{critical_count} critical semantic issue(s) detected",
            )

        if warning_count > 2:
            return (
                RiskLevel.COMPLEX,
                0.75,
                f"{warning_count} warning-level semantic issues detected",
            )

        if warning_count > 0:
            return (
                RiskLevel.MEDIUM_RISK,
                0.70,
                f"{warning_count} semantic warning(s) detected",
            )

        return RiskLevel.SAFE, 0.8, "Minor semantic concerns"
