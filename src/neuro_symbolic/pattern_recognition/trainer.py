"""
Pattern Trainer for training pattern recognition models.

Provides training pipeline for pattern models including data preprocessing,
augmentation, and model checkpointing.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
from src.neuro_symbolic.pattern_recognition.engine import (
    PatternRecognitionEngine,
    PatternType,
)


@dataclass
class TrainingConfig:
    """Configuration for pattern model training."""

    epochs: int = 100
    batch_size: int = 32
    learning_rate: float = 0.001
    validation_split: float = 0.15
    early_stopping_patience: int = 10
    checkpoint_dir: str = "checkpoints/pattern_recognition"
    log_interval: int = 10
    augment_data: bool = True
    augmentation_factor: int = 3
    noise_level: float = 0.01
    shuffle_data: bool = True
    seed: int | None = 42


@dataclass
class TrainingResult:
    """Results from training run."""

    epochs_completed: int
    final_loss: float
    final_val_loss: float
    final_accuracy: float
    final_val_accuracy: float
    training_time_seconds: float
    best_epoch: int
    best_val_loss: float
    checkpoint_path: str | None = None
    history: dict[str, list[float]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "epochs_completed": self.epochs_completed,
            "final_loss": self.final_loss,
            "final_val_loss": self.final_val_loss,
            "final_accuracy": self.final_accuracy,
            "final_val_accuracy": self.final_val_accuracy,
            "training_time_seconds": self.training_time_seconds,
            "best_epoch": self.best_epoch,
            "best_val_loss": self.best_val_loss,
            "checkpoint_path": self.checkpoint_path,
            "history": self.history,
        }


class PatternTrainer:
    """Training pipeline for pattern recognition models.

    Handles data preprocessing, augmentation, training loop, and checkpointing.
    """

    def __init__(
        self,
        engine: PatternRecognitionEngine | None = None,
        config: TrainingConfig | None = None,
    ):
        """Initialize pattern trainer.

        Args:
            engine: Pattern recognition engine to train
            config: Training configuration
        """
        self.engine = engine or PatternRecognitionEngine()
        self.config = config or TrainingConfig()
        self._best_val_loss = float("inf")
        self._patience_counter = 0
        self._checkpoints: list[str] = []

    def preprocess_training_data(
        self,
        raw_data: list[dict[str, Any]],
        sequence_length: int | None = None,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Preprocess raw data into training format.

        Args:
            raw_data: List of data samples with 'data' and 'label' keys
            sequence_length: Override sequence length

        Returns:
            Tuple of (X, y) arrays
        """
        seq_len = sequence_length or self.engine.config.sequence_length
        num_features = self.engine.config.num_features
        num_classes = self.engine.config.num_pattern_classes

        X_list = []
        y_list = []

        for sample in raw_data:
            data = sample.get("data", [])
            label = sample.get("label", "unknown")

            # Convert label to index
            try:
                label_idx = PatternType(label).value
                label_idx = [
                    p.value for p in PatternType if p != PatternType.UNKNOWN
                ].index(label)
            except (ValueError, IndexError):
                continue

            # Convert data to numpy
            if isinstance(data, list):
                data = np.array(data)

            # Handle different data formats
            if data.ndim == 1:
                # Single price series - create OHLCV pseudo-features
                if len(data) < seq_len:
                    continue

                # Create sliding windows
                for i in range(len(data) - seq_len + 1):
                    window = data[i : i + seq_len]

                    # Create OHLCV features
                    features = np.zeros((seq_len, num_features))
                    features[:, 0] = window  # Close
                    features[:, 1] = window * 1.001  # High
                    features[:, 2] = window * 0.999  # Low
                    features[:, 3] = window  # Open
                    features[:, 4] = 1000  # Volume

                    X_list.append(features)

                    # One-hot encode label
                    y_onehot = np.zeros(num_classes)
                    y_onehot[label_idx] = 1
                    y_list.append(y_onehot)

            elif data.ndim == 2:
                # Already has features
                if data.shape[0] < seq_len:
                    continue

                for i in range(data.shape[0] - seq_len + 1):
                    window = data[i : i + seq_len]
                    if window.shape[1] != num_features:
                        continue

                    X_list.append(window)
                    y_onehot = np.zeros(num_classes)
                    y_onehot[label_idx] = 1
                    y_list.append(y_onehot)

        if not X_list:
            raise ValueError("No valid training samples found")

        X = np.array(X_list)
        y = np.array(y_list)

        # Normalize
        mean = np.mean(X, axis=(0, 1), keepdims=True)
        std = np.std(X, axis=(0, 1), keepdims=True) + 1e-8
        X = (X - mean) / std

        return X, y

    def augment_data(
        self,
        X: np.ndarray,
        y: np.ndarray,
        factor: int | None = None,
        noise_level: float | None = None,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Augment training data with noise and transformations.

        Args:
            X: Training features
            y: Training labels
            factor: Augmentation multiplier
            noise_level: Standard deviation of noise

        Returns:
            Augmented (X, y) arrays
        """
        factor = factor or self.config.augmentation_factor
        noise_level = noise_level or self.config.noise_level

        if not self.config.augment_data or factor <= 1:
            return X, y

        X_aug = [X]
        y_aug = [y]

        for _ in range(factor - 1):
            # Add Gaussian noise
            noise = np.random.normal(0, noise_level, X.shape)
            X_noisy = X + noise
            X_aug.append(X_noisy)
            y_aug.append(y)

            # Time warping (stretch/compress)
            X_warped = self._time_warp(X)
            if X_warped is not None:
                X_aug.append(X_warped)
                y_aug.append(y)

            # Scaling
            scale = np.random.uniform(0.95, 1.05)
            X_scaled = X * scale
            X_aug.append(X_scaled)
            y_aug.append(y)

        return np.concatenate(X_aug, axis=0), np.concatenate(y_aug, axis=0)

    def _time_warp(self, X: np.ndarray) -> np.ndarray | None:
        """Apply time warping augmentation.

        Args:
            X: Input array

        Returns:
            Time-warped array or None
        """
        try:
            batch_size, seq_len, features = X.shape
            warped = np.zeros_like(X)

            for b in range(batch_size):
                # Random warping factor
                warp_factor = np.random.uniform(0.9, 1.1)
                new_len = int(seq_len * warp_factor)

                # Interpolate to new length then back
                indices = np.linspace(0, seq_len - 1, new_len)
                for f in range(features):
                    warped[b, :, f] = np.interp(
                        np.arange(seq_len),
                        indices,
                        np.interp(indices, np.arange(seq_len), X[b, :, f]),
                    )

            return warped
        except Exception:
            return None

    def create_synthetic_dataset(
        self,
        n_samples: int = 1000,
        sequence_length: int | None = None,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Create synthetic training data for pattern recognition.

        Args:
            n_samples: Number of samples per pattern type
            sequence_length: Override sequence length

        Returns:
            Tuple of (X, y) arrays
        """
        seq_len = sequence_length or self.engine.config.sequence_length
        num_features = self.engine.config.num_features
        pattern_types = [p for p in PatternType if p != PatternType.UNKNOWN]

        X_list = []
        y_list = []

        for pattern_idx, pattern_type in enumerate(pattern_types):
            for _ in range(n_samples):
                # Generate pattern with noise
                pattern = self._generate_pattern(pattern_type, seq_len)

                # Add noise
                noise = np.random.normal(0, 0.05, (seq_len, num_features))
                pattern = pattern + noise

                X_list.append(pattern)

                # One-hot encode
                y_onehot = np.zeros(len(pattern_types))
                y_onehot[pattern_idx] = 1
                y_list.append(y_onehot)

        X = np.array(X_list)
        y = np.array(y_list)

        # Shuffle
        indices = np.random.permutation(len(X))
        return X[indices], y[indices]

    def _generate_pattern(self, pattern_type: PatternType, seq_len: int) -> np.ndarray:
        """Generate synthetic pattern data.

        Args:
            pattern_type: Type of pattern to generate
            seq_len: Sequence length

        Returns:
            Pattern array of shape (seq_len, num_features)
        """
        num_features = 5  # OHLCV
        pattern = np.zeros((seq_len, num_features))

        x = np.linspace(0, 4 * np.pi, seq_len)

        if pattern_type == PatternType.DOUBLE_TOP:
            base = -np.abs(np.sin(x)) + 1
        elif pattern_type == PatternType.DOUBLE_BOTTOM:
            base = np.abs(np.sin(x)) - 1
        elif pattern_type == PatternType.HEAD_AND_SHOULDERS:
            base = np.sin(x) * np.interp(x, [0, 2 * np.pi, 4 * np.pi], [0.7, 1.0, 0.7])
        elif pattern_type == PatternType.ASCENDING_TRIANGLE:
            base = np.minimum(0.3 + (x / (4 * np.pi)) * 0.5, 0.7)
        elif pattern_type == PatternType.DESCENDING_TRIANGLE:
            base = np.maximum(0.7 - (x / (4 * np.pi)) * 0.5, 0.3)
        elif pattern_type == PatternType.BULL_FLAG:
            rise = np.minimum(x / np.pi, 1.0) * 0.7
            base = np.where(x < np.pi, rise, 0.7 - (x - np.pi) * 0.02)
        elif pattern_type == PatternType.BEAR_FLAG:
            fall = np.maximum(0.7 - x / np.pi * 0.7, 0.0)
            base = np.where(x < np.pi, fall, (x - np.pi) * 0.02)
        elif pattern_type == PatternType.CUP_AND_HANDLE:
            cup = -np.abs(np.sin(x[: int(len(x) * 0.8)])) + 0.5
            handle = np.linspace(0.5, 0.4, len(x) - len(cup))
            base = np.concatenate([cup, handle])
        elif pattern_type == PatternType.ROUNDED_BOTTOM:
            base = -np.cos(x) / 2 + 0.5
        elif pattern_type == PatternType.WEDGE_RISING:
            base = 0.3 + (x / (4 * np.pi)) * 0.3 + np.sin(x * 2) * 0.1
        elif pattern_type == PatternType.WEDGE_FALLING:
            base = 0.7 - (x / (4 * np.pi)) * 0.3 - np.sin(x * 2) * 0.1
        elif pattern_type == PatternType.CHANNEL_UP:
            base = 0.3 + (x / (4 * np.pi)) * 0.4 + np.sin(x) * 0.05
        elif pattern_type == PatternType.CHANNEL_DOWN:
            base = 0.7 - (x / (4 * np.pi)) * 0.4 - np.sin(x) * 0.05
        elif pattern_type == PatternType.V_TOP:
            base = np.maximum(0.8 - np.abs(x - 2 * np.pi) * 0.2, 0.0)
        elif pattern_type == PatternType.V_BOTTOM:
            base = np.minimum(np.abs(x - 2 * np.pi) * 0.2, 0.8)
        else:
            # Random pattern
            base = np.cumsum(np.random.randn(seq_len)) * 0.01

        # Ensure base matches sequence length
        if len(base) != seq_len:
            base = np.interp(
                np.linspace(0, 1, seq_len), np.linspace(0, 1, len(base)), base
            )

        # Create OHLCV from base
        pattern[:, 0] = base  # Close
        pattern[:, 1] = base * 1.01  # High
        pattern[:, 2] = base * 0.99  # Low
        pattern[:, 3] = base  # Open
        pattern[:, 4] = np.abs(np.random.randn(seq_len)) * 1000 + 500  # Volume

        return pattern

    def train(
        self,
        X: np.ndarray | None = None,
        y: np.ndarray | None = None,
        raw_data: list[dict[str, Any]] | None = None,
        n_synthetic: int | None = None,
        callbacks: list[Callable] | None = None,
    ) -> TrainingResult:
        """Train the pattern recognition model.

        Args:
            X: Preprocessed training features
            y: Training labels
            raw_data: Raw data to preprocess
            n_synthetic: Generate n_synthetic samples per pattern
            callbacks: Optional training callbacks

        Returns:
            TrainingResult with training metrics
        """
        start_time = datetime.now()

        # Prepare data
        if X is None or y is None:
            if raw_data is not None:
                X, y = self.preprocess_training_data(raw_data)
            elif n_synthetic is not None:
                X, y = self.create_synthetic_dataset(n_synthetic)
            else:
                # Default: create synthetic dataset
                X, y = self.create_synthetic_dataset(500)

        # Augment data
        X, y = self.augment_data(X, y)

        # Set up callbacks
        if callbacks is None:
            callbacks = []

        # Add early stopping callback
        def early_stopping_callback(epoch, train_loss, val_loss):
            if val_loss < self._best_val_loss:
                self._best_val_loss = val_loss
                self._patience_counter = 0
                self._save_checkpoint(epoch)
            else:
                self._patience_counter += 1

        callbacks.append(early_stopping_callback)

        # Train
        history = self.engine.fit(
            X,
            y,
            epochs=self.config.epochs,
            batch_size=self.config.batch_size,
            validation_split=self.config.validation_split,
            verbose=self.config.log_interval <= 10,
            callbacks=callbacks,
        )

        end_time = datetime.now()
        training_time = (end_time - start_time).total_seconds()

        # Compute final metrics
        val_split = self.config.validation_split
        n_val = int(len(X) * val_split)
        X_val, y_val = X[-n_val:], y[-n_val:]

        metrics = self.engine.network.evaluate(X_val, y_val)

        result = TrainingResult(
            epochs_completed=len(history["loss"]),
            final_loss=history["loss"][-1],
            final_val_loss=history["val_loss"][-1],
            final_accuracy=metrics.get("accuracy", 0.0),
            final_val_accuracy=metrics.get("accuracy", 0.0),
            training_time_seconds=training_time,
            best_epoch=np.argmin(history["val_loss"]),
            best_val_loss=min(history["val_loss"]),
            checkpoint_path=self._checkpoints[-1] if self._checkpoints else None,
            history=history,
        )

        return result

    def _save_checkpoint(self, epoch: int) -> None:
        """Save model checkpoint.

        Args:
            epoch: Current epoch number
        """
        checkpoint_dir = Path(self.config.checkpoint_dir)
        checkpoint_dir.mkdir(parents=True, exist_ok=True)

        checkpoint_path = checkpoint_dir / f"checkpoint_epoch_{epoch}"
        self.engine.save(checkpoint_path)

        self._checkpoints.append(str(checkpoint_path))

        # Keep only last 5 checkpoints
        if len(self._checkpoints) > 5:
            old_checkpoint = Path(self._checkpoints.pop(0))
            if old_checkpoint.exists():
                import shutil

                shutil.rmtree(old_checkpoint)

    def load_best_checkpoint(self) -> bool:
        """Load the best checkpoint.

        Returns:
            True if checkpoint loaded successfully
        """
        if not self._checkpoints:
            return False

        best_checkpoint = None

        for checkpoint_path in self._checkpoints:
            try:
                checkpoint_dir = Path(checkpoint_path)
                if checkpoint_dir.exists():
                    # Check if this is the best
                    # For simplicity, use the last saved
                    best_checkpoint = checkpoint_path
            except Exception:
                continue

        if best_checkpoint:
            self.engine = PatternRecognitionEngine.load(best_checkpoint)
            return True

        return False

    def cross_validate(
        self,
        X: np.ndarray,
        y: np.ndarray,
        n_folds: int = 5,
    ) -> dict[str, float]:
        """Perform k-fold cross validation.

        Args:
            X: Training features
            y: Training labels
            n_folds: Number of folds

        Returns:
            Dictionary of cross-validation metrics
        """
        fold_size = len(X) // n_folds
        results = []

        for fold in range(n_folds):
            # Split data
            val_start = fold * fold_size
            val_end = val_start + fold_size

            X_val = X[val_start:val_end]
            y_val = y[val_start:val_end]
            X_train = np.concatenate([X[:val_start], X[val_end:]])
            y_train = np.concatenate([y[:val_start], y[val_end:]])

            # Reset engine
            self.engine = PatternRecognitionEngine()

            # Train
            self.train(X_train, y_train)

            # Evaluate
            metrics = self.engine.network.evaluate(X_val, y_val)
            results.append(metrics)

        # Aggregate results
        return {
            "mean_accuracy": np.mean([r["accuracy"] for r in results]),
            "std_accuracy": np.std([r["accuracy"] for r in results]),
            "mean_loss": np.mean([r["loss"] for r in results]),
            "std_loss": np.std([r["loss"] for r in results]),
        }
