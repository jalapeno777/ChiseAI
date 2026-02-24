<<<<<<< HEAD
"""Neuro-symbolic AI module for ChiseAI."""

from src.neuro_symbolic.pattern_recognition.engine import PatternRecognitionEngine
from src.neuro_symbolic.pattern_recognition.inference import PatternInference
from src.neuro_symbolic.pattern_recognition.library import PatternLibrary
from src.neuro_symbolic.pattern_recognition.trainer import PatternTrainer
from src.neuro_symbolic.reasoning import (
    HybridReasoningEngine,
    HybridReasoningResult,
    analyze_market_data,
)

__all__ = [
    "HybridReasoningEngine",
    "HybridReasoningResult",
    "PatternInference",
    "PatternLibrary",
    "PatternRecognitionEngine",
    "PatternTrainer",
    "analyze_market_data",
]
=======
"""
Neuro-Symbolic AI Module for ChiseAI.

This module integrates neural networks with symbolic reasoning for
advanced pattern recognition and decision-making in trading contexts.
"""

from src.neuro_symbolic.pattern_recognition.engine import PatternRecognitionEngine
from src.neuro_symbolic.pattern_recognition.inference import PatternInference
from src.neuro_symbolic.pattern_recognition.library import PatternLibrary
from src.neuro_symbolic.pattern_recognition.trainer import PatternTrainer

__all__ = [
    "PatternRecognitionEngine",
    "PatternInference",
    "PatternLibrary",
    "PatternTrainer",
]
>>>>>>> 3b079b8 (chore(ST-NS-035): snapshot local dirty worktree state before branch cleanup)
