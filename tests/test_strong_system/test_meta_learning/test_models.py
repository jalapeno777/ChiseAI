"""Tests for meta-learning models module.

Tests ParameterStore, LinearModel, MAML, and Reptile classes.
"""

from __future__ import annotations

import numpy as np
import pytest

from src.strong_system.meta_learning.controller import Episode
from src.strong_system.meta_learning.models import (
    LinearModel,
    MAML,
    ParameterStore,
    Reptile,
)


class TestParameterStore:
    """Tests for ParameterStore class."""

    def test_store_creation_empty(self):
        """Test creating empty parameter store."""
        store = ParameterStore()
        assert len(store.params) == 0

    def test_store_creation_with_params(self):
        """Test creating store with initial parameters."""
        params = {"W": np.random.randn(10, 5), "b": np.zeros(5)}
        store = ParameterStore(params)

        assert "W" in store
        assert "b" in store
        assert store["W"].shape == (10, 5)

    def test_store_setitem_getitem(self):
        """Test setting and getting parameters."""
        store = ParameterStore()

        store["W"] = np.random.randn(10, 5)
        store["b"] = np.zeros(5)

        assert store["W"].shape == (10, 5)
        assert store["b"].shape == (5,)

    def test_store_contains(self):
        """Test checking parameter existence."""
        store = ParameterStore()
        store["W"] = np.random.randn(10, 5)

        assert "W" in store
        assert "b" not in store

    def test_store_zero_grad(self):
        """Test zeroing gradients."""
        store = ParameterStore()
        store["W"] = np.random.randn(10, 5)
        store["b"] = np.zeros(5)

        store.zero_grad()

        assert "W" in store.grads
        assert "b" in store.grads
        assert np.allclose(store.grads["W"], 0)
        assert np.allclose(store.grads["b"], 0)

    def test_store_step(self):
        """Test SGD parameter update."""
        store = ParameterStore()
        store["W"] = np.ones((5, 3))
        store["b"] = np.ones(3)

        store.zero_grad()
        store.grads["W"] = np.ones((5, 3)) * 0.1
        store.grads["b"] = np.ones(3) * 0.1

        store.step(lr=0.01)

        assert np.allclose(store["W"], 0.999)  # 1.0 - 0.01 * 0.1
        assert np.allclose(store["b"], 0.999)

    def test_store_copy(self):
        """Test copying parameter store."""
        store = ParameterStore()
        store["W"] = np.random.randn(10, 5)
        store["b"] = np.zeros(5)

        copy = store.copy()

        assert np.allclose(store["W"], copy["W"])
        assert np.allclose(store["b"], copy["b"])

        # Modify copy shouldn't affect original
        copy["W"][0, 0] = 999
        assert store["W"][0, 0] != 999

    def test_store_to_dict(self):
        """Test converting to dictionary."""
        store = ParameterStore()
        store["W"] = np.random.randn(10, 5)

        d = store.to_dict()

        assert "W" in d
        assert np.allclose(d["W"], store["W"])

    def test_store_from_dict(self):
        """Test creating from dictionary."""
        params = {"W": np.random.randn(10, 5), "b": np.zeros(5)}

        store = ParameterStore.from_dict(params)

        assert np.allclose(store["W"], params["W"])
        assert np.allclose(store["b"], params["b"])


class TestLinearModel:
    """Tests for LinearModel class."""

    def test_model_creation(self):
        """Test model creation."""
        model = LinearModel(input_dim=10, output_dim=5)

        assert model.input_dim == 10
        assert model.output_dim == 5
        assert "W" in model.parameters
        assert "b" in model.parameters
        assert model.parameters["W"].shape == (10, 5)
        assert model.parameters["b"].shape == (5,)

    def test_model_creation_xavier_init(self):
        """Test Xavier initialization."""
        model = LinearModel(input_dim=100, output_dim=50, initialization="xavier")

        # Xavier init should have std ~ sqrt(2 / (100 + 50))
        expected_std = np.sqrt(2.0 / 150)
        actual_std = np.std(model.parameters["W"])

        # Check it's in reasonable range (within factor of 2)
        assert actual_std < expected_std * 2
        assert actual_std > expected_std / 2

    def test_model_creation_he_init(self):
        """Test He initialization."""
        model = LinearModel(input_dim=100, output_dim=50, initialization="he")

        # He init should have std ~ sqrt(2 / 100)
        expected_std = np.sqrt(2.0 / 100)
        actual_std = np.std(model.parameters["W"])

        assert actual_std < expected_std * 2
        assert actual_std > expected_std / 2

    def test_model_forward(self):
        """Test forward pass."""
        model = LinearModel(input_dim=10, output_dim=5)
        x = np.random.randn(32, 10)

        output = model.forward(None, x)

        assert output.shape == (32, 5)

    def test_model_forward_with_params(self):
        """Test forward pass with custom parameters."""
        model = LinearModel(input_dim=10, output_dim=5)
        x = np.random.randn(32, 10)

        custom_params = model.parameters.copy()
        custom_params["W"] = np.ones((10, 5))
        custom_params["b"] = np.zeros(5)

        output = model.forward(custom_params, x)

        # With W=ones, output should be sum of inputs per output dim
        expected = np.sum(x, axis=1, keepdims=True) * np.ones((1, 5))
        assert np.allclose(output, expected)

    def test_model_compute_loss_mse(self):
        """Test MSE loss computation."""
        model = LinearModel(input_dim=10, output_dim=5)
        x = np.random.randn(32, 10)
        y = np.random.randn(32, 5)

        loss = model.compute_loss(None, x, y, loss_type="mse")

        assert isinstance(loss, float)
        assert loss >= 0

    def test_model_compute_loss_cross_entropy(self):
        """Test cross-entropy loss computation."""
        model = LinearModel(input_dim=10, output_dim=5)
        x = np.random.randn(32, 10)
        y = np.random.randint(0, 5, 32)

        loss = model.compute_loss(None, x, y, loss_type="cross_entropy")

        assert isinstance(loss, float)
        assert loss > 0  # Cross-entropy is always positive

    def test_model_compute_gradients_mse(self):
        """Test gradient computation for MSE."""
        model = LinearModel(input_dim=10, output_dim=5)
        x = np.random.randn(32, 10)
        y = np.random.randn(32, 5)

        grads = model.compute_gradients(None, x, y, loss_type="mse")

        assert "W" in grads
        assert "b" in grads
        assert grads["W"].shape == (10, 5)
        assert grads["b"].shape == (5,)

    def test_model_compute_gradients_cross_entropy(self):
        """Test gradient computation for cross-entropy."""
        model = LinearModel(input_dim=10, output_dim=5)
        x = np.random.randn(32, 10)
        y = np.random.randint(0, 5, 32)

        grads = model.compute_gradients(None, x, y, loss_type="cross_entropy")

        assert "W" in grads
        assert "b" in grads


class TestMAML:
    """Tests for MAML class."""

    def test_maml_creation(self):
        """Test MAML creation."""
        base_model = LinearModel(input_dim=10, output_dim=5)
        maml = MAML(base_model, inner_lr=0.01, n_inner_steps=5)

        assert maml.inner_lr == 0.01
        assert maml.n_inner_steps == 5
        assert maml.first_order == False

    def test_maml_meta_parameters(self):
        """Test accessing meta-parameters."""
        base_model = LinearModel(input_dim=10, output_dim=5)
        maml = MAML(base_model)

        params = maml.meta_parameters
        assert "W" in params
        assert "b" in params

    def test_maml_adapt(self):
        """Test inner loop adaptation."""
        base_model = LinearModel(input_dim=10, output_dim=5)
        maml = MAML(base_model, inner_lr=0.01, n_inner_steps=5)

        support_data = np.random.randn(20, 10)
        support_labels = np.random.randint(0, 5, 20)

        adapted_params = maml.adapt(support_data, support_labels)

        assert "W" in adapted_params
        assert "b" in adapted_params
        # Adapted params should be different from meta params
        assert not np.allclose(adapted_params["W"], maml.meta_parameters["W"])

    def test_maml_adapt_n_steps(self):
        """Test adaptation with different number of steps."""
        base_model = LinearModel(input_dim=10, output_dim=5)
        maml = MAML(base_model, inner_lr=0.01, n_inner_steps=5)

        support_data = np.random.randn(20, 10)
        support_labels = np.random.randint(0, 5, 20)

        adapted_5 = maml.adapt(support_data, support_labels, n_steps=5)
        adapted_10 = maml.adapt(support_data, support_labels, n_steps=10)

        # More steps should lead to different parameters
        assert not np.allclose(adapted_5["W"], adapted_10["W"])

    def test_maml_predict(self):
        """Test prediction with adapted parameters."""
        base_model = LinearModel(input_dim=10, output_dim=5)
        maml = MAML(base_model)

        data = np.random.randn(32, 10)
        predictions = maml.predict(data)

        assert predictions.shape == (32, 5)

    def test_maml_predict_with_params(self):
        """Test prediction with custom parameters."""
        base_model = LinearModel(input_dim=10, output_dim=5)
        maml = MAML(base_model)

        data = np.random.randn(32, 10)
        custom_params = maml.meta_parameters.copy()

        predictions = maml.predict(data, custom_params)

        assert predictions.shape == (32, 5)

    def test_maml_compute_loss(self):
        """Test loss computation."""
        base_model = LinearModel(input_dim=10, output_dim=5)
        maml = MAML(base_model)

        data = np.random.randn(32, 10)
        labels = np.random.randint(0, 5, 32)

        loss = maml.compute_loss(maml.meta_parameters, data, labels)

        assert isinstance(loss, float)
        assert loss > 0

    def test_maml_compute_meta_gradient(self):
        """Test meta-gradient computation."""
        base_model = LinearModel(input_dim=10, output_dim=5)
        maml = MAML(base_model, inner_lr=0.01, n_inner_steps=3)

        # Create episodes
        episodes = []
        for i in range(5):
            episode = Episode(
                task_id=f"task_{i}",
                support_data=np.random.randn(20, 10),
                support_labels=np.random.randint(0, 5, 20),
                query_data=np.random.randn(30, 10),
                query_labels=np.random.randint(0, 5, 30),
            )
            episodes.append(episode)

        meta_grad = maml.compute_meta_gradient(episodes)

        assert "W" in meta_grad
        assert "b" in meta_grad
        assert meta_grad["W"].shape == (10, 5)
        assert meta_grad["b"].shape == (5,)

    def test_maml_meta_update(self):
        """Test meta-parameter update."""
        base_model = LinearModel(input_dim=10, output_dim=5)
        maml = MAML(base_model)

        old_W = maml.meta_parameters["W"].copy()

        meta_grad = {"W": np.ones((10, 5)) * 0.01, "b": np.ones(5) * 0.01}

        maml.meta_update(meta_grad, meta_lr=0.001)

        # Parameters should have changed
        assert not np.allclose(maml.meta_parameters["W"], old_W)

    def test_maml_evaluate(self):
        """Test MAML evaluation."""
        base_model = LinearModel(input_dim=10, output_dim=5)
        maml = MAML(base_model, inner_lr=0.01, n_inner_steps=3)

        # Create episodes
        episodes = []
        for i in range(5):
            episode = Episode(
                task_id=f"task_{i}",
                support_data=np.random.randn(20, 10),
                support_labels=np.random.randint(0, 5, 20),
                query_data=np.random.randn(30, 10),
                query_labels=np.random.randint(0, 5, 30),
            )
            episodes.append(episode)

        metrics = maml.evaluate(episodes)

        assert "pre_adapt_loss" in metrics
        assert "post_adapt_loss" in metrics
        assert "improvement" in metrics
        assert metrics["improvement"] >= 0  # Adaptation should improve or stay same


class TestReptile:
    """Tests for Reptile class."""

    def test_reptile_creation(self):
        """Test Reptile creation."""
        base_model = LinearModel(input_dim=10, output_dim=5)
        reptile = Reptile(base_model, inner_lr=0.01, n_inner_steps=10)

        assert reptile.inner_lr == 0.01
        assert reptile.n_inner_steps == 10

    def test_reptile_meta_parameters(self):
        """Test accessing meta-parameters."""
        base_model = LinearModel(input_dim=10, output_dim=5)
        reptile = Reptile(base_model)

        params = reptile.meta_parameters
        assert "W" in params
        assert "b" in params

    def test_reptile_adapt(self):
        """Test adaptation (same as MAML inner loop)."""
        base_model = LinearModel(input_dim=10, output_dim=5)
        reptile = Reptile(base_model, inner_lr=0.01, n_inner_steps=10)

        support_data = np.random.randn(20, 10)
        support_labels = np.random.randint(0, 5, 20)

        adapted_params = reptile.adapt(support_data, support_labels)

        assert "W" in adapted_params
        assert "b" in adapted_params

    def test_reptile_meta_update(self):
        """Test Reptile meta-update."""
        base_model = LinearModel(input_dim=10, output_dim=5)
        reptile = Reptile(base_model)

        old_W = reptile.meta_parameters["W"].copy()

        # Create adapted parameters
        adapted = reptile.meta_parameters.copy()
        adapted["W"] = adapted["W"] + np.ones((10, 5)) * 0.1
        adapted["b"] = adapted["b"] + np.ones(5) * 0.1

        reptile.meta_update(adapted, meta_lr=0.1)

        # Parameters should move toward adapted
        assert not np.allclose(reptile.meta_parameters["W"], old_W)

    def test_reptile_meta_update_batch(self):
        """Test Reptile meta-update from multiple adaptations."""
        base_model = LinearModel(input_dim=10, output_dim=5)
        reptile = Reptile(base_model)

        old_W = reptile.meta_parameters["W"].copy()

        # Create multiple adapted parameter sets
        adapted_list = []
        for i in range(3):
            adapted = reptile.meta_parameters.copy()
            adapted["W"] = adapted["W"] + np.random.randn(10, 5) * 0.1
            adapted["b"] = adapted["b"] + np.random.randn(5) * 0.1
            adapted_list.append(adapted)

        reptile.meta_update_batch(adapted_list, meta_lr=0.1)

        # Parameters should have changed
        assert not np.allclose(reptile.meta_parameters["W"], old_W)

    def test_reptile_evaluate(self):
        """Test Reptile evaluation."""
        base_model = LinearModel(input_dim=10, output_dim=5)
        reptile = Reptile(base_model, inner_lr=0.01, n_inner_steps=5)

        # Create episodes
        episodes = []
        for i in range(5):
            episode = Episode(
                task_id=f"task_{i}",
                support_data=np.random.randn(20, 10),
                support_labels=np.random.randint(0, 5, 20),
                query_data=np.random.randn(30, 10),
                query_labels=np.random.randint(0, 5, 30),
            )
            episodes.append(episode)

        metrics = reptile.evaluate(episodes)

        assert "pre_adapt_loss" in metrics
        assert "post_adapt_loss" in metrics
        assert "improvement" in metrics


class TestMAMLvsReptile:
    """Comparison tests between MAML and Reptile."""

    def test_same_base_model(self):
        """Test that both can use the same base model."""
        base_model = LinearModel(input_dim=10, output_dim=5)

        maml = MAML(base_model, inner_lr=0.01, n_inner_steps=5)

        # Create new base model with same architecture for reptile
        base_model2 = LinearModel(input_dim=10, output_dim=5)
        base_model2.parameters["W"] = base_model.parameters["W"].copy()
        base_model2.parameters["b"] = base_model.parameters["b"].copy()
        reptile = Reptile(base_model2, inner_lr=0.01, n_inner_steps=5)

        # Both should adapt similarly
        support_data = np.random.randn(20, 10)
        support_labels = np.random.randint(0, 5, 20)

        maml_adapted = maml.adapt(support_data, support_labels, n_steps=5)
        reptile_adapted = reptile.adapt(support_data, support_labels, n_steps=5)

        # With same initialization and steps, adaptations should be similar
        assert maml_adapted["W"].shape == reptile_adapted["W"].shape
