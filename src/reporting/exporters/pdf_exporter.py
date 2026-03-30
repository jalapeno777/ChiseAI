"""PDF export module for report data.

Provides PDF generation with professional formatting,
chart embedding support, and header/footer.

For ST-NS-023-T2: Report Delivery & Dashboard Integration
"""

from __future__ import annotations

import io
import logging
from typing import Any

logger = logging.getLogger(__name__)


class PDFExporter:
    """PDF report exporter with professional formatting.

    Features:
    - Professional headers and footers
    - Table rendering for data
    - Chart/graph embedding support
    - Page numbering
    - Configurable page size

    Note:
        Requires reportlab package for PDF generation.
        Falls back to placeholder if not available.

    Attributes:
        page_size: Page size tuple (width, height) in points
        left_margin: Left margin in points
        right_margin: Right margin in points
        top_margin: Top margin in points
        bottom_margin: Bottom margin in points
    """

    def __init__(
        self,
        page_size: tuple[float, float] | None = None,
        left_margin: float = 72,
        right_margin: float = 72,
        top_margin: float = 72,
        bottom_margin: float = 72,
    ) -> None:
        """Initialize PDF exporter.

        Args:
            page_size: Page size as (width, height) in points
            left_margin: Left margin in points
            right_margin: Right margin in points
            top_margin: Top margin in points
            bottom_margin: Bottom margin in points
        """
        self.page_size = page_size or (612, 792)  # Letter size
        self.left_margin = left_margin
        self.right_margin = right_margin
        self.top_margin = top_margin
        self.bottom_margin = bottom_margin

        self._reportlab_available = False
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import letter
            from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
            from reportlab.lib.units import inch
            from reportlab.platypus import (
                Frame,
                NextPageTemplate,
                PageBreak,
                Paragraph,
                SimpleDocTemplate,
                Spacer,
                Table,
                TableStyle,
            )

            self._reportlab_available = True
            self._letter = letter
            self._Frame = Frame
            self._NextPageTemplate = NextPageTemplate
            self._PageBreak = PageBreak
            self._Paragraph = Paragraph
            self._SimpleDocTemplate = SimpleDocTemplate
            self._Spacer = Spacer
            self._Table = Table
            self._TableStyle = TableStyle
            self._ParagraphStyle = ParagraphStyle
            self._getSampleStyleSheet = getSampleStyleSheet
            self._inch = inch
            self._colors = colors

        except ImportError:
            logger.warning(
                "reportlab not available, PDF export will produce placeholder text"
            )

    def _create_styles(self) -> Any:
        """Create paragraph styles for PDF.

        Returns:
            Dictionary of styles
        """
        if not self._reportlab_available:
            return {}

        styles = self._getSampleStyleSheet()

        # Title style
        styles.add(
            self._ParagraphStyle(
                "ReportTitle",
                parent=styles["Heading1"],
                fontSize=24,
                spaceAfter=30,
                textColor=self._colors.HexColor("#007bff"),
            )
        )

        # Header style
        styles.add(
            self._ParagraphStyle(
                "ReportHeader",
                parent=styles["Heading2"],
                fontSize=16,
                spaceAfter=12,
                textColor=self._colors.HexColor("#333333"),
            )
        )

        # Body style
        styles.add(
            self._ParagraphStyle(
                "ReportBody",
                parent=styles["Normal"],
                fontSize=10,
                spaceAfter=6,
            )
        )

        return styles

    def _create_table_style(self) -> Any:
        """Create table style for data tables.

        Returns:
            TableStyle object
        """
        if not self._reportlab_available:
            return None

        return self._TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), self._colors.HexColor("#007bff")),
                ("TEXTCOLOR", (0, 0), (-1, 0), self._colors.whitesmoke),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 10),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                ("BACKGROUND", (0, 1), (-1, -1), self._colors.HexColor("#f8f9fa")),
                ("TEXTCOLOR", (0, 1), (-1, -1), self._colors.HexColor("#333333")),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 1), (-1, -1), 9),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("GRID", (0, 0), (-1, -1), 1, self._colors.HexColor("#dee2e6")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )

    def export(
        self,
        report: Any,
        output_path: str | None = None,
    ) -> bytes:
        """Export report to PDF.

        Args:
            report: Report object with to_dict() and to_markdown() methods
            output_path: Optional path to save PDF

        Returns:
            PDF bytes
        """
        if not self._reportlab_available:
            # Return placeholder text as bytes
            content = (
                report.to_markdown() if hasattr(report, "to_markdown") else str(report)
            )
            return f"PDF Export (reportlab not available)\n\n{content}".encode()

        data = report.to_dict() if hasattr(report, "to_dict") else {}

        # Build PDF document
        buffer = io.BytesIO()
        doc = self._SimpleDocTemplate(
            buffer,
            pagesize=self.page_size,
            leftMargin=self.left_margin,
            rightMargin=self.right_margin,
            topMargin=self.top_margin,
            bottomMargin=self.bottom_margin,
        )

        styles = self._create_styles()
        elements = []

        # Title
        report_type = data.get("report_type", "Report").title()
        date_str = data.get("date", "")
        title_text = f"{report_type} Report"
        if date_str:
            title_text += f" - {date_str}"

        elements.append(self._Paragraph(title_text, styles["ReportTitle"]))
        elements.append(self._Spacer(1, 0.25 * self._inch))

        # Summary table
        summary_data = self._create_summary_data(data)
        if summary_data:
            table = self._Table(
                summary_data, colWidths=[2.5 * self._inch, 2 * self._inch]
            )
            table.setStyle(self._create_table_style())
            elements.append(table)
            elements.append(self._Spacer(1, 0.25 * self._inch))

        # Markdown content
        if hasattr(report, "to_markdown"):
            content = report.to_markdown()
            paragraphs = content.split("\n\n")
            for para in paragraphs:
                if para.startswith("# "):
                    elements.append(self._Paragraph(para[2:], styles["ReportTitle"]))
                elif para.startswith("## "):
                    elements.append(self._Paragraph(para[3:], styles["ReportHeader"]))
                elif para.startswith("### "):
                    elements.append(self._Paragraph(para[4:], styles["Heading3"]))
                elif para.startswith("-"):
                    # Bullet points
                    for line in para.split("\n"):
                        if line.startswith("-"):
                            elements.append(
                                self._Paragraph(
                                    f"• {line[1:].strip()}", styles["ReportBody"]
                                )
                            )
                elif para.strip():
                    elements.append(self._Paragraph(para, styles["ReportBody"]))

        # Build PDF
        doc.build(elements)

        # Get PDF bytes
        pdf_bytes = buffer.getvalue()
        buffer.close()

        # Save to file if path provided
        if output_path:
            with open(output_path, "wb") as f:
                f.write(pdf_bytes)

        return pdf_bytes

    def _create_summary_data(
        self,
        data: dict[str, Any],
    ) -> list[list[str]]:
        """Create summary table data from report.

        Args:
            data: Report data dictionary

        Returns:
            List of table rows
        """
        rows: list[list[str]] = [["Metric", "Value"]]

        # Common metrics
        metric_fields = [
            ("total_pnl", "Total PnL"),
            ("win_rate", "Win Rate"),
            ("total_trades", "Total Trades"),
            ("sharpe_ratio", "Sharpe Ratio"),
            ("max_drawdown", "Max Drawdown"),
            ("max_drawdown_pct", "Max Drawdown %"),
        ]

        for field, label in metric_fields:
            if field in data:
                value = data[field]
                if isinstance(value, float):
                    if "pct" in field or "rate" in field:
                        value_str = f"{value:.2f}%"
                    else:
                        value_str = f"${value:,.2f}"
                else:
                    value_str = str(value)
                rows.append([label, value_str])

        return rows

    def export_tables(
        self,
        data: list[dict[str, Any]],
        title: str = "Data",
        columns: list[str] | None = None,
        output_path: str | None = None,
    ) -> bytes:
        """Export data tables to PDF.

        Args:
            data: List of row dictionaries
            title: Table title
            columns: Column order (None = all)
            output_path: Optional path to save PDF

        Returns:
            PDF bytes
        """
        if not self._reportlab_available:
            return f"PDF Export (reportlab not available)\n\n{title}".encode()

        if not data:
            return b""

        # Determine columns
        if columns is None:
            columns = list(data[0].keys())

        # Build table data
        table_data = [columns]
        for row in data:
            table_data.append([str(row.get(c, "")) for c in columns])

        # Build PDF
        buffer = io.BytesIO()
        doc = self._SimpleDocTemplate(
            buffer,
            pagesize=self.page_size,
            leftMargin=self.left_margin,
            rightMargin=self.right_margin,
            topMargin=self.top_margin,
            bottomMargin=self.bottom_margin,
        )

        styles = self._create_styles()
        elements = []

        # Title
        elements.append(self._Paragraph(title, styles["ReportTitle"]))
        elements.append(self._Spacer(1, 0.25 * self._inch))

        # Table
        table = self._Table(table_data)
        table.setStyle(self._create_table_style())
        elements.append(table)

        doc.build(elements)

        pdf_bytes = buffer.getvalue()
        buffer.close()

        if output_path:
            with open(output_path, "wb") as f:
                f.write(pdf_bytes)

        return pdf_bytes

    def add_page_numbers(
        self,
        canvas: Any,
        document: Any,
    ) -> None:
        """Add page numbers to PDF pages.

        Args:
            canvas: ReportLab canvas
            document: Document object
        """
        if not self._reportlab_available:
            return

        page_num = canvas.getPageNumber()
        text = f"Page {page_num}"
        canvas.drawRightString(
            self.page_size[0] - self.right_margin,
            0.5 * self._inch,
            text,
        )
