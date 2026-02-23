---
name: chiseai-testing-patterns
description: Testing patterns and best practices for ChiseAI Python code with pytest, coverage, and quality gates.
metadata:
  version: "1.0"
  opencode_min_version: "1.1.60"
  author: "ChiseAI Team"
  last_updated: "2026-02-23"
---

# chiseai-testing-patterns

## Goal

Ensure code quality through proper testing with consistent patterns, comprehensive coverage, and CI integration that catches regressions before merge.

## When To Use

- **Writing new code** - Add tests alongside implementation
- **Refactoring existing code** - Ensure behavior is preserved with tests
- **Before PR submission** - Verify all tests pass and coverage meets threshold
- **Debugging test failures** - Follow systematic diagnosis patterns
- **Improving test coverage** - Identify and fill coverage gaps
- **Adding new modules** - Establish test structure from the start

## When Not To Use

- **Documentation-only changes** - No code logic to test
- **Configuration file updates** - No executable code (unless validation logic exists)
- **Emergency hotfixes** - Apply fix first, add tests after (document the gap)
- **Third-party library code** - Not our responsibility to test

## Testing Requirements

### Coverage Standards

| Metric | Threshold | Enforcement |
|--------|-----------|-------------|
| Line Coverage | ≥ 80% | CI Gate (blocks merge) |
| Branch Coverage | ≥ 70% | Warning (not blocking) |
| New Code Coverage | 100% | Pre-commit check |

### Test File Naming Conventions

```
tests/
├── test_<module>/
│   ├── __init__.py
│   ├── test_<component>.py      # Unit tests
│   ├── test_integration.py      # Integration tests
│   └── conftest.py              # Shared fixtures
```

**Rules:**
- Test files MUST start with `test_`
- Test classes MUST start with `Test`
- Test functions MUST start with `test_`
- Fixture files MUST be named `conftest.py`

### Test Organization (Mirror src/ Structure)

```
src/
├── governance/
│   ├── sentinel/
│   │   ├── api.py
│   │   └── checker.py
│   └── validator.py

tests/
├── test_governance/
│   ├── test_sentinel/
│   │   ├── test_api.py          # Tests for api.py
│   │   ├── test_checker.py      # Tests for checker.py
│   │   └── conftest.py          # Sentinel-specific fixtures
│   └── test_validator.py        # Tests for validator.py
```

### Required Test Types

| Type | Purpose | Location Pattern |
|------|---------|------------------|
| Unit | Test isolated functions/classes | `tests/test_<module>/test_<component>.py` |
| Integration | Test component interactions | `tests/test_<module>/test_integration.py` |
| API | Test HTTP endpoints | `tests/test_<module>/test_api.py` |
| Benchmark | Performance testing (optional) | `tests/test_<module>/benchmark_*.py` |

## Test Patterns

### Pattern 1: Unit Test with Fixtures

```python
"""Tests for utility functions."""

import pytest
from src.utils.calculators import calculate_risk_score


class TestRiskScoreCalculator:
    """Tests for risk score calculation."""

    @pytest.fixture
    def sample_position(self):
        """Create a sample position for testing."""
        return {
            "size": 100.0,
            "entry_price": 50000.0,
            "stop_loss": 48000.0,
            "leverage": 2.0,
        }

    def test_calculate_risk_score_normal(self, sample_position):
        """Test risk score calculation with normal inputs."""
        result = calculate_risk_score(sample_position)
        assert 0 <= result <= 1

    def test_calculate_risk_score_zero_size(self, sample_position):
        """Test risk score with zero position size."""
        sample_position["size"] = 0.0
        result = calculate_risk_score(sample_position)
        assert result == 0.0

    @pytest.mark.parametrize("leverage,expected_range", [
        (1.0, (0.0, 0.3)),
        (5.0, (0.3, 0.6)),
        (10.0, (0.6, 1.0)),
    ])
    def test_risk_increases_with_leverage(
        self, sample_position, leverage, expected_range
    ):
        """Test that risk score increases with leverage."""
        sample_position["leverage"] = leverage
        result = calculate_risk_score(sample_position)
        assert expected_range[0] <= result <= expected_range[1]
```

### Pattern 2: Mocking External Services

```python
"""Tests with mocked external services."""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from src.data.exchange_client import ExchangeClient


class TestExchangeClientWithMocks:
    """Tests using mocks for external services."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        mock = MagicMock()
        mock.ping.return_value = True
        mock.get.return_value = None
        mock.set.return_value = True
        return mock

    @pytest.fixture
    def mock_exchange_api(self):
        """Create a mock exchange API response."""
        return {
            "symbol": "BTC/USDT",
            "price": 50000.0,
            "volume": 1000000.0,
        }

    def test_fetch_price_uses_cache(self, mock_redis):
        """Test that price fetch uses Redis cache when available."""
        mock_redis.get.return_value = "50000.0"
        
        client = ExchangeClient(redis_client=mock_redis)
        price = client.get_cached_price("BTC/USDT")
        
        mock_redis.get.assert_called_once_with("price:BTC/USDT")
        assert price == 50000.0

    @patch("src.data.exchange_client.requests.get")
    def test_fetch_price_from_api(self, mock_get, mock_redis, mock_exchange_api):
        """Test price fetch from API when cache miss."""
        mock_redis.get.return_value = None  # Cache miss
        mock_get.return_value.json.return_value = mock_exchange_api
        
        client = ExchangeClient(redis_client=mock_redis)
        price = client.get_price("BTC/USDT")
        
        assert price == 50000.0
        mock_redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_fetch_orderbook(self, mock_redis):
        """Test async orderbook fetching."""
        client = ExchangeClient(redis_client=mock_redis)
        
        with patch.object(
            client, "_async_fetch", new_callable=AsyncMock
        ) as mock_fetch:
            mock_fetch.return_value = {"bids": [], "asks": []}
            result = await client.fetch_orderbook_async("BTC/USDT")
            
            assert result == {"bids": [], "asks": []}
            mock_fetch.assert_called_once_with("BTC/USDT")
```

### Pattern 3: Testing Async Code

```python
"""Tests for async functions."""

import pytest
from src.signal_generation.async_processor import AsyncSignalProcessor


class TestAsyncSignalProcessor:
    """Tests for async signal processing."""

    @pytest.fixture
    async def processor(self):
        """Create an async processor instance."""
        proc = AsyncSignalProcessor()
        await proc.initialize()
        yield proc
        await proc.cleanup()

    @pytest.mark.asyncio
    async def test_process_signal_success(self, processor):
        """Test successful signal processing."""
        signal = {
            "symbol": "BTC/USDT",
            "action": "buy",
            "confidence": 0.85,
        }
        
        result = await processor.process(signal)
        
        assert result["status"] == "processed"
        assert result["signal_id"] is not None

    @pytest.mark.asyncio
    async def test_process_signal_low_confidence_rejected(self, processor):
        """Test that low confidence signals are rejected."""
        signal = {
            "symbol": "BTC/USDT",
            "action": "buy",
            "confidence": 0.45,  # Below threshold
        }
        
        result = await processor.process(signal)
        
        assert result["status"] == "rejected"
        assert "confidence" in result["reason"].lower()

    @pytest.mark.asyncio
    async def test_concurrent_processing(self, processor):
        """Test concurrent signal processing."""
        import asyncio
        
        signals = [
            {"symbol": f"COIN{i}/USDT", "action": "buy", "confidence": 0.8}
            for i in range(10)
        ]
        
        results = await asyncio.gather(*[
            processor.process(s) for s in signals
        ])
        
        assert len(results) == 10
        assert all(r["status"] in ("processed", "rejected") for r in results)
```

### Pattern 4: Parameterized Tests

```python
"""Parameterized test patterns."""

import pytest
from src.confidence.calculator import calculate_confidence


class TestConfidenceCalculatorParameterized:
    """Tests using parametrization for comprehensive coverage."""

    @pytest.mark.parametrize("signal_strength,historical_accuracy,expected", [
        # (signal_strength, historical_accuracy, expected_confidence)
        (0.9, 0.85, 0.765),   # High signal, good history
        (0.5, 0.5, 0.25),     # Medium signal, average history
        (0.3, 0.9, 0.27),     # Low signal, excellent history
        (0.0, 0.5, 0.0),      # Zero signal
        (1.0, 1.0, 1.0),      # Perfect inputs
    ])
    def test_confidence_calculation(
        self, signal_strength, historical_accuracy, expected
    ):
        """Test confidence calculation across input ranges."""
        result = calculate_confidence(signal_strength, historical_accuracy)
        assert abs(result - expected) < 0.01

    @pytest.mark.parametrize("invalid_input", [
        -0.1,   # Negative
        1.1,    # > 1
        float('nan'),
        float('inf'),
        None,
        "string",
    ])
    def test_confidence_invalid_inputs(self, invalid_input):
        """Test that invalid inputs raise appropriate errors."""
        with pytest.raises((ValueError, TypeError)):
            calculate_confidence(invalid_input, 0.5)
```

### Pattern 5: Test Isolation and Cleanup

```python
"""Tests demonstrating proper isolation and cleanup."""

import pytest
import tempfile
import os
from pathlib import Path


class TestWithFilesystemIsolation:
    """Tests with proper filesystem isolation."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test files."""
        dir_path = tempfile.mkdtemp()
        yield Path(dir_path)
        # Cleanup: Remove all files and directory
        for file in Path(dir_path).glob("*"):
            file.unlink()
        os.rmdir(dir_path)

    @pytest.fixture
    def config_file(self, temp_dir):
        """Create a test config file."""
        config_path = temp_dir / "test_config.yaml"
        config_path.write_text("key: value\n")
        yield config_path
        # Cleanup happens in temp_dir fixture

    def test_config_loading(self, config_file):
        """Test config file loading."""
        from src.config.loader import load_config
        
        config = load_config(config_file)
        assert config["key"] == "value"


class TestWithRedisIsolation:
    """Tests with Redis state isolation."""

    @pytest.fixture
    def redis_key_prefix(self):
        """Generate unique key prefix for test isolation."""
        import uuid
        return f"test:{uuid.uuid4()}:"

    @pytest.fixture
    def isolated_redis(self, mock_redis, redis_key_prefix):
        """Create Redis mock with isolated key namespace."""
        storage = {}
        
        def get_with_prefix(key):
            return storage.get(f"{redis_key_prefix}{key}")
        
        def set_with_prefix(key, value):
            storage[f"{redis_key_prefix}{key}"] = value
            return True
        
        mock_redis.get.side_effect = get_with_prefix
        mock_redis.set.side_effect = set_with_prefix
        
        yield mock_redis
        # storage is garbage collected after test
```

## CI Integration

### Pre-Commit Hooks

Tests run automatically via `.git/hooks/pre-commit`:

```bash
# .pre-commit-config.yaml (if present)
repos:
  - repo: local
    hooks:
      - id: pytest-quick
        name: Quick pytest
        entry: pytest tests/ -q -x --tb=short
        language: system
        pass_filenames: false
```

### Woodpecker CI Pipeline

Tests in CI follow this flow:

```yaml
# .woodpecker.yml
pipeline:
  test-unit:
    image: python:3.11
    commands:
      - pip install -e .[dev]
      - pytest tests/ -v --cov=src --cov-report=xml --cov-fail-under=80
    when:
      event: [push, pull_request]

  test-integration:
    image: python:3.11
    commands:
      - pip install -e .[dev]
      - pytest tests/ -v -m integration
    when:
      event: [push, pull_request]
```

### Coverage Reporting

Coverage is tracked and reported:

```bash
# Generate coverage report
pytest tests/ --cov=src --cov-report=html --cov-report=term

# Coverage output locations:
# - htmlcov/          (HTML report)
# - coverage.xml      (XML for CI)
# - .coverage         (Data file)
```

### Test Failure Handling

When tests fail in CI:

1. **Identify** - Use `chise-ci-root-cause` command
2. **Reproduce** - Run failing test locally with same flags
3. **Fix** - Make minimal fix to address root cause
4. **Verify** - Run full test suite locally before push
5. **Document** - Add regression test if applicable

## Templates

### Unit Test Template

```python
"""Tests for <module_name>.

<One-line description of what's being tested>.
"""

import pytest
from unittest.mock import MagicMock, patch
from src.<module_path> import <ClassName>


class Test<ClassName>:
    """Tests for <ClassName>."""

    @pytest.fixture
    def sample_data(self):
        """Create sample data for testing."""
        return {"key": "value"}

    @pytest.fixture
    def instance(self, sample_data):
        """Create instance under test."""
        return <ClassName>(sample_data)

    def test_<method_name>_normal_case(self, instance):
        """Test <method> with normal inputs."""
        result = instance.<method>()
        assert result == <expected>

    def test_<method_name>_edge_case(self, instance):
        """Test <method> with edge case."""
        # Setup edge case
        result = instance.<method>()
        assert result == <expected>

    def test_<method_name>_raises_on_invalid(self, instance):
        """Test that <method> raises error on invalid input."""
        with pytest.raises(<ExpectedError>):
            instance.<method>(invalid_input)
```

### Integration Test Template

```python
"""Integration tests for <feature>.

Tests the interaction between <component_a> and <component_b>.
"""

import pytest
from src.<module_a> import <ComponentA>
from src.<module_b> import <ComponentB>


class Test<Feature>Integration:
    """Integration tests for <feature>."""

    @pytest.fixture
    def component_a(self):
        """Create component A."""
        return <ComponentA>()

    @pytest.fixture
    def component_b(self, component_a):
        """Create component B with dependency on A."""
        return <ComponentB>(component_a)

    @pytest.fixture
    def integrated_system(self, component_a, component_b):
        """Create fully integrated system."""
        return {
            "a": component_a,
            "b": component_b,
        }

    @pytest.mark.integration
    def test_end_to_end_flow(self, integrated_system):
        """Test complete flow through integrated system."""
        # Setup
        input_data = {"test": "data"}
        
        # Execute
        result_a = integrated_system["a"].process(input_data)
        result_b = integrated_system["b"].transform(result_a)
        
        # Verify
        assert result_b["status"] == "success"

    @pytest.mark.integration
    @pytest.mark.slow
    def test_performance_under_load(self, integrated_system):
        """Test system performance under load."""
        import time
        
        start = time.time()
        for _ in range(100):
            integrated_system["a"].process({"test": "data"})
        duration = time.time() - start
        
        assert duration < 5.0  # Should complete in under 5 seconds
```

### Test Fixture Template

```python
"""Shared fixtures for <module> tests.

This conftest.py provides fixtures used across all test files
in this test module.
"""

import pytest
from unittest.mock import MagicMock
from pathlib import Path


# Path fixtures
@pytest.fixture
def test_data_dir():
    """Path to test data directory."""
    return Path(__file__).parent / "test_data"


@pytest.fixture
def sample_config(test_data_dir):
    """Load sample configuration."""
    import yaml
    config_path = test_data_dir / "sample_config.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


# Mock fixtures
@pytest.fixture
def mock_redis():
    """Create a mock Redis client with common behaviors."""
    mock = MagicMock()
    mock.ping.return_value = True
    mock.get.return_value = None
    mock.set.return_value = True
    mock.delete.return_value = 1
    return mock


@pytest.fixture
def mock_postgres():
    """Create a mock PostgreSQL connection."""
    mock = MagicMock()
    mock.execute.return_value = MagicMock()
    mock.fetch.return_value = []
    mock.fetchrow.return_value = None
    return mock


# Async fixtures
@pytest.fixture
async def async_client():
    """Create an async test client."""
    from httpx import AsyncClient
    async with AsyncClient() as client:
        yield client


# Session-scoped fixtures (expensive setup)
@pytest.fixture(scope="session")
def test_database():
    """Create test database (session-scoped for efficiency)."""
    # Setup
    db = create_test_database()
    yield db
    # Teardown
    db.close()
```

### Mock Setup Template

```python
"""Mock setup utilities for testing."""

from unittest.mock import MagicMock, patch, AsyncMock
from contextlib import contextmanager


def create_mock_exchange(tickers=None):
    """Create a mock exchange client with predefined tickers."""
    tickers = tickers or {}
    
    mock = MagicMock()
    mock.fetch_ticker.side_effect = lambda symbol: tickers.get(symbol, {
        "symbol": symbol,
        "last": 0.0,
        "bid": 0.0,
        "ask": 0.0,
    })
    mock.fetch_order_book.return_value = {
        "bids": [[50000.0, 1.0]],
        "asks": [[50001.0, 1.0]],
    }
    return mock


def create_mock_redis_with_data(data_dict):
    """Create a mock Redis client with predefined data."""
    storage = dict(data_dict)
    
    mock = MagicMock()
    mock.get.side_effect = lambda k: storage.get(k)
    mock.set.side_effect = lambda k, v: storage.update({k: v}) or True
    mock.delete.side_effect = lambda k: storage.pop(k, None) and 1
    mock.exists.side_effect = lambda k: k in storage
    return mock


@contextmanager
def mock_environment(**env_vars):
    """Context manager to temporarily set environment variables."""
    import os
    original = {}
    
    for key, value in env_vars.items():
        original[key] = os.environ.get(key)
        os.environ[key] = str(value)
    
    try:
        yield
    finally:
        for key, value in original.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


class AsyncContextManagerMock:
    """Mock for async context managers."""
    
    def __init__(self, return_value):
        self.return_value = return_value
    
    async def __aenter__(self):
        return self.return_value
    
    async def __aexit__(self, *args):
        return False
```

### Coverage Report Template

```markdown
## Coverage Report for <module>

### Summary
- **Line Coverage**: XX%
- **Branch Coverage**: XX%
- **Missing Lines**: XX

### Coverage by File

| File | Lines | Covered | % |
|------|-------|---------|---|
| src/module/file1.py | 100 | 85 | 85% |
| src/module/file2.py | 50 | 40 | 80% |

### Uncovered Lines

```
src/module/file1.py:
  - Lines 45-52: Error handling path (rare)
  - Line 78: Debug logging (optional)

src/module/file2.py:
  - Lines 20-25: Deprecated function
```

### Recommended Actions

1. Add test for `file1.py:45-52` - Error scenario
2. Remove or test `file2.py:20-25` - Deprecated code
3. Add integration test for full coverage

### Coverage Command

```bash
pytest tests/test_module/ --cov=src/module --cov-report=term-missing
```
```

## Examples

### Example 1: Simple Unit Test for a Utility Function

**Situation**: Need to test a utility function that calculates position size.

**Code under test** (`src/trading/position_sizing.py`):
```python
def calculate_position_size(
    account_balance: float,
    risk_per_trade: float,
    entry_price: float,
    stop_loss_price: float,
) -> float:
    """Calculate position size based on risk parameters."""
    if entry_price <= 0 or stop_loss_price <= 0:
        raise ValueError("Prices must be positive")
    
    risk_amount = account_balance * risk_per_trade
    price_risk = abs(entry_price - stop_loss_price)
    
    if price_risk == 0:
        raise ValueError("Entry and stop loss cannot be equal")
    
    return risk_amount / price_risk
```

**Test file** (`tests/test_trading/test_position_sizing.py`):
```python
"""Tests for position sizing calculations."""

import pytest
from src.trading.position_sizing import calculate_position_size


class TestCalculatePositionSize:
    """Tests for calculate_position_size function."""

    def test_normal_calculation(self):
        """Test normal position size calculation."""
        result = calculate_position_size(
            account_balance=10000.0,
            risk_per_trade=0.02,  # 2%
            entry_price=50000.0,
            stop_loss_price=49000.0,
        )
        # Risk amount = 10000 * 0.02 = 200
        # Price risk = 50000 - 49000 = 1000
        # Position size = 200 / 1000 = 0.2
        assert result == pytest.approx(0.2)

    def test_long_position_with_stop_above(self):
        """Test that stop above entry still works (short position)."""
        result = calculate_position_size(
            account_balance=10000.0,
            risk_per_trade=0.01,
            entry_price=50000.0,
            stop_loss_price=51000.0,  # Stop above entry
        )
        assert result == pytest.approx(0.1)

    @pytest.mark.parametrize("risk,expected_range", [
        (0.01, (0.05, 0.15)),   # 1% risk
        (0.02, (0.15, 0.25)),   # 2% risk
        (0.05, (0.45, 0.55)),   # 5% risk
    ])
    def test_varying_risk_percentages(self, risk, expected_range):
        """Test position size scales with risk percentage."""
        result = calculate_position_size(
            account_balance=10000.0,
            risk_per_trade=risk,
            entry_price=50000.0,
            stop_loss_price=49500.0,
        )
        assert expected_range[0] <= result <= expected_range[1]

    def test_raises_on_zero_entry_price(self):
        """Test that zero entry price raises ValueError."""
        with pytest.raises(ValueError, match="positive"):
            calculate_position_size(
                account_balance=10000.0,
                risk_per_trade=0.02,
                entry_price=0.0,
                stop_loss_price=49000.0,
            )

    def test_raises_on_equal_prices(self):
        """Test that equal entry and stop loss raises ValueError."""
        with pytest.raises(ValueError, match="cannot be equal"):
            calculate_position_size(
                account_balance=10000.0,
                risk_per_trade=0.02,
                entry_price=50000.0,
                stop_loss_price=50000.0,
            )
```

### Example 2: Integration Test with External API Mocking

**Situation**: Testing an exchange client that fetches market data.

**Test file** (`tests/test_data_exchange/test_client.py`):
```python
"""Integration tests for exchange client."""

import pytest
from unittest.mock import patch, MagicMock
from src.data_exchange.client import ExchangeClient


class TestExchangeClientIntegration:
    """Integration tests with mocked API responses."""

    @pytest.fixture
    def mock_api_response(self):
        """Sample API response for BTC/USDT."""
        return {
            "symbol": "BTC/USDT",
            "last": 50000.0,
            "bid": 49999.0,
            "ask": 50001.0,
            "volume": 1000000.0,
            "timestamp": 1708700000000,
        }

    @pytest.fixture
    def client(self, mock_redis):
        """Create exchange client with mocked dependencies."""
        return ExchangeClient(
            exchange_id="bybit",
            redis_client=mock_redis,
        )

    @patch("src.data_exchange.client.requests.get")
    def test_fetch_and_cache_ticker(self, mock_get, client, mock_api_response, mock_redis):
        """Test ticker fetch and caching flow."""
        # Setup mock response
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = mock_api_response

        # Execute
        ticker = client.fetch_ticker("BTC/USDT")

        # Verify response
        assert ticker["symbol"] == "BTC/USDT"
        assert ticker["last"] == 50000.0

        # Verify caching
        mock_redis.set.assert_called()
        call_args = mock_redis.set.call_args
        assert "ticker:BTC/USDT" in call_args[0][0]

    def test_fetch_from_cache(self, client, mock_redis, mock_api_response):
        """Test that cached data is returned when available."""
        import json
        mock_redis.get.return_value = json.dumps(mock_api_response)

        ticker = client.fetch_ticker("BTC/USDT")

        assert ticker["last"] == 50000.0
        # Should not make API call
        mock_redis.get.assert_called_once_with("ticker:BTC/USDT")

    @patch("src.data_exchange.client.requests.get")
    def test_handles_api_error_gracefully(self, mock_get, client, mock_redis):
        """Test graceful handling of API errors."""
        mock_get.return_value.status_code = 500
        mock_get.return_value.raise_for_status.side_effect = Exception("API Error")
        mock_redis.get.return_value = None  # No cache

        with pytest.raises(Exception, match="API Error"):
            client.fetch_ticker("BTC/USDT")

    @pytest.mark.asyncio
    async def test_concurrent_fetches(self, client):
        """Test concurrent ticker fetches don't cause issues."""
        import asyncio
        
        with patch.object(client, "_fetch_single") as mock_fetch:
            mock_fetch.return_value = {"last": 50000.0}
            
            results = await asyncio.gather(*[
                client.fetch_ticker_async(f"COIN{i}/USDT")
                for i in range(10)
            ])
            
            assert len(results) == 10
            assert all(r["last"] == 50000.0 for r in results)
```

### Example 3: Fixing a Test Coverage Gap

**Situation**: Coverage report shows 65% coverage for `src/risk/manager.py`.

**Step 1: Identify uncovered lines**
```bash
$ pytest tests/test_risk/ --cov=src/risk --cov-report=term-missing

Name                      Stmts   Miss  Cover   Missing
-------------------------------------------------------
src/risk/manager.py         120    42    65%   45-52, 78-85, 110-115
```

**Step 2: Analyze missing coverage**
```python
# Lines 45-52: Emergency shutdown path (rarely triggered)
# Lines 78-85: Risk limit exceeded handling
# Lines 110-115: Invalid configuration validation
```

**Step 3: Add tests for uncovered paths**
```python
# tests/test_risk/test_manager_coverage.py
"""Tests to improve coverage for risk manager."""

import pytest
from src.risk.manager import RiskManager


class TestRiskManagerEmergencyShutdown:
    """Tests for emergency shutdown path (lines 45-52)."""

    @pytest.fixture
    def manager(self):
        return RiskManager()

    def test_emergency_shutdown_closes_positions(self, manager):
        """Test that emergency shutdown closes all positions."""
        # Setup active positions
        manager._positions = {
            "BTC/USDT": {"size": 1.0, "side": "long"},
            "ETH/USDT": {"size": 10.0, "side": "long"},
        }

        manager.emergency_shutdown("Manual trigger")

        assert len(manager._positions) == 0
        assert manager._shutdown_triggered is True

    def test_emergency_shutdown_prevents_new_orders(self, manager):
        """Test that shutdown prevents new orders."""
        manager.emergency_shutdown("Test")

        with pytest.raises(RuntimeError, match="shutdown"):
            manager.place_order("BTC/USDT", "buy", 1.0)


class TestRiskManagerLimitExceeded:
    """Tests for risk limit exceeded (lines 78-85)."""

    def test_blocks_order_exceeding_limit(self):
        """Test that orders exceeding limit are blocked."""
        manager = RiskManager(max_position_value=10000)
        
        with pytest.raises(ValueError, match="exceeds limit"):
            manager.validate_order("BTC/USDT", 1.0, 50000.0)


class TestRiskManagerConfigValidation:
    """Tests for configuration validation (lines 110-115)."""

    def test_rejects_negative_max_position(self):
        """Test that negative max position is rejected."""
        with pytest.raises(ValueError, match="must be positive"):
            RiskManager(max_position_value=-1000)

    def test_rejects_zero_risk_limit(self):
        """Test that zero risk limit is rejected."""
        with pytest.raises(ValueError, match="must be positive"):
            RiskManager(risk_limit=0.0)
```

**Step 4: Verify coverage improvement**
```bash
$ pytest tests/test_risk/ --cov=src/risk --cov-report=term-missing

Name                      Stmts   Miss  Cover   Missing
-------------------------------------------------------
src/risk/manager.py         120     5    96%   150-154
```

## Exit Conditions

Stop and escalate to Jarvis if:

- **Test infrastructure down** - pytest cannot run after 3 retries
- **Coverage tools broken** - coverage.py fails to collect data
- **CI environment issues** - Tests pass locally but always fail in CI
- **Flaky tests** - Same test passes/fails inconsistently 3+ times
- **Database/Redis unavailable** - Integration tests cannot connect to dependencies
- **Import errors in test modules** - Circular imports or missing dependencies

## Troubleshooting/Safety

### Common Issues

| Issue | Symptoms | Resolution |
|-------|----------|------------|
| **Flaky tests** | Pass/fail randomly | Check for race conditions, shared state, timing issues |
| **Slow tests** | >5s per test | Mock external calls, use fixtures efficiently |
| **Mock leakage** | Tests fail in isolation | Use `pytest-mock` or ensure cleanup in fixtures |
| **Coverage gaps** | <80% coverage | Run `--cov-report=term-missing` to identify |
| **Import errors** | Module not found | Check PYTHONPATH, use `conftest.py` for path setup |
| **Fixture conflicts** | Fixtures overwrite each other | Use unique names, scope appropriately |

### Flaky Test Debugging

```bash
# Run single test multiple times to detect flakiness
pytest tests/test_module/test_file.py::test_name --count=10

# Run with verbose output and randomness seed
pytest tests/ -v --randomly-seed=12345
```

### Mock Leak Prevention

```python
# BAD: Mock persists beyond test
@patch('module.function')
def test_something(mock_func):
    ...

# GOOD: Mock is scoped to test
def test_something(mocker):  # pytest-mock fixture
    mock_func = mocker.patch('module.function')
    ...
    # Auto-cleanup after test
```

### Coverage Gap Analysis

```bash
# Generate detailed coverage report
pytest tests/ --cov=src --cov-report=html

# View in browser
open htmlcov/index.html

# Find specific uncovered lines
pytest tests/ --cov=src --cov-report=term-missing | grep "SRC_FILE"
```

### Safety Checks

- [ ] Never commit with failing tests
- [ ] Never skip tests with `@pytest.mark.skip` without justification
- [ ] Never use `# pragma: no cover` without documenting reason
- [ ] Always clean up resources in fixtures (files, connections, etc.)
- [ ] Always use isolated test data (don't modify production data)

## Related Skills

- **python-quality** - General Python quality workflow (linting, formatting)
- **chiseai-validation** - Pre-commit and CI validation gates
- **chiseai-git-workflow** - Branch and PR workflow for test changes
- **chiseai-incident-response** - Handling test-related incidents in CI

## Related Commands

- **BMAD Testing Commands**:
  - `.opencode/command/bmad-tea-teach-me-testing.md` - Learning about testing
  - `.opencode/command/bmad-tea-testarch-atdd.md` - Acceptance test-driven development
  - `.opencode/command/bmad-tea-testarch-framework.md` - Test framework guidance
  - `.opencode/command/bmad-tea-testarch-automate.md` - Test automation
  - `.opencode/command/bmad-tea-testarch-ci.md` - CI testing integration

- **Validation Commands**:
  - `.opencode/command/chise-precommit-gates.md` - Pre-commit validation including tests
  - `.opencode/command/chise-ci-root-cause.md` - Diagnose CI test failures
  - `.opencode/command/chise-ci-failure-bundle.md` - Collect test failure evidence

---

## Quick Reference

### Essential pytest Flags

```bash
# Run all tests
pytest tests/

# Run with coverage
pytest tests/ --cov=src --cov-report=term-missing

# Run specific test file
pytest tests/test_module/test_file.py

# Run specific test
pytest tests/test_module/test_file.py::TestClass::test_method

# Run tests matching pattern
pytest tests/ -k "pattern"

# Run only unit tests (skip integration)
pytest tests/ -m "not integration"

# Verbose output
pytest tests/ -v

# Stop on first failure
pytest tests/ -x

# Run in parallel (requires pytest-xdist)
pytest tests/ -n auto
```

### Test Markers

```python
@pytest.mark.asyncio      # Async test
@pytest.mark.integration  # Integration test
@pytest.mark.slow         # Slow test (>1s)
@pytest.mark.skip         # Skip this test
@pytest.mark.parametrize  # Parameterized test
```
