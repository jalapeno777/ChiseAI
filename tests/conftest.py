from __future__ import annotations

import functools
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

# Add src and project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from data_ingestion.ohlcv_fetcher import OHLCVData  # noqa: E402

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_FIXTURES_DIR = Path(__file__).parent / "fixtures"
_SNAPSHOTS_DIR = _FIXTURES_DIR / "market_snapshots"
_EXPECTATIONS_DIR = _FIXTURES_DIR / "indicator_expectations"

# ---------------------------------------------------------------------------
# Fixture loading utilities with caching
# ---------------------------------------------------------------------------

_snapshot_cache: dict[str, list[OHLCVData]] = {}
_expectations_cache: dict[str, dict[str, Any]] = {}


def _json_round_trip(obj: Any) -> Any:
    """Round-trip through JSON to match the precision stored in fixture files.

    When we generate expectations we serialize to JSON, so comparing against the
    deserialized form requires the same round-trip on computed values.
    """
    return json.loads(json.dumps(obj))


@functools.lru_cache(maxsize=32)
def list_market_snapshots() -> list[str]:
    """Return sorted list of available snapshot keys (without .json extension).

    Example: ['btc_usdt_1m', 'btc_usdt_5m', 'eth_usdt_1h']
    """
    keys = sorted(p.stem for p in _SNAPSHOTS_DIR.glob("*.json"))
    return keys


@functools.lru_cache(maxsize=32)
def list_indicator_expectations() -> list[str]:
    """Return sorted list of available expectation keys (without _expectations.json).

    Example: ['btc_usdt_1m', 'btc_usdt_5m', 'eth_usdt_1h']
    """
    keys = sorted(
        p.stem.replace("_expectations", "")
        for p in _EXPECTATIONS_DIR.glob("*_expectations.json")
    )
    return keys


def load_snapshot(data_key: str) -> list[OHLCVData]:
    """Load a market snapshot by key and return a list of OHLCVData.

    Results are cached in-memory so repeated calls within a test session
    return the same list object.

    Args:
        data_key: Snapshot identifier, e.g. 'btc_usdt_1m'

    Returns:
        List of OHLCVData parsed from the JSON snapshot

    Raises:
        FileNotFoundError: If the snapshot file does not exist
    """
    if data_key in _snapshot_cache:
        return _snapshot_cache[data_key]

    path = _SNAPSHOTS_DIR / f"{data_key}.json"
    if not path.exists():
        available = list_market_snapshots()
        raise FileNotFoundError(
            f"Snapshot '{data_key}' not found at {path}. Available: {available}"
        )

    with open(path) as f:
        data = json.load(f)

    candles = data["candles"]
    ohlcv_list = [
        OHLCVData(
            timestamp=0,  # synthetic snapshots use sequential candles
            open_price=float(c[0]),
            high_price=float(c[1]),
            low_price=float(c[2]),
            close_price=float(c[3]),
            volume=float(c[4]),
        )
        for c in candles
    ]
    _snapshot_cache[data_key] = ohlcv_list
    return ohlcv_list


def load_expectations(data_key: str) -> dict[str, Any]:
    """Load validated indicator expectations by key.

    Results are cached in-memory so repeated calls within a test session
    return the same dict.

    Args:
        data_key: Expectation identifier, e.g. 'btc_usdt_1m'

    Returns:
        Dict with indicator expectations (rsi, macd, bollinger_bands, atr,
        volume_profile)

    Raises:
        FileNotFoundError: If the expectations file does not exist
    """
    if data_key in _expectations_cache:
        return _expectations_cache[data_key]

    path = _EXPECTATIONS_DIR / f"{data_key}_expectations.json"
    if not path.exists():
        available = list_indicator_expectations()
        raise FileNotFoundError(
            f"Expectations '{data_key}' not found at {path}. Available: {available}"
        )

    with open(path) as f:
        expectations = json.load(f)

    _expectations_cache[data_key] = expectations
    return expectations


def load_snapshot_pair(
    data_key: str,
) -> tuple[list[OHLCVData], dict[str, Any]]:
    """Load both snapshot data and expectations for a given key.

    Convenience function for tests that need both the OHLCV data and
    the expected indicator outputs.

    Args:
        data_key: Snapshot/expectation identifier, e.g. 'btc_usdt_1m'

    Returns:
        Tuple of (ohlcv_list, expectations_dict)
    """
    return load_snapshot(data_key), load_expectations(data_key)


def clear_fixture_caches() -> None:
    """Clear all in-memory fixture caches.

    Useful for tests that need to force reload or to free memory.
    """
    _snapshot_cache.clear()
    _expectations_cache.clear()
    load_snapshot.cache_clear()
    load_expectations.cache_clear()
    list_market_snapshots.cache_clear()
    list_indicator_expectations.cache_clear()


# ---------------------------------------------------------------------------
# Streamlit test skip logic
# ---------------------------------------------------------------------------


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Skip Streamlit dashboard tests unless explicitly enabled.

    Streamlit is deprecated for ChiseAI in the short term, and CI does not install it.
    Enable locally by setting CHISE_ENABLE_STREAMLIT_TESTS=1 and ensuring streamlit
    is installed.
    """

    enable = os.environ.get("CHISE_ENABLE_STREAMLIT_TESTS", "").strip() == "1"
    if enable:
        if importlib.util.find_spec("streamlit") is None:
            raise pytest.UsageError(
                "CHISE_ENABLE_STREAMLIT_TESTS=1 but streamlit is not installed."
            )
        return

    skip = pytest.mark.skip(
        reason=(
            "Streamlit tests disabled by default; set CHISE_ENABLE_STREAMLIT_TESTS=1 "
            "to run."
        )
    )

    for item in items:
        # Only skip tests that are known to require Streamlit.
        path = str(item.fspath)
        if path.endswith("test_risk_exposure_panel.py"):
            item.add_marker(skip)


# ---------------------------------------------------------------------------
# Parametrized pytest fixtures
# ---------------------------------------------------------------------------

_all_snapshot_keys = [
    "btc_usdt_1m",
    "btc_usdt_5m",
    "btc_usdt_1h",
    "eth_usdt_1m",
    "eth_usdt_5m",
    "eth_usdt_1h",
]


@pytest.fixture(params=_all_snapshot_keys)
def any_snapshot(request: pytest.FixtureRequest) -> list[OHLCVData]:
    """Parametrized fixture yielding OHLCV data for each available snapshot.

    Use when you want a test to run against all market snapshots.
    """
    return load_snapshot(request.param)


@pytest.fixture(params=_all_snapshot_keys)
def any_expectations(request: pytest.FixtureRequest) -> dict[str, Any]:
    """Parametrized fixture yielding indicator expectations for each snapshot.

    Use when you want a test to validate against all expectation sets.
    """
    return load_expectations(request.param)


@pytest.fixture(params=_all_snapshot_keys)
def any_snapshot_pair(
    request: pytest.FixtureRequest,
) -> tuple[list[OHLCVData], dict[str, Any]]:
    """Parametrized fixture yielding (ohlcv, expectations) for each snapshot.

    Use when you need both data and expected indicator outputs together.
    """
    return load_snapshot_pair(request.param)


@pytest.fixture(params=["btc_usdt_1m", "eth_usdt_1h"])
def btc_1m_snapshot(request: pytest.FixtureRequest) -> list[OHLCVData]:
    """BTC/USDT 1-minute snapshot for quick indicator tests."""
    return load_snapshot(request.param)


@pytest.fixture
def btc_1m_ohlcv() -> list[OHLCVData]:
    """BTC/USDT 1-minute OHLCV data."""
    return load_snapshot("btc_usdt_1m")


@pytest.fixture
def btc_5m_ohlcv() -> list[OHLCVData]:
    """BTC/USDT 5-minute OHLCV data."""
    return load_snapshot("btc_usdt_5m")


@pytest.fixture
def btc_1h_ohlcv() -> list[OHLCVData]:
    """BTC/USDT 1-hour OHLCV data."""
    return load_snapshot("btc_usdt_1h")


@pytest.fixture
def eth_1m_ohlcv() -> list[OHLCVData]:
    """ETH/USDT 1-minute OHLCV data."""
    return load_snapshot("eth_usdt_1m")


@pytest.fixture
def eth_5m_ohlcv() -> list[OHLCVData]:
    """ETH/USDT 5-minute OHLCV data."""
    return load_snapshot("eth_usdt_5m")


@pytest.fixture
def eth_1h_ohlcv() -> list[OHLCVData]:
    """ETH/USDT 1-hour OHLCV data."""
    return load_snapshot("eth_usdt_1h")


@pytest.fixture
def btc_1m_expectations() -> dict[str, Any]:
    """Validated indicator expectations for BTC/USDT 1-minute data."""
    return load_expectations("btc_usdt_1m")


@pytest.fixture
def btc_5m_expectations() -> dict[str, Any]:
    """Validated indicator expectations for BTC/USDT 5-minute data."""
    return load_expectations("btc_usdt_5m")


@pytest.fixture
def btc_1h_expectations() -> dict[str, Any]:
    """Validated indicator expectations for BTC/USDT 1-hour data."""
    return load_expectations("btc_usdt_1h")


@pytest.fixture
def eth_1m_expectations() -> dict[str, Any]:
    """Validated indicator expectations for ETH/USDT 1-minute data."""
    return load_expectations("eth_usdt_1m")


@pytest.fixture
def eth_5m_expectations() -> dict[str, Any]:
    """Validated indicator expectations for ETH/USDT 5-minute data."""
    return load_expectations("eth_usdt_5m")


@pytest.fixture
def eth_1h_expectations() -> dict[str, Any]:
    """Validated indicator expectations for ETH/USDT 1-hour data."""
    return load_expectations("eth_usdt_1h")
