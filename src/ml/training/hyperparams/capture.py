"""Hyperparameter capture utilities."""

from typing import Any, Dict

from .models import HyperparameterSet


class HyperparameterCapture:
    """Utility class for capturing hyperparameters from various sources."""

    @staticmethod
    def capture_from_config(config_dict: Dict[str, Any]) -> HyperparameterSet:
        """Capture hyperparameters from a configuration dictionary.

        Args:
            config_dict: Dictionary containing hyperparameter configuration

        Returns:
            HyperparameterSet instance
        """
        # Extract required fields with defaults
        learning_rate = float(config_dict.get("learning_rate", 0.001))
        batch_size = int(config_dict.get("batch_size", 32))
        epochs = int(config_dict.get("epochs", 10))
        optimizer = str(config_dict.get("optimizer", "adam"))
        loss_function = str(config_dict.get("loss_function", "mse"))

        # Extract nested dictionaries with defaults
        model_architecture = config_dict.get("model_architecture", {})
        if not isinstance(model_architecture, dict):
            model_architecture = {}

        regularization = config_dict.get("regularization", {})
        if not isinstance(regularization, dict):
            regularization = {}

        custom_params = config_dict.get("custom_params", {})
        if not isinstance(custom_params, dict):
            custom_params = {}

        from datetime import datetime

        return HyperparameterSet(
            learning_rate=learning_rate,
            batch_size=batch_size,
            epochs=epochs,
            optimizer=optimizer,
            loss_function=loss_function,
            model_architecture=model_architecture,
            regularization=regularization,
            custom_params=custom_params,
            captured_at=datetime.now(),
        )

    @staticmethod
    def capture_from_training_pipeline(pipeline: Any) -> HyperparameterSet:
        """Capture hyperparameters from a training pipeline object.

        Args:
            pipeline: Training pipeline object with hyperparameter attributes

        Returns:
            HyperparameterSet instance
        """
        # Try to extract hyperparameters from common pipeline attributes
        config_dict = {}

        # Check for common attribute names
        if hasattr(pipeline, "hyperparameters"):
            config_dict = pipeline.hyperparameters
        elif hasattr(pipeline, "config"):
            config_dict = pipeline.config
        elif hasattr(pipeline, "params"):
            config_dict = pipeline.params
        elif hasattr(pipeline, "get_params"):
            config_dict = pipeline.get_params()
        else:
            # Try to extract from __dict__
            config_dict = getattr(pipeline, "__dict__", {})

        # Ensure we have a dictionary
        if not isinstance(config_dict, dict):
            config_dict = {}

        return HyperparameterCapture.capture_from_config(config_dict)

    @staticmethod
    def validate_hyperparams(hyperparams: HyperparameterSet) -> bool:
        """Validate hyperparameter values.

        Args:
            hyperparams: HyperparameterSet to validate

        Returns:
            True if hyperparameters are valid, False otherwise
        """
        try:
            # Check required fields have reasonable values
            if hyperparams.learning_rate <= 0:
                return False
            if hyperparams.batch_size <= 0:
                return False
            if hyperparams.epochs <= 0:
                return False
            if not hyperparams.optimizer:
                return False
            if not hyperparams.loss_function:
                return False

            # Check dictionaries are valid
            if not isinstance(hyperparams.model_architecture, dict):
                return False
            if not isinstance(hyperparams.regularization, dict):
                return False
            if not isinstance(hyperparams.custom_params, dict):
                return False

            return True
        except (AttributeError, TypeError):
            return False
