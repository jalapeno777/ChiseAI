"""Tests for storage interface."""

import pytest

from market_analysis.signal_storage.interface import SignalStorageInterface


class TestSignalStorageInterface:
    """Tests for SignalStorageInterface abstract class."""

    def test_is_abstract(self):
        """Test that SignalStorageInterface is abstract."""
        with pytest.raises(TypeError):
            SignalStorageInterface()

    def test_required_methods(self):
        """Test that all required methods are abstract."""
        abstract_methods = SignalStorageInterface.__abstractmethods__

        assert "store_signal" in abstract_methods
        assert "store_outcome" in abstract_methods
        assert "query_signals" in abstract_methods
        assert "get_signal_by_id" in abstract_methods
        assert "get_outcome_by_signal_id" in abstract_methods
        assert "query_signals_with_outcomes" in abstract_methods
        assert "calculate_prediction_accuracy" in abstract_methods
        assert "get_unresolved_signals" in abstract_methods
        assert "close" in abstract_methods
