"""
PR Pipeline Module.

This module handles autonomous PR processing for the ChiseAI swarm.
Part of EP-AUTO-GIT-001: AI Swarm Autonomous PR Pipeline.

Paths:
- Standard Path: GitReviewBot reviews (not auto-merge), <12 min target
- Fast Path: Auto-merge for trivial changes (future)
- Complex Path: Human escalation required
"""

from .standard_path import StandardPathHandler

__all__ = ["StandardPathHandler"]
