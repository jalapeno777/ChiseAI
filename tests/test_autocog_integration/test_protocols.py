"""Tests for knowledge transfer protocols."""

import pytest
from datetime import datetime
from src.autocog_integration.protocols import (
    KnowledgeTransferProtocol,
    TransferEvent,
    TransferStatus,
    TransferPriority,
    ValidationResult,
)


class TestTransferEvent:
    """Tests for TransferEvent."""

    def test_create_transfer_event(self):
        """Test creating a transfer event."""
        event = TransferEvent(
            source_system="autocog",
            target_system="strong",
            knowledge_type="action",
            knowledge_item_id="test_001",
            payload={"test": "data"},
        )

        assert event.source_system == "autocog"
        assert event.target_system == "strong"
        assert event.knowledge_type == "action"
        assert event.knowledge_item_id == "test_001"
        assert event.status == TransferStatus.PENDING
        assert event.priority == TransferPriority.MEDIUM

    def test_mark_in_progress(self):
        """Test marking transfer as in progress."""
        event = TransferEvent()
        event.mark_in_progress()
        assert event.status == TransferStatus.IN_PROGRESS

    def test_mark_completed(self):
        """Test marking transfer as completed."""
        event = TransferEvent()
        event.mark_completed()
        assert event.status == TransferStatus.COMPLETED

    def test_mark_failed(self):
        """Test marking transfer as failed."""
        event = TransferEvent()
        event.mark_failed("Test error")
        assert event.status == TransferStatus.FAILED
        assert event.error == "Test error"

    def test_mark_validated(self):
        """Test marking transfer as validated."""
        event = TransferEvent()
        event.mark_validated()
        assert event.status == TransferStatus.VALIDATED


class TestValidationResult:
    """Tests for ValidationResult."""

    def test_create_validation_result(self):
        """Test creating validation result."""
        result = ValidationResult()
        assert result.is_valid is False
        assert result.errors == []
        assert result.warnings == []

    def test_add_error(self):
        """Test adding validation error."""
        result = ValidationResult()
        result.add_error("Test error")
        assert result.is_valid is False
        assert "Test error" in result.errors

    def test_add_warning(self):
        """Test adding validation warning."""
        result = ValidationResult()
        result.add_warning("Test warning")
        assert "Test warning" in result.warnings


class TestKnowledgeTransferProtocol:
    """Tests for KnowledgeTransferProtocol."""

    def test_create_protocol(self):
        """Test creating protocol."""
        protocol = KnowledgeTransferProtocol()
        assert protocol.max_retries == 3
        assert protocol.enable_validation is True

    def test_create_transfer_event(self):
        """Test creating transfer event through protocol."""
        protocol = KnowledgeTransferProtocol()
        event = protocol.create_transfer_event(
            source_system="autocog",
            target_system="strong",
            knowledge_type="action",
            knowledge_item_id="test_001",
            payload={"test": "data"},
        )

        assert event.source_system == "autocog"
        assert event.target_system == "strong"
        assert event.knowledge_type == "action"

    def test_validate_transfer_valid(self):
        """Test validating a valid transfer."""
        protocol = KnowledgeTransferProtocol()
        event = protocol.create_transfer_event(
            source_system="autocog",
            target_system="strong",
            knowledge_type="action",
            knowledge_item_id="test_001",
            payload={"action_id": "001", "action_type": "execute", "parameters": {}},
        )

        result = protocol.validate_transfer(event)
        assert result.is_valid is True
        assert result.errors == []

    def test_validate_transfer_missing_fields(self):
        """Test validating transfer with missing fields."""
        protocol = KnowledgeTransferProtocol()
        event = protocol.create_transfer_event(
            source_system="",
            target_system="strong",
            knowledge_type="",
            knowledge_item_id="",
            payload={},
        )

        result = protocol.validate_transfer(event)
        assert result.is_valid is False
        assert len(result.errors) > 0

    def test_validate_autocog_action(self):
        """Test validating AUTOCOG action."""
        protocol = KnowledgeTransferProtocol()
        event = protocol.create_transfer_event(
            source_system="autocog",
            target_system="strong",
            knowledge_type="action",
            knowledge_item_id="action_001",
            payload={"action_id": "001", "action_type": "execute", "parameters": {}},
        )

        result = protocol.validate_transfer(event)
        assert result.is_valid is True

    def test_validate_autocog_action_missing_field(self):
        """Test validating AUTOCOG action with missing field."""
        protocol = KnowledgeTransferProtocol()
        event = protocol.create_transfer_event(
            source_system="autocog",
            target_system="strong",
            knowledge_type="action",
            knowledge_item_id="action_001",
            payload={"action_id": "001"},  # Missing action_type and parameters
        )

        result = protocol.validate_transfer(event)
        assert result.is_valid is False
        assert any("action_type" in error for error in result.errors)

    def test_validate_autocog_assessment(self):
        """Test validating AUTOCOG assessment."""
        protocol = KnowledgeTransferProtocol()
        event = protocol.create_transfer_event(
            source_system="autocog",
            target_system="strong",
            knowledge_type="assessment",
            knowledge_item_id="assessment_001",
            payload={
                "artifact_id": "001",
                "confidence_score": 0.85,
                "recommendations": ["rec1", "rec2"],
            },
        )

        result = protocol.validate_transfer(event)
        assert result.is_valid is True

    def test_validate_autocog_validation_result(self):
        """Test validating AUTOCOG validation result."""
        protocol = KnowledgeTransferProtocol()
        event = protocol.create_transfer_event(
            source_system="autocog",
            target_system="strong",
            knowledge_type="validation_result",
            knowledge_item_id="validation_001",
            payload={
                "validation_id": "001",
                "is_valid": True,
                "findings": {"test": "passed"},
            },
        )

        result = protocol.validate_transfer(event)
        assert result.is_valid is True

    def test_validate_strong_belief_embedding(self):
        """Test validating STRONG belief embedding."""
        protocol = KnowledgeTransferProtocol()
        event = protocol.create_transfer_event(
            source_system="strong",
            target_system="autocog",
            knowledge_type="belief_embedding",
            knowledge_item_id="embedding_001",
            payload={
                "embedding_id": "001",
                "vector": [0.1, 0.2, 0.3],
                "metadata": {"test": "data"},
            },
        )

        result = protocol.validate_transfer(event)
        assert result.is_valid is True

    def test_validate_strong_learning_update(self):
        """Test validating STRONG learning update."""
        protocol = KnowledgeTransferProtocol()
        event = protocol.create_transfer_event(
            source_system="strong",
            target_system="autocog",
            knowledge_type="learning_update",
            knowledge_item_id="update_001",
            payload={
                "update_id": "001",
                "gradient_info": {"loss": 0.1},
                "loss_value": 0.1,
            },
        )

        result = protocol.validate_transfer(event)
        assert result.is_valid is True

    def test_validate_strong_symbolic_rule(self):
        """Test validating STRONG symbolic rule."""
        protocol = KnowledgeTransferProtocol()
        event = protocol.create_transfer_event(
            source_system="strong",
            target_system="autocog",
            knowledge_type="symbolic_rule",
            knowledge_item_id="rule_001",
            payload={
                "rule_id": "001",
                "rule_expression": "x > 0",
                "confidence": 0.9,
            },
        )

        result = protocol.validate_transfer(event)
        assert result.is_valid is True

    def test_can_retry(self):
        """Test retry logic."""
        protocol = KnowledgeTransferProtocol(max_retries=3)
        event = protocol.create_transfer_event(
            source_system="autocog",
            target_system="strong",
            knowledge_type="action",
            knowledge_item_id="test_001",
            payload={"test": "data"},
        )

        assert protocol.can_retry(event) is True

        # Simulate retries
        for i in range(3):
            protocol.record_retry(event)

        assert protocol.can_retry(event) is False

    def test_get_transfer_history(self):
        """Test getting transfer from history."""
        protocol = KnowledgeTransferProtocol()
        event = protocol.create_transfer_event(
            source_system="autocog",
            target_system="strong",
            knowledge_type="action",
            knowledge_item_id="test_001",
            payload={"test": "data"},
        )

        retrieved = protocol.get_transfer_history(event.transfer_id)
        assert retrieved is not None
        assert retrieved.transfer_id == event.transfer_id

    def test_get_transfers_by_system(self):
        """Test getting transfers by system."""
        protocol = KnowledgeTransferProtocol()

        # Create multiple transfers
        protocol.create_transfer_event(
            source_system="autocog",
            target_system="strong",
            knowledge_type="action",
            knowledge_item_id="test_001",
            payload={},
        )
        protocol.create_transfer_event(
            source_system="strong",
            target_system="autocog",
            knowledge_type="belief_embedding",
            knowledge_item_id="test_002",
            payload={},
        )

        autocog_transfers = protocol.get_transfers_by_system("autocog")
        assert len(autocog_transfers) == 2

        strong_transfers = protocol.get_transfers_by_system("strong")
        assert len(strong_transfers) == 2

    def test_get_transfers_by_status(self):
        """Test getting transfers by status."""
        protocol = KnowledgeTransferProtocol()

        event1 = protocol.create_transfer_event(
            source_system="autocog",
            target_system="strong",
            knowledge_type="action",
            knowledge_item_id="test_001",
            payload={},
        )
        event1.mark_completed()

        event2 = protocol.create_transfer_event(
            source_system="autocog",
            target_system="strong",
            knowledge_type="action",
            knowledge_item_id="test_002",
            payload={},
        )
        event2.mark_failed("Test error")

        completed = protocol.get_transfers_by_status(TransferStatus.COMPLETED)
        assert len(completed) == 1

        failed = protocol.get_transfers_by_status(TransferStatus.FAILED)
        assert len(failed) == 1
