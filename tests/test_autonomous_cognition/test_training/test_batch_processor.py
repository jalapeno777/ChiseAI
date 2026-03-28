"""Tests for batch_processor module."""

import pytest
from src.autonomous_cognition.training.batch_processor import (
    Batch,
    BatchProcessor,
    create_batch_processor,
    default_collate,
    dict_collate,
)


class TestBatch:
    """Tests for Batch dataclass."""

    def test_batch_creation(self):
        """Test basic batch creation."""
        batch = Batch(
            data=[1, 2, 3],
            indices=[0, 1, 2],
            start_idx=0,
        )
        assert batch.size == 3
        assert batch.is_empty is False
        assert batch.is_last is False

    def test_batch_empty(self):
        """Test empty batch."""
        batch = Batch(data=[], indices=[], start_idx=0)
        assert batch.size == 0
        assert batch.is_empty is True


class TestDefaultCollate:
    """Tests for default_collate function."""

    def test_default_collate_returns_list(self):
        """Test that default collate returns list as-is."""
        data = [1, 2, 3]
        result = default_collate(data)
        assert result == data


class TestDictCollate:
    """Tests for dict_collate function."""

    def test_dict_collate(self):
        """Test dictionary collation."""
        data = [
            {"a": 1, "b": 2},
            {"a": 3, "b": 4},
        ]
        result = dict_collate(data)
        assert result == {"a": [1, 3], "b": [2, 4]}

    def test_dict_collate_empty(self):
        """Test dict collate with empty list."""
        result = dict_collate([])
        assert result == {}


class TestBatchProcessor:
    """Tests for BatchProcessor class."""

    def test_creation(self):
        """Test batch processor creation."""
        processor = BatchProcessor(batch_size=32, shuffle=True)
        assert processor.batch_size == 32
        assert processor.shuffle is True

    def test_invalid_batch_size(self):
        """Test that invalid batch size raises error."""
        with pytest.raises(ValueError, match="batch_size must be positive"):
            BatchProcessor(batch_size=0)

        with pytest.raises(ValueError, match="batch_size must be positive"):
            BatchProcessor(batch_size=-1)

    def test_process_no_shuffle(self):
        """Test processing without shuffle."""
        processor = BatchProcessor(batch_size=3, shuffle=False)
        data = list(range(10))
        batches = processor.process(data)

        assert len(batches) == 4  # 10/3 = 3 full + 1 partial
        assert batches[0].data == [0, 1, 2]
        assert batches[0].indices == [0, 1, 2]

    def test_process_with_shuffle(self):
        """Test processing with shuffle."""
        processor = BatchProcessor(batch_size=3, shuffle=True, seed=42)
        data = list(range(10))
        batches = processor.process(data)

        assert len(batches) == 4
        # With seed 42, shuffle should produce deterministic results
        assert batches[0].start_idx == 0

    def test_process_drop_last(self):
        """Test processing with drop_last."""
        processor = BatchProcessor(batch_size=3, shuffle=False, drop_last=True)
        data = list(range(10))
        batches = processor.process(data)

        # 10/3 = 3 full batches, 1 partial dropped
        assert len(batches) == 3

    def test_process_empty_data(self):
        """Test processing empty data."""
        processor = BatchProcessor(batch_size=32)
        batches = processor.process([])
        assert len(batches) == 0

    def test_process_single_batch(self):
        """Test processing data smaller than batch size."""
        processor = BatchProcessor(batch_size=32, shuffle=False)
        data = list(range(5))
        batches = processor.process(data)

        assert len(batches) == 1
        assert batches[0].data == [0, 1, 2, 3, 4]
        assert batches[0].is_last is True

    def test_batch_metadata(self):
        """Test batch metadata is set correctly."""
        processor = BatchProcessor(batch_size=3, shuffle=False)
        data = list(range(10))
        batches = processor.process(data)

        assert batches[0].metadata["batch_num"] == 0
        assert batches[0].metadata["total_batches"] == 4
        assert batches[-1].is_last is True

    def test_process_with_dict_collate(self):
        """Test processing with dict collate function."""
        processor = BatchProcessor(
            batch_size=2,
            shuffle=False,
            collate_fn=dict_collate,
        )
        data = [
            {"a": 1, "b": 2},
            {"a": 3, "b": 4},
            {"a": 5, "b": 6},
        ]
        batches = processor.process(data)

        assert len(batches) == 2
        assert isinstance(batches[0].data, dict)
        assert batches[0].data["a"] == [1, 3]

    def test_get_num_batches(self):
        """Test num batches calculation."""
        processor = BatchProcessor(batch_size=3, drop_last=False)

        assert processor.get_num_batches(10) == 4
        assert processor.get_num_batches(9) == 3
        assert processor.get_num_batches(0) == 0

    def test_get_num_batches_drop_last(self):
        """Test num batches with drop_last."""
        processor = BatchProcessor(batch_size=3, drop_last=True)

        assert processor.get_num_batches(10) == 3
        assert processor.get_num_batches(9) == 3

    def test_reset_seed(self):
        """Test seed reset."""
        processor = BatchProcessor(batch_size=2, shuffle=True, seed=42)
        data = list(range(10))

        batches1 = processor.process(data)
        processor.reset_seed()
        batches2 = processor.process(data)

        # Same seed should produce same shuffle
        assert batches1[0].indices == batches2[0].indices


class TestCreateBatchProcessor:
    """Tests for create_batch_processor factory."""

    def test_create_with_default_collate(self):
        """Test factory with default collate."""
        processor = create_batch_processor(
            batch_size=16,
            collate_fn_name="default",
        )
        assert processor.batch_size == 16
        assert processor.collate_fn is default_collate

    def test_create_with_dict_collate(self):
        """Test factory with dict collate."""
        processor = create_batch_processor(
            batch_size=16,
            collate_fn_name="dict",
        )
        assert processor.batch_size == 16
        assert processor.collate_fn is dict_collate

    def test_create_with_gradient_accumulation(self):
        """Test factory with gradient accumulation."""
        processor = create_batch_processor(
            batch_size=8,
            gradient_accumulation_steps=4,
        )
        assert processor.gradient_accumulation_steps == 4
