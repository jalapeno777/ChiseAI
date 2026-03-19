"""Tests for data format converters."""

import pytest
from src.autocog_integration.converters import (
    AutocogToStrongConverter,
    StrongToAutocogConverter,
    BidirectionalConverter,
)


class TestAutocogToStrongConverter:
    """Tests for AUTOCOG to STRONG converter."""

    def test_create_converter(self):
        """Test creating converter."""
        converter = AutocogToStrongConverter()
        assert converter is not None

    def test_can_convert_valid_autocog_data(self):
        """Test checking if valid AUTOCOG data can be converted."""
        converter = AutocogToStrongConverter()
        data = {
            "knowledge_type": "action",
            "source_system": "autocog",
            "payload": {"test": "data"},
        }
        assert converter.can_convert(data) is True

    def test_can_convert_invalid_data(self):
        """Test checking if invalid data can be converted."""
        converter = AutocogToStrongConverter()

        # Missing knowledge_type
        data1 = {"source_system": "autocog"}
        assert converter.can_convert(data1) is False

        # Missing source_system
        data2 = {"knowledge_type": "action"}
        assert converter.can_convert(data2) is False

        # Wrong source_system
        data3 = {
            "knowledge_type": "action",
            "source_system": "strong",
        }
        assert converter.can_convert(data3) is False

    def test_convert_action(self):
        """Test converting AUTOCOG action to STRONG format."""
        converter = AutocogToStrongConverter()
        data = {
            "knowledge_type": "action",
            "knowledge_item_id": "action_001",
            "source_system": "autocog",
            "payload": {
                "action_id": "001",
                "action_type": "execute",
                "parameters": {"param1": "value1"},
                "priority": "high",
                "confidence": 0.85,
                "timestamp": "2024-01-01T00:00:00Z",
            },
        }

        result = converter.convert(data)

        assert result["knowledge_type"] == "belief_embedding"
        assert result["embedding_id"] == "001"
        assert "vector" in result
        assert result["metadata"]["action_type"] == "execute"
        assert result["metadata"]["priority"] == "high"
        assert result["confidence"] == 0.85

    def test_convert_assessment(self):
        """Test converting AUTOCOG assessment to STRONG format."""
        converter = AutocogToStrongConverter()
        data = {
            "knowledge_type": "assessment",
            "knowledge_item_id": "assessment_001",
            "source_system": "autocog",
            "payload": {
                "artifact_id": "001",
                "confidence_score": 0.90,
                "recommendations": ["rec1", "rec2"],
                "findings": {"finding1": "value1"},
            },
        }

        result = converter.convert(data)

        assert result["knowledge_type"] == "learning_update"
        assert result["update_id"] == "001"
        assert result["gradient_info"]["confidence_score"] == 0.90
        assert result["gradient_info"]["recommendations"] == ["rec1", "rec2"]
        assert abs(result["loss_value"] - 0.10) < 0.001  # 1.0 - 0.90

    def test_convert_validation_result(self):
        """Test converting AUTOCOG validation result to STRONG format."""
        converter = AutocogToStrongConverter()
        data = {
            "knowledge_type": "validation_result",
            "knowledge_item_id": "validation_001",
            "source_system": "autocog",
            "payload": {
                "validation_id": "001",
                "is_valid": True,
                "findings": {
                    "check1": True,
                    "check2": False,
                    "score": 0.95,
                },
            },
        }

        result = converter.convert(data)

        assert result["knowledge_type"] == "symbolic_rule"
        assert result["rule_id"] == "001"
        assert "rule_expression" in result
        assert result["confidence"] == 0.9  # is_valid=True gives 0.9

    def test_convert_cycle_result(self):
        """Test converting AUTOCOG cycle result to STRONG format."""
        converter = AutocogToStrongConverter()
        data = {
            "knowledge_type": "cycle_result",
            "knowledge_item_id": "cycle_001",
            "source_system": "autocog",
            "payload": {
                "cycle_id": "001",
                "cycle_type": "meta_learning",
                "metrics": {"success_rate": 0.85, "accuracy": 0.90},
                "completed_at": "2024-01-01T00:00:00Z",
            },
        }

        result = converter.convert(data)

        assert result["knowledge_type"] == "meta_learning_update"
        assert result["update_id"] == "cycle_001"
        assert result["performance_metrics"]["success_rate"] == 0.85
        assert result["learning_rate_adjustment"] == 1.1  # success_rate > 0.8

    def test_convert_generic(self):
        """Test converting generic AUTOCOG data to STRONG format."""
        converter = AutocogToStrongConverter()
        data = {
            "knowledge_type": "unknown_type",
            "knowledge_item_id": "generic_001",
            "source_system": "autocog",
            "payload": {"test": "data"},
        }

        result = converter.convert(data)

        assert result["knowledge_type"] == "generic_embedding"
        assert result["embedding_id"] == "generic_001"
        assert "vector" in result

    def test_convert_invalid_data_raises_error(self):
        """Test that converting invalid data raises error."""
        converter = AutocogToStrongConverter()
        data = {
            "knowledge_type": "action",
            "source_system": "strong",  # Wrong source system
        }

        with pytest.raises(ValueError, match="cannot be converted"):
            converter.convert(data)


class TestStrongToAutocogConverter:
    """Tests for STRONG to AUTOCOG converter."""

    def test_create_converter(self):
        """Test creating converter."""
        converter = StrongToAutocogConverter()
        assert converter is not None

    def test_can_convert_valid_strong_data(self):
        """Test checking if valid STRONG data can be converted."""
        converter = StrongToAutocogConverter()
        data = {
            "knowledge_type": "belief_embedding",
            "source_system": "strong",
            "payload": {"test": "data"},
        }
        assert converter.can_convert(data) is True

    def test_can_convert_invalid_data(self):
        """Test checking if invalid data can be converted."""
        converter = StrongToAutocogConverter()

        # Missing knowledge_type
        data1 = {"source_system": "strong"}
        assert converter.can_convert(data1) is False

        # Missing source_system
        data2 = {"knowledge_type": "belief_embedding"}
        assert converter.can_convert(data2) is False

        # Wrong source_system
        data3 = {
            "knowledge_type": "belief_embedding",
            "source_system": "autocog",
        }
        assert converter.can_convert(data3) is False

    def test_convert_belief_embedding(self):
        """Test converting STRONG belief embedding to AUTOCOG format."""
        converter = StrongToAutocogConverter()
        data = {
            "knowledge_type": "belief_embedding",
            "knowledge_item_id": "embedding_001",
            "source_system": "strong",
            "embedding_id": "001",
            "vector": [0.1, 0.2, 0.3],
            "metadata": {
                "action_type": "execute",
                "parameters": {"param1": "value1"},
                "priority": "high",
                "timestamp": "2024-01-01T00:00:00Z",
            },
            "confidence": 0.85,
        }

        result = converter.convert(data)

        assert result["knowledge_type"] == "action"
        assert result["action_id"] == "001"
        assert result["action_type"] == "execute"
        assert result["parameters"] == {"param1": "value1"}
        assert result["priority"] == "high"
        assert result["confidence"] == 0.85

    def test_convert_learning_update(self):
        """Test converting STRONG learning update to AUTOCOG format."""
        converter = StrongToAutocogConverter()
        data = {
            "knowledge_type": "learning_update",
            "knowledge_item_id": "update_001",
            "source_system": "strong",
            "update_id": "001",
            "gradient_info": {
                "confidence_score": 0.90,
                "recommendations": ["rec1", "rec2"],
                "findings": {"finding1": "value1"},
            },
            "loss_value": 0.10,
        }

        result = converter.convert(data)

        assert result["knowledge_type"] == "assessment"
        assert result["artifact_id"] == "001"
        assert result["confidence_score"] == 0.90
        assert result["recommendations"] == ["rec1", "rec2"]
        assert result["findings"] == {"finding1": "value1"}

    def test_convert_symbolic_rule(self):
        """Test converting STRONG symbolic rule to AUTOCOG format."""
        converter = StrongToAutocogConverter()
        data = {
            "knowledge_type": "symbolic_rule",
            "knowledge_item_id": "rule_001",
            "source_system": "strong",
            "rule_id": "001",
            "rule_expression": "x > 0",
            "confidence": 0.85,
            "metadata": {
                "findings": {"finding1": "value1"},
                "validated_at": "2024-01-01T00:00:00Z",
            },
        }

        result = converter.convert(data)

        assert result["knowledge_type"] == "validation_result"
        assert result["validation_id"] == "001"
        assert result["is_valid"] is True  # confidence > 0.5
        assert result["findings"] == {"finding1": "value1"}
        assert result["rule_expression"] == "x > 0"

    def test_convert_meta_learning_update(self):
        """Test converting STRONG meta-learning update to AUTOCOG format."""
        converter = StrongToAutocogConverter()
        data = {
            "knowledge_type": "meta_learning_update",
            "knowledge_item_id": "meta_001",
            "source_system": "strong",
            "update_id": "meta_001",
            "performance_metrics": {"accuracy": 0.90, "loss": 0.10},
            "learning_rate_adjustment": 1.1,
            "metadata": {
                "cycle_id": "001",
                "cycle_type": "meta_learning",
                "completed_at": "2024-01-01T00:00:00Z",
            },
        }

        result = converter.convert(data)

        assert result["knowledge_type"] == "cycle_result"
        assert result["cycle_id"] == "001"
        assert result["metrics"]["accuracy"] == 0.90
        assert result["learning_rate_adjustment"] == 1.1

    def test_convert_generic(self):
        """Test converting generic STRONG data to AUTOCOG format."""
        converter = StrongToAutocogConverter()
        data = {
            "knowledge_type": "unknown_type",
            "knowledge_item_id": "generic_001",
            "source_system": "strong",
            "embedding_id": "001",
            "vector": [0.1, 0.2, 0.3],
            "metadata": {"test": "data"},
            "confidence": 0.85,
        }

        result = converter.convert(data)

        assert result["knowledge_type"] == "generic_knowledge"
        assert result["knowledge_item_id"] == "001"
        assert result["payload"] == [0.1, 0.2, 0.3]

    def test_convert_invalid_data_raises_error(self):
        """Test that converting invalid data raises error."""
        converter = StrongToAutocogConverter()
        data = {
            "knowledge_type": "belief_embedding",
            "source_system": "autocog",  # Wrong source system
        }

        with pytest.raises(ValueError, match="cannot be converted"):
            converter.convert(data)


class TestBidirectionalConverter:
    """Tests for bidirectional converter."""

    def test_create_converter(self):
        """Test creating bidirectional converter."""
        converter = BidirectionalConverter()
        assert converter is not None
        assert converter.autocog_to_strong is not None
        assert converter.strong_to_autocog is not None

    def test_convert_autocog_to_strong(self):
        """Test converting AUTOCOG to STRONG."""
        converter = BidirectionalConverter()
        data = {
            "knowledge_type": "action",
            "source_system": "autocog",
            "payload": {"action_id": "001", "action_type": "execute", "parameters": {}},
        }

        result = converter.convert(data, "autocog_to_strong")
        assert result["knowledge_type"] == "belief_embedding"

    def test_convert_strong_to_autocog(self):
        """Test converting STRONG to AUTOCOG."""
        converter = BidirectionalConverter()
        data = {
            "knowledge_type": "belief_embedding",
            "source_system": "strong",
            "embedding_id": "001",
            "vector": [0.1, 0.2, 0.3],
            "metadata": {},
        }

        result = converter.convert(data, "strong_to_autocog")
        assert result["knowledge_type"] == "action"

    def test_can_convert_autocog_to_strong(self):
        """Test checking if AUTOCOG to STRONG conversion is possible."""
        converter = BidirectionalConverter()
        data = {
            "knowledge_type": "action",
            "source_system": "autocog",
        }

        assert converter.can_convert(data, "autocog_to_strong") is True
        assert converter.can_convert(data, "strong_to_autocog") is False

    def test_can_convert_strong_to_autocog(self):
        """Test checking if STRONG to AUTOCOG conversion is possible."""
        converter = BidirectionalConverter()
        data = {
            "knowledge_type": "belief_embedding",
            "source_system": "strong",
        }

        assert converter.can_convert(data, "strong_to_autocog") is True
        assert converter.can_convert(data, "autocog_to_strong") is False

    def test_invalid_direction_raises_error(self):
        """Test that invalid direction raises error."""
        converter = BidirectionalConverter()
        data = {"test": "data"}

        # convert should raise ValueError for invalid direction
        with pytest.raises(ValueError, match="Unknown conversion direction"):
            converter.convert(data, "invalid_direction")

        # can_convert should return False for invalid direction (not raise)
        result = converter.can_convert(data, "invalid_direction")
        assert result is False
