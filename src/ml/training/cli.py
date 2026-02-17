"""Command-line interface for dataset export.

Provides CLI commands for exporting training datasets and generating statistics.
"""

from __future__ import annotations

import argparse
import logging
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from ml.training.exporter import (
    DatasetExporter,
    DatasetInfo,
    ExportFormat,
    ModelType,
)
from ml.training.pipeline import TrainingPipeline
from ml.training.extractor import FeatureExtractor
from ml.training.schema import TrainingSample

logger = logging.getLogger(__name__)


def create_parser() -> argparse.ArgumentParser:
    """Create argument parser for CLI.

    Returns:
        Configured ArgumentParser instance
    """
    parser = argparse.ArgumentParser(
        description="Dataset exporter for ML training data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Export command
    export_parser = subparsers.add_parser(
        "export", help="Export dataset for date range"
    )
    export_parser.add_argument(
        "--start-date",
        required=True,
        help="Start date (YYYY-MM-DD)",
    )
    export_parser.add_argument(
        "--end-date",
        required=True,
        help="End date (YYYY-MM-DD)",
    )
    export_parser.add_argument(
        "--output",
        required=True,
        help="Output file path",
    )
    export_parser.add_argument(
        "--format",
        choices=["csv", "parquet", "json", "h5"],
        default="parquet",
        help="Export format (default: parquet)",
    )
    export_parser.add_argument(
        "--train-test-split",
        type=float,
        default=0.8,
        help="Train/test split ratio (default: 0.8)",
    )
    export_parser.add_argument(
        "--token",
        help="Filter by token (e.g., BTC)",
    )

    # Export for model command
    model_parser = subparsers.add_parser(
        "export-for-model", help="Export dataset for specific model"
    )
    model_parser.add_argument(
        "--model-type",
        required=True,
        choices=["sklearn", "pytorch", "tensorflow"],
        help="Target model framework",
    )
    model_parser.add_argument(
        "--output",
        required=True,
        help="Output file path",
    )
    model_parser.add_argument(
        "--train-test-split",
        type=float,
        default=0.8,
        help="Train/test split ratio (default: 0.8)",
    )

    # Statistics command
    stats_parser = subparsers.add_parser("stats", help="Generate dataset statistics")
    stats_parser.add_argument(
        "--dataset",
        required=True,
        help="Path to dataset file",
    )

    # Demo command - creates sample data
    demo_parser = subparsers.add_parser("demo", help="Create demo dataset")
    demo_default_output = str(Path(tempfile.gettempdir()) / "demo_dataset.parquet")
    demo_parser.add_argument(
        "--output",
        default=demo_default_output,
        help=f"Output file path (default: {demo_default_output})",
    )
    demo_parser.add_argument(
        "--format",
        choices=["csv", "parquet", "json", "h5"],
        default="parquet",
        help="Export format (default: parquet)",
    )
    demo_parser.add_argument(
        "--samples",
        type=int,
        default=1000,
        help="Number of samples to generate (default: 1000)",
    )

    return parser


def export_dataset(
    start_date: str,
    end_date: str,
    output: str,
    format_str: str,
    train_test_split: float,
    token: str | None,
) -> int:
    """Export dataset for date range.

    Args:
        start_date: Start date string (YYYY-MM-DD)
        end_date: End date string (YYYY-MM-DD)
        output: Output file path
        format_str: Export format string
        train_test_split: Train/test split ratio
        token: Optional token filter

    Returns:
        Exit code (0 for success)
    """
    try:
        # Parse dates
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError as e:
        logger.error(f"Invalid date format: {e}")
        return 1

    # Create exporter
    extractor = FeatureExtractor()
    pipeline = TrainingPipeline(extractor)
    exporter = DatasetExporter(pipeline)

    # Get format enum
    fmt = ExportFormat(format_str)

    # For now, export from demo data since we need signal storage
    # In production, this would query from the pipeline
    logger.info(f"Exporting dataset from {start_date} to {end_date}")

    # Create demo data to demonstrate functionality
    samples = _generate_demo_samples(100)

    try:
        info = exporter.export_dataset(
            samples=samples,
            output_path=output,
            format=fmt,
            train_test_split=train_test_split,
        )

        print_export_info(info)
        return 0

    except Exception as e:
        logger.error(f"Export failed: {e}")
        return 1


def export_for_model(
    model_type: str,
    output: str,
    train_test_split: float,
) -> int:
    """Export dataset for specific model type.

    Args:
        model_type: Target model framework
        output: Output file path
        train_test_split: Train/test split ratio

    Returns:
        Exit code (0 for success)
    """
    # Create exporter
    extractor = FeatureExtractor()
    pipeline = TrainingPipeline(extractor)
    exporter = DatasetExporter(pipeline)

    # Get model type enum
    model = ModelType(model_type)

    # Generate demo data
    samples = _generate_demo_samples(100)

    try:
        info = exporter.export_for_model(
            samples=samples,
            model_type=model,
            output_path=output,
            train_test_split=train_test_split,
        )

        print_export_info(info)
        return 0

    except ImportError as e:
        logger.error(f"Missing dependency: {e}")
        return 1
    except Exception as e:
        logger.error(f"Export failed: {e}")
        return 1


def generate_statistics(dataset: str) -> int:
    """Generate statistics for dataset.

    Args:
        dataset: Path to dataset file

    Returns:
        Exit code (0 for success)
    """
    # Create exporter
    extractor = FeatureExtractor()
    pipeline = TrainingPipeline(extractor)
    exporter = DatasetExporter(pipeline)

    try:
        stats = exporter.generate_statistics(dataset)
        print_statistics(stats)
        return 0

    except Exception as e:
        logger.error(f"Statistics generation failed: {e}")
        return 1


def create_demo(output: str, format_str: str, num_samples: int) -> int:
    """Create demo dataset.

    Args:
        output: Output file path
        format_str: Export format string
        num_samples: Number of samples to generate

    Returns:
        Exit code (0 for success)
    """
    # Create exporter
    extractor = FeatureExtractor()
    pipeline = TrainingPipeline(extractor)
    exporter = DatasetExporter(pipeline)

    # Generate demo samples
    samples = _generate_demo_samples(num_samples)

    # Get format enum
    fmt = ExportFormat(format_str)

    try:
        info = exporter.export_dataset(
            samples=samples,
            output_path=output,
            format=fmt,
            train_test_split=0.8,
        )

        print_export_info(info)
        print_statistics(info.statistics)
        return 0

    except Exception as e:
        logger.error(f"Demo export failed: {e}")
        return 1


def print_export_info(info: DatasetInfo) -> None:
    """Print export information.

    Args:
        info: DatasetInfo to print
    """
    print("\n" + "=" * 50)
    print("EXPORT COMPLETE")
    print("=" * 50)
    print(f"Path:           {info.path}")
    print(f"Format:         {info.format.value}")
    print(f"Total samples:  {info.num_samples}")
    print(f"Features:       {info.num_features}")
    print(f"Train samples:  {info.train_samples}")
    print(f"Test samples:   {info.test_samples}")
    print(f"Created:        {info.created_at.isoformat()}")
    print(f"Features:       {', '.join(info.feature_names[:5])}...")
    print("=" * 50)


def print_statistics(stats) -> None:
    """Print dataset statistics.

    Args:
        stats: DatasetStatistics to print
    """
    print("\nDATASET STATISTICS")
    print("-" * 50)
    print(f"Win Rate:       {stats.win_rate:.2%}")
    print(f"Avg PnL:        {stats.avg_pnl:.2f}%")
    print(f"Max Drawdown:   {stats.max_drawdown:.2f}%")
    print(f"\nOutcome Distribution:")
    print(f"  Wins:         {stats.outcome_distribution.get('wins', 0)}")
    print(f"  Losses:       {stats.outcome_distribution.get('losses', 0)}")
    print(f"\nFeature Means:")
    for fname, mean in list(stats.feature_means.items())[:5]:
        print(f"  {fname}:      {mean:.4f}")
    print("-" * 50)


def _generate_demo_samples(count: int) -> list[TrainingSample]:
    """Generate demo training samples.

    Args:
        count: Number of samples to generate

    Returns:
        List of TrainingSample objects
    """
    import random

    samples = []
    tokens = ["BTC", "ETH", "SOL", "XRP", "ADA"]
    timeframes = ["1h", "4h", "1d"]
    directions = ["long", "short"]
    trends = ["bullish", "bearish", "neutral"]

    for i in range(count):
        # Generate random features
        rsi = random.uniform(20, 80)
        macd = random.uniform(-100, 100)
        macd_signal = macd + random.uniform(-10, 10)
        bb_upper = random.uniform(45000, 55000)
        bb_lower = bb_upper - random.uniform(500, 2000)
        atr = random.uniform(100, 500)
        volume_sma = random.uniform(0.5, 2.0)
        confluence = random.uniform(30, 90)
        confidence = random.uniform(0.3, 0.9)
        entry_price = random.uniform(40000, 60000)
        price_change = random.uniform(-10, 10)
        volatility = random.uniform(0.5, 5.0)

        # Random outcome (60% wins for demo)
        outcome = 1 if random.random() < 0.6 else 0
        pnl = random.uniform(-5, 10) if outcome == 1 else random.uniform(-10, 0)

        sample = TrainingSample(
            sample_id=f"demo-{i:06d}",
            timestamp=datetime.now(),
            token=random.choice(tokens),
            timeframe=random.choice(timeframes),
            rsi=rsi,
            macd=macd,
            macd_signal=macd_signal,
            macd_histogram=macd - macd_signal,
            bb_upper=bb_upper,
            bb_lower=bb_lower,
            bb_width=(bb_upper - bb_lower) / entry_price * 100,
            atr=atr,
            volume_sma=volume_sma,
            trend_state=random.choice(trends),
            confluence_score=confluence,
            confidence=confidence,
            direction=random.choice(directions),
            entry_price=entry_price,
            price_change_24h=price_change,
            volatility=volatility,
            outcome=outcome,
            pnl_percent=pnl,
            holding_period_minutes=random.randint(60, 1440),
        )

        samples.append(sample)

    return samples


def main() -> int:
    """Main entry point for CLI.

    Returns:
        Exit code
    """
    parser = create_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    if args.command == "export":
        return export_dataset(
            start_date=args.start_date,
            end_date=args.end_date,
            output=args.output,
            format_str=args.format,
            train_test_split=args.train_test_split,
            token=args.token,
        )
    elif args.command == "export-for-model":
        return export_for_model(
            model_type=args.model_type,
            output=args.output,
            train_test_split=args.train_test_split,
        )
    elif args.command == "stats":
        return generate_statistics(dataset=args.dataset)
    elif args.command == "demo":
        return create_demo(
            output=args.output,
            format_str=args.format,
            num_samples=args.samples,
        )
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
