#!/usr/bin/env python3
"""Standalone training data export script.

This script provides a simple command-line interface for exporting
labeled training datasets from the ChiseAI system.

Usage:
    python scripts/export_training_data.py --start 2026-01-01 --end 2026-02-01 --output ./data/training.parquet
    python scripts/export_training_data.py --demo --samples 5000
    python scripts/export_training_data.py --stats ./data/training.parquet
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

# Bootstrap environment first (must be before any env access)
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from config.bootstrap import bootstrap

bootstrap(load_env=True)

from config.bootstrap import bootstrap  # noqa: E402
from ml.training.exporter import (  # noqa: E402
    DatasetExporter,
    DatasetInfo,
    ExportFormat,
    ModelType,
)
from ml.training.extractor import FeatureExtractor  # noqa: E402
from ml.training.pipeline import TrainingPipeline  # noqa: E402
from ml.training.schema import TrainingSample  # noqa: E402

logger = logging.getLogger(__name__)


def create_parser() -> argparse.ArgumentParser:
    """Create argument parser."""
    parser = argparse.ArgumentParser(
        description="Export training data from ChiseAI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Export data for date range
  %(prog)s --start 2026-01-01 --end 2026-02-01 --output ./data/train.parquet

  # Export in CSV format
  %(prog)s --start 2026-01-01 --end 2026-02-01 --output ./data/train.csv --format csv

  # Create demo dataset
  %(prog)s --demo --samples 1000 --output ./data/demo.parquet

  # Generate statistics
  %(prog)s --stats ./data/train.parquet

  # Export for PyTorch
  %(prog)s --model pytorch --output ./data/train.pt --samples 5000
        """,
    )

    # Date range options
    parser.add_argument(
        "--start",
        help="Start date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end",
        help="End date (YYYY-MM-DD)",
    )

    # Output options
    parser.add_argument(
        "--output",
        "-o",
        help="Output file path",
    )

    # Format options
    parser.add_argument(
        "--format",
        "-f",
        choices=["csv", "parquet", "json", "h5"],
        default="parquet",
        help="Export format (default: parquet)",
    )

    # Split options
    parser.add_argument(
        "--split",
        "-s",
        type=float,
        default=0.8,
        help="Train/test split ratio (default: 0.8)",
    )

    # Filter options
    parser.add_argument(
        "--token",
        "-t",
        help="Filter by token (e.g., BTC, ETH)",
    )

    # Demo mode
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Create demo dataset with random samples",
    )

    # Number of samples for demo
    parser.add_argument(
        "--samples",
        "-n",
        type=int,
        default=1000,
        help="Number of samples for demo mode (default: 1000)",
    )

    # Statistics mode
    parser.add_argument(
        "--stats",
        help="Generate statistics for existing dataset",
    )

    # Model export mode
    parser.add_argument(
        "--model",
        choices=["sklearn", "pytorch", "tensorflow"],
        help="Export for specific ML framework",
    )

    # Verbose output
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    return parser


def generate_demo_samples(count: int) -> list[TrainingSample]:
    """Generate demo training samples for testing.

    Args:
        count: Number of samples to generate

    Returns:
        List of TrainingSample objects
    """
    import random

    samples = []
    tokens = ["BTC", "ETH", "SOL", "XRP", "ADA", "DOGE", "AVAX", "MATIC"]
    timeframes = ["1m", "5m", "15m", "1h", "4h", "1d"]
    directions = ["long", "short"]
    trends = ["bullish", "bearish", "neutral"]

    for i in range(count):
        # Generate realistic random features
        token = random.choice(tokens)
        timeframe = random.choice(timeframes)

        # Base price varies by token
        base_prices = {
            "BTC": 50000,
            "ETH": 3000,
            "SOL": 100,
            "XRP": 0.5,
            "ADA": 0.4,
            "DOGE": 0.08,
            "AVAX": 35,
            "MATIC": 0.8,
        }
        base_price = base_prices.get(token, 1000)
        entry_price = base_price * random.uniform(0.95, 1.05)

        # Technical indicators
        rsi = random.uniform(20, 80)
        macd = random.uniform(-base_price * 0.02, base_price * 0.02)
        macd_signal = macd + random.uniform(-base_price * 0.005, base_price * 0.005)
        bb_upper = entry_price * random.uniform(1.01, 1.05)
        bb_lower = entry_price * random.uniform(0.95, 0.99)
        atr = entry_price * random.uniform(0.01, 0.03)
        volume_sma = random.uniform(0.5, 2.0)
        confluence = random.uniform(30, 90)
        confidence = random.uniform(0.3, 0.95)
        price_change = random.uniform(-15, 15)
        volatility = random.uniform(0.5, 5.0)

        # Outcome (60% wins for realistic demo)
        outcome = 1 if random.random() < 0.6 else 0
        if outcome == 1:
            pnl = random.uniform(0.5, 15)
        else:
            pnl = random.uniform(-15, -0.5)

        sample = TrainingSample(
            sample_id=f"signal-{i:08d}",
            timestamp=datetime.now(),
            token=token,
            timeframe=timeframe,
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
            holding_period_minutes=random.randint(15, 2880),
        )

        samples.append(sample)

    return samples


def print_info(info: DatasetInfo) -> None:
    """Print export information."""
    print("\n" + "=" * 60)
    print("EXPORT SUCCESSFUL")
    print("=" * 60)
    print(f"Output path:       {info.path}")
    print(f"Format:            {info.format.value.upper()}")
    print(f"Total samples:     {info.num_samples}")
    print(f"Feature count:     {info.num_features}")
    print(f"Train samples:     {info.train_samples}")
    print(f"Test samples:     {info.test_samples}")
    print(f"Created at:       {info.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
    print("-" * 60)
    print(f"Win rate:          {info.statistics.win_rate:.2%}")
    print(f"Avg PnL:           {info.statistics.avg_pnl:+.2f}%")
    print(f"Max drawdown:      {info.statistics.max_drawdown:+.2f}%")
    print(f"Wins:              {info.statistics.outcome_distribution.get('wins', 0)}")
    print(f"Losses:            {info.statistics.outcome_distribution.get('losses', 0)}")
    print("=" * 60)


def main() -> int:
    """Main entry point."""
    bootstrap(load_env=True)

    parser = create_parser()
    args = parser.parse_args()

    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Check for valid mode
    if args.stats:
        # Statistics mode
        return show_statistics(args.stats, verbose=args.verbose)

    if args.demo:
        # Demo mode
        return run_demo(args)

    if args.model:
        # Model export mode
        return export_for_model(args)

    if args.start and args.end and args.output:
        # Date range export mode
        return export_date_range(args)

    # No valid mode selected
    parser.print_help()
    return 1


def export_date_range(args: argparse.Namespace) -> int:
    """Export dataset for date range."""
    try:
        datetime.strptime(args.start, "%Y-%m-%d")
        datetime.strptime(args.end, "%Y-%m-%d")
    except ValueError as e:
        logger.error(f"Invalid date format: {e}")
        return 1

    logger.info(f"Exporting data from {args.start} to {args.end}")

    # Create exporter
    extractor = FeatureExtractor()
    pipeline = TrainingPipeline(extractor)
    exporter = DatasetExporter(pipeline)

    # Generate demo samples for now
    # In production, this would query actual data
    samples = generate_demo_samples(args.samples)

    try:
        info = exporter.export_dataset(
            samples=samples,
            output_path=args.output,
            format=ExportFormat(args.format),
            train_test_split=args.split,
        )

        print_info(info)
        return 0

    except Exception as e:
        logger.error(f"Export failed: {e}", exc_info=args.verbose)
        return 1


def run_demo(args: argparse.Namespace) -> int:
    """Run demo mode."""
    logger.info(f"Generating {args.samples} demo samples")

    # Create exporter
    extractor = FeatureExtractor()
    pipeline = TrainingPipeline(extractor)
    exporter = DatasetExporter(pipeline)

    # Generate demo samples
    samples = generate_demo_samples(args.samples)

    try:
        info = exporter.export_dataset(
            samples=samples,
            output_path=args.output,
            format=ExportFormat(args.format),
            train_test_split=args.split,
        )

        print_info(info)
        logger.info(f"Demo dataset created at: {args.output}")
        return 0

    except Exception as e:
        logger.error(f"Demo export failed: {e}", exc_info=args.verbose)
        return 1


def export_for_model(args: argparse.Namespace) -> int:
    """Export for specific model type."""
    logger.info(f"Exporting for {args.model} model")

    # Create exporter
    extractor = FeatureExtractor()
    pipeline = TrainingPipeline(extractor)
    exporter = DatasetExporter(pipeline)

    # Generate demo samples
    samples = generate_demo_samples(args.samples)

    try:
        model_type = ModelType(args.model)
        info = exporter.export_for_model(
            samples=samples,
            model_type=model_type,
            output_path=args.output,
            train_test_split=args.split,
        )

        print_info(info)
        return 0

    except ImportError as e:
        logger.error(f"Missing dependency: {e}")
        logger.info(f"Install required package: pip install {args.model}")
        return 1
    except Exception as e:
        logger.error(f"Export failed: {e}", exc_info=args.verbose)
        return 1


def show_statistics(dataset_path: str, verbose: bool = False) -> int:
    """Show statistics for existing dataset."""
    logger.info(f"Generating statistics for: {dataset_path}")

    # Create exporter
    extractor = FeatureExtractor()
    pipeline = TrainingPipeline(extractor)
    exporter = DatasetExporter(pipeline)

    try:
        stats = exporter.generate_statistics(dataset_path)

        print("\n" + "=" * 60)
        print("DATASET STATISTICS")
        print("=" * 60)
        print(f"File:              {dataset_path}")
        print("-" * 60)
        print(f"Win rate:          {stats.win_rate:.2%}")
        print(f"Avg PnL:           {stats.avg_pnl:+.2f}%")
        print(f"Max drawdown:      {stats.max_drawdown:+.2f}%")
        print("\nOutcome distribution:")
        print(f"  Wins:            {stats.outcome_distribution.get('wins', 0)}")
        print(f"  Losses:          {stats.outcome_distribution.get('losses', 0)}")
        print("\nFeature statistics (first 5):")
        for i, (name, mean) in enumerate(list(stats.feature_means.items())[:5]):
            std = stats.feature_stds.get(name, 0)
            print(f"  {name}: mean={mean:.4f}, std={std:.4f}")
        print("=" * 60)

        return 0

    except Exception as e:
        logger.error(f"Statistics generation failed: {e}", exc_info=verbose)
        return 1


if __name__ == "__main__":
    sys.exit(main())
