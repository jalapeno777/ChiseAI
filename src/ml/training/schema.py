"""Training data schema definitions.

Defines Pydantic models for training data validation, including
signal features, labels, and metadata.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from ml.training.features import FeatureValidator, TrendState
from ml.training.version import CURRENT_SCHEMA_VERSION, SchemaVersionManager


class TrainingSample(BaseModel):
    """Single training sample with features and labels.

    Attributes:
        sample_id: Unique sample identifier
        timestamp: Sample timestamp (UTC)
        schema_version: Schema version for backward compatibility

        # Features (input)
        token: Trading pair token
        timeframe: Chart timeframe
        rsi: Relative Strength Index (0-100)
        macd: MACD line value
        macd_signal: MACD signal line value
        macd_histogram: MACD histogram value
        bb_upper: Bollinger Bands upper band
        bb_lower: Bollinger Bands lower band
        bb_width: Bollinger Bands width percentage
        atr: Average True Range
        volume_sma: Volume SMA ratio
        trend_state: Market trend state
        confluence_score: Confluence score (0-100)
        confidence: Signal confidence (0.0-1.0)
        direction: Signal direction
        entry_price: Entry price at signal time
        price_change_24h: 24h price change percentage
        volatility: Price volatility measure

        # Labels (target)
        outcome: Trade outcome (1=win, 0=loss)
        pnl_percent: Profit/loss percentage
        holding_period_minutes: Trade duration in minutes

        # Confidence metadata
        predicted_prob: Model predicted probability
        confidence_bin: Confidence bucket (0-10)
    """

    # Metadata
    sample_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=datetime.now)
    schema_version: str = Field(default=str(CURRENT_SCHEMA_VERSION))

    # Features (input)
    token: str = Field(..., description="Trading pair token (e.g., BTC, ETH)")
    timeframe: str = Field(..., description="Chart timeframe (e.g., 1h, 4h)")

    # Technical indicators
    rsi: float | None = Field(None, ge=0.0, le=100.0, description="RSI (0-100)")
    macd: float | None = Field(None, description="MACD line value")
    macd_signal: float | None = Field(None, description="MACD signal line value")
    macd_histogram: float | None = Field(None, description="MACD histogram value")
    bb_upper: float | None = Field(None, ge=0.0, description="BB upper band")
    bb_lower: float | None = Field(None, ge=0.0, description="BB lower band")
    bb_width: float | None = Field(None, ge=0.0, description="BB width percentage")
    atr: float | None = Field(None, ge=0.0, description="Average True Range")
    volume_sma: float | None = Field(None, ge=0.0, description="Volume SMA ratio")

    # Trend and confluence
    trend_state: str | None = Field(
        None, description="Trend state (bullish/bearish/neutral/unknown)"
    )
    confluence_score: float | None = Field(
        None, ge=0.0, le=100.0, description="Confluence score (0-100)"
    )
    confidence: float | None = Field(
        None, ge=0.0, le=1.0, description="Signal confidence (0.0-1.0)"
    )
    direction: str | None = Field(
        None, description="Signal direction (long/short/neutral)"
    )

    # Price data
    entry_price: float | None = Field(None, ge=0.0, description="Entry price")
    price_change_24h: float | None = Field(None, description="24h price change %")
    volatility: float | None = Field(None, ge=0.0, description="Volatility measure")

    # Labels (target)
    outcome: int | None = Field(
        None, ge=0, le=1, description="Trade outcome (1=win, 0=loss)"
    )
    pnl_percent: float | None = Field(None, description="PnL percentage")
    holding_period_minutes: int | None = Field(
        None, ge=0, description="Holding period in minutes"
    )

    # Confidence metadata
    predicted_prob: float | None = Field(
        None, ge=0.0, le=1.0, description="Model predicted probability"
    )
    confidence_bin: int | None = Field(
        None, ge=0, le=10, description="Confidence bucket (0-10)"
    )

    @field_validator("trend_state")
    @classmethod
    def validate_trend_state(cls, v: str | None) -> str | None:
        """Validate trend state value."""
        if v is None:
            return v
        allowed = ["bullish", "bearish", "neutral", "unknown"]
        if v not in allowed:
            raise ValueError(f"trend_state must be one of {allowed}")
        return v

    @field_validator("direction")
    @classmethod
    def validate_direction(cls, v: str | None) -> str | None:
        """Validate direction value."""
        if v is None:
            return v
        allowed = ["long", "short", "neutral"]
        if v not in allowed:
            raise ValueError(f"direction must be one of {allowed}")
        return v

    @field_validator("timeframe")
    @classmethod
    def validate_timeframe(cls, v: str) -> str:
        """Validate timeframe value."""
        allowed = [
            "1m",
            "5m",
            "15m",
            "30m",
            "1h",
            "2h",
            "4h",
            "6h",
            "8h",
            "12h",
            "1d",
            "3d",
            "1w",
        ]
        if v not in allowed:
            raise ValueError(f"timeframe must be one of {allowed}")
        return v

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return self.model_dump()

    def to_feature_dict(self) -> dict[str, Any]:
        """Get feature values only (no metadata/labels)."""
        feature_fields = [
            "token",
            "timeframe",
            "rsi",
            "macd",
            "macd_signal",
            "macd_histogram",
            "bb_upper",
            "bb_lower",
            "bb_width",
            "atr",
            "volume_sma",
            "trend_state",
            "confluence_score",
            "confidence",
            "direction",
            "entry_price",
            "price_change_24h",
            "volatility",
        ]
        return {k: v for k, v in self.to_dict().items() if k in feature_fields}

    def to_label_dict(self) -> dict[str, Any]:
        """Get label values only."""
        label_fields = ["outcome", "pnl_percent", "holding_period_minutes"]
        return {k: v for k, v in self.to_dict().items() if k in label_fields}

    def is_validated(self) -> tuple[bool, list[str]]:
        """Validate sample against feature specifications.

        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        validator = FeatureValidator()
        features = self.to_feature_dict()
        return validator.validate_features(features)

    def has_labels(self) -> bool:
        """Check if sample has labels (for supervised learning)."""
        return self.outcome is not None

    def get_confidence_bucket(self) -> int:
        """Calculate confidence bucket from confidence value."""
        if self.confidence is None:
            return 0
        return min(int(self.confidence * 10), 10)


class TrainingDataset:
    """Collection of training samples with export capabilities.

    Attributes:
        samples: List of training samples
        version_manager: Schema version manager
    """

    def __init__(self) -> None:
        """Initialize empty dataset."""
        self.samples: list[TrainingSample] = []
        self.version_manager = SchemaVersionManager()

    def add_sample(self, sample: TrainingSample) -> bool:
        """Add a sample to the dataset.

        Args:
            sample: Training sample to add

        Returns:
            True if added successfully
        """
        # Validate sample
        is_valid, errors = sample.is_validated()
        if not is_valid:
            raise ValueError(f"Invalid sample: {', '.join(errors)}")

        # Check schema version compatibility
        compatible, msg = self.version_manager.check_compatibility(
            sample.schema_version
        )
        if not compatible:
            raise ValueError(f"Schema version incompatible: {msg}")

        self.samples.append(sample)
        return True

    def add_samples(self, samples: list[TrainingSample]) -> int:
        """Add multiple samples to the dataset.

        Args:
            samples: List of training samples

        Returns:
            Number of samples added
        """
        added = 0
        for sample in samples:
            try:
                if self.add_sample(sample):
                    added += 1
            except ValueError:
                # Skip invalid samples
                pass
        return added

    def get_samples(self) -> list[TrainingSample]:
        """Get all samples."""
        return self.samples.copy()

    def get_labeled_samples(self) -> list[TrainingSample]:
        """Get samples with labels."""
        return [s for s in self.samples if s.has_labels()]

    def get_unlabeled_samples(self) -> list[TrainingSample]:
        """Get samples without labels."""
        return [s for s in self.samples if not s.has_labels()]

    def get_sample_count(self) -> int:
        """Get total sample count."""
        return len(self.samples)

    def get_feature_matrix(self) -> list[dict[str, Any]]:
        """Get features as list of dictionaries."""
        return [s.to_feature_dict() for s in self.samples]

    def get_label_matrix(self) -> list[dict[str, Any]]:
        """Get labels as list of dictionaries."""
        return [s.to_label_dict() for s in self.get_labeled_samples()]

    def validate_schema(self, data: dict[str, Any]) -> bool:
        """Validate data against schema.

        Args:
            data: Dictionary to validate

        Returns:
            True if valid
        """
        try:
            TrainingSample(**data)
            return True
        except Exception:
            return False

    def export_parquet(self, path: str) -> bool:
        """Export dataset to Parquet format.

        Args:
            path: Output file path

        Returns:
            True if successful
        """
        from pathlib import Path
        from ml.training.storage_format import ParquetHandler

        data = [s.to_dict() for s in self.samples]
        handler = ParquetHandler()
        return handler.export(data, Path(path))

    def export_csv(self, path: str) -> bool:
        """Export dataset to CSV format.

        Args:
            path: Output file path

        Returns:
            True if successful
        """
        from pathlib import Path
        from ml.training.storage_format import CSVHandler

        data = [s.to_dict() for s in self.samples]
        handler = CSVHandler()
        return handler.export(data, Path(path))

    def export_json(self, path: str) -> bool:
        """Export dataset to JSON format.

        Args:
            path: Output file path

        Returns:
            True if successful
        """
        import json
        from pathlib import Path

        data = [s.to_dict() for s in self.samples]
        with open(Path(path), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
        return True

    def get_statistics(self) -> dict[str, Any]:
        """Get dataset statistics."""
        if not self.samples:
            return {
                "sample_count": 0,
                "labeled_count": 0,
                "unlabeled_count": 0,
            }

        labeled = self.get_labeled_samples()

        # Collect unique values
        tokens = set()
        timeframes = set()
        outcomes = []

        for sample in self.samples:
            tokens.add(sample.token)
            timeframes.add(sample.timeframe)
            if sample.outcome is not None:
                outcomes.append(sample.outcome)

        return {
            "sample_count": len(self.samples),
            "labeled_count": len(labeled),
            "unlabeled_count": len(self.samples) - len(labeled),
            "unique_tokens": sorted(tokens),
            "unique_timeframes": sorted(timeframes),
            "outcome_distribution": {
                "wins": outcomes.count(1),
                "losses": outcomes.count(0),
            }
            if outcomes
            else None,
            "win_rate": outcomes.count(1) / len(outcomes) if outcomes else None,
            "schema_version": self.version_manager.get_version_string(),
        }

    @classmethod
    def from_dicts(cls, data: list[dict[str, Any]]) -> TrainingDataset:
        """Create dataset from list of dictionaries.

        Args:
            data: List of sample dictionaries

        Returns:
            TrainingDataset instance
        """
        dataset = cls()
        for item in data:
            try:
                sample = TrainingSample(**item)
                dataset.add_sample(sample)
            except Exception:
                # Skip invalid samples - intentionally continuing with remaining data
                pass  # nosec B110
        return dataset

    @classmethod
    def from_parquet(cls, path: str) -> TrainingDataset:
        """Load dataset from Parquet file.

        Args:
            path: Input file path

        Returns:
            TrainingDataset instance
        """
        from pathlib import Path
        from ml.training.storage_format import ParquetHandler

        handler = ParquetHandler()
        data = handler.import_data(Path(path))
        return cls.from_dicts(data)

    @classmethod
    def from_csv(cls, path: str) -> TrainingDataset:
        """Load dataset from CSV file.

        Args:
            path: Input file path

        Returns:
            TrainingDataset instance
        """
        from pathlib import Path
        from ml.training.storage_format import CSVHandler

        handler = CSVHandler()
        data = handler.import_data(Path(path))
        return cls.from_dicts(data)
