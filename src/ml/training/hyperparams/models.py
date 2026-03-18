"""Hyperparameter models for ML training."""

import hashlib
import json
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any, Dict


@dataclass
class HyperparameterSet:
    """Container for hyperparameter sets used in ML training."""

    learning_rate: float
    batch_size: int
    epochs: int
    optimizer: str
    loss_function: str
    model_architecture: Dict[str, Any]
    regularization: Dict[str, Any]
    custom_params: Dict[str, Any]
    captured_at: datetime

    def to_dict(self) -> Dict[str, Any]:
        """Convert hyperparameter set to dictionary."""
        result = asdict(self)
        # Convert datetime to ISO format string for JSON serialization
        result["captured_at"] = self.captured_at.isoformat()
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HyperparameterSet":
        """Create HyperparameterSet from dictionary."""
        # Convert ISO format string back to datetime
        if "captured_at" in data and isinstance(data["captured_at"], str):
            data["captured_at"] = datetime.fromisoformat(data["captured_at"])
        return cls(**data)

    def to_json(self) -> str:
        """Serialize hyperparameter set to JSON string."""
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> "HyperparameterSet":
        """Create HyperparameterSet from JSON string."""
        data = json.loads(json_str)
        return cls.from_dict(data)

    def get_hash(self) -> str:
        """Generate a hash of the hyperparameter set for comparison."""
        # Create a deterministic string representation
        dict_repr = self.to_dict()
        # Sort keys to ensure consistent ordering
        sorted_str = json.dumps(dict_repr, sort_keys=True)
        # Generate SHA256 hash
        return hashlib.sha256(sorted_str.encode("utf-8")).hexdigest()
