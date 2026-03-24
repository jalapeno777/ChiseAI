"""Tests for meta-learning training module.

Tests MetaTrainingLoop, EpisodeTrainer, TrainingConfig, and TrainingMetrics.
"""

from __future__ import annotations

import numpy as np
from src.strong_system.meta_learning.controller import Episode
from src.strong_system.meta_learning.models import MAML, LinearModel, Reptile
from src.strong_system.meta_learning.training import (
    EpisodeTrainer,
    MetaTrainingLoop,
    TrainingConfig,
    TrainingMetrics,
)


class TestTrainingConfig:
    """Tests for TrainingConfig class."""

    def test_default_config(self):
        """Test default configuration."""
        config = TrainingConfig()

        assert config.n_epochs == 100
        assert config.episodes_per_epoch == 10
        assert config.meta_lr == 0.001
        assert config.inner_lr == 0.01
        assert config.n_inner_steps == 5
        assert config.eval_interval == 10
        assert config.early_stopping_patience == 20
        assert config.verbose is True

    def test_custom_config(self):
        """Test custom configuration."""
        config = TrainingConfig(
            n_epochs=50, meta_lr=0.01, episodes_per_epoch=20, verbose=False
        )

        assert config.n_epochs == 50
        assert config.meta_lr == 0.01
        assert config.episodes_per_epoch == 20
        assert config.verbose is False
        # Other values should be defaults
        assert config.n_inner_steps == 5


class TestTrainingMetrics:
    """Tests for TrainingMetrics class."""

    def test_default_metrics(self):
        """Test default metrics creation."""
        metrics = TrainingMetrics()

        assert metrics.epoch == 0
        assert metrics.meta_loss == 0.0
        assert metrics.inner_losses == []
        assert metrics.pre_adapt_accuracy == 0.0
        assert metrics.post_adapt_accuracy == 0.0

    def test_metrics_with_values(self):
        """Test metrics with specific values."""
        metrics = TrainingMetrics(
            epoch=5,
            meta_loss=0.5,
            inner_losses=[0.6, 0.5, 0.4],
            pre_adapt_accuracy=0.7,
            post_adapt_accuracy=0.85,
        )

        assert metrics.epoch == 5
        assert metrics.meta_loss == 0.5
        assert len(metrics.inner_losses) == 3

    def test_metrics_to_dict(self):
        """Test converting metrics to dictionary."""
        metrics = TrainingMetrics(
            epoch=10, meta_loss=0.3, custom_metrics={"val_loss": 0.4}
        )

        d = metrics.to_dict()

        assert d["epoch"] == 10
        assert d["meta_loss"] == 0.3
        assert d["val_loss"] == 0.4


class TestMetaTrainingLoop:
    """Tests for MetaTrainingLoop class."""

    def test_training_loop_creation(self):
        """Test training loop creation."""
        base_model = LinearModel(input_dim=10, output_dim=5)
        maml = MAML(base_model)
        trainer = MetaTrainingLoop(maml)

        assert trainer.meta_model == maml
        assert isinstance(trainer.config, TrainingConfig)
        assert trainer.history == []

    def test_training_loop_with_custom_config(self):
        """Test training loop with custom config."""
        base_model = LinearModel(input_dim=10, output_dim=5)
        maml = MAML(base_model)
        config = TrainingConfig(n_epochs=50, meta_lr=0.01)

        trainer = MetaTrainingLoop(maml, config=config)

        assert trainer.config.n_epochs == 50
        assert trainer.config.meta_lr == 0.01

    def test_train_epoch(self):
        """Test training for one epoch."""
        base_model = LinearModel(input_dim=10, output_dim=5)
        maml = MAML(base_model, inner_lr=0.01, n_inner_steps=3)
        trainer = MetaTrainingLoop(maml)

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

        metrics = trainer._train_epoch(0, episodes)

        assert isinstance(metrics, TrainingMetrics)
        assert metrics.epoch == 0
        # Loss should be computed
        assert metrics.meta_loss >= 0

    def test_sample_episodes(self):
        """Test episode sampling."""
        base_model = LinearModel(input_dim=10, output_dim=5)
        maml = MAML(base_model)
        trainer = MetaTrainingLoop(maml)

        episodes = []
        for i in range(10):
            episode = Episode(
                task_id=f"task_{i}",
                support_data=np.random.randn(20, 10),
                support_labels=np.random.randint(0, 5, 20),
                query_data=np.random.randn(30, 10),
                query_labels=np.random.randint(0, 5, 30),
            )
            episodes.append(episode)

        sampled = trainer._sample_episodes(episodes, 5)

        assert len(sampled) == 5

    def test_sample_episodes_more_than_available(self):
        """Test sampling more episodes than available."""
        base_model = LinearModel(input_dim=10, output_dim=5)
        maml = MAML(base_model)
        trainer = MetaTrainingLoop(maml)

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

        sampled = trainer._sample_episodes(episodes, 10)

        # Should return all available
        assert len(sampled) == 5

    def test_evaluate(self):
        """Test evaluation."""
        base_model = LinearModel(input_dim=10, output_dim=5)
        maml = MAML(base_model, inner_lr=0.01, n_inner_steps=3)
        trainer = MetaTrainingLoop(maml)

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

        metrics = trainer.evaluate(episodes)

        assert "pre_adapt_loss" in metrics
        assert "post_adapt_loss" in metrics
        assert "improvement" in metrics

    def test_manual_evaluate(self):
        """Test manual evaluation without model.evaluate()."""
        base_model = LinearModel(input_dim=10, output_dim=5)
        maml = MAML(base_model, inner_lr=0.01, n_inner_steps=3)
        trainer = MetaTrainingLoop(maml)

        # Create episodes
        episodes = []
        for i in range(3):
            episode = Episode(
                task_id=f"task_{i}",
                support_data=np.random.randn(20, 10),
                support_labels=np.random.randint(0, 5, 20),
                query_data=np.random.randn(30, 10),
                query_labels=np.random.randint(0, 5, 30),
            )
            episodes.append(episode)

        metrics = trainer._manual_evaluate(episodes)

        assert "pre_adapt_loss" in metrics
        assert "post_adapt_loss" in metrics

    def test_create_summary(self):
        """Test training summary creation."""
        base_model = LinearModel(input_dim=10, output_dim=5)
        maml = MAML(base_model)
        trainer = MetaTrainingLoop(maml)

        # Add some history
        trainer.history = [
            TrainingMetrics(epoch=0, meta_loss=1.0),
            TrainingMetrics(epoch=1, meta_loss=0.8),
            TrainingMetrics(epoch=2, meta_loss=0.6),
        ]
        trainer._best_loss = 0.6

        summary = trainer._create_summary()

        assert summary["epochs_trained"] == 3
        assert summary["final_meta_loss"] == 0.6
        assert summary["best_loss"] == 0.6
        assert len(summary["history"]) == 3

    def test_get_learning_curve(self):
        """Test getting learning curve data."""
        base_model = LinearModel(input_dim=10, output_dim=5)
        maml = MAML(base_model)
        trainer = MetaTrainingLoop(maml)

        # Add some history
        trainer.history = [
            TrainingMetrics(epoch=0, meta_loss=1.0),
            TrainingMetrics(epoch=1, meta_loss=0.8),
            TrainingMetrics(epoch=2, meta_loss=0.6),
        ]

        curve = trainer.get_learning_curve()

        assert "epochs" in curve
        assert "meta_losses" in curve
        assert len(curve["epochs"]) == 3
        assert len(curve["meta_losses"]) == 3


class TestEpisodeTrainer:
    """Tests for EpisodeTrainer class."""

    def test_episode_trainer_creation(self):
        """Test episode trainer creation."""
        base_model = LinearModel(input_dim=10, output_dim=5)
        maml = MAML(base_model)
        trainer = EpisodeTrainer(maml, lr=0.01, n_steps=20)

        assert trainer.model == maml
        assert trainer.lr == 0.01
        assert trainer.n_steps == 20

    def test_train_on_episode_support_only(self):
        """Test training on episode with support set only."""
        base_model = LinearModel(input_dim=10, output_dim=5)
        maml = MAML(base_model, inner_lr=0.01, n_inner_steps=3)
        trainer = EpisodeTrainer(maml, lr=0.01, n_steps=10)

        episode = Episode(
            task_id="task_1",
            support_data=np.random.randn(20, 10),
            support_labels=np.random.randint(0, 5, 20),
            query_data=np.random.randn(30, 10),
            query_labels=np.random.randint(0, 5, 30),
        )

        loss_history = trainer.train_on_episode(episode, use_support_only=True)

        assert len(loss_history) == 10
        # Loss should generally decrease (or at least be computed)
        assert all(isinstance(l, float) for l in loss_history)

    def test_train_on_episode_full(self):
        """Test training on episode with full data."""
        base_model = LinearModel(input_dim=10, output_dim=5)
        maml = MAML(base_model, inner_lr=0.01, n_inner_steps=3)
        trainer = EpisodeTrainer(maml, lr=0.01, n_steps=10)

        episode = Episode(
            task_id="task_1",
            support_data=np.random.randn(20, 10),
            support_labels=np.random.randint(0, 5, 20),
            query_data=np.random.randn(30, 10),
            query_labels=np.random.randint(0, 5, 30),
        )

        loss_history = trainer.train_on_episode(episode, use_support_only=False)

        assert len(loss_history) == 10

    def test_evaluate_on_episode(self):
        """Test evaluating on episode."""
        base_model = LinearModel(input_dim=10, output_dim=5)
        maml = MAML(base_model)
        trainer = EpisodeTrainer(maml)

        episode = Episode(
            task_id="task_1",
            support_data=np.random.randn(20, 10),
            support_labels=np.random.randint(0, 5, 20),
            query_data=np.random.randn(30, 10),
            query_labels=np.random.randint(0, 5, 30),
        )

        metrics = trainer.evaluate_on_episode(episode)

        assert "loss" in metrics
        assert "accuracy" in metrics
        assert isinstance(metrics["loss"], float)
        assert isinstance(metrics["accuracy"], float)


class TestTrainingWithReptile:
    """Tests for training with Reptile algorithm."""

    def test_reptile_training_loop(self):
        """Test training loop with Reptile."""
        base_model = LinearModel(input_dim=10, output_dim=5)
        reptile = Reptile(base_model, inner_lr=0.01, n_inner_steps=5)

        config = TrainingConfig(n_epochs=5, episodes_per_epoch=3, verbose=False)
        trainer = MetaTrainingLoop(reptile, config=config)

        # Create episodes
        episodes = []
        for i in range(10):
            episode = Episode(
                task_id=f"task_{i}",
                support_data=np.random.randn(20, 10),
                support_labels=np.random.randint(0, 5, 20),
                query_data=np.random.randn(30, 10),
                query_labels=np.random.randint(0, 5, 30),
            )
            episodes.append(episode)

        # Train
        summary = trainer.train(episodes, verbose=False)

        assert summary["epochs_trained"] > 0

    def test_reptile_episode_trainer(self):
        """Test episode trainer with Reptile."""
        base_model = LinearModel(input_dim=10, output_dim=5)
        reptile = Reptile(base_model, inner_lr=0.01, n_inner_steps=5)
        trainer = EpisodeTrainer(reptile, lr=0.01, n_steps=10)

        episode = Episode(
            task_id="task_1",
            support_data=np.random.randn(20, 10),
            support_labels=np.random.randint(0, 5, 20),
            query_data=np.random.randn(30, 10),
            query_labels=np.random.randint(0, 5, 30),
        )

        loss_history = trainer.train_on_episode(episode)

        assert len(loss_history) == 10
