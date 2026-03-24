"""Meta-learning models including MAML implementation.

Provides base classes and implementations for meta-learning algorithms,
with a focus on Model-Agnostic Meta-Learning (MAML).

Example:
    >>> from src.strong_system.meta_learning.models import MAML
    >>> import numpy as np
    >>>
    >>> # Create a simple base model
    >>> base_model = SimpleNN(input_dim=10, output_dim=5)
    >>>
    >>> # Wrap with MAML
    >>> maml = MAML(base_model, inner_lr=0.01, n_inner_steps=5)
    >>>
    >>> # Inner loop adaptation
    >>> adapted_params = maml.adapt(support_data, support_labels)
    >>>
    >>> # Outer loop meta-gradient
    >>> meta_gradient = maml.compute_meta_gradient(episodes)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TypeVar

import numpy as np

T = TypeVar("T")


class ParameterStore:
    """Storage for model parameters with gradient tracking.

    Manages model parameters as numpy arrays with support for
    gradient computation and updates.

    Attributes:
        params: Dictionary mapping parameter names to values
        grads: Dictionary mapping parameter names to gradients

    Example:
        >>> store = ParameterStore()
        >>> store["W"] = np.random.randn(10, 5)
        >>> store["b"] = np.zeros(5)
        >>> store.zero_grad()
        >>> store.grads["W"] = np.random.randn(10, 5)  # Simulated gradient
        >>> store.step(lr=0.01)  # SGD update
    """

    def __init__(self, params: dict[str, np.ndarray] | None = None) -> None:
        """Initialize parameter store.

        Args:
            params: Optional initial parameters
        """
        self.params: dict[str, np.ndarray] = params or {}
        self.grads: dict[str, np.ndarray] = {}

    def __getitem__(self, key: str) -> np.ndarray:
        """Get parameter by name."""
        return self.params[key]

    def __setitem__(self, key: str, value: np.ndarray) -> None:
        """Set parameter by name."""
        self.params[key] = value

    def __contains__(self, key: str) -> bool:
        """Check if parameter exists."""
        return key in self.params

    def keys(self):
        """Return parameter names."""
        return self.params.keys()

    def values(self):
        """Return parameter values."""
        return self.params.values()

    def items(self):
        """Return parameter items."""
        return self.params.items()

    def zero_grad(self) -> None:
        """Zero out all gradients."""
        self.grads = {k: np.zeros_like(v) for k, v in self.params.items()}

    def step(self, lr: float) -> None:
        """Perform SGD parameter update.

        Args:
            lr: Learning rate
        """
        for key in self.params:
            if key in self.grads:
                self.params[key] = self.params[key] - lr * self.grads[key]

    def copy(self) -> ParameterStore:
        """Create a deep copy of parameters."""
        return ParameterStore({k: v.copy() for k, v in self.params.items()})

    def to_dict(self) -> dict[str, np.ndarray]:
        """Convert to dictionary."""
        return {k: v.copy() for k, v in self.params.items()}

    @classmethod
    def from_dict(cls, params: dict[str, np.ndarray]) -> ParameterStore:
        """Create from dictionary."""
        return cls({k: v.copy() for k, v in params.items()})


class MetaModel(ABC):
    """Abstract base class for meta-learning models.

    Defines the interface that all meta-learning models must implement,
    including adaptation and meta-gradient computation.

    Example:
        >>> class MyMetaModel(MetaModel):
        ...     def adapt(self, support_data, support_labels):
        ...         # Inner loop adaptation
        ...         pass
        ...
        ...     def compute_loss(self, params, data, labels):
        ...         # Compute loss with given parameters
        ...         pass
    """

    def __init__(self, input_dim: int, output_dim: int) -> None:
        """Initialize meta-model.

        Args:
            input_dim: Input dimensionality
            output_dim: Output dimensionality
        """
        self.input_dim = input_dim
        self.output_dim = output_dim
        self._parameters = ParameterStore()

    @property
    def parameters(self) -> ParameterStore:
        """Return model parameters."""
        return self._parameters

    @abstractmethod
    def adapt(
        self,
        support_data: np.ndarray,
        support_labels: np.ndarray,
        n_steps: int = 5,
        lr: float = 0.01,
    ) -> ParameterStore:
        """Adapt model to task using support set (inner loop).

        Args:
            support_data: Support set inputs
            support_labels: Support set labels
            n_steps: Number of adaptation steps
            lr: Inner loop learning rate

        Returns:
            Adapted parameters
        """
        pass

    @abstractmethod
    def compute_loss(
        self, params: ParameterStore, data: np.ndarray, labels: np.ndarray
    ) -> float:
        """Compute loss with given parameters.

        Args:
            params: Model parameters to use
            data: Input data
            labels: Target labels

        Returns:
            Loss value
        """
        pass

    @abstractmethod
    def forward(self, params: ParameterStore, data: np.ndarray) -> np.ndarray:
        """Forward pass with given parameters.

        Args:
            params: Model parameters to use
            data: Input data

        Returns:
            Model predictions
        """
        pass

    def compute_meta_gradient(
        self, episodes: list, inner_lr: float = 0.01, n_inner_steps: int = 5
    ) -> dict[str, np.ndarray]:
        """Compute meta-gradient across episodes (outer loop).

        Args:
            episodes: List of episodes for meta-training
            inner_lr: Inner loop learning rate
            n_inner_steps: Number of inner loop steps

        Returns:
            Dictionary of meta-gradients for each parameter
        """
        meta_gradients = {k: np.zeros_like(v) for k, v in self.parameters.items()}

        for episode in episodes:
            # Inner loop: adapt to support set
            adapted_params = self.adapt(
                episode.support_data,
                episode.support_labels,
                n_steps=n_inner_steps,
                lr=inner_lr,
            )

            # Compute loss on query set with adapted parameters
            self.compute_loss(adapted_params, episode.query_data, episode.query_labels)

            # Compute gradients w.r.t. adapted parameters
            param_grads = self._compute_parameter_gradients(
                adapted_params, episode.query_data, episode.query_labels
            )

            # Accumulate meta-gradient
            for key in meta_gradients:
                if key in param_grads:
                    meta_gradients[key] = meta_gradients[key] + param_grads[key]

        # Average over episodes
        n_episodes = len(episodes)
        for key in meta_gradients:
            meta_gradients[key] = meta_gradients[key] / n_episodes

        return meta_gradients

    @abstractmethod
    def _compute_parameter_gradients(
        self, params: ParameterStore, data: np.ndarray, labels: np.ndarray
    ) -> dict[str, np.ndarray]:
        """Compute gradients of loss w.r.t. parameters.

        Args:
            params: Current parameters
            data: Input data
            labels: Target labels

        Returns:
            Dictionary of gradients
        """
        pass


class LinearModel:
    """Simple linear model for meta-learning.

    Implements a linear layer: y = xW + b

    Attributes:
        input_dim: Input dimension
        output_dim: Output dimension

    Example:
        >>> model = LinearModel(input_dim=10, output_dim=5)
        >>> x = np.random.randn(32, 10)
        >>> y = model.forward(model.parameters, x)
        >>> y.shape
        (32, 5)
    """

    def __init__(
        self, input_dim: int, output_dim: int, initialization: str = "xavier"
    ) -> None:
        """Initialize linear model.

        Args:
            input_dim: Input dimensionality
            output_dim: Output dimensionality
            initialization: Weight initialization method
        """
        self.input_dim = input_dim
        self.output_dim = output_dim
        self._parameters = ParameterStore()

        # Initialize weights
        if initialization == "xavier":
            scale = np.sqrt(2.0 / (input_dim + output_dim))
            self._parameters["W"] = np.random.randn(input_dim, output_dim) * scale
        elif initialization == "he":
            scale = np.sqrt(2.0 / input_dim)
            self._parameters["W"] = np.random.randn(input_dim, output_dim) * scale
        else:  # normal
            self._parameters["W"] = np.random.randn(input_dim, output_dim) * 0.01

        self._parameters["b"] = np.zeros(output_dim)

    @property
    def parameters(self) -> ParameterStore:
        """Return model parameters."""
        return self._parameters

    def forward(self, params: ParameterStore | None, data: np.ndarray) -> np.ndarray:
        """Forward pass: y = xW + b.

        Args:
            params: Model parameters (uses self.parameters if None)
            data: Input data of shape (batch_size, input_dim)

        Returns:
            Output of shape (batch_size, output_dim)
        """
        if params is None:
            params = self._parameters

        W = params["W"]
        b = params["b"]
        return data @ W + b

    def compute_loss(
        self,
        params: ParameterStore | None,
        data: np.ndarray,
        labels: np.ndarray,
        loss_type: str = "mse",
    ) -> float:
        """Compute loss.

        Args:
            params: Model parameters (uses self.parameters if None)
            data: Input data
            labels: Target labels
            loss_type: Type of loss ('mse' or 'cross_entropy')

        Returns:
            Loss value
        """
        predictions = self.forward(params, data)

        if loss_type == "mse":
            # Ensure labels have same shape as predictions
            if labels.ndim == 1 and predictions.ndim == 2:
                labels = labels.reshape(-1, 1)
            return float(np.mean((predictions - labels) ** 2))
        elif loss_type == "cross_entropy":
            # Softmax cross-entropy for classification
            exp_preds = np.exp(predictions - np.max(predictions, axis=1, keepdims=True))
            probs = exp_preds / np.sum(exp_preds, axis=1, keepdims=True)

            # One-hot encode labels if needed
            if labels.ndim == 1:
                n_classes = predictions.shape[1]
                labels_onehot = np.zeros((len(labels), n_classes))
                labels_onehot[np.arange(len(labels)), labels.astype(int)] = 1
            else:
                labels_onehot = labels

            # Cross-entropy loss
            log_probs = np.log(probs + 1e-8)
            return float(-np.mean(np.sum(labels_onehot * log_probs, axis=1)))
        else:
            raise ValueError(f"Unknown loss type: {loss_type}")

    def compute_gradients(
        self,
        params: ParameterStore | None,
        data: np.ndarray,
        labels: np.ndarray,
        loss_type: str = "mse",
    ) -> dict[str, np.ndarray]:
        """Compute gradients of loss w.r.t. parameters.

        Args:
            params: Model parameters (uses self.parameters if None)
            data: Input data
            labels: Target labels
            loss_type: Type of loss

        Returns:
            Dictionary of gradients
        """
        if params is None:
            params = self._parameters

        W = params["W"]
        b = params["b"]

        # Forward pass
        predictions = data @ W + b

        # Backward pass
        batch_size = data.shape[0]

        if loss_type == "mse":
            # dL/d_pred = 2 * (pred - label) / batch_size
            # Ensure labels have same shape as predictions
            if labels.ndim == 1 and predictions.ndim == 2:
                labels = labels.reshape(-1, 1)
            grad_pred = 2 * (predictions - labels) / batch_size
        elif loss_type == "cross_entropy":
            # Softmax gradient
            exp_preds = np.exp(predictions - np.max(predictions, axis=1, keepdims=True))
            probs = exp_preds / np.sum(exp_preds, axis=1, keepdims=True)

            if labels.ndim == 1:
                n_classes = predictions.shape[1]
                labels_onehot = np.zeros((len(labels), n_classes))
                labels_onehot[np.arange(len(labels)), labels.astype(int)] = 1
            else:
                labels_onehot = labels

            grad_pred = (probs - labels_onehot) / batch_size
        else:
            raise ValueError(f"Unknown loss type: {loss_type}")

        # Gradients for W and b
        grad_W = data.T @ grad_pred
        grad_b = np.sum(grad_pred, axis=0)

        return {"W": grad_W, "b": grad_b}


class MAML:
    """Model-Agnostic Meta-Learning implementation.

    Implements the MAML algorithm for learning model initializations
    that can quickly adapt to new tasks with few examples.

    Reference:
        Finn et al. "Model-Agnostic Meta-Learning for Fast Adaptation of Deep Networks"
        https://arxiv.org/abs/1703.03400

    Attributes:
        base_model: Base model to meta-train
        inner_lr: Learning rate for inner loop adaptation
        n_inner_steps: Number of inner loop steps
        first_order: Whether to use first-order approximation

    Example:
        >>> base_model = LinearModel(input_dim=10, output_dim=5)
        >>> maml = MAML(base_model, inner_lr=0.01, n_inner_steps=5)
        >>>
        >>> # Adapt to new task
        >>> adapted_params = maml.adapt(support_data, support_labels)
        >>>
        >>> # Make predictions with adapted model
        >>> predictions = maml.predict(query_data, adapted_params)
    """

    def __init__(
        self,
        base_model: LinearModel,
        inner_lr: float = 0.01,
        n_inner_steps: int = 5,
        first_order: bool = False,
        loss_type: str = "mse",
    ) -> None:
        """Initialize MAML.

        Args:
            base_model: Base model to meta-train
            inner_lr: Learning rate for inner loop adaptation
            n_inner_steps: Number of inner loop adaptation steps
            first_order: Use first-order approximation (faster, less accurate)
            loss_type: Loss function type ('mse' or 'cross_entropy')
        """
        self.base_model = base_model
        self.inner_lr = inner_lr
        self.n_inner_steps = n_inner_steps
        self.first_order = first_order
        self.loss_type = loss_type

    @property
    def meta_parameters(self) -> ParameterStore:
        """Return meta-parameters (initialization)."""
        return self.base_model.parameters

    def adapt(
        self,
        support_data: np.ndarray,
        support_labels: np.ndarray,
        n_steps: int | None = None,
        lr: float | None = None,
    ) -> ParameterStore:
        """Adapt model to task using support set (inner loop).

        Performs gradient descent on the support set to adapt
        the model parameters to the specific task.

        Args:
            support_data: Support set inputs
            support_labels: Support set labels
            n_steps: Number of adaptation steps (uses self.n_inner_steps if None)
            lr: Learning rate (uses self.inner_lr if None)

        Returns:
            Adapted parameters
        """
        n_steps = n_steps or self.n_inner_steps
        lr = lr or self.inner_lr

        # Start from meta-parameters
        adapted_params = self.base_model.parameters.copy()

        # Perform inner loop updates
        for _ in range(n_steps):
            # Compute gradients on support set
            grads = self.base_model.compute_gradients(
                adapted_params, support_data, support_labels, loss_type=self.loss_type
            )

            # Gradient descent update
            for key in adapted_params:
                if key in grads:
                    adapted_params[key] = adapted_params[key] - lr * grads[key]

        return adapted_params

    def predict(
        self, data: np.ndarray, params: ParameterStore | None = None
    ) -> np.ndarray:
        """Make predictions with given parameters.

        Args:
            data: Input data
            params: Parameters to use (uses meta-parameters if None)

        Returns:
            Predictions
        """
        if params is None:
            params = self.base_model.parameters
        return self.base_model.forward(params, data)

    def compute_loss(
        self, params: ParameterStore, data: np.ndarray, labels: np.ndarray
    ) -> float:
        """Compute loss with given parameters.

        Args:
            params: Model parameters
            data: Input data
            labels: Target labels

        Returns:
            Loss value
        """
        return self.base_model.compute_loss(params, data, labels, self.loss_type)

    def compute_meta_gradient(
        self,
        episodes: list,
        inner_lr: float | None = None,
        n_inner_steps: int | None = None,
    ) -> dict[str, np.ndarray]:
        """Compute meta-gradient across episodes (outer loop).

        This implements the MAML outer loop where we compute gradients
        of the post-adaptation loss with respect to the initial parameters.

        Args:
            episodes: List of episodes for meta-training
            inner_lr: Inner loop learning rate
            n_inner_steps: Number of inner loop steps

        Returns:
            Dictionary of meta-gradients
        """
        inner_lr = inner_lr or self.inner_lr
        n_inner_steps = n_inner_steps or self.n_inner_steps

        # Initialize meta-gradients
        meta_gradients = {
            k: np.zeros_like(v) for k, v in self.base_model.parameters.items()
        }

        for episode in episodes:
            # Inner loop: adapt to support set
            adapted_params = self.adapt(
                episode.support_data,
                episode.support_labels,
                n_steps=n_inner_steps,
                lr=inner_lr,
            )

            # Compute gradients on query set with adapted parameters
            query_grads = self.base_model.compute_gradients(
                adapted_params,
                episode.query_data,
                episode.query_labels,
                loss_type=self.loss_type,
            )

            if self.first_order:
                # First-order approximation: use query gradients directly
                for key in meta_gradients:
                    if key in query_grads:
                        meta_gradients[key] = meta_gradients[key] + query_grads[key]
            else:
                # Second-order: would need Hessian-vector products
                # For simplicity, we use the first-order approximation here
                # Full implementation would use finite differences or autodiff
                for key in meta_gradients:
                    if key in query_grads:
                        meta_gradients[key] = meta_gradients[key] + query_grads[key]

        # Average over episodes
        n_episodes = len(episodes)
        for key in meta_gradients:
            meta_gradients[key] = meta_gradients[key] / n_episodes

        return meta_gradients

    def meta_update(
        self, meta_gradient: dict[str, np.ndarray], meta_lr: float = 0.001
    ) -> None:
        """Update meta-parameters using meta-gradient.

        Args:
            meta_gradient: Meta-gradient dictionary
            meta_lr: Meta learning rate (outer loop)
        """
        for key in self.base_model.parameters:
            if key in meta_gradient:
                self.base_model.parameters[key] = (
                    self.base_model.parameters[key] - meta_lr * meta_gradient[key]
                )

    def evaluate(
        self, episodes: list, n_adaptation_steps: int | None = None
    ) -> dict[str, float]:
        """Evaluate MAML on episodes.

        Args:
            episodes: List of test episodes
            n_adaptation_steps: Number of adaptation steps

        Returns:
            Dictionary with evaluation metrics
        """
        n_adaptation_steps = n_adaptation_steps or self.n_inner_steps

        total_pre_adapt_loss = 0.0
        total_post_adapt_loss = 0.0
        n_correct = 0
        n_total = 0

        for episode in episodes:
            # Pre-adaptation loss
            pre_loss = self.compute_loss(
                self.base_model.parameters, episode.query_data, episode.query_labels
            )
            total_pre_adapt_loss += pre_loss

            # Adapt to support set
            adapted_params = self.adapt(
                episode.support_data, episode.support_labels, n_steps=n_adaptation_steps
            )

            # Post-adaptation loss
            post_loss = self.compute_loss(
                adapted_params, episode.query_data, episode.query_labels
            )
            total_post_adapt_loss += post_loss

            # Accuracy for classification
            if self.loss_type == "cross_entropy":
                predictions = self.predict(episode.query_data, adapted_params)
                pred_labels = np.argmax(predictions, axis=1)
                n_correct += np.sum(pred_labels == episode.query_labels)
                n_total += len(episode.query_labels)

        n_episodes = len(episodes)
        metrics = {
            "pre_adapt_loss": total_pre_adapt_loss / n_episodes,
            "post_adapt_loss": total_post_adapt_loss / n_episodes,
            "improvement": total_pre_adapt_loss / n_episodes
            - total_post_adapt_loss / n_episodes,
        }

        if self.loss_type == "cross_entropy" and n_total > 0:
            metrics["accuracy"] = n_correct / n_total

        return metrics


class Reptile:
    """Reptile meta-learning algorithm.

    A simpler alternative to MAML that doesn't require second-order gradients.
    Reptile works by moving the meta-parameters towards the adapted parameters.

    Reference:
        Nichol et al. "On First-Order Meta-Learning Algorithms"
        https://arxiv.org/abs/1803.02999

    Attributes:
        base_model: Base model to meta-train
        inner_lr: Learning rate for task adaptation
        n_inner_steps: Number of inner loop steps

    Example:
        >>> base_model = LinearModel(input_dim=10, output_dim=5)
        >>> reptile = Reptile(base_model, inner_lr=0.01, n_inner_steps=10)
        >>> # Adapt and update
        >>> adapted = reptile.adapt(support_data, support_labels)
        >>> reptile.meta_update(adapted, meta_lr=0.1)
    """

    def __init__(
        self,
        base_model: LinearModel,
        inner_lr: float = 0.01,
        n_inner_steps: int = 10,
        loss_type: str = "mse",
    ) -> None:
        """Initialize Reptile.

        Args:
            base_model: Base model to meta-train
            inner_lr: Learning rate for task adaptation
            n_inner_steps: Number of inner loop steps
            loss_type: Loss function type
        """
        self.base_model = base_model
        self.inner_lr = inner_lr
        self.n_inner_steps = n_inner_steps
        self.loss_type = loss_type

    @property
    def meta_parameters(self) -> ParameterStore:
        """Return meta-parameters."""
        return self.base_model.parameters

    def adapt(
        self,
        support_data: np.ndarray,
        support_labels: np.ndarray,
        n_steps: int | None = None,
        lr: float | None = None,
    ) -> ParameterStore:
        """Adapt model to task (same as MAML inner loop).

        Args:
            support_data: Support set inputs
            support_labels: Support set labels
            n_steps: Number of adaptation steps
            lr: Learning rate

        Returns:
            Adapted parameters
        """
        n_steps = n_steps or self.n_inner_steps
        lr = lr or self.inner_lr

        adapted_params = self.base_model.parameters.copy()

        for _ in range(n_steps):
            grads = self.base_model.compute_gradients(
                adapted_params, support_data, support_labels, loss_type=self.loss_type
            )

            for key in adapted_params:
                if key in grads:
                    adapted_params[key] = adapted_params[key] - lr * grads[key]

        return adapted_params

    def compute_loss(
        self, params: ParameterStore, data: np.ndarray, labels: np.ndarray
    ) -> float:
        """Compute loss with given parameters.

        Args:
            params: Model parameters
            data: Input data
            labels: Target labels

        Returns:
            Loss value
        """
        return self.base_model.compute_loss(params, data, labels, self.loss_type)

    def meta_update(self, adapted_params: ParameterStore, meta_lr: float = 0.1) -> None:
        """Update meta-parameters towards adapted parameters.

        This is the key Reptile update: θ_meta = θ_meta + ε(θ_adapted - θ_meta)

        Args:
            adapted_params: Adapted parameters from task
            meta_lr: Meta learning rate (interpolation factor)
        """
        for key in self.base_model.parameters:
            if key in adapted_params:
                diff = adapted_params[key] - self.base_model.parameters[key]
                self.base_model.parameters[key] = (
                    self.base_model.parameters[key] + meta_lr * diff
                )

    def meta_update_batch(
        self, adapted_params_list: list[ParameterStore], meta_lr: float = 0.1
    ) -> None:
        """Update meta-parameters from multiple adapted parameter sets.

        Args:
            adapted_params_list: List of adapted parameters from tasks
            meta_lr: Meta learning rate
        """
        # Average the adapted parameters
        avg_adapted = {}
        for key in self.base_model.parameters:
            avg_adapted[key] = np.mean(
                [params[key] for params in adapted_params_list], axis=0
            )

        # Update meta-parameters towards average
        for key in self.base_model.parameters:
            diff = avg_adapted[key] - self.base_model.parameters[key]
            self.base_model.parameters[key] = (
                self.base_model.parameters[key] + meta_lr * diff
            )

    def evaluate(
        self, episodes: list, n_adaptation_steps: int | None = None
    ) -> dict[str, float]:
        """Evaluate Reptile on episodes.

        Args:
            episodes: List of test episodes
            n_adaptation_steps: Number of adaptation steps

        Returns:
            Dictionary with evaluation metrics
        """
        n_adaptation_steps = n_adaptation_steps or self.n_inner_steps

        total_pre_adapt_loss = 0.0
        total_post_adapt_loss = 0.0
        n_correct = 0
        n_total = 0

        for episode in episodes:
            # Pre-adaptation loss
            pre_loss = self.base_model.compute_loss(
                self.base_model.parameters,
                episode.query_data,
                episode.query_labels,
                self.loss_type,
            )
            total_pre_adapt_loss += pre_loss

            # Adapt
            adapted_params = self.adapt(
                episode.support_data, episode.support_labels, n_steps=n_adaptation_steps
            )

            # Post-adaptation loss
            post_loss = self.base_model.compute_loss(
                adapted_params, episode.query_data, episode.query_labels, self.loss_type
            )
            total_post_adapt_loss += post_loss

            # Accuracy
            if self.loss_type == "cross_entropy":
                predictions = self.base_model.forward(
                    adapted_params, episode.query_data
                )
                pred_labels = np.argmax(predictions, axis=1)
                n_correct += np.sum(pred_labels == episode.query_labels)
                n_total += len(episode.query_labels)

        n_episodes = len(episodes)
        metrics = {
            "pre_adapt_loss": total_pre_adapt_loss / n_episodes,
            "post_adapt_loss": total_post_adapt_loss / n_episodes,
            "improvement": total_pre_adapt_loss / n_episodes
            - total_post_adapt_loss / n_episodes,
        }

        if self.loss_type == "cross_entropy" and n_total > 0:
            metrics["accuracy"] = n_correct / n_total

        return metrics
