"""Data format converters for cross-system knowledge transfer."""

from abc import ABC, abstractmethod
from typing import Any


class DataFormatConverter(ABC):
    """Abstract base class for data format converters."""

    @abstractmethod
    def convert(self, data: dict[str, Any]) -> dict[str, Any]:
        """Convert data from source format to target format."""
        pass

    @abstractmethod
    def can_convert(self, data: dict[str, Any]) -> bool:
        """Check if data can be converted."""
        pass


class AutocogToStrongConverter(DataFormatConverter):
    """Converts AUTOCOG data formats to STRONG system formats."""

    def convert(self, data: dict[str, Any]) -> dict[str, Any]:
        """Convert AUTOCOG data to STRONG format."""
        if not self.can_convert(data):
            raise ValueError("Data cannot be converted from AUTOCOG to STRONG format")

        knowledge_type = data.get("knowledge_type", "")

        if knowledge_type == "action":
            return self._convert_action(data)
        elif knowledge_type == "assessment":
            return self._convert_assessment(data)
        elif knowledge_type == "validation_result":
            return self._convert_validation_result(data)
        elif knowledge_type == "cycle_result":
            return self._convert_cycle_result(data)
        else:
            return self._convert_generic(data)

    def can_convert(self, data: dict[str, Any]) -> bool:
        """Check if data can be converted from AUTOCOG format."""
        return (
            isinstance(data, dict)
            and "knowledge_type" in data
            and "source_system" in data
            and data.get("source_system") == "autocog"
        )

    def _convert_action(self, data: dict[str, Any]) -> dict[str, Any]:
        """Convert AUTOCOG action to STRONG belief embedding."""
        payload = data.get("payload", {})

        return {
            "knowledge_type": "belief_embedding",
            "embedding_id": payload.get("action_id", ""),
            "vector": self._action_to_vector(payload),
            "metadata": {
                "action_type": payload.get("action_type", ""),
                "parameters": payload.get("parameters", {}),
                "priority": payload.get("priority", "medium"),
                "timestamp": payload.get("timestamp", ""),
                "source": "autocog_action",
            },
            "confidence": payload.get("confidence", 0.5),
        }

    def _convert_assessment(self, data: dict[str, Any]) -> dict[str, Any]:
        """Convert AUTOCOG assessment to STRONG learning update."""
        payload = data.get("payload", {})

        return {
            "knowledge_type": "learning_update",
            "update_id": payload.get("artifact_id", ""),
            "gradient_info": {
                "assessment_type": "self_assessment",
                "confidence_score": payload.get("confidence_score", 0.0),
                "recommendations": payload.get("recommendations", []),
                "findings": payload.get("findings", {}),
            },
            "loss_value": 1.0 - payload.get("confidence_score", 0.0),
            "metadata": {
                "assessment_id": payload.get("artifact_id", ""),
                "generated_at": payload.get("generated_at", ""),
                "source": "autocog_assessment",
            },
        }

    def _convert_validation_result(self, data: dict[str, Any]) -> dict[str, Any]:
        """Convert AUTOCOG validation result to STRONG symbolic rule."""
        payload = data.get("payload", {})

        return {
            "knowledge_type": "symbolic_rule",
            "rule_id": payload.get("validation_id", ""),
            "rule_expression": self._validation_to_rule(payload),
            "confidence": 0.9 if payload.get("is_valid", False) else 0.1,
            "metadata": {
                "validation_id": payload.get("validation_id", ""),
                "validated_at": payload.get("validated_at", ""),
                "findings": payload.get("findings", {}),
                "source": "autocog_validation",
            },
        }

    def _convert_cycle_result(self, data: dict[str, Any]) -> dict[str, Any]:
        """Convert AUTOCOG cycle result to STRONG meta-learning update."""
        payload = data.get("payload", {})

        return {
            "knowledge_type": "meta_learning_update",
            "update_id": f"cycle_{payload.get('cycle_id', '')}",
            "performance_metrics": payload.get("metrics", {}),
            "learning_rate_adjustment": self._calculate_lr_adjustment(payload),
            "metadata": {
                "cycle_id": payload.get("cycle_id", ""),
                "cycle_type": payload.get("cycle_type", ""),
                "completed_at": payload.get("completed_at", ""),
                "source": "autocog_cycle",
            },
        }

    def _convert_generic(self, data: dict[str, Any]) -> dict[str, Any]:
        """Convert generic AUTOCOG data to STRONG format."""
        return {
            "knowledge_type": "generic_embedding",
            "embedding_id": data.get("knowledge_item_id", ""),
            "vector": self._generic_to_vector(data),
            "metadata": {
                "original_type": data.get("knowledge_type", ""),
                "converted_at": "",
                "source": "autocog_generic",
            },
        }

    def _action_to_vector(self, action: dict[str, Any]) -> list:
        """Convert action to vector representation."""
        # Simple vectorization - in practice would use proper embedding
        action_type = action.get("action_type", "")
        priority = action.get("priority", "medium")

        # Create a simple vector based on action characteristics
        vector = [
            1.0 if action_type == "execute" else 0.5,
            1.0 if priority == "high" else 0.7 if priority == "medium" else 0.3,
            float(action.get("confidence", 0.5)),
        ]
        return vector

    def _validation_to_rule(self, validation: dict[str, Any]) -> str:
        """Convert validation result to symbolic rule expression."""
        findings = validation.get("findings", {})
        is_valid = validation.get("is_valid", False)

        # Create a simple rule expression
        rule_parts = []
        for key, value in findings.items():
            if isinstance(value, bool):
                rule_parts.append(f"{key}={value}")
            elif isinstance(value, (int, float)):
                rule_parts.append(f"{key}>{value}")

        return f"validation_passed={is_valid} AND {' AND '.join(rule_parts)}"

    def _calculate_lr_adjustment(self, cycle_result: dict[str, Any]) -> float:
        """Calculate learning rate adjustment from cycle result."""
        metrics = cycle_result.get("metrics", {})
        success_rate = metrics.get("success_rate", 0.5)

        # Adjust learning rate based on success rate
        if success_rate > 0.8:
            return 1.1  # Increase learning rate
        elif success_rate < 0.3:
            return 0.9  # Decrease learning rate
        else:
            return 1.0  # Keep same

    def _generic_to_vector(self, data: dict[str, Any]) -> list:
        """Convert generic data to vector representation."""
        # Simple vectorization for generic data
        payload = data.get("payload", {})
        return [float(hash(str(payload)) % 1000) / 1000.0]


class StrongToAutocogConverter(DataFormatConverter):
    """Converts STRONG system data formats to AUTOCOG formats."""

    def convert(self, data: dict[str, Any]) -> dict[str, Any]:
        """Convert STRONG data to AUTOCOG format."""
        if not self.can_convert(data):
            raise ValueError("Data cannot be converted from STRONG to AUTOCOG format")

        knowledge_type = data.get("knowledge_type", "")

        if knowledge_type == "belief_embedding":
            return self._convert_belief_embedding(data)
        elif knowledge_type == "learning_update":
            return self._convert_learning_update(data)
        elif knowledge_type == "symbolic_rule":
            return self._convert_symbolic_rule(data)
        elif knowledge_type == "meta_learning_update":
            return self._convert_meta_learning_update(data)
        else:
            return self._convert_generic(data)

    def can_convert(self, data: dict[str, Any]) -> bool:
        """Check if data can be converted from STRONG format."""
        return (
            isinstance(data, dict)
            and "knowledge_type" in data
            and "source_system" in data
            and data.get("source_system") == "strong"
        )

    def _convert_belief_embedding(self, data: dict[str, Any]) -> dict[str, Any]:
        """Convert STRONG belief embedding to AUTOCOG action."""
        metadata = data.get("metadata", {})

        return {
            "knowledge_type": "action",
            "action_id": data.get("embedding_id", ""),
            "action_type": metadata.get("action_type", "execute"),
            "parameters": metadata.get("parameters", {}),
            "priority": metadata.get("priority", "medium"),
            "confidence": data.get("confidence", 0.5),
            "timestamp": metadata.get("timestamp", ""),
            "source_system": "strong",
        }

    def _convert_learning_update(self, data: dict[str, Any]) -> dict[str, Any]:
        """Convert STRONG learning update to AUTOCOG assessment."""
        gradient_info = data.get("gradient_info", {})

        return {
            "knowledge_type": "assessment",
            "artifact_id": data.get("update_id", ""),
            "confidence_score": 1.0 - data.get("loss_value", 0.0),
            "recommendations": gradient_info.get("recommendations", []),
            "findings": gradient_info.get("findings", {}),
            "assessment_type": gradient_info.get("assessment_type", "self_assessment"),
            "generated_at": data.get("metadata", {}).get("generated_at", ""),
            "source_system": "strong",
        }

    def _convert_symbolic_rule(self, data: dict[str, Any]) -> dict[str, Any]:
        """Convert STRONG symbolic rule to AUTOCOG validation result."""
        metadata = data.get("metadata", {})

        return {
            "knowledge_type": "validation_result",
            "validation_id": data.get("rule_id", ""),
            "is_valid": data.get("confidence", 0.0) > 0.5,
            "findings": metadata.get("findings", {}),
            "validated_at": metadata.get("validated_at", ""),
            "rule_expression": data.get("rule_expression", ""),
            "source_system": "strong",
        }

    def _convert_meta_learning_update(self, data: dict[str, Any]) -> dict[str, Any]:
        """Convert STRONG meta-learning update to AUTOCOG cycle result."""
        metadata = data.get("metadata", {})

        return {
            "knowledge_type": "cycle_result",
            "cycle_id": metadata.get("cycle_id", ""),
            "cycle_type": metadata.get("cycle_type", "meta_learning"),
            "metrics": data.get("performance_metrics", {}),
            "completed_at": metadata.get("completed_at", ""),
            "learning_rate_adjustment": data.get("learning_rate_adjustment", 1.0),
            "source_system": "strong",
        }

    def _convert_generic(self, data: dict[str, Any]) -> dict[str, Any]:
        """Convert generic STRONG data to AUTOCOG format."""
        return {
            "knowledge_type": "generic_knowledge",
            "knowledge_item_id": data.get("embedding_id", ""),
            "payload": data.get("vector", []),
            "metadata": data.get("metadata", {}),
            "confidence": data.get("confidence", 0.5),
            "source_system": "strong",
        }


class BidirectionalConverter:
    """Bidirectional converter supporting both AUTOCOG->STRONG and STRONG->AUTOCOG."""

    def __init__(self):
        self.autocog_to_strong = AutocogToStrongConverter()
        self.strong_to_autocog = StrongToAutocogConverter()

    def convert(self, data: dict[str, Any], direction: str) -> dict[str, Any]:
        """
        Convert data in specified direction.

        Args:
            data: Data to convert
            direction: "autocog_to_strong" or "strong_to_autocog"

        Returns:
            Converted data
        """
        if direction == "autocog_to_strong":
            return self.autocog_to_strong.convert(data)
        elif direction == "strong_to_autocog":
            return self.strong_to_autocog.convert(data)
        else:
            raise ValueError(f"Unknown conversion direction: {direction}")

    def can_convert(self, data: dict[str, Any], direction: str) -> bool:
        """Check if data can be converted in specified direction."""
        if direction == "autocog_to_strong":
            return self.autocog_to_strong.can_convert(data)
        elif direction == "strong_to_autocog":
            return self.strong_to_autocog.can_convert(data)
        else:
            return False
