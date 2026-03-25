"""ML Analyzer Module for ChiseAI.

This module provides ML analysis capabilities for signal performance
and model evaluation.

Components:
- ict_analyzer: ICT signal performance analysis (CVD, FVG, Order Block)

Usage:
    from ml.analyzer import ICTAnalyzer, ICTAnalysisReport

    analyzer = ICTAnalyzer()
    report = await analyzer.analyze_ict_signals(matches)
"""

from __future__ import annotations

# ICT Analyzer components (ST-ICT-017)
from ml.analyzer.ict_analyzer import (
    ICTAnalysisConfig,
    ICTAnalysisReport,
    ICTAnalyzer,
    ICTDriftIndicator,
    ICTDriftSeverity,
    ICTSignalPerformance,
)

__all__ = [
    # ICT Analyzer (ST-ICT-017)
    "ICTAnalyzer",
    "ICTAnalysisConfig",
    "ICTAnalysisReport",
    "ICTSignalPerformance",
    "ICTDriftIndicator",
    "ICTDriftSeverity",
]
