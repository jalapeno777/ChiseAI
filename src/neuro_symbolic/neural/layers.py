"""
Neural network layer implementations.

Provides Conv1D, LSTM, and Dense layers for time series pattern recognition.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np

from src.neuro_symbolic.neural.activations import get_activation


@dataclass
class LayerConfig:
    """Configuration for neural network layers."""

    input_size: int
    output_size: int
    activation: str = "relu"
    use_bias: bool = True
    dropout_rate: float = 0.0


class BaseLayer(ABC):
    """Abstract base class for neural network layers."""

    def __init__(self, config: LayerConfig):
        self.config = config
        self.weights: np.ndarray | None = None
        self.bias: np.ndarray | None = None
        self.activation_fn, self.activation_deriv = get_activation(config.activation)
        self._initialized = False

    @abstractmethod
    def initialize(self, seed: int | None = None) -> None:
        """Initialize layer weights."""
        pass

    @abstractmethod
    def forward(self, x: np.ndarray, training: bool = False) -> np.ndarray:
        """Forward pass through the layer."""
        pass

    @abstractmethod
    def backward(self, grad_output: np.ndarray, learning_rate: float) -> np.ndarray:
        """Backward pass for gradient computation."""
        pass

    def get_weights(self) -> tuple[np.ndarray | None, np.ndarray | None]:
        """Get layer weights and bias."""
        return self.weights, self.bias

    def set_weights(self, weights: np.ndarray, bias: np.ndarray | None = None) -> None:
        """Set layer weights and bias."""
        self.weights = weights
        self.bias = bias
        self._initialized = True


class DenseLayer(BaseLayer):
    """Fully connected (dense) layer."""

    def __init__(self, config: LayerConfig):
        super().__init__(config)
        self.last_input: np.ndarray | None = None
        self.last_activation: np.ndarray | None = None

    def initialize(self, seed: int | None = None) -> None:
        """Initialize weights using Xavier/Glorot initialization."""
        if seed is not None:
            np.random.seed(seed)

        # Xavier initialization for sigmoid/tanh, He for ReLU
        if self.config.activation in ("relu", "leaky_relu"):
            scale = np.sqrt(2.0 / self.config.input_size)
        else:
            scale = np.sqrt(2.0 / (self.config.input_size + self.config.output_size))

        self.weights = (
            np.random.randn(self.config.input_size, self.config.output_size) * scale
        )

        if self.config.use_bias:
            self.bias = np.zeros((1, self.config.output_size))

        self._initialized = True

    def forward(self, x: np.ndarray, training: bool = False) -> np.ndarray:
        """Forward pass: y = activation(x @ W + b)."""
        if not self._initialized:
            self.initialize()

        self.last_input = x
        z = np.dot(x, self.weights)
        if self.config.use_bias:
            z = z + self.bias

        self.last_activation = self.activation_fn(z)
        return self.last_activation

    def backward(self, grad_output: np.ndarray, learning_rate: float) -> np.ndarray:
        """Backward pass with gradient descent update."""
        # Gradient through activation
        if self.config.activation != "softmax":
            grad_activation = grad_output * self.activation_deriv(self.last_activation)
        else:
            grad_activation = grad_output

        # Gradient w.r.t. weights
        grad_weights = np.dot(self.last_input.T, grad_activation)

        # Gradient w.r.t. bias
        grad_bias = None
        if self.config.use_bias:
            grad_bias = np.sum(grad_activation, axis=0, keepdims=True)

        # Gradient w.r.t. input
        grad_input = np.dot(grad_activation, self.weights.T)

        # Update weights
        self.weights -= learning_rate * grad_weights
        if self.config.use_bias and grad_bias is not None:
            self.bias -= learning_rate * grad_bias

        return grad_input


class ConvLayer(BaseLayer):
    """1D Convolutional layer for time series processing."""

    def __init__(self, config: LayerConfig):
        # For conv: input_size = input_channels, output_size = filters
        super().__init__(config)
        self.kernel_size: int = 3  # Default kernel size
        self.stride: int = 1
        self.padding: str = "same"
        self.last_input: np.ndarray | None = None
        self.last_collected_inputs: np.ndarray | None = None

    def initialize(self, seed: int | None = None) -> None:
        """Initialize convolutional filters."""
        if seed is not None:
            np.random.seed(seed)

        # He initialization for ReLU
        scale = np.sqrt(2.0 / (self.kernel_size * self.config.input_size))

        # Shape: (kernel_size, input_channels, filters)
        self.weights = (
            np.random.randn(
                self.kernel_size, self.config.input_size, self.config.output_size
            )
            * scale
        )

        if self.config.use_bias:
            self.bias = np.zeros((1, self.config.output_size))

        self._initialized = True

    def _collect_patches(self, x: np.ndarray) -> np.ndarray:
        """Collect sliding window patches from input."""
        batch_size, seq_len, channels = x.shape

        if self.padding == "same":
            pad_size = (self.kernel_size - 1) // 2
            x_padded = np.pad(x, ((0, 0), (pad_size, pad_size), (0, 0)), mode="edge")
        else:
            x_padded = x

        output_len = (
            seq_len + (2 * pad_size if self.padding == "same" else 0) - self.kernel_size
        ) // self.stride + 1

        patches = []
        for i in range(0, output_len * self.stride, self.stride):
            patch = x_padded[:, i : i + self.kernel_size, :]
            patches.append(patch)

        return np.array(patches)  # Shape: (output_len, batch, kernel, channels)

    def forward(self, x: np.ndarray, training: bool = False) -> np.ndarray:
        """Forward pass: apply convolution and activation."""
        if not self._initialized:
            self.initialize()

        self.last_input = x
        patches = self._collect_patches(x)
        self.last_collected_inputs = patches

        # Convolution: patches @ weights + bias
        # patches: (output_len, batch, kernel, channels)
        # weights: (kernel, channels, filters)
        output = np.einsum("lbkc,kcf->lbf", patches, self.weights)

        if self.config.use_bias:
            output = output + self.bias

        # Apply activation
        output = self.activation_fn(output)

        # Transpose to (batch, output_len, filters)
        return np.transpose(output, (1, 0, 2))

    def backward(self, grad_output: np.ndarray, learning_rate: float) -> np.ndarray:
        """Backward pass for convolution."""
        # Simplified gradient computation
        # grad_output shape: (batch, output_len, filters)

        batch_size, output_len, _ = grad_output.shape

        # Gradient through activation
        grad_activation = grad_output  # Simplified for now

        # Compute gradient w.r.t. filters
        # This is a simplified version
        grad_weights = np.zeros_like(self.weights)

        for t in range(output_len):
            for b in range(batch_size):
                patch = self.last_collected_inputs[t, b]  # (kernel, channels)
                grad = grad_activation[b, t]  # (filters,)
                grad_weights += np.einsum("kc,f->kcf", patch, grad)

        grad_weights /= batch_size

        # Update weights
        self.weights -= learning_rate * grad_weights

        if self.config.use_bias:
            grad_bias = np.sum(grad_activation, axis=(0, 1), keepdims=True)
            self.bias -= learning_rate * grad_bias

        # Gradient w.r.t. input (simplified)
        grad_input = np.zeros_like(self.last_input)
        for t in range(output_len):
            for b in range(batch_size):
                grad = grad_activation[b, t]
                grad_contribution = np.einsum("kcf,f->kc", self.weights, grad)
                start_idx = t * self.stride
                end_idx = start_idx + self.kernel_size
                if self.padding == "same":
                    pad_size = (self.kernel_size - 1) // 2
                    start_idx = max(0, start_idx - pad_size)
                    end_idx = min(self.last_input.shape[1], end_idx - pad_size)
                grad_input[b, start_idx:end_idx] += grad_contribution[
                    : end_idx - start_idx
                ]

        return grad_input


class LSTMLayer(BaseLayer):
    """LSTM layer for sequential pattern learning."""

    def __init__(self, config: LayerConfig):
        super().__init__(config)
        self.return_sequences: bool = True
        self.hidden_state: np.ndarray | None = None
        self.cell_state: np.ndarray | None = None

        # LSTM gates: forget, input, candidate, output
        self.Wf: np.ndarray | None = None  # Forget gate weights
        self.Wi: np.ndarray | None = None  # Input gate weights
        self.Wc: np.ndarray | None = None  # Candidate weights
        self.Wo: np.ndarray | None = None  # Output gate weights

        self.Uf: np.ndarray | None = None  # Forget gate recurrent weights
        self.Ui: np.ndarray | None = None  # Input gate recurrent weights
        self.Uc: np.ndarray | None = None  # Candidate recurrent weights
        self.Uo: np.ndarray | None = None  # Output gate recurrent weights

        self.bf: np.ndarray | None = None
        self.bi: np.ndarray | None = None
        self.bc: np.ndarray | None = None
        self.bo: np.ndarray | None = None

        self.cache: dict = {}

    def initialize(self, seed: int | None = None) -> None:
        """Initialize LSTM weights."""
        if seed is not None:
            np.random.seed(seed)

        hidden_size = self.config.output_size
        input_size = self.config.input_size

        # Xavier initialization
        scale = np.sqrt(2.0 / (input_size + hidden_size))

        # Input weights
        self.Wf = np.random.randn(input_size, hidden_size) * scale
        self.Wi = np.random.randn(input_size, hidden_size) * scale
        self.Wc = np.random.randn(input_size, hidden_size) * scale
        self.Wo = np.random.randn(input_size, hidden_size) * scale

        # Recurrent weights
        self.Uf = np.random.randn(hidden_size, hidden_size) * scale
        self.Ui = np.random.randn(hidden_size, hidden_size) * scale
        self.Uc = np.random.randn(hidden_size, hidden_size) * scale
        self.Uo = np.random.randn(hidden_size, hidden_size) * scale

        # Biases
        if self.config.use_bias:
            self.bf = np.zeros((1, hidden_size))
            self.bi = np.zeros((1, hidden_size))
            self.bc = np.zeros((1, hidden_size))
            self.bo = np.zeros((1, hidden_size))

        self._initialized = True

    def _sigmoid(self, x: np.ndarray) -> np.ndarray:
        """Numerically stable sigmoid."""
        return np.where(
            x >= 0,
            1 / (1 + np.exp(-x)),
            np.exp(x) / (1 + np.exp(x)),
        )

    def forward(self, x: np.ndarray, training: bool = False) -> np.ndarray:
        """Forward pass through LSTM."""
        if not self._initialized:
            self.initialize()

        batch_size, seq_len, _ = x.shape
        hidden_size = self.config.output_size

        # Initialize states
        h = np.zeros((batch_size, hidden_size))
        c = np.zeros((batch_size, hidden_size))

        outputs = []
        self.cache = {
            "inputs": [],
            "hiddens": [h.copy()],
            "cells": [c.copy()],
            "gates": [],
        }

        for t in range(seq_len):
            xt = x[:, t, :]

            # Gates
            ft = self._sigmoid(xt @ self.Wf + h @ self.Uf + self.bf)
            it = self._sigmoid(xt @ self.Wi + h @ self.Ui + self.bi)
            ct_tilde = np.tanh(xt @ self.Wc + h @ self.Uc + self.bc)
            ot = self._sigmoid(xt @ self.Wo + h @ self.Uo + self.bo)

            # Cell state update
            c = ft * c + it * ct_tilde

            # Hidden state update
            h = ot * np.tanh(c)

            outputs.append(h.copy())
            self.cache["inputs"].append(xt.copy())
            self.cache["hiddens"].append(h.copy())
            self.cache["cells"].append(c.copy())
            self.cache["gates"].append(
                (ft.copy(), it.copy(), ct_tilde.copy(), ot.copy())
            )

        if self.return_sequences:
            return np.stack(outputs, axis=1)  # (batch, seq, hidden)
        else:
            return h  # (batch, hidden)

    def backward(self, grad_output: np.ndarray, learning_rate: float) -> np.ndarray:
        """Backward pass through LSTM (simplified for training)."""
        batch_size = grad_output.shape[0]
        seq_len = len(self.cache["inputs"])
        input_size = self.config.input_size
        hidden_size = self.config.output_size

        # Initialize gradients
        dWf = np.zeros_like(self.Wf)
        dWi = np.zeros_like(self.Wi)
        dWc = np.zeros_like(self.Wc)
        dWo = np.zeros_like(self.Wo)

        dUf = np.zeros_like(self.Uf)
        dUi = np.zeros_like(self.Ui)
        dUc = np.zeros_like(self.Uc)
        dUo = np.zeros_like(self.Uo)

        dbf = np.zeros_like(self.bf)
        dbi = np.zeros_like(self.bi)
        dbc = np.zeros_like(self.bc)
        dbo = np.zeros_like(self.bo)

        dh_next = np.zeros((batch_size, hidden_size))
        dc_next = np.zeros((batch_size, hidden_size))

        grad_input = np.zeros((batch_size, seq_len, input_size))

        for t in reversed(range(seq_len)):
            ft, it, ct_tilde, ot = self.cache["gates"][t]
            xt = self.cache["inputs"][t]
            h_prev = self.cache["hiddens"][t]
            c_prev = self.cache["cells"][t]
            c = self.cache["cells"][t + 1]

            # Get gradient
            if self.return_sequences:
                dh = grad_output[:, t, :] + dh_next
            elif t == seq_len - 1:
                dh = grad_output + dh_next
            else:
                dh = dh_next

            dc = dc_next + dh * ot * (1 - np.tanh(c) ** 2)

            # Gate gradients
            dft = dc * c_prev * ft * (1 - ft)
            dit = dc * ct_tilde * it * (1 - it)
            dct = dc * it * (1 - ct_tilde**2)
            dot = dh * np.tanh(c) * ot * (1 - ot)

            # Weight gradients
            dWf += xt.T @ dft
            dWi += xt.T @ dit
            dWc += xt.T @ dct
            dWo += xt.T @ dot

            dUf += h_prev.T @ dft
            dUi += h_prev.T @ dit
            dUc += h_prev.T @ dct
            dUo += h_prev.T @ dot

            dbf += np.sum(dft, axis=0, keepdims=True)
            dbi += np.sum(dit, axis=0, keepdims=True)
            dbc += np.sum(dct, axis=0, keepdims=True)
            dbo += np.sum(dot, axis=0, keepdims=True)

            # Input gradient
            grad_input[:, t, :] = (
                dft @ self.Wf.T + dit @ self.Wi.T + dct @ self.Wc.T + dot @ self.Wo.T
            )

            # Next iteration gradients
            dh_next = (
                dft @ self.Uf.T + dit @ self.Ui.T + dct @ self.Uc.T + dot @ self.Uo.T
            )
            dc_next = dc * ft

        # Update weights
        self.Wf -= learning_rate * dWf / batch_size
        self.Wi -= learning_rate * dWi / batch_size
        self.Wc -= learning_rate * dWc / batch_size
        self.Wo -= learning_rate * dWo / batch_size

        self.Uf -= learning_rate * dUf / batch_size
        self.Ui -= learning_rate * dUi / batch_size
        self.Uc -= learning_rate * dUc / batch_size
        self.Uo -= learning_rate * dUo / batch_size

        if self.config.use_bias:
            self.bf -= learning_rate * dbf / batch_size
            self.bi -= learning_rate * dbi / batch_size
            self.bc -= learning_rate * dbc / batch_size
            self.bo -= learning_rate * dbo / batch_size

        return grad_input

    def reset_states(self) -> None:
        """Reset hidden and cell states."""
        self.hidden_state = None
        self.cell_state = None


class DropoutLayer(BaseLayer):
    """Dropout layer for regularization."""

    def __init__(self, rate: float = 0.5):
        config = LayerConfig(input_size=1, output_size=1)  # Placeholder
        super().__init__(config)
        self.rate = rate
        self.mask: np.ndarray | None = None

    def initialize(self, seed: int | None = None) -> None:
        """Dropout doesn't have weights."""
        self._initialized = True

    def forward(self, x: np.ndarray, training: bool = False) -> np.ndarray:
        """Apply dropout mask during training."""
        if training and self.rate > 0:
            self.mask = (np.random.random(x.shape) > self.rate).astype(float)
            self.mask /= 1 - self.rate  # Scale to maintain expected value
            return x * self.mask
        return x

    def backward(self, grad_output: np.ndarray, learning_rate: float) -> np.ndarray:
        """Backward pass applies the same mask."""
        if self.mask is not None:
            return grad_output * self.mask
        return grad_output
