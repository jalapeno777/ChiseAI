#!/usr/bin/env python3
"""Unit tests for order and fill storage without Redis dependency.

For PAPER-VALIDATION-001: Implement dedicated order and fill key storage
"""

import os
import sys
import uuid
from unittest.mock import MagicMock

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from orders.fill_storage import FillStorage
from orders.manager import OrderFillManager
from orders.storage import OrderStorage


def test_order_storage():
    """Test OrderStorage with mock Redis."""
    print("Testing OrderStorage...")

    mock_redis = MagicMock()
    mock_redis.get.return_value = None
    mock_redis.set.return_value = True
    mock_redis.zadd.return_value = 1
    mock_redis.expire.return_value = True

    storage = OrderStorage(redis_client=mock_redis)

    # Test store_order
    order_id = f"order-{uuid.uuid4().hex[:8]}"
    result = storage.store_order(
        order_id=order_id,
        symbol="BTCUSDT",
        side="buy",
        order_type="market",
        quantity=0.5,
        price=65000.0,
        signal_id="signal-123",
        correlation_id="corr-456",
        metadata={"strategy": "momentum"},
    )

    assert result is not None, "store_order should return key"
    assert result.startswith("order:"), f"Key should start with 'order:', got {result}"
    print(f"  ✓ store_order returns key: {result}")

    # Verify Redis calls
    mock_redis.set.assert_called()
    mock_redis.zadd.assert_called()
    print("  ✓ Redis set() and zadd() called")

    return True


def test_fill_storage():
    """Test FillStorage with mock Redis."""
    print("\nTesting FillStorage...")

    mock_redis = MagicMock()
    mock_redis.get.return_value = None
    mock_redis.set.return_value = True
    mock_redis.zadd.return_value = 1
    mock_redis.expire.return_value = True

    storage = FillStorage(redis_client=mock_redis)

    # Test store_fill
    order_id = f"order-{uuid.uuid4().hex[:8]}"
    result = storage.store_fill(
        order_id=order_id,
        symbol="BTCUSDT",
        side="buy",
        quantity=0.5,
        price=65000.0,
        signal_id="signal-123",
        correlation_id="corr-456",
        metadata={"fill_type": "complete"},
    )

    assert result is not None, "store_fill should return key"
    assert result.startswith("fill:"), f"Key should start with 'fill:', got {result}"
    print(f"  ✓ store_fill returns key: {result}")

    # Verify Redis calls
    mock_redis.set.assert_called()
    mock_redis.zadd.assert_called()
    print("  ✓ Redis set() and zadd() called")

    return True


def test_order_fill_manager():
    """Test OrderFillManager with mock Redis."""
    print("\nTesting OrderFillManager...")

    mock_redis = MagicMock()
    mock_redis.get.return_value = None
    mock_redis.set.return_value = True
    mock_redis.zadd.return_value = 1
    mock_redis.expire.return_value = True
    mock_redis.zrevrange.return_value = []
    mock_redis.zcard.return_value = 0

    manager = OrderFillManager(redis_client=mock_redis)

    # Test create_order
    order_id = f"order-{uuid.uuid4().hex[:8]}"
    signal_id = f"signal-{uuid.uuid4().hex[:8]}"
    correlation_id = str(uuid.uuid4())

    result = manager.create_order(
        order_id=order_id,
        symbol="BTCUSDT",
        side="buy",
        order_type="market",
        quantity=0.5,
        price=65000.0,
        signal_id=signal_id,
        correlation_id=correlation_id,
        metadata={"strategy": "momentum"},
    )

    assert result["success"] is True, "create_order should succeed"
    assert result["order_id"] == order_id
    assert result["order_key"].startswith("order:")
    print(f"  ✓ create_order succeeds with key: {result['order_key']}")

    # Test record_fill
    fill_result = manager.record_fill(
        order_id=order_id,
        symbol="BTCUSDT",
        side="buy",
        quantity=0.5,
        price=65000.0,
        signal_id=signal_id,
        correlation_id=correlation_id,
    )

    assert fill_result["success"] is True, "record_fill should succeed"
    assert fill_result["fill_key"].startswith("fill:")
    print(f"  ✓ record_fill succeeds with key: {fill_result['fill_key']}")

    return True


def test_key_patterns():
    """Verify key patterns are correct."""
    print("\nTesting key patterns...")

    # OrderStorage patterns
    assert OrderStorage.ORDER_KEY_PATTERN == "order:{order_id}"
    assert OrderStorage.SYMBOL_INDEX_KEY == "order:index:by_symbol"
    assert OrderStorage.SIGNAL_INDEX_KEY == "order:index:by_signal"
    assert OrderStorage.TIME_INDEX_KEY == "order:index:by_time"
    print("  ✓ OrderStorage key patterns correct")

    # FillStorage patterns
    assert FillStorage.FILL_KEY_PATTERN == "fill:{fill_id}"
    assert FillStorage.ORDER_INDEX_KEY == "fill:index:by_order"
    assert FillStorage.SYMBOL_INDEX_KEY == "fill:index:by_symbol"
    assert FillStorage.TIME_INDEX_KEY == "fill:index:by_time"
    print("  ✓ FillStorage key patterns correct")

    return True


def test_data_structures():
    """Test that data structures are correct."""
    print("\nTesting data structures...")

    mock_redis = MagicMock()
    mock_redis.get.return_value = None
    mock_redis.set.return_value = True
    mock_redis.zadd.return_value = 1
    mock_redis.expire.return_value = True

    # Test order data structure
    storage = OrderStorage(redis_client=mock_redis)
    order_id = "test-order-123"

    storage.store_order(
        order_id=order_id,
        symbol="BTCUSDT",
        side="buy",
        order_type="market",
        quantity=0.5,
        price=65000.0,
        signal_id="signal-123",
        correlation_id="corr-456",
    )

    # Get the data that was passed to redis.set()
    call_args = mock_redis.set.call_args
    call_args[0][0]
    data_json = call_args[0][1]
    import json

    data = json.loads(data_json)

    # Verify order data structure
    assert "order_id" in data
    assert "symbol" in data
    assert "side" in data
    assert "order_type" in data
    assert "quantity" in data
    assert "price" in data
    assert "state" in data
    assert "signal_id" in data
    assert "correlation_id" in data
    assert "created_at" in data
    print("  ✓ Order data structure correct")

    # Test fill data structure
    fill_storage = FillStorage(redis_client=mock_redis)
    fill_storage.store_fill(
        order_id=order_id,
        symbol="BTCUSDT",
        side="buy",
        quantity=0.5,
        price=65000.0,
        signal_id="signal-123",
        correlation_id="corr-456",
    )

    call_args = mock_redis.set.call_args
    data_json = call_args[0][1]
    data = json.loads(data_json)

    # Verify fill data structure
    assert "fill_id" in data
    assert "order_id" in data
    assert "symbol" in data
    assert "side" in data
    assert "quantity" in data
    assert "price" in data
    assert "notional_value" in data
    assert "signal_id" in data
    assert "correlation_id" in data
    assert "timestamp" in data
    print("  ✓ Fill data structure correct")

    return True


def main():
    """Run all tests."""
    print("=" * 70)
    print("PAPER-VALIDATION-001: Order and Fill Storage Unit Tests")
    print("=" * 70)

    tests = [
        ("Key Patterns", test_key_patterns),
        ("Data Structures", test_data_structures),
        ("OrderStorage", test_order_storage),
        ("FillStorage", test_fill_storage),
        ("OrderFillManager", test_order_fill_manager),
    ]

    passed = 0
    failed = 0

    for name, test_func in tests:
        try:
            if test_func():
                passed += 1
            else:
                failed += 1
                print(f"  ✗ {name} failed")
        except Exception as e:
            failed += 1
            print(f"  ✗ {name} failed with error: {e}")

    print("\n" + "=" * 70)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 70)

    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
