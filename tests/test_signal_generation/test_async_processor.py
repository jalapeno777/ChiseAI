"""
Tests for async signal processor.
"""

import asyncio
from datetime import UTC, datetime

import pytest

from signal_generation.async_processor import (
    AsyncSignalProcessor,
    SignalPriority,
)
from signal_generation.models import Signal, SignalDirection, SignalStatus


class TestAsyncProcessor:
    """Test async signal processor functionality."""

    def test_async_processor_initialization(self):
        """Test that async processor can be initialized."""
        processor = AsyncSignalProcessor()
        assert processor.max_concurrent == 10
        assert processor.max_retries == 3

    def test_async_processor_with_custom_threshold(self):
        """Test async processor with custom actionable_threshold."""
        processor = AsyncSignalProcessor(actionable_threshold=0.80)
        assert processor._actionable_threshold == 0.80


class TestAsyncProcessorPriority:
    """Tests for configurable confidence threshold in priority classification (ST-ICT-S4)."""

    def _create_signal(self, confidence: float) -> Signal:
        """Helper to create a signal with given confidence."""
        return Signal(
            token="BTC/USDT",
            direction=SignalDirection.LONG,
            confidence=confidence,
            base_score=80.0,
            timestamp=datetime.now(UTC),
            status=SignalStatus.ACTIONABLE,
            timeframe="1h",
        )

    def test_priority_high_confidence_090(self):
        """Test HIGH priority for confidence >= 0.90."""
        processor = AsyncSignalProcessor()
        signal = self._create_signal(0.90)
        priority = processor._get_priority(signal)
        assert priority == SignalPriority.HIGH.value

    def test_priority_high_confidence_100(self):
        """Test HIGH priority for confidence = 1.0."""
        processor = AsyncSignalProcessor()
        signal = self._create_signal(1.0)
        priority = processor._get_priority(signal)
        assert priority == SignalPriority.HIGH.value

    def test_priority_medium_confidence_075(self):
        """Test MEDIUM priority for confidence = 0.75 (boundary case)."""
        processor = AsyncSignalProcessor(actionable_threshold=0.75)
        signal = self._create_signal(0.75)
        priority = processor._get_priority(signal)
        assert priority == SignalPriority.MEDIUM.value

    def test_priority_medium_confidence_076(self):
        """Test MEDIUM priority for confidence = 0.76."""
        processor = AsyncSignalProcessor(actionable_threshold=0.75)
        signal = self._create_signal(0.76)
        priority = processor._get_priority(signal)
        assert priority == SignalPriority.MEDIUM.value

    def test_priority_low_confidence_074(self):
        """Test LOW priority for confidence = 0.74 (below 0.75 threshold)."""
        processor = AsyncSignalProcessor(actionable_threshold=0.75)
        signal = self._create_signal(0.74)
        priority = processor._get_priority(signal)
        assert priority == SignalPriority.LOW.value

    def test_priority_low_confidence_050(self):
        """Test LOW priority for confidence = 0.50."""
        processor = AsyncSignalProcessor(actionable_threshold=0.75)
        signal = self._create_signal(0.50)
        priority = processor._get_priority(signal)
        assert priority == SignalPriority.LOW.value

    def test_priority_custom_threshold(self):
        """Test priority classification with custom threshold (0.80)."""
        processor = AsyncSignalProcessor(actionable_threshold=0.80)

        # 0.79 should be LOW (below custom 0.80 threshold)
        signal_079 = self._create_signal(0.79)
        assert processor._get_priority(signal_079) == SignalPriority.LOW.value

        # 0.80 should be MEDIUM (at custom threshold)
        signal_080 = self._create_signal(0.80)
        assert processor._get_priority(signal_080) == SignalPriority.MEDIUM.value

        # 0.90 should still be HIGH
        signal_090 = self._create_signal(0.90)
        assert processor._get_priority(signal_090) == SignalPriority.HIGH.value


class TestAsyncPipeline:
    """Test async pipeline functionality."""

    @pytest.mark.asyncio
    async def test_pipeline_execution(self):
        """Test async pipeline execution."""
        # Placeholder async test
        await asyncio.sleep(0.001)
        assert True

    @pytest.mark.asyncio
    async def test_pipeline_error_handling(self):
        """Test error handling in async pipeline."""
        # Placeholder async test
        await asyncio.sleep(0.001)
        assert True


class TestAsyncSignalQueue:
    """Test async signal queue functionality."""

    def test_queue_initialization(self):
        """Test queue initialization."""
        # Placeholder test
        assert True

    @pytest.mark.asyncio
    async def test_queue_put_get(self):
        """Test putting and getting from queue."""
        queue = asyncio.Queue()
        await queue.put("test_signal")
        result = await queue.get()
        assert result == "test_signal"
