"""Retry policy models for ST-NS-039."""

from dataclasses import dataclass
from enum import Enum
from typing import Optional
import random


class BackoffStrategy(Enum):
    EXPONENTIAL = "exponential"
    LINEAR = "linear"
    FIXED = "fixed"


class JitterType(Enum):
    FULL = "full"
    EQUAL = "equal"
    NONE = "none"


@dataclass
class RetryPolicy:
    max_attempts: int = 3
    base_delay_ms: int = 100
    max_delay_ms: int = 30000
    backoff_strategy: BackoffStrategy = BackoffStrategy.EXPONENTIAL
    jitter_type: JitterType = JitterType.FULL
    jitter_factor: float = 0.1
    budget_limit_per_minute: int = 100
    circuit_breaker_name: Optional[str] = None

    def calculate_delay(self, attempt: int) -> float:
        """Calculate delay for a retry attempt."""
        if self.backoff_strategy == BackoffStrategy.EXPONENTIAL:
            delay = min(self.base_delay_ms * (2**attempt), self.max_delay_ms)
        elif self.backoff_strategy == BackoffStrategy.LINEAR:
            delay = min(self.base_delay_ms * (attempt + 1), self.max_delay_ms)
        else:  # FIXED
            delay = self.base_delay_ms

        # Apply jitter
        if self.jitter_type == JitterType.FULL:
            delay = delay * (
                1 + random.uniform(-self.jitter_factor, self.jitter_factor)
            )
        elif self.jitter_type == JitterType.EQUAL:
            delay = (delay / 2) + (delay / 2) * random.uniform(0, self.jitter_factor)

        return max(0, delay) / 1000.0  # Convert to seconds
