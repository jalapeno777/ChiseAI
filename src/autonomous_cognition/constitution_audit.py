"""Automated constitution audit and violation escalation."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any

# Ensure script-mode imports can resolve both `governance.*` and `src.*`.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _PROJECT_ROOT / "src"
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

@dataclass
class ConstitutionAuditResult:
    """Result of constitution audit pass."""

    violations: list[Any]

    @property
    def critical_count(self) -> int:
        return len(
            [
                v
                for v in self.violations
                if v.severity.value in {"P0", "P1"}
            ]
        )


class ConstitutionAuditEngine:
    """Runs automated constitution compliance checks."""

    def __init__(self, detector: Any | None = None):
        if detector is None:
            module = import_module("governance.constitution.violation_detector")
            detector = module.ViolationDetector()
        self._detector = detector
        self._detector.register_default_rules()

    def run(
        self, actions: list[str], context: dict[str, Any] | None = None
    ) -> ConstitutionAuditResult:
        """Run audit over action log stream."""
        found: list[Any] = []
        for action in actions:
            found.extend(self._detector.detect(action=action, context=context or {}))
        return ConstitutionAuditResult(violations=found)
