"""Labeled dataset exporter for ML training.

Provides DatasetExporter class that creates training datasets from processed
signals with outcomes, supporting multiple export formats compatible with
various ML frameworks (scikit-learn, PyTorch, TensorFlow).
"""

from __future__ import annotations

import json
import logging
import math
import random
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

import numpy as np

from ml.training.pipeline import TrainingPipeline
from ml.training.schema import TrainingSample

logger = logging.getLogger(__name__)


class ExportFormat(Enum):
    """Supported export formats for training datasets."""

    CSV = "csv"
    PARQUET = "parquet"
    JSON = "json"
    HDF5 = "h5"


class ModelType(Enum):
    """Model types for optimized exports."""

    SKLEARN = "sklearn"  # scikit-learn compatible
    PYTORCH = "pytorch"  # PyTorch tensors
    TENSORFLOW = "tensorflow"  # TensorFlow datasets


@dataclass
class DatasetStatistics:
    """Statistics for exported dataset."""

    win_rate: float = 0.0
    avg_pnl: float = 0.0
    max_drawdown: float = 0.0
    feature_means: dict[str, float] = field(default_factory=dict)
    feature_stds: dict[str, float] = field(default_factory=dict)
    outcome_distribution: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "win_rate": self.win_rate,
            "avg_pnl": self.avg_pnl,
            "max_drawdown": self.max_drawdown,
            "feature_means": self.feature_means,
            "feature_stds": self.feature_stds,
            "outcome_distribution": self.outcome_distribution,
        }


@dataclass
class DatasetInfo:
    """Information about exported dataset."""

    path: str
    format: ExportFormat
    num_samples: int
    num_features: int
    train_samples: int
    test_samples: int
    created_at: datetime
    feature_names: list[str]
    statistics: DatasetStatistics

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "path": self.path,
            "format": self.format.value,
            "num_samples": self.num_samples,
            "num_features": self.num_features,
            "train_samples": self.train_samples,
            "test_samples": self.test_samples,
            "created_at": self.created_at.isoformat(),
            "feature_names": self.feature_names,
            "statistics": self.statistics.to_dict(),
        }


class DatasetExporter:
    """Exports labeled training datasets.

    Provides methods to export training data with features and labels
    in various formats compatible with ML frameworks.

    Attributes:
        pipeline: TrainingPipeline instance for data processing
    """

    # Numeric feature columns to include in exports
    FEATURE_COLUMNS = [
        "rsi",
        "macd",
        "macd_signal",
        "macd_histogram",
        "bb_upper",
        "bb_lower",
        "bb_width",
        "atr",
        "volume_sma",
        "confluence_score",
        "confidence",
        "entry_price",
        "price_change_24h",
        "volatility",
    ]

    LABEL_COLUMNS = ["outcome", "pnl_percent", "holding_period_minutes"]

    def __init__(self, pipeline: TrainingPipeline) -> None:
        """Initialize dataset exporter.

        Args:
            pipeline: TrainingPipeline instance for data processing
        """
        self.pipeline = pipeline

    def export_dataset(
        self,
        samples: list[TrainingSample],
        output_path: str,
        format: ExportFormat = ExportFormat.PARQUET,
        train_test_split: float = 0.8,
        shuffle: bool = True,
        random_seed: int = 42,
    ) -> DatasetInfo:
        """Export labeled dataset.

        Args:
            samples: List of training samples
            output_path: Output file path
            format: Export format (CSV, Parquet, JSON, HDF5)
            train_test_split: Fraction for training split (0.0-1.0)
            shuffle: Whether to shuffle before splitting
            random_seed: Random seed for reproducibility

        Returns:
            DatasetInfo with export details and statistics
        """
        if not samples:
            raise ValueError("No samples to export")

        # Filter to labeled samples only
        labeled_samples = [s for s in samples if s.has_labels()]
        if not labeled_samples:
            raise ValueError("No labeled samples found")

        # Convert to DataFrame-like structure
        data = self._samples_to_dicts(labeled_samples)

        # Split into train/test
        train_data, test_data = self._split_data(
            data, train_test_split, shuffle, random_seed
        )

        # Generate statistics
        statistics = self._calculate_statistics(labeled_samples)

        # Get feature names
        feature_names = self._get_feature_names(data)

        # Export based on format
        output_path_obj = Path(output_path)
        self._export_data(data, output_path_obj, format)

        # Also export train/test splits if requested
        if train_test_split > 0 and train_test_split < 1:
            train_path = (
                output_path_obj.parent
                / f"{output_path_obj.stem}_train{output_path_obj.suffix}"
            )
            test_path = (
                output_path_obj.parent
                / f"{output_path_obj.stem}_test{output_path_obj.suffix}"
            )
            self._export_data(train_data, train_path, format)
            self._export_data(test_data, test_path, format)

        return DatasetInfo(
            path=output_path,
            format=format,
            num_samples=len(data),
            num_features=len(feature_names),
            train_samples=len(train_data),
            test_samples=len(test_data),
            created_at=datetime.now(),
            feature_names=feature_names,
            statistics=statistics,
        )

    def export_for_model(
        self,
        samples: list[TrainingSample],
        model_type: ModelType,
        output_path: str,
        train_test_split: float = 0.8,
    ) -> DatasetInfo:
        """Export dataset optimized for specific model type.

        Args:
            samples: List of training samples
            model_type: Target model framework
            output_path: Output file path
            train_test_split: Fraction for training split

        Returns:
            DatasetInfo with export details
        """
        labeled_samples = [s for s in samples if s.has_labels()]
        if not labeled_samples:
            raise ValueError("No labeled samples found")

        if model_type == ModelType.PYTORCH:
            return self._export_pytorch(labeled_samples, output_path, train_test_split)
        elif model_type == ModelType.TENSORFLOW:
            return self._export_tensorflow(
                labeled_samples, output_path, train_test_split
            )
        else:
            # Default to Parquet for sklearn
            return self.export_dataset(
                labeled_samples,
                output_path,
                ExportFormat.PARQUET,
                train_test_split,
            )

    def generate_statistics(self, dataset_path: str) -> DatasetStatistics:
        """Generate statistics for exported dataset.

        Args:
            dataset_path: Path to dataset file

        Returns:
            DatasetStatistics with computed metrics
        """
        path = Path(dataset_path)

        # Determine format from extension
        suffix = path.suffix.lower()
        if suffix == ".csv":
            format_type = "csv"
        elif suffix == ".parquet":
            format_type = "parquet"
        elif suffix == ".json":
            format_type = "json"
        elif suffix == ".h5" or suffix == ".hdf5":
            format_type = "hdf5"
        else:
            raise ValueError(f"Unknown format: {suffix}")

        # Load data
        data = self._load_data(path, format_type)

        if not data:
            return DatasetStatistics()

        # Calculate statistics from samples
        samples = [TrainingSample(**d) for d in data]
        return self._calculate_statistics(samples)

    def _samples_to_dicts(self, samples: list[TrainingSample]) -> list[dict[str, Any]]:
        """Convert samples to list of dictionaries.

        Args:
            samples: List of TrainingSample objects

        Returns:
            List of sample dictionaries
        """
        result = []
        for sample in samples:
            d = sample.to_dict()
            # Convert datetime to ISO string
            if isinstance(d.get("timestamp"), datetime):
                d["timestamp"] = d["timestamp"].isoformat()
            result.append(d)
        return result

    def _split_data(
        self,
        data: list[dict[str, Any]],
        train_test_split: float,
        shuffle: bool,
        random_seed: int,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Split data into train and test sets.

        Args:
            data: List of sample dictionaries
            train_test_split: Fraction for training
            shuffle: Whether to shuffle
            random_seed: Random seed

        Returns:
            Tuple of (train_data, test_data)
        """
        if train_test_split <= 0 or train_test_split >= 1:
            # No split needed
            return data, []

        if shuffle:
            random.seed(random_seed)
            shuffled = data.copy()
            random.shuffle(shuffled)
        else:
            shuffled = data

        split_idx = int(len(shuffled) * train_test_split)
        train_data = shuffled[:split_idx]
        test_data = shuffled[split_idx:]

        return train_data, test_data

    def _calculate_statistics(self, samples: list[TrainingSample]) -> DatasetStatistics:
        """Calculate dataset statistics.

        Args:
            samples: List of training samples

        Returns:
            DatasetStatistics with computed metrics
        """
        if not samples:
            return DatasetStatistics()

        # Calculate outcome distribution
        outcomes = [s.outcome for s in samples if s.outcome is not None]
        wins = outcomes.count(1) if outcomes else 0
        losses = outcomes.count(0) if outcomes else 0

        win_rate = wins / len(outcomes) if outcomes else 0.0

        # Calculate PnL statistics
        pnl_values = [s.pnl_percent for s in samples if s.pnl_percent is not None]
        avg_pnl = sum(pnl_values) / len(pnl_values) if pnl_values else 0.0

        # Calculate max drawdown
        max_drawdown = self._calculate_max_drawdown(pnl_values)

        # Calculate feature means and stds
        feature_means: dict[str, float] = {}
        feature_stds: dict[str, float] = {}

        for col in self.FEATURE_COLUMNS:
            values = []
            for sample in samples:
                val = getattr(sample, col, None)
                if val is not None:
                    values.append(val)

            if values:
                feature_means[col] = sum(values) / len(values)
                if len(values) > 1:
                    variance = sum((x - feature_means[col]) ** 2 for x in values) / len(
                        values
                    )
                    feature_stds[col] = math.sqrt(variance)
                else:
                    feature_stds[col] = 0.0
            else:
                feature_means[col] = 0.0
                feature_stds[col] = 0.0

        return DatasetStatistics(
            win_rate=win_rate,
            avg_pnl=avg_pnl,
            max_drawdown=max_drawdown,
            feature_means=feature_means,
            feature_stds=feature_stds,
            outcome_distribution={"wins": wins, "losses": losses},
        )

    def _calculate_max_drawdown(self, pnl_values: list[float]) -> float:
        """Calculate maximum drawdown from PnL values.

        Args:
            pnl_values: List of PnL percentages

        Returns:
            Maximum drawdown (negative value)
        """
        if not pnl_values:
            return 0.0

        running_max = 0.0
        max_drawdown = 0.0

        cumulative = 0.0
        for pnl in pnl_values:
            cumulative += pnl
            if cumulative > running_max:
                running_max = cumulative
            drawdown = running_max - cumulative
            if drawdown > max_drawdown:
                max_drawdown = drawdown

        return -max_drawdown

    def _get_feature_names(self, data: list[dict[str, Any]]) -> list[str]:
        """Get feature column names.

        Args:
            data: List of sample dictionaries

        Returns:
            List of feature column names
        """
        if not data:
            return self.FEATURE_COLUMNS

        # Use columns that exist in the data
        features = []
        for col in self.FEATURE_COLUMNS:
            if col in data[0]:
                features.append(col)
        return features

    def _export_data(
        self,
        data: list[dict[str, Any]],
        path: Path,
        format: ExportFormat,
    ) -> None:
        """Export data to specified format.

        Args:
            data: List of sample dictionaries
            path: Output file path
            format: Export format
        """
        if format == ExportFormat.CSV:
            self._export_csv(data, path)
        elif format == ExportFormat.PARQUET:
            self._export_parquet(data, path)
        elif format == ExportFormat.JSON:
            self._export_json(data, path)
        elif format == ExportFormat.HDF5:
            self._export_hdf5(data, path)
        else:
            raise ValueError(f"Unsupported format: {format}")

    def _export_csv(self, data: list[dict[str, Any]], path: Path) -> None:
        """Export to CSV format."""
        import csv

        if not data:
            path.touch()
            return

        fieldnames = sorted(data[0].keys())

        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)

        logger.info(f"Exported {len(data)} samples to {path}")

    def _export_parquet(self, data: list[dict[str, Any]], path: Path) -> None:
        """Export to Parquet format."""
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
        except ImportError as e:
            raise ImportError("pyarrow is required for Parquet export") from e

        table = pa.Table.from_pylist(data)
        pq.write_table(
            table,
            path,
            compression="zstd",
            use_dictionary=True,
        )

        logger.info(f"Exported {len(data)} samples to {path}")

    def _export_json(self, data: list[dict[str, Any]], path: Path) -> None:
        """Export to JSON format."""
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)

        logger.info(f"Exported {len(data)} samples to {path}")

    def _export_hdf5(self, data: list[dict[str, Any]], path: Path) -> None:
        """Export to HDF5 format."""
        try:
            import h5py
        except ImportError as e:
            raise ImportError("h5py is required for HDF5 export") from e

        if not data:
            # Create empty HDF5 file
            with h5py.File(path, "w") as f:
                pass
            return

        # Convert data to numpy arrays
        # Separate features and labels
        feature_names = [
            k
            for k in data[0].keys()
            if k
            not in [
                "sample_id",
                "timestamp",
                "schema_version",
                "token",
                "timeframe",
                "trend_state",
                "direction",
            ]
        ]

        num_samples = len(data)
        num_features = len(feature_names)

        # Create datasets
        with h5py.File(path, "w") as f:
            # Features dataset
            features_data = np.zeros((num_samples, num_features), dtype=np.float32)
            for i, sample in enumerate(data):
                for j, fname in enumerate(feature_names):
                    val = sample.get(fname)
                    if val is not None:
                        features_data[i, j] = val

            f.create_dataset("features", data=features_data)
            f.create_dataset("feature_names", data=np.array(feature_names, dtype="S50"))

            # Labels dataset (outcome)
            outcomes = np.array(
                [sample.get("outcome", -1) for sample in data], dtype=np.int8
            )
            f.create_dataset("labels", data=outcomes)

            # Additional metadata
            f.attrs["num_samples"] = num_samples
            f.attrs["num_features"] = num_features
            f.attrs["created_at"] = datetime.now().isoformat()

        logger.info(f"Exported {len(data)} samples to {path}")

    def _load_data(self, path: Path, format_type: str) -> list[dict[str, Any]]:
        """Load data from file.

        Args:
            path: Input file path
            format_type: Format type (csv, parquet, json, hdf5)

        Returns:
            List of sample dictionaries
        """
        if format_type == "csv":
            return self._load_csv(path)
        elif format_type == "parquet":
            return self._load_parquet(path)
        elif format_type == "json":
            return self._load_json(path)
        elif format_type == "hdf5":
            return self._load_hdf5(path)
        else:
            raise ValueError(f"Unknown format: {format_type}")

    def _load_csv(self, path: Path) -> list[dict[str, Any]]:
        """Load data from CSV."""
        import csv

        data = []
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                converted = {}
                for key, value in row.items():
                    if value == "":
                        converted[key] = None
                    else:
                        try:
                            converted[key] = int(value)
                        except ValueError:
                            try:
                                converted[key] = float(value)
                            except ValueError:
                                converted[key] = value
                data.append(converted)
        return data

    def _load_parquet(self, path: Path) -> list[dict[str, Any]]:
        """Load data from Parquet."""
        import pyarrow.parquet as pq

        table = pq.read_table(path)
        return table.to_pylist()

    def _load_json(self, path: Path) -> list[dict[str, Any]]:
        """Load data from JSON."""
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def _load_hdf5(self, path: Path) -> list[dict[str, Any]]:
        """Load data from HDF5."""
        import h5py

        data = []
        with h5py.File(path, "r") as f:
            features = f["features"]
            feature_names = [n.decode("utf-8") for n in f["feature_names"][:]]
            labels = f["labels"]

            for i in range(features.shape[0]):
                sample = {}
                for j, fname in enumerate(feature_names):
                    sample[fname] = float(features[i, j])
                sample["outcome"] = int(labels[i])
                data.append(sample)

        return data

    def _export_pytorch(
        self,
        samples: list[TrainingSample],
        output_path: str,
        train_test_split: float,
    ) -> DatasetInfo:
        """Export dataset in PyTorch format.

        Args:
            samples: List of training samples
            output_path: Output file path
            train_test_split: Fraction for training

        Returns:
            DatasetInfo with export details
        """
        try:
            import torch
        except ImportError as e:
            raise ImportError("PyTorch is required for pytorch export") from e

        # Prepare feature matrix
        feature_names = self.FEATURE_COLUMNS
        X = []
        y = []

        for sample in samples:
            features = []
            for fname in feature_names:
                val = getattr(sample, fname, None)
                features.append(val if val is not None else 0.0)
            X.append(features)

            outcome = sample.outcome if sample.outcome is not None else 0
            y.append(outcome)

        X_tensor = torch.tensor(X, dtype=torch.float32)
        y_tensor = torch.tensor(y, dtype=torch.long)

        # Split data
        split_idx = int(len(X_tensor) * train_test_split)
        X_train, X_test = X_tensor[:split_idx], X_tensor[split_idx:]
        y_train, y_test = y_tensor[:split_idx], y_tensor[split_idx:]

        # Save
        path = Path(output_path)
        torch.save(
            {
                "X_train": X_train,
                "y_train": y_train,
                "X_test": X_test,
                "y_test": y_test,
                "feature_names": feature_names,
            },
            path,
        )

        # Calculate statistics
        statistics = self._calculate_statistics(samples)

        logger.info(f"Exported PyTorch dataset to {path}")

        return DatasetInfo(
            path=output_path,
            format=ExportFormat.HDF5,  # Closest match
            num_samples=len(samples),
            num_features=len(feature_names),
            train_samples=split_idx,
            test_samples=len(samples) - split_idx,
            created_at=datetime.now(),
            feature_names=feature_names,
            statistics=statistics,
        )

    def _export_tensorflow(
        self,
        samples: list[TrainingSample],
        output_path: str,
        train_test_split: float,
    ) -> DatasetInfo:
        """Export dataset in TensorFlow format.

        Args:
            samples: List of training samples
            output_path: Output file path
            train_test_split: Fraction for training

        Returns:
            DatasetInfo with export details
        """
        try:
            import tensorflow as tf
        except ImportError as e:
            raise ImportError("TensorFlow is required for tensorflow export") from e

        # Prepare feature matrix
        feature_names = self.FEATURE_COLUMNS
        X = []
        y = []

        for sample in samples:
            features = []
            for fname in feature_names:
                val = getattr(sample, fname, None)
                features.append(val if val is not None else 0.0)
            X.append(features)

            outcome = sample.outcome if sample.outcome is not None else 0
            y.append(outcome)

        X_array = np.array(X, dtype=np.float32)
        y_array = np.array(y, dtype=np.int32)

        # Split data
        split_idx = int(len(X_array) * train_test_split)
        X_train, X_test = X_array[:split_idx], X_array[split_idx:]
        y_train, y_test = y_array[:split_idx], y_array[split_idx:]

        # Create TF datasets
        train_ds = tf.data.Dataset.from_tensor_slices((X_train, y_train))
        test_ds = tf.data.Dataset.from_tensor_slices((X_test, y_test))

        # Save as TFRecord
        path = Path(output_path)
        train_path = path.parent / f"{path.stem}_train{path.suffix}"
        test_path = path.parent / f"{path.stem}_test{path.suffix}"

        # Write train TFRecord
        with tf.io.TFRecordWriter(str(train_path)) as writer:
            for features, label in train_ds:
                example = tf.train.Example()
                for i, fname in enumerate(feature_names):
                    example.features.feature[fname].float_list.value.append(
                        float(features[i])
                    )
                example.features.feature["label"].int64_list.value.append(int(label))
                writer.write(example.SerializeToString())

        # Write test TFRecord
        with tf.io.TFRecordWriter(str(test_path)) as writer:
            for features, label in test_ds:
                example = tf.train.Example()
                for i, fname in enumerate(feature_names):
                    example.features.feature[fname].float_list.value.append(
                        float(features[i])
                    )
                example.features.feature["label"].int64_list.value.append(int(label))
                writer.write(example.SerializeToString())

        # Calculate statistics
        statistics = self._calculate_statistics(samples)

        logger.info(f"Exported TensorFlow dataset to {path}")

        return DatasetInfo(
            path=output_path,
            format=ExportFormat.HDF5,  # Closest match
            num_samples=len(samples),
            num_features=len(feature_names),
            train_samples=split_idx,
            test_samples=len(samples) - split_idx,
            created_at=datetime.now(),
            feature_names=feature_names,
            statistics=statistics,
        )


def export_from_samples(
    samples: list[TrainingSample],
    output_path: str,
    format: ExportFormat = ExportFormat.PARQUET,
    train_test_split: float = 0.8,
) -> DatasetInfo:
    """Convenience function to export samples directly.

    Args:
        samples: List of training samples
        output_path: Output file path
        format: Export format
        train_test_split: Train/test split ratio

    Returns:
        DatasetInfo with export details
    """
    # Create a minimal pipeline for the exporter
    from ml.training.extractor import FeatureExtractor

    extractor = FeatureExtractor()
    pipeline = TrainingPipeline(extractor)
    exporter = DatasetExporter(pipeline)

    return exporter.export_dataset(
        samples=samples,
        output_path=output_path,
        format=format,
        train_test_split=train_test_split,
    )
