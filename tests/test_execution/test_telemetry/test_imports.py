"""Tests for execution telemetry package imports."""


class TestPackageImports:
    """Test that all public API is accessible."""

    def test_import_execution_metrics(self):
        """Test ExecutionMetrics import."""
        from execution.telemetry import ExecutionMetrics

        assert ExecutionMetrics is not None

    def test_import_exporter(self):
        """Test ExecutionTelemetryExporter import."""
        from execution.telemetry import ExecutionTelemetryExporter

        assert ExecutionTelemetryExporter is not None

    def test_import_collector(self):
        """Test ExecutionCollector import."""
        from execution.telemetry import ExecutionCollector

        assert ExecutionCollector is not None

    def test_import_calculator(self):
        """Test KPICalculator import."""
        from execution.telemetry import KPICalculator

        assert KPICalculator is not None

    def test_import_order_event(self):
        """Test OrderEvent import."""
        from execution.telemetry import OrderEvent

        assert OrderEvent is not None

    def test_import_position_event(self):
        """Test PositionEvent import."""
        from execution.telemetry import PositionEvent

        assert PositionEvent is not None

    def test_import_trade(self):
        """Test Trade import."""
        from execution.telemetry import Trade

        assert Trade is not None

    def test_import_enums(self):
        """Test enum imports."""
        from execution.telemetry import OrderSide, OrderStatus, PositionSide

        assert OrderSide is not None
        assert OrderStatus is not None
        assert PositionSide is not None

    def test_all_exports(self):
        """Test __all__ exports."""
        from execution.telemetry import __all__

        expected = [
            "ExecutionMetrics",
            "ExecutionTelemetryExporter",
            "ExecutionCollector",
            "KPICalculator",
            "OrderEvent",
            "OrderSide",
            "OrderStatus",
            "PositionEvent",
            "PositionSide",
            "Trade",
        ]

        for item in expected:
            assert item in __all__
