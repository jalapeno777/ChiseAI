"""Tests for hyperparameter tracking functionality."""

import json
import sys
from datetime import datetime

import pytest

sys.path.insert(0, "src")
from ml.training.hyperparams import (
    HyperparameterSet,
    HyperparameterCapture,
    HyperparameterComparator,
)


class TestHyperparameterSet:
    """Test HyperparameterSet dataclass functionality."""

    def test_hyperparameter_set_creation(self):
        """Test creating a HyperparameterSet instance."""
        hp = HyperparameterSet(
            learning_rate=0.001,
            batch_size=32,
            epochs=100,
            optimizer="adam",
            loss_function="mse",
            model_architecture={"layers": [128, 64, 32]},
            regularization={"l2": 0.01},
            custom_params={"dropout": 0.5},
            captured_at=datetime.now(),
        )

        assert hp.learning_rate == 0.001
        assert hp.batch_size == 32
        assert hp.epochs == 100
        assert hp.optimizer == "adam"
        assert hp.loss_function == "mse"
        assert hp.model_architecture == {"layers": [128, 64, 32]}
        assert hp.regularization == {"l2": 0.01}
        assert hp.custom_params == {"dropout": 0.5}

    def test_to_dict(self):
        """Test converting HyperparameterSet to dictionary."""
        captured_at = datetime(2024, 1, 1, 12, 0, 0)
        hp = HyperparameterSet(
            learning_rate=0.01,
            batch_size=64,
            epochs=50,
            optimizer="sgd",
            loss_function="cross_entropy",
            model_architecture={"layers": [256, 128]},
            regularization={"l1": 0.001},
            custom_params={"momentum": 0.9},
            captured_at=captured_at,
        )

        result = hp.to_dict()

        assert result["learning_rate"] == 0.01
        assert result["batch_size"] == 64
        assert result["epochs"] == 50
        assert result["optimizer"] == "sgd"
        assert result["loss_function"] == "cross_entropy"
        assert result["model_architecture"] == {"layers": [256, 128]}
        assert result["regularization"] == {"l1": 0.001}
        assert result["custom_params"] == {"momentum": 0.9}
        assert result["captured_at"] == captured_at.isoformat()

    def test_from_dict(self):
        """Test creating HyperparameterSet from dictionary."""
        data = {
            "learning_rate": 0.005,
            "batch_size": 128,
            "epochs": 200,
            "optimizer": "rmsprop",
            "loss_function": "binary_crossentropy",
            "model_architecture": {"layers": [512, 256, 128]},
            "regularization": {"l2": 0.001},
            "custom_params": {"beta": 0.999},
            "captured_at": "2024-01-01T12:00:00",
        }

        hp = HyperparameterSet.from_dict(data)

        assert hp.learning_rate == 0.005
        assert hp.batch_size == 128
        assert hp.epochs == 200
        assert hp.optimizer == "rmsprop"
        assert hp.loss_function == "binary_crossentropy"
        assert hp.model_architecture == {"layers": [512, 256, 128]}
        assert hp.regularization == {"l2": 0.001}
        assert hp.custom_params == {"beta": 0.999}
        assert hp.captured_at == datetime(2024, 1, 1, 12, 0, 0)

    def test_to_json(self):
        """Test serializing HyperparameterSet to JSON."""
        captured_at = datetime(2024, 1, 1, 12, 0, 0)
        hp = HyperparameterSet(
            learning_rate=0.001,
            batch_size=32,
            epochs=10,
            optimizer="adam",
            loss_function="mse",
            model_architecture={},
            regularization={},
            custom_params={},
            captured_at=captured_at,
        )

        json_str = hp.to_json()

        # Verify it's valid JSON
        parsed = json.loads(json_str)
        assert parsed["learning_rate"] == 0.001
        assert parsed["batch_size"] == 32
        assert parsed["captured_at"] == captured_at.isoformat()

    def test_from_json(self):
        """Test creating HyperparameterSet from JSON string."""
        json_str = """{
            "learning_rate": 0.002,
            "batch_size": 256,
            "epochs": 150,
            "optimizer": "adamw",
            "loss_function": "huber",
            "model_architecture": {"layers": [1024, 512]},
            "regularization": {"l1": 0.0001, "l2": 0.0001},
            "custom_params": {"warmup_steps": 1000},
            "captured_at": "2024-01-01T12:00:00"
        }"""

        hp = HyperparameterSet.from_json(json_str)

        assert hp.learning_rate == 0.002
        assert hp.batch_size == 256
        assert hp.epochs == 150
        assert hp.optimizer == "adamw"
        assert hp.loss_function == "huber"
        assert hp.model_architecture == {"layers": [1024, 512]}
        assert hp.regularization == {"l1": 0.0001, "l2": 0.0001}
        assert hp.custom_params == {"warmup_steps": 1000}

    def test_get_hash(self):
        """Test generating hash of hyperparameter set."""
        captured_at = datetime(2024, 1, 1, 12, 0, 0)
        hp1 = HyperparameterSet(
            learning_rate=0.001,
            batch_size=32,
            epochs=100,
            optimizer="adam",
            loss_function="mse",
            model_architecture={"layers": [128, 64]},
            regularization={"l2": 0.01},
            custom_params={},
            captured_at=captured_at,
        )

        hp2 = HyperparameterSet(
            learning_rate=0.001,
            batch_size=32,
            epochs=100,
            optimizer="adam",
            loss_function="mse",
            model_architecture={"layers": [128, 64]},
            regularization={"l2": 0.01},
            custom_params={},
            captured_at=captured_at,
        )

        # Same hyperparameters should produce same hash
        assert hp1.get_hash() == hp2.get_hash()

        # Different hyperparameters should produce different hash
        hp3 = HyperparameterSet(
            learning_rate=0.002,  # Different
            batch_size=32,
            epochs=100,
            optimizer="adam",
            loss_function="mse",
            model_architecture={"layers": [128, 64]},
            regularization={"l2": 0.01},
            custom_params={},
            captured_at=captured_at,
        )

        assert hp1.get_hash() != hp3.get_hash()


class TestHyperparameterCapture:
    """Test HyperparameterCapture functionality."""

    def test_capture_from_config(self):
        """Test capturing hyperparameters from config dictionary."""
        config = {
            "learning_rate": 0.001,
            "batch_size": 64,
            "epochs": 50,
            "optimizer": "adam",
            "loss_function": "mse",
            "model_architecture": {"layers": [128, 64]},
            "regularization": {"l2": 0.01},
            "custom_params": {"dropout": 0.5},
        }

        hp = HyperparameterCapture.capture_from_config(config)

        assert hp.learning_rate == 0.001
        assert hp.batch_size == 64
        assert hp.epochs == 50
        assert hp.optimizer == "adam"
        assert hp.loss_function == "mse"
        assert hp.model_architecture == {"layers": [128, 64]}
        assert hp.regularization == {"l2": 0.01}
        assert hp.custom_params == {"dropout": 0.5}

    def test_capture_from_config_with_defaults(self):
        """Test capturing hyperparameters with default values."""
        config = {}  # Empty config

        hp = HyperparameterCapture.capture_from_config(config)

        assert hp.learning_rate == 0.001  # Default
        assert hp.batch_size == 32  # Default
        assert hp.epochs == 10  # Default
        assert hp.optimizer == "adam"  # Default
        assert hp.loss_function == "mse"  # Default
        assert hp.model_architecture == {}
        assert hp.regularization == {}
        assert hp.custom_params == {}

    def test_capture_from_training_pipeline_with_hyperparameters_attr(self):
        """Test capturing from pipeline with hyperparameters attribute."""

        class MockPipeline:
            def __init__(self):
                self.hyperparameters = {
                    "learning_rate": 0.01,
                    "batch_size": 128,
                    "epochs": 200,
                    "optimizer": "sgd",
                    "loss_function": "cross_entropy",
                }

        pipeline = MockPipeline()
        hp = HyperparameterCapture.capture_from_training_pipeline(pipeline)

        assert hp.learning_rate == 0.01
        assert hp.batch_size == 128
        assert hp.epochs == 200
        assert hp.optimizer == "sgd"
        assert hp.loss_function == "cross_entropy"

    def test_capture_from_training_pipeline_with_config_attr(self):
        """Test capturing from pipeline with config attribute."""

        class MockPipeline:
            def __init__(self):
                self.config = {"learning_rate": 0.005, "batch_size": 256, "epochs": 150}

        pipeline = MockPipeline()
        hp = HyperparameterCapture.capture_from_training_pipeline(pipeline)

        assert hp.learning_rate == 0.005
        assert hp.batch_size == 256
        assert hp.epochs == 150

    def test_validate_hyperparams_valid(self):
        """Test validating valid hyperparameters."""
        captured_at = datetime.now()
        hp = HyperparameterSet(
            learning_rate=0.001,
            batch_size=32,
            epochs=100,
            optimizer="adam",
            loss_function="mse",
            model_architecture={},
            regularization={},
            custom_params={},
            captured_at=captured_at,
        )

        assert HyperparameterCapture.validate_hyperparams(hp) is True

    def test_validate_hyperparams_invalid_learning_rate(self):
        """Test validating hyperparameters with invalid learning rate."""
        captured_at = datetime.now()
        hp = HyperparameterSet(
            learning_rate=-0.001,  # Invalid: negative
            batch_size=32,
            epochs=100,
            optimizer="adam",
            loss_function="mse",
            model_architecture={},
            regularization={},
            custom_params={},
            captured_at=captured_at,
        )

        assert HyperparameterCapture.validate_hyperparams(hp) is False

    def test_validate_hyperparams_invalid_batch_size(self):
        """Test validating hyperparameters with invalid batch size."""
        captured_at = datetime.now()
        hp = HyperparameterSet(
            learning_rate=0.001,
            batch_size=0,  # Invalid: zero
            epochs=100,
            optimizer="adam",
            loss_function="mse",
            model_architecture={},
            regularization={},
            custom_params={},
            captured_at=captured_at,
        )

        assert HyperparameterCapture.validate_hyperparams(hp) is False

    def test_validate_hyperparams_empty_optimizer(self):
        """Test validating hyperparameters with empty optimizer."""
        captured_at = datetime.now()
        hp = HyperparameterSet(
            learning_rate=0.001,
            batch_size=32,
            epochs=100,
            optimizer="",  # Invalid: empty string
            loss_function="mse",
            model_architecture={},
            regularization={},
            custom_params={},
            captured_at=captured_at,
        )

        assert HyperparameterCapture.validate_hyperparams(hp) is False


class TestHyperparameterComparator:
    """Test HyperparameterComparator functionality."""

    def test_compare_identical_sets(self):
        """Test comparing identical hyperparameter sets."""
        captured_at = datetime.now()
        hp1 = HyperparameterSet(
            learning_rate=0.001,
            batch_size=32,
            epochs=100,
            optimizer="adam",
            loss_function="mse",
            model_architecture={"layers": [128, 64]},
            regularization={"l2": 0.01},
            custom_params={},
            captured_at=captured_at,
        )

        hp2 = HyperparameterSet(
            learning_rate=0.001,
            batch_size=32,
            epochs=100,
            optimizer="adam",
            loss_function="mse",
            model_architecture={"layers": [128, 64]},
            regularization={"l2": 0.01},
            custom_params={},
            captured_at=captured_at,
        )

        diff = HyperparameterComparator.compare(hp1, hp2)

        assert len(diff["changed"]) == 0
        assert len(diff["added"]) == 0
        assert len(diff["removed"]) == 0
        assert len(diff["unchanged"]) > 0

    def test_compare_changed_parameters(self):
        """Test comparing hyperparameter sets with changed parameters."""
        captured_at = datetime.now()
        hp1 = HyperparameterSet(
            learning_rate=0.001,
            batch_size=32,
            epochs=100,
            optimizer="adam",
            loss_function="mse",
            model_architecture={"layers": [128, 64]},
            regularization={"l2": 0.01},
            custom_params={},
            captured_at=captured_at,
        )

        hp2 = HyperparameterSet(
            learning_rate=0.002,  # Changed
            batch_size=64,  # Changed
            epochs=100,
            optimizer="adam",
            loss_function="mse",
            model_architecture={"layers": [128, 64]},
            regularization={"l2": 0.01},
            custom_params={},
            captured_at=captured_at,
        )

        diff = HyperparameterComparator.compare(hp1, hp2)

        assert "learning_rate" in diff["changed"]
        assert "batch_size" in diff["changed"]
        assert diff["changed"]["learning_rate"]["old"] == 0.001
        assert diff["changed"]["learning_rate"]["new"] == 0.002
        assert diff["changed"]["batch_size"]["old"] == 32
        assert diff["changed"]["batch_size"]["new"] == 64

    def test_compare_added_parameters(self):
        """Test comparing hyperparameter sets with added parameters."""
        captured_at = datetime.now()
        hp1 = HyperparameterSet(
            learning_rate=0.001,
            batch_size=32,
            epochs=100,
            optimizer="adam",
            loss_function="mse",
            model_architecture={"layers": [128, 64]},
            regularization={"l2": 0.01},
            custom_params={"dropout": 0.5},
            captured_at=captured_at,
        )

        hp2 = HyperparameterSet(
            learning_rate=0.001,
            batch_size=32,
            epochs=100,
            optimizer="adam",
            loss_function="mse",
            model_architecture={"layers": [128, 64]},
            regularization={"l2": 0.01},
            custom_params={"dropout": 0.5, "momentum": 0.9},  # Added parameter
            captured_at=captured_at,
        )

        diff = HyperparameterComparator.compare(hp1, hp2)

        assert "custom_params" in diff["changed"]  # custom_params itself changed

    def test_diff_to_string(self):
        """Test converting diff to string."""
        diff = {
            "changed": {
                "learning_rate": {"old": 0.001, "new": 0.002},
                "batch_size": {"old": 32, "new": 64},
            },
            "added": {},
            "removed": {},
            "unchanged": {"epochs": 100, "optimizer": "adam"},
        }

        result = HyperparameterComparator.diff_to_string(diff)

        assert "Changed parameters:" in result
        assert "learning_rate: 0.001 → 0.002" in result
        assert "batch_size: 32 → 64" in result
        assert "Unchanged parameters: 2" in result

    def test_diff_to_string_no_differences(self):
        """Test converting diff to string when there are no differences."""
        diff = {
            "changed": {},
            "added": {},
            "removed": {},
            "unchanged": {"learning_rate": 0.001, "batch_size": 32},
        }

        result = HyperparameterComparator.diff_to_string(diff)

        assert "No differences found" in result

    def test_get_changed_params(self):
        """Test getting list of changed parameters."""
        captured_at = datetime.now()
        hp1 = HyperparameterSet(
            learning_rate=0.001,
            batch_size=32,
            epochs=100,
            optimizer="adam",
            loss_function="mse",
            model_architecture={"layers": [128, 64]},
            regularization={"l2": 0.01},
            custom_params={},
            captured_at=captured_at,
        )

        hp2 = HyperparameterSet(
            learning_rate=0.002,  # Changed
            batch_size=32,
            epochs=150,  # Changed
            optimizer="sgd",  # Changed
            loss_function="mse",
            model_architecture={"layers": [128, 64]},
            regularization={"l2": 0.01},
            custom_params={},
            captured_at=captured_at,
        )

        changed = HyperparameterComparator.get_changed_params(hp1, hp2)

        assert "learning_rate" in changed
        assert "epochs" in changed
        assert "optimizer" in changed
        assert "batch_size" not in changed

    def test_get_unchanged_params(self):
        """Test getting list of unchanged parameters."""
        captured_at = datetime.now()
        hp1 = HyperparameterSet(
            learning_rate=0.001,
            batch_size=32,
            epochs=100,
            optimizer="adam",
            loss_function="mse",
            model_architecture={"layers": [128, 64]},
            regularization={"l2": 0.01},
            custom_params={},
            captured_at=captured_at,
        )

        hp2 = HyperparameterSet(
            learning_rate=0.002,  # Changed
            batch_size=32,  # Unchanged
            epochs=100,  # Unchanged
            optimizer="adam",  # Unchanged
            loss_function="mse",
            model_architecture={"layers": [128, 64]},
            regularization={"l2": 0.01},
            custom_params={},
            captured_at=captured_at,
        )

        unchanged = HyperparameterComparator.get_unchanged_params(hp1, hp2)

        assert "batch_size" in unchanged
        assert "epochs" in unchanged
        assert "optimizer" in unchanged
        assert "learning_rate" not in unchanged
