"""Market Structure Detection Module.

This module provides tools for detecting market structure including:
- Swing pivot identification (swing highs/lows)
- BOS/CHoCH classification (Break of Structure / Change of Character)
- Structure-aware trend analysis

Usage:
    from market_analysis.structure import StructureDetector, SwingPivot, BOSCHoCH

    detector = StructureDetector()
    structure = detector.detect_structure(data)
"""

from __future__ import annotations

from market_analysis.structure.bos_choch import (
    BOSCHoCH,
    BOSCHoCHClassifier,
    BOSCHoCHType,
    StructureLevel,
)
from market_analysis.structure.structure_detector import (
    StructureDetectionResult,
    StructureDetector,
)
from market_analysis.structure.swing_pivot import (
    PivotType,
    SwingPivot,
    SwingPivotDetector,
)

__all__ = [
    "BOSCHoCH",
    "BOSCHoCHClassifier",
    "BOSCHoCHType",
    "PivotType",
    "StructureDetectionResult",
    "StructureDetector",
    "StructureLevel",
    "SwingPivot",
    "SwingPivotDetector",
]
