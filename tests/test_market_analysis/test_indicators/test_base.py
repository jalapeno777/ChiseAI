"""Tests for base indicator interface."""

from datetime import UTC, datetime

import pytest

from data_ingestion.ohlcv_fetcher import OHLCVData
from market_analysis.indicators.base import BaseIndicator, Signal, SignalDirection


class MockIndicator(BaseIndicator):
    """Mock indicator for testing."""

    @property
    def description(self) -> str:
        return "Mock indicator for testing"

    @property
    def parameters(self) -> dict:
        return {"param1": 1, "param2": 2}

    def compute(self, data):
        return {"result": len(data)}

    def validate(self, data):
        return len(data) > 0

    def get_metadata(self):
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }


class TestSignal:
    """Test cases for Signal dataclass."""

    def test_creation(self):
        """Test creating a valid signal."""
        signal = Signal(
            direction=SignalDirection.BUY,
            confidence=0.85,
            timestamp=datetime.now(UTC),
            metadata={"test": "data"},
        )
        assert signal.direction == SignalDirection.BUY
        assert signal.confidence == 0.85

    def test_invalid_confidence_high(self):
        """Test signal with confidence > 1."""
        with pytest.raises(ValueError):
            Signal(
                direction=SignalDirection.SELL,
                confidence=1.5,
                timestamp=datetime.now(UTC),
                metadata={},
            )

    def test_invalid_confidence_low(self):
        """Test signal with confidence < 0."""
        with pytest.raises(ValueError):
            Signal(
                direction=SignalDirection.HOLD,
                confidence=-0.1,
                timestamp=datetime.now(UTC),
                metadata={},
            )


class TestBaseIndicator:
    """Test cases for BaseIndicator abstract class."""

    def test_name_default(self):
        """Test default name is class name."""
        indicator = MockIndicator()
        assert indicator.name == "MockIndicator"

    def test_name_custom(self):
        """Test custom name."""
        indicator = MockIndicator(name="CustomName")
        assert indicator.name == "CustomName"

    def test_compute(self, sample_ohlcv_data):
        """Test compute method."""
        indicator = MockIndicator()
        result = indicator.compute(sample_ohlcv_data)
        assert result["result"] == len(sample_ohlcv_data)

    def test_validate(self, sample_ohlcv_data):
        """Test validate method."""
        indicator = MockIndicator()
        assert indicator.validate(sample_ohlcv_data) is True
        assert indicator.validate([]) is False

    def test_get_metadata(self):
        """Test metadata retrieval."""
        indicator = MockIndicator()
        metadata = indicator.get_metadata()
        assert metadata["name"] == "MockIndicator"
        assert "description" in metadata
        assert "parameters" in metadata

    def test_to_signal_default(self):
        """Test default signal conversion."""
        indicator = MockIndicator()
        signal = indicator.to_signal({})
        assert signal.direction == SignalDirection.HOLD
        assert signal.confidence == 0.5


@pytest.fixture
def sample_ohlcv_data():
    """Create sample OHLCV data for testing."""
    return [
        OHLCVData(
            timestamp=1000 + i * 60000,
            open_price=100.0 + i,
            high_price=101.0 + i,
            low_price=99.0 + i,
            close_price=100.5 + i,
            volume=1000.0 + i * 100,
        )
        for i in range(20)
    ]
