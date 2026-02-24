"""
Neural network model for pattern recognition.

Provides a flexible neural network architecture for time series pattern analysis.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from src.neuro_symbolic.neural.layers import (
    BaseLayer,
    ConvLayer,
    DenseLayer,
    DropoutLayer,
    LayerConfig,
    LSTMLayer,
)


@dataclass
class NetworkConfig:
    """Configuration for neural network architecture."""

    input_shape: tuple  # (sequence_length, features)
    output_size: int
    layers: list[dict[str, Any]] = field(default_factory=list)
    learning_rate: float = 0.001
    loss: str = "mse"


class NeuralNetwork:
    """Neural network for pattern recognition.

    Supports stacking of Conv1D, LSTM, and Dense layers for time series analysis.
    """

    def __init__(self, config: NetworkConfig | None = None):
        """Initialize neural network.

        Args:
            config: Network configuration. If None, creates default architecture.
        """
        self.config = config or self._default_config()
        self.layers: list[BaseLayer] = []
        self._build_network()
        self.training_history: list[dict[str, float]] = []

    def _default_config(self) -> NetworkConfig:
        """Create default network configuration."""
        return NetworkConfig(
            input_shape=(50, 1),  # 50 timesteps, 1 feature
            output_size=5,  # 5 pattern classes
            layers=[
                {"type": "conv", "filters": 32, "kernel_size": 3, "activation": "relu"},
                {"type": "lstm", "units": 64, "return_sequences": True},
                {"type": "lstm", "units": 32, "return_sequences": False},
                {"type": "dense", "units": 16, "activation": "relu"},
                {"type": "dense", "units": 5, "activation": "softmax"},
            ],
            learning_rate=0.001,
            loss="categorical_crossentropy",
        )

    def _build_network(self) -> None:
        """Build network from configuration."""
        self.layers = []
        seq_len, features = self.config.input_shape

        prev_size = features
        for i, layer_config in enumerate(self.config.layers):
            layer_type = layer_config.get("type", "dense")

            if layer_type == "conv":
                filters = layer_config.get("filters", 32)
                config = LayerConfig(
                    input_size=features,
                    output_size=filters,
                    activation=layer_config.get("activation", "relu"),
                )
                layer = ConvLayer(config)
                layer.kernel_size = layer_config.get("kernel_size", 3)
                layer.initialize()
                prev_size = filters

            elif layer_type == "lstm":
                units = layer_config.get("units", 64)
                config = LayerConfig(
                    input_size=prev_size,
                    output_size=units,
                    activation=layer_config.get("activation", "tanh"),
                )
                layer = LSTMLayer(config)
                layer.return_sequences = layer_config.get("return_sequences", True)
                layer.initialize()
                prev_size = units

            elif layer_type == "dense":
                units = layer_config.get("units", 32)
                is_output = i == len(self.config.layers) - 1
                config = LayerConfig(
                    input_size=prev_size,
                    output_size=units,
                    activation=layer_config.get(
                        "activation", "relu" if not is_output else "softmax"
                    ),
                )
                layer = DenseLayer(config)
                layer.initialize()
                prev_size = units

            elif layer_type == "dropout":
                rate = layer_config.get("rate", 0.5)
                layer = DropoutLayer(rate)

            else:
                raise ValueError(f"Unknown layer type: {layer_type}")

            self.layers.append(layer)

    def forward(self, x: np.ndarray, training: bool = False) -> np.ndarray:
        """Forward pass through all layers.

        Args:
            x: Input array of shape (batch, sequence, features)
            training: Whether in training mode (enables dropout)

        Returns:
            Network output
        """
        output = x
        for layer in self.layers:
            output = layer.forward(output, training=training)
        return output

    def backward(self, grad_output: np.ndarray) -> np.ndarray:
        """Backward pass through all layers.

        Args:
            grad_output: Gradient from loss function

        Returns:
            Gradient w.r.t. input
        """
        grad = grad_output
        for layer in reversed(self.layers):
            grad = layer.backward(grad, self.config.learning_rate)
        return grad

    def compute_loss(
        self,
        predictions: np.ndarray,
        targets: np.ndarray,
        loss_type: str | None = None,
    ) -> float:
        """Compute loss between predictions and targets.

        Args:
            predictions: Network predictions
            targets: Ground truth targets
            loss_type: Loss function type (overrides config)

        Returns:
            Loss value
        """
        loss_type = loss_type or self.config.loss

        if loss_type == "mse":
            return float(np.mean((predictions - targets) ** 2))
        elif loss_type == "mae":
            return float(np.mean(np.abs(predictions - targets)))
        elif loss_type == "categorical_crossentropy":
            # Clip to avoid log(0)
            eps = 1e-15
            predictions = np.clip(predictions, eps, 1 - eps)
            return float(-np.mean(targets * np.log(predictions)))
        elif loss_type == "binary_crossentropy":
            eps = 1e-15
            predictions = np.clip(predictions, eps, 1 - eps)
            return float(
                -np.mean(
                    targets * np.log(predictions)
                    + (1 - targets) * np.log(1 - predictions)
                )
            )
        else:
            raise ValueError(f"Unknown loss type: {loss_type}")

    def compute_loss_gradient(
        self,
        predictions: np.ndarray,
        targets: np.ndarray,
        loss_type: str | None = None,
    ) -> np.ndarray:
        """Compute gradient of loss w.r.t. predictions.

        Args:
            predictions: Network predictions
            targets: Ground truth targets
            loss_type: Loss function type

        Returns:
            Gradient array
        """
        loss_type = loss_type or self.config.loss

        if loss_type == "mse":
            return 2 * (predictions - targets) / predictions.size
        elif loss_type == "categorical_crossentropy":
            # Combined softmax + cross-entropy gradient
            return predictions - targets
        elif loss_type == "binary_crossentropy":
            eps = 1e-15
            predictions = np.clip(predictions, eps, 1 - eps)
            return (predictions - targets) / (predictions * (1 - predictions))
        else:
            return predictions - targets

    def fit(
        self,
        x: np.ndarray,
        y: np.ndarray,
        epochs: int = 100,
        batch_size: int = 32,
        validation_split: float = 0.1,
        verbose: bool = True,
        callbacks: list[Callable] | None = None,
    ) -> dict[str, list[float]]:
        """Train the network.

        Args:
            x: Training data
            y: Training labels
            epochs: Number of training epochs
            batch_size: Batch size for training
            validation_split: Fraction of data for validation
            verbose: Print progress
            callbacks: Optional callbacks

        Returns:
            Training history dictionary
        """
        n_samples = x.shape[0]
        n_val = int(n_samples * validation_split)
        n_train = n_samples - n_val

        # Shuffle data
        indices = np.random.permutation(n_samples)
        x_shuffled = x[indices]
        y_shuffled = y[indices]

        x_train, x_val = x_shuffled[:n_train], x_shuffled[n_train:]
        y_train, y_val = y_shuffled[:n_train], y_shuffled[n_train:]

        history = {"loss": [], "val_loss": []}

        for epoch in range(epochs):
            # Training
            train_loss = 0.0
            n_batches = int(np.ceil(n_train / batch_size))

            for i in range(n_batches):
                start = i * batch_size
                end = min(start + batch_size, n_train)

                x_batch = x_train[start:end]
                y_batch = y_train[start:end]

                # Forward pass
                predictions = self.forward(x_batch, training=True)

                # Compute loss
                loss = self.compute_loss(predictions, y_batch)
                train_loss += loss

                # Backward pass
                grad = self.compute_loss_gradient(predictions, y_batch)
                self.backward(grad)

            train_loss /= n_batches

            # Validation
            val_predictions = self.forward(x_val, training=False)
            val_loss = self.compute_loss(val_predictions, y_val)

            history["loss"].append(train_loss)
            history["val_loss"].append(val_loss)

            if verbose and (epoch + 1) % 10 == 0:
                print(
                    f"Epoch {epoch + 1}/{epochs} - loss: {train_loss:.4f} - val_loss: {val_loss:.4f}"
                )

            # Run callbacks
            if callbacks:
                for callback in callbacks:
                    callback(epoch, train_loss, val_loss)

        self.training_history = [
            {"epoch": i, "loss": loss_val, "val_loss": vl}
            for i, (loss_val, vl) in enumerate(
                zip(history["loss"], history["val_loss"], strict=False)
            )
        ]
        return history

    def predict(self, x: np.ndarray) -> np.ndarray:
        """Make predictions on input data.

        Args:
            x: Input data

        Returns:
            Network predictions
        """
        return self.forward(x, training=False)

    def predict_class(self, x: np.ndarray) -> np.ndarray:
        """Predict class labels.

        Args:
            x: Input data

        Returns:
            Predicted class indices
        """
        predictions = self.predict(x)
        return np.argmax(predictions, axis=-1)

    def evaluate(self, x: np.ndarray, y: np.ndarray) -> dict[str, float]:
        """Evaluate network performance.

        Args:
            x: Test data
            y: Test labels

        Returns:
            Dictionary of metrics
        """
        predictions = self.predict(x)
        loss = self.compute_loss(predictions, y)

        # For classification
        pred_classes = np.argmax(predictions, axis=-1)
        true_classes = np.argmax(y, axis=-1) if y.ndim > 1 else y
        accuracy = np.mean(pred_classes == true_classes)

        return {
            "loss": loss,
            "accuracy": accuracy,
        }

    def save(self, path: str | Path) -> None:
        """Save model weights and configuration.

        Args:
            path: Path to save model
        """
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)

        # Save configuration
        config_dict = {
            "input_shape": self.config.input_shape,
            "output_size": self.config.output_size,
            "layers": self.config.layers,
            "learning_rate": self.config.learning_rate,
            "loss": self.config.loss,
        }
        with open(path / "config.json", "w") as f:
            json.dump(config_dict, f, indent=2)

        # Save weights
        weights_dict = {}
        for i, layer in enumerate(self.layers):
            if hasattr(layer, "weights") and layer.weights is not None:
                weights_dict[f"layer_{i}_weights"] = layer.weights.tolist()
                if hasattr(layer, "bias") and layer.bias is not None:
                    weights_dict[f"layer_{i}_bias"] = layer.bias.tolist()

            # Save LSTM weights
            if isinstance(layer, LSTMLayer):
                for name in [
                    "Wf",
                    "Wi",
                    "Wc",
                    "Wo",
                    "Uf",
                    "Ui",
                    "Uc",
                    "Uo",
                    "bf",
                    "bi",
                    "bc",
                    "bo",
                ]:
                    attr = getattr(layer, name)
                    if attr is not None:
                        weights_dict[f"layer_{i}_{name}"] = attr.tolist()

        with open(path / "weights.json", "w") as f:
            json.dump(weights_dict, f)

    @classmethod
    def load(cls, path: str | Path) -> "NeuralNetwork":
        """Load model from saved state.

        Args:
            path: Path to saved model

        Returns:
            Loaded NeuralNetwork instance
        """
        path = Path(path)

        # Load configuration
        with open(path / "config.json") as f:
            config_dict = json.load(f)

        config = NetworkConfig(
            input_shape=tuple(config_dict["input_shape"]),
            output_size=config_dict["output_size"],
            layers=config_dict["layers"],
            learning_rate=config_dict["learning_rate"],
            loss=config_dict["loss"],
        )

        network = cls(config)

        # Load weights
        with open(path / "weights.json") as f:
            weights_dict = json.load(f)

        for i, layer in enumerate(network.layers):
            if hasattr(layer, "weights"):
                weights_key = f"layer_{i}_weights"
                bias_key = f"layer_{i}_bias"
                if weights_key in weights_dict:
                    layer.weights = np.array(weights_dict[weights_key])
                if bias_key in weights_dict:
                    layer.bias = np.array(weights_dict[bias_key])

            # Load LSTM weights
            if isinstance(layer, LSTMLayer):
                for name in [
                    "Wf",
                    "Wi",
                    "Wc",
                    "Wo",
                    "Uf",
                    "Ui",
                    "Uc",
                    "Uo",
                    "bf",
                    "bi",
                    "bc",
                    "bo",
                ]:
                    key = f"layer_{i}_{name}"
                    if key in weights_dict:
                        setattr(layer, name, np.array(weights_dict[key]))

        return network

    def summary(self) -> str:
        """Get network architecture summary.

        Returns:
            String summary of network architecture
        """
        lines = ["Neural Network Architecture", "=" * 40]
        lines.append(f"Input shape: {self.config.input_shape}")
        lines.append(f"Output size: {self.config.output_size}")
        lines.append(f"Learning rate: {self.config.learning_rate}")
        lines.append(f"Loss function: {self.config.loss}")
        lines.append("")
        lines.append("Layers:")

        total_params = 0
        for i, layer in enumerate(self.layers):
            layer_type = type(layer).__name__
            params = 0

            if hasattr(layer, "weights") and layer.weights is not None:
                params += layer.weights.size
            if hasattr(layer, "bias") and layer.bias is not None:
                params += layer.bias.size

            if isinstance(layer, LSTMLayer):
                for name in ["Wf", "Wi", "Wc", "Wo", "Uf", "Ui", "Uc", "Uo"]:
                    attr = getattr(layer, name)
                    if attr is not None:
                        params += attr.size
                for name in ["bf", "bi", "bc", "bo"]:
                    attr = getattr(layer, name)
                    if attr is not None:
                        params += attr.size

            total_params += params
            lines.append(f"  {i + 1}. {layer_type}: {params:,} parameters")

        lines.append("")
        lines.append(f"Total parameters: {total_params:,}")
        return "\n".join(lines)
