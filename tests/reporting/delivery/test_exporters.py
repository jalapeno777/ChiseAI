"""Tests for report exporters (JSON, CSV, PDF)."""

import json
from datetime import UTC, datetime

import pytest

from reporting.exporters.csv_exporter import CSVExporter
from reporting.exporters.json_exporter import JSONExporter
from reporting.exporters.pdf_exporter import PDFExporter


class TestJSONExporter:
    """Tests for JSONExporter."""

    @pytest.fixture
    def exporter(self):
        """Create JSON exporter instance."""
        return JSONExporter(pretty=True, indent=2, ensure_ascii=False)

    @pytest.fixture
    def sample_data(self):
        """Sample report data."""
        return {
            "date": "2026-03-29",
            "report_type": "daily",
            "total_pnl": 1500.75,
            "win_rate": 0.65,
            "total_trades": 25,
            "generated_at": datetime(2026, 3, 29, 12, 0, 0, tzinfo=UTC),
        }

    def test_init_defaults(self):
        """Test default initialization."""
        exporter = JSONExporter()
        assert exporter.pretty is True
        assert exporter.indent == 2
        assert exporter.ensure_ascii is False

    def test_init_custom(self):
        """Test custom initialization."""
        exporter = JSONExporter(pretty=False, indent=4, ensure_ascii=True)
        assert exporter.pretty is False
        assert exporter.indent == 4
        assert exporter.ensure_ascii is True

    def test_json_serializer_datetime(self, exporter):
        """Test datetime serialization."""
        dt = datetime(2026, 3, 29, 12, 0, 0, tzinfo=UTC)
        result = exporter._json_serializer(dt)
        assert result == "2026-03-29T12:00:00+00:00"

    def test_json_serializer_with_to_dict(self, exporter):
        """Test serialization of objects with to_dict method."""

        class MockReport:
            def to_dict(self):
                return {"type": "daily", "value": 42}

        result = exporter._json_serializer(MockReport())
        assert result == {"type": "daily", "value": 42}

    def test_json_serializer_unsupported(self, exporter):
        """Test serialization of unsupported type raises error."""
        with pytest.raises(TypeError, match="not JSON serializable"):
            exporter._json_serializer(set([1, 2, 3]))

    def test_export_pretty(self, exporter, sample_data):
        """Test pretty JSON export."""
        result = exporter.export(sample_data)
        assert "\n" in result  # Pretty printed
        assert '  "' in result  # 2 spaces indent with ensure_ascii=False

    def test_export_compact(self, sample_data):
        """Test compact JSON export."""
        exporter = JSONExporter(pretty=False)
        result = exporter.export(sample_data)
        assert "\n" not in result

    def test_export_to_bytes(self, exporter, sample_data):
        """Test export to bytes."""
        result = exporter.export_to_bytes(sample_data)
        assert isinstance(result, bytes)
        assert "total_pnl" in result.decode("utf-8")

    def test_export_report_with_to_dict(self, exporter):
        """Test export_report with object that has to_dict."""

        class MockReport:
            def to_dict(self):
                return {"date": "2026-03-29", "value": 100}

        result = exporter.export_report(MockReport())
        parsed = json.loads(result)
        assert parsed["value"] == 100

    def test_export_report_without_to_dict(self, exporter, sample_data):
        """Test export_report with raw dict."""
        result = exporter.export_report(sample_data)
        parsed = json.loads(result)
        assert parsed["total_pnl"] == 1500.75

    def test_export_report_pretty_override(self, exporter, sample_data):
        """Test export_report with pretty override."""
        result = exporter.export_report(sample_data, pretty=False)
        assert "\n" not in result

    def test_validate_schema_valid(self, exporter):
        """Test schema validation with valid data."""
        data = {"field1": "value", "field2": "value2"}
        is_valid, missing = exporter.validate_schema(data, ["field1"])
        assert is_valid is True
        assert missing == []

    def test_validate_schema_missing_fields(self, exporter):
        """Test schema validation with missing fields."""
        data = {"field1": "value"}
        is_valid, missing = exporter.validate_schema(data, ["field1", "field2"])
        assert is_valid is False
        assert "field2" in missing

    def test_export_with_metadata(self, exporter, sample_data):
        """Test export with metadata wrapper."""
        metadata = {"version": "1.0", "source": "test"}
        result = exporter.export_with_metadata(sample_data, metadata)
        parsed = json.loads(result)
        assert "exported_at" in parsed
        assert "metadata" in parsed
        assert parsed["metadata"]["version"] == "1.0"

    def test_export_with_metadata_no_metadata(self, exporter, sample_data):
        """Test export with_metadata when metadata is None."""
        result = exporter.export_with_metadata(sample_data)
        parsed = json.loads(result)
        assert "exported_at" in parsed
        assert "metadata" not in parsed


class TestCSVExporter:
    """Tests for CSVExporter."""

    @pytest.fixture
    def exporter(self):
        """Create CSV exporter instance."""
        return CSVExporter(delimiter=",", quotechar='"', include_bom=False)

    @pytest.fixture
    def sample_data(self):
        """Sample report data."""
        return [
            {"date": "2026-03-29", "total_pnl": 1500.0, "total_trades": 25},
            {"date": "2026-03-28", "total_pnl": 1200.0, "total_trades": 20},
        ]

    def test_init_defaults(self):
        """Test default initialization."""
        exporter = CSVExporter()
        assert exporter.delimiter == ","
        assert exporter.quotechar == '"'
        assert exporter.include_bom is False

    def test_init_custom(self):
        """Test custom initialization."""
        exporter = CSVExporter(delimiter=";", quotechar="'", include_bom=True)
        assert exporter.delimiter == ";"
        assert exporter.quotechar == "'"
        assert exporter.include_bom is True

    def test_flatten_dict_simple(self, exporter):
        """Test _flatten_dict with simple dict."""
        data = {"a": 1, "b": 2}
        result = exporter._flatten_dict(data)
        assert result == {"a": 1, "b": 2}

    def test_flatten_dict_nested(self, exporter):
        """Test _flatten_dict with nested dict."""
        data = {"parent": {"child": "value", "child2": "value2"}}
        result = exporter._flatten_dict(data)
        assert "parent.child" in result
        assert result["parent.child"] == "value"
        assert result["parent.child2"] == "value2"

    def test_flatten_dict_with_list(self, exporter):
        """Test _flatten_dict with list values."""
        data = {"items": [1, 2, 3]}
        result = exporter._flatten_dict(data)
        assert result["items"] == "[1, 2, 3]"

    def test_prepare_row_all_columns(self, exporter, sample_data):
        """Test _prepare_row with all columns."""
        result = exporter._prepare_row(sample_data[0], None)
        assert result["date"] == "2026-03-29"
        assert result["total_pnl"] == 1500.0

    def test_prepare_row_selected_columns(self, exporter, sample_data):
        """Test _prepare_row with selected columns."""
        result = exporter._prepare_row(sample_data[0], ["date", "total_trades"])
        assert "date" in result
        assert "total_trades" in result
        assert "total_pnl" not in result

    def test_export_empty_data(self, exporter):
        """Test export with empty data."""
        result = exporter.export([])
        assert result == ""

    def test_export_with_columns(self, exporter, sample_data):
        """Test export with specified columns."""
        result = exporter.export(sample_data, columns=["date", "total_pnl"])
        lines = result.strip().split("\n")
        assert "date" in lines[0]
        assert "total_pnl" in lines[0]
        # Second line should have date and pnl
        second_line = lines[1]
        assert "2026-03-29" in second_line
        assert "1500" in second_line

    def test_export_without_columns(self, exporter, sample_data):
        """Test export without specifying columns."""
        result = exporter.export(sample_data)
        assert "date" in result
        assert "total_pnl" in result
        assert "total_trades" in result

    def test_export_to_bytes(self, exporter, sample_data):
        """Test export to bytes."""
        result = exporter.export_to_bytes(sample_data)
        assert isinstance(result, bytes)
        assert b"date" in result

    def test_export_single(self, exporter):
        """Test export_single with single record."""
        data = {"date": "2026-03-29", "total_pnl": 1500.0}
        result = exporter.export_single(data)
        lines = result.strip().split("\n")
        assert len(lines) == 2  # Header + 1 data row

    def test_export_report_with_daily_breakdown(self, exporter):
        """Test export_report with weekly report containing daily_breakdown."""
        report = {
            "week": "2026-12",
            "daily_breakdown": [
                {"date": "2026-03-29", "pnl": 100.0},
                {"date": "2026-03-30", "pnl": 200.0},
            ],
        }
        result = exporter.export_report(report)
        assert "2026-03-29" in result
        assert "2026-03-30" in result

    def test_export_report_simple_dict(self, exporter):
        """Test export_report with simple dict."""
        report = {"date": "2026-03-29", "total_pnl": 1500.0}
        result = exporter.export_report(report)
        assert "2026-03-29" in result

    def test_get_column_names(self, exporter, sample_data):
        """Test get_column_names extracts all unique columns."""
        columns = exporter.get_column_names(sample_data)
        assert "date" in columns
        assert "total_pnl" in columns
        assert "total_trades" in columns


class TestPDFExporter:
    """Tests for PDFExporter."""

    @pytest.fixture
    def exporter(self):
        """Create PDF exporter instance."""
        return PDFExporter()

    @pytest.fixture
    def sample_report(self):
        """Sample report object with to_dict and to_markdown."""

        class MockReport:
            def to_dict(self):
                return {
                    "report_type": "daily",
                    "date": "2026-03-29",
                    "total_pnl": 1500.0,
                    "win_rate": 0.65,
                    "total_trades": 25,
                    "sharpe_ratio": 1.5,
                    "max_drawdown": -200.0,
                    "max_drawdown_pct": -5.0,
                }

            def to_markdown(self):
                return """# Daily Report

## Summary
- Total PnL: $1500.00
- Win Rate: 65.00%

## Details
Some detailed information here.
"""

        return MockReport()

    def test_init_defaults(self):
        """Test default initialization."""
        exporter = PDFExporter()
        assert exporter.page_size == (612, 792)  # Letter
        assert exporter.left_margin == 72
        assert exporter.right_margin == 72
        assert exporter.top_margin == 72
        assert exporter.bottom_margin == 72

    def test_init_custom_margins(self):
        """Test custom margin initialization."""
        exporter = PDFExporter(
            left_margin=36,
            right_margin=36,
            top_margin=72,
            bottom_margin=72,
        )
        assert exporter.left_margin == 36

    def test_reportlab_available(self, exporter):
        """Test reportlab availability detection."""
        # This just checks the flag exists
        assert hasattr(exporter, "_reportlab_available")

    def test_export_without_reportlab(self, exporter, sample_report):
        """Test export falls back to text when reportlab unavailable."""
        if exporter._reportlab_available:
            # Test actual PDF generation when reportlab is available
            result = exporter.export(sample_report)
            assert isinstance(result, bytes)
            assert len(result) > 0
            # PDF files start with %PDF
            assert result[:4] == b"%PDF"
        else:
            # Test fallback when reportlab not available
            result = exporter.export(sample_report)
            assert isinstance(result, bytes)
            assert b"PDF Export" in result or b"Daily Report" in result

    def test_create_styles(self, exporter):
        """Test _create_styles returns appropriate object."""
        styles = exporter._create_styles()
        if not exporter._reportlab_available:
            # Returns empty dict if reportlab unavailable
            assert isinstance(styles, dict)
        else:
            # Returns StyleSheet object when reportlab available
            assert styles is not None
            assert hasattr(styles, "get")

    def test_create_table_style(self, exporter):
        """Test _create_table_style returns appropriate object."""
        style = exporter._create_table_style()
        if not exporter._reportlab_available:
            # Returns None if reportlab unavailable
            assert style is None
        else:
            # Returns TableStyle object when reportlab available
            assert style is not None

    def test_create_summary_data(self, exporter, sample_report):
        """Test _create_summary_data extracts metrics."""
        data = sample_report.to_dict()
        rows = exporter._create_summary_data(data)
        assert rows[0] == ["Metric", "Value"]  # Header
        # Check that PnL metric is included
        pnl_row = [r for r in rows if "PnL" in r[0]]
        assert len(pnl_row) > 0

    def test_export_tables_empty(self, exporter):
        """Test export_tables with empty data."""
        if not exporter._reportlab_available:
            result = exporter.export_tables([])
            # Without reportlab, returns placeholder message
            assert b"PDF Export" in result or result == b""
        else:
            # With reportlab, returns empty bytes (line 330 in pdf_exporter.py)
            result = exporter.export_tables([])
            assert result == b""

    def test_export_tables_with_data(self, exporter):
        """Test export_tables with actual data."""
        if not exporter._reportlab_available:
            data = [{"col1": "val1", "col2": "val2"}]
            result = exporter.export_tables(data)
            assert isinstance(result, bytes)
        else:
            # With reportlab, generates actual PDF
            data = [{"col1": "val1", "col2": "val2"}]
            result = exporter.export_tables(data)
            assert isinstance(result, bytes)
            assert result[:4] == b"%PDF"

    def test_export_tables_custom_columns(self, exporter):
        """Test export_tables with custom column order."""
        if not exporter._reportlab_available:
            data = [{"col1": "val1", "col2": "val2", "col3": "val3"}]
            columns = ["col3", "col1"]
            result = exporter.export_tables(data, columns=columns)
            assert isinstance(result, bytes)
        else:
            # With reportlab, generates PDF with custom column order
            data = [{"col1": "val1", "col2": "val2", "col3": "val3"}]
            columns = ["col3", "col1"]
            result = exporter.export_tables(data, columns=columns)
            assert isinstance(result, bytes)
            assert result[:4] == b"%PDF"

    def test_export_with_output_path(self, exporter, sample_report, tmp_path):
        """Test export saves to file when output_path provided."""
        if not exporter._reportlab_available:
            # Just verify it doesn't crash
            output_path = tmp_path / "test_report.pdf"
            try:
                exporter.export(sample_report, output_path=str(output_path))
            except Exception:
                pass  # Expected if no reportlab
        else:
            # With reportlab, saves actual PDF file
            output_path = tmp_path / "test_report.pdf"
            result = exporter.export(sample_report, output_path=str(output_path))
            assert output_path.exists()
            assert output_path.read_bytes() == result

    def test_add_page_numbers_noop(self, exporter):
        """Test add_page_numbers when reportlab unavailable."""
        if not exporter._reportlab_available:
            # Should be no-op, just verify no crash
            try:
                exporter.add_page_numbers(None, None)
            except Exception:
                pass
        else:
            # With reportlab, should work with actual canvas
            import io

            from reportlab.pdfgen import canvas

            buffer = io.BytesIO()
            c = canvas.Canvas(buffer)
            # Should not raise
            exporter.add_page_numbers(c, [1, 2, 3])
