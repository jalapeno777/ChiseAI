"""Trading recap module for generating reports from persisted outcomes.

Generates trading recaps by querying canonical persisted data from Redis.
"""

from execution.recap.generator import TradingRecapGenerator

__all__ = ["TradingRecapGenerator"]
