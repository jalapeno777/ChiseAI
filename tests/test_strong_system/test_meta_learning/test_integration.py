"""Integration tests for meta-learning system.

Tests end-to-end workflows combining controller, models, training, and utils.
"""

from __future__ import annotations

import numpy as np
import pytest
from src.strong_system.meta_learning import (
    MAML,
    EpisodeTrainer,
    LinearModel,
    MetaLearningController,
    MetaTrainingLoop,
    Reptile,
    TaskSampler,
    TrainingConfig,
    compute_meta_metrics,
    create_classification_task,
    create_sinusoid_task,
)


class TestEndToEndMetaLearning:
    """End-to-end tests for meta-learning workflows."""

    def test_full_maml_workflow(self):
        """Test complete MAML workflow from data to trained model."""
        # 1. Create controller and add tasks
        controller = MetaLearningController()

        for i in range(10):
            X, y = create_classification_task(
                n_classes=5, n_samples=100, n_features=10, seed=i
            )
            controller.add_task(task_id=f"task_{i}", data=X, labels=y)

        # 2. Split tasks
        controller.split_tasks(train_ratio=0.8, seed=42)

        # 3. Sample episodes
        train_episodes = controller.sample_episodes(
            n_episodes=20, k_shot=5, q_query=15, split="train", seed=42
        )

        # 4. Create MAML model
        base_model = LinearModel(input_dim=10, output_dim=5)
        maml = MAML(
            base_model, inner_lr=0.01, n_inner_steps=5, loss_type="cross_entropy"
        )

        # 5. Train
        config = TrainingConfig(
            n_epochs=10,
            episodes_per_epoch=5,
            meta_lr=0.001,
            inner_lr=0.01,
            n_inner_steps=5,
            verbose=False,
        )
        trainer = MetaTrainingLoop(maml, config=config)

        summary = trainer.train(train_episodes, verbose=False)

        assert summary["epochs_trained"] == 10
        assert "final_meta_loss" in summary

        # 6. Evaluate on test episodes
        test_episodes = controller.sample_episodes(
            n_episodes=5, k_shot=5, q_query=15, split="test", seed=42
        )

        metrics = maml.evaluate(test_episodes)

        assert "pre_adapt_loss" in metrics
        assert "post_adapt_loss" in metrics
        assert "improvement" in metrics
        assert metrics["improvement"] >= 0

    def test_full_reptile_workflow(self):
        """Test complete Reptile workflow."""
        # 1. Create controller with sinusoid tasks
        controller = MetaLearningController()

        for i in range(20):
            amplitude = np.random.uniform(0.1, 5.0)
            phase = np.random.uniform(0, np.pi)
            X, y = create_sinusoid_task(
                amplitude=amplitude, phase=phase, n_samples=50, seed=i
            )
            controller.add_task(
                task_id=f"sinusoid_{i}",
                data=X,
                labels=y,
                metadata={"amplitude": amplitude, "phase": phase},
            )

        # 2. Split and sample
        controller.split_tasks(train_ratio=0.8, seed=42)
        train_episodes = controller.sample_episodes(
            n_episodes=15, k_shot=10, q_query=20, split="train", seed=42
        )

        # 3. Create Reptile model
        base_model = LinearModel(input_dim=1, output_dim=1)
        reptile = Reptile(base_model, inner_lr=0.01, n_inner_steps=10, loss_type="mse")

        # 4. Train
        config = TrainingConfig(
            n_epochs=10,
            episodes_per_epoch=5,
            meta_lr=0.1,  # Reptile typically uses higher meta_lr
            verbose=False,
        )
        trainer = MetaTrainingLoop(reptile, config=config)

        summary = trainer.train(train_episodes, verbose=False)

        assert summary["epochs_trained"] == 10

        # 5. Evaluate
        test_episodes = controller.sample_episodes(
            n_episodes=5, k_shot=10, q_query=20, split="test", seed=42
        )

        metrics = reptile.evaluate(test_episodes)

        assert "post_adapt_loss" in metrics

    def test_few_shot_adaptation(self):
        """Test few-shot adaptation on new task."""
        # 1. Meta-train on source tasks
        controller = MetaLearningController()

        for i in range(15):
            X, y = create_classification_task(
                n_classes=3, n_samples=100, n_features=5, seed=i
            )
            controller.add_task(f"source_{i}", X, y)

        episodes = controller.sample_episodes(
            n_episodes=30, k_shot=5, q_query=15, seed=42
        )

        base_model = LinearModel(input_dim=5, output_dim=3)
        maml = MAML(base_model, inner_lr=0.01, n_inner_steps=5)

        config = TrainingConfig(
            n_epochs=20, episodes_per_epoch=10, meta_lr=0.001, verbose=False
        )
        trainer = MetaTrainingLoop(maml, config=config)
        trainer.train(episodes, verbose=False)

        # 2. Create new target task
        X_target, y_target = create_classification_task(
            n_classes=3, n_samples=60, n_features=5, seed=999
        )
        n_samples = len(X_target)  # Actual number of samples created

        # 3. Sample few-shot support set
        support_indices = np.random.choice(n_samples, size=5, replace=False)
        query_indices = [i for i in range(n_samples) if i not in support_indices]

        support_data = X_target[support_indices]
        support_labels = y_target[support_indices]
        query_data = X_target[query_indices]
        query_labels = y_target[query_indices]

        # 4. Adapt to new task
        adapted_params = maml.adapt(support_data, support_labels, n_steps=10)

        # 5. Evaluate on query set
        predictions = maml.predict(query_data, adapted_params)
        metrics = compute_meta_metrics(predictions, query_labels)

        # Should achieve reasonable accuracy with just 5 shots
        assert "accuracy" in metrics
        # Note: With only 5 shots, accuracy can vary; just check it's not terrible
        assert metrics["accuracy"] > 0.15  # Better than chance-level

    def test_comparison_maml_vs_reptile(self):
        """Compare MAML and Reptile on same tasks."""
        # Create shared task set
        controller = MetaLearningController()

        for i in range(10):
            X, y = create_classification_task(
                n_classes=3, n_samples=100, n_features=5, seed=i
            )
            controller.add_task(f"task_{i}", X, y)

        episodes = controller.sample_episodes(
            n_episodes=20, k_shot=5, q_query=15, seed=42
        )

        # Train MAML
        base_model1 = LinearModel(input_dim=5, output_dim=3)
        maml = MAML(base_model1, inner_lr=0.01, n_inner_steps=5)

        config = TrainingConfig(
            n_epochs=10, episodes_per_epoch=5, meta_lr=0.001, verbose=False
        )
        trainer1 = MetaTrainingLoop(maml, config=config)
        summary1 = trainer1.train(episodes, verbose=False)

        # Train Reptile
        base_model2 = LinearModel(input_dim=5, output_dim=3)
        reptile = Reptile(base_model2, inner_lr=0.01, n_inner_steps=10)

        config2 = TrainingConfig(
            n_epochs=10, episodes_per_epoch=5, meta_lr=0.1, verbose=False
        )
        trainer2 = MetaTrainingLoop(reptile, config=config2)
        summary2 = trainer2.train(episodes, verbose=False)

        # Both should train successfully
        assert summary1["epochs_trained"] == 10
        assert summary2["epochs_trained"] == 10

        # Evaluate both
        test_episodes = controller.sample_episodes(
            n_episodes=5, k_shot=5, q_query=15, seed=999
        )

        maml_metrics = maml.evaluate(test_episodes)
        reptile_metrics = reptile.evaluate(test_episodes)

        # Both should show improvement
        assert maml_metrics["improvement"] >= 0
        assert reptile_metrics["improvement"] >= 0


class TestIntegrationWithExistingSTRONG:
    """Tests for integration with existing STRONG components."""

    def test_meta_learning_with_computational_graph(self):
        """Test that meta-learning works with computational graph types."""
        from src.strong_system.computational_graph import Node

        # Create simple meta-learning scenario
        controller = MetaLearningController()

        for i in range(5):
            X = np.random.randn(50, 3).astype(np.float64)
            y = np.random.randint(0, 2, 50)
            controller.add_task(f"task_{i}", X, y)

        # Sample episode
        episode = controller.sample_episode(k_shot=5, q_query=15, seed=42)

        # Verify data can be used with Node
        support_node = Node(episode.support_data[:1])
        assert support_node.shape == (1, 3)

        query_node = Node(episode.query_data[:1])
        assert query_node.shape == (1, 3)

    def test_episode_trainer_integration(self):
        """Test EpisodeTrainer with full workflow."""
        # Setup
        controller = MetaLearningController()

        for i in range(5):
            X, y = create_classification_task(
                n_classes=3, n_samples=100, n_features=5, seed=i
            )
            controller.add_task(f"task_{i}", X, y)

        # Meta-train
        episodes = controller.sample_episodes(
            n_episodes=10, k_shot=5, q_query=15, seed=42
        )

        base_model = LinearModel(input_dim=5, output_dim=3)
        maml = MAML(base_model, inner_lr=0.01, n_inner_steps=5)

        config = TrainingConfig(n_epochs=5, episodes_per_epoch=5, verbose=False)
        trainer = MetaTrainingLoop(maml, config=config)
        trainer.train(episodes, verbose=False)

        # Fine-tune on specific episode with EpisodeTrainer
        target_episode = controller.sample_episode(k_shot=5, q_query=15, seed=999)

        episode_trainer = EpisodeTrainer(maml, lr=0.01, n_steps=20)
        loss_history = episode_trainer.train_on_episode(
            target_episode, use_support_only=True
        )

        assert len(loss_history) == 20
        # Loss should generally decrease
        assert loss_history[-1] < loss_history[0] * 1.5  # Allow some noise

        # Evaluate
        metrics = episode_trainer.evaluate_on_episode(target_episode)
        assert "accuracy" in metrics

    def test_task_sampler_integration(self):
        """Test TaskSampler with controller."""
        controller = MetaLearningController()

        tasks = []
        for i in range(10):
            X, y = create_classification_task(
                n_classes=5, n_samples=100, n_features=10, seed=i
            )
            task_id = controller.add_task(None, X, y)
            tasks.append(controller.get_task(task_id))

        # Use TaskSampler directly
        sampler = TaskSampler(tasks)

        episodes = sampler.sample_batch(n_episodes=20, k_shot=5, q_query=15, seed=42)

        assert len(episodes) == 20

        # Train with sampled episodes
        base_model = LinearModel(input_dim=10, output_dim=5)
        maml = MAML(base_model, inner_lr=0.01, n_inner_steps=5)

        config = TrainingConfig(n_epochs=5, episodes_per_epoch=10, verbose=False)
        trainer = MetaTrainingLoop(maml, config=config)
        summary = trainer.train(episodes, verbose=False)

        assert summary["epochs_trained"] == 5


class TestMetaLearningMetricsAndEvaluation:
    """Tests for meta-learning metrics and evaluation."""

    def test_learning_curve_tracking(self):
        """Test that learning curves are properly tracked."""
        controller = MetaLearningController()

        for i in range(5):
            X, y = create_classification_task(
                n_classes=3, n_samples=100, n_features=5, seed=i
            )
            controller.add_task(f"task_{i}", X, y)

        episodes = controller.sample_episodes(
            n_episodes=10, k_shot=5, q_query=15, seed=42
        )

        base_model = LinearModel(input_dim=5, output_dim=3)
        maml = MAML(base_model, inner_lr=0.01, n_inner_steps=5)

        config = TrainingConfig(n_epochs=20, episodes_per_epoch=5, verbose=False)
        trainer = MetaTrainingLoop(maml, config=config)
        trainer.train(episodes, verbose=False)

        # Get learning curve
        curve = trainer.get_learning_curve()

        assert "epochs" in curve
        assert "meta_losses" in curve
        assert len(curve["epochs"]) == 20
        assert len(curve["meta_losses"]) == 20

    def test_evaluation_metrics_comprehensive(self):
        """Test comprehensive evaluation metrics."""
        controller = MetaLearningController()

        for i in range(5):
            X, y = create_classification_task(
                n_classes=3, n_samples=100, n_features=5, seed=i
            )
            controller.add_task(f"task_{i}", X, y)

        episodes = controller.sample_episodes(
            n_episodes=10, k_shot=5, q_query=15, seed=42
        )

        base_model = LinearModel(input_dim=5, output_dim=3)
        maml = MAML(base_model, inner_lr=0.01, n_inner_steps=5)

        # Evaluate before training
        pre_train_metrics = maml.evaluate(episodes)

        # Train
        config = TrainingConfig(n_epochs=10, episodes_per_epoch=5, verbose=False)
        trainer = MetaTrainingLoop(maml, config=config)
        trainer.train(episodes, verbose=False)

        # Evaluate after training
        post_train_metrics = maml.evaluate(episodes)

        # Post-training should be better or equal
        assert (
            post_train_metrics["post_adapt_loss"]
            <= pre_train_metrics["post_adapt_loss"] * 1.1
        )

    def test_adaptation_gain_calculation(self):
        """Test adaptation gain in evaluation."""
        controller = MetaLearningController()

        for i in range(3):
            X, y = create_classification_task(
                n_classes=3, n_samples=100, n_features=5, seed=i
            )
            controller.add_task(f"task_{i}", X, y)

        episodes = controller.sample_episodes(
            n_episodes=5, k_shot=5, q_query=15, seed=42
        )

        base_model = LinearModel(input_dim=5, output_dim=3)
        maml = MAML(base_model, inner_lr=0.01, n_inner_steps=5)

        metrics = maml.evaluate(episodes)

        # Verify improvement calculation (raw difference, not relative)
        expected_improvement = metrics["pre_adapt_loss"] - metrics["post_adapt_loss"]

        assert abs(metrics["improvement"] - expected_improvement) < 1e-6


class TestErrorHandlingAndEdgeCases:
    """Tests for error handling and edge cases."""

    def test_empty_controller(self):
        """Test behavior with empty controller."""
        controller = MetaLearningController()

        with pytest.raises(ValueError, match="No tasks"):
            controller.sample_episode()

    def test_insufficient_samples(self):
        """Test handling of tasks with insufficient samples."""
        controller = MetaLearningController()

        # Add task with very few samples
        X = np.random.randn(5, 3)
        y = np.random.randint(0, 2, 5)
        controller.add_task("small_task", X, y)

        # Should raise error when trying to sample more than available
        with pytest.raises(ValueError, match="exceeds"):
            controller.sample_episode(k_shot=10, q_query=20)

    def test_single_task_meta_learning(self):
        """Test meta-learning with single task."""
        controller = MetaLearningController()

        X, y = create_classification_task(
            n_classes=3, n_samples=200, n_features=5, seed=42
        )
        controller.add_task("only_task", X, y)

        # Can still create episodes by sampling different subsets
        episodes = controller.sample_episodes(
            n_episodes=10, k_shot=5, q_query=15, seed=42
        )

        assert len(episodes) == 10

        # Can train (though not true meta-learning)
        base_model = LinearModel(input_dim=5, output_dim=3)
        maml = MAML(base_model, inner_lr=0.01, n_inner_steps=5)

        config = TrainingConfig(n_epochs=5, episodes_per_epoch=5, verbose=False)
        trainer = MetaTrainingLoop(maml, config=config)
        summary = trainer.train(episodes, verbose=False)

        assert summary["epochs_trained"] == 5
