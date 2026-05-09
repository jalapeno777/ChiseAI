"""Strategy executors - concrete implementations satisfying StrategyProtocol.

ST-MVP-010: ICT Confluence Strategy implementation.
"""

from __future__ import annotations

from .ict_executor import ICTConfluenceExecutor

__all__ = [
    "ICTConfluenceExecutor",
]
