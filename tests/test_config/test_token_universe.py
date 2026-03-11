"""Tests for token universe configuration.

This module verifies that all required tokens are properly configured
across the paper trading system configuration files.
"""

from pathlib import Path

import pytest
import yaml

# Expected token universe (minimum active set)
EXPECTED_TOKENS = {"BTC", "ETH", "SOL", "LINK", "BNB"}


class TestBybitEndpointsConfig:
    """Tests for config/bybit_endpoints.yaml."""

    @pytest.fixture
    def bybit_config(self):
        """Load bybit_endpoints.yaml configuration."""
        config_path = (
            Path(__file__).parent.parent.parent / "config" / "bybit_endpoints.yaml"
        )
        with open(config_path) as f:
            return yaml.safe_load(f)

    def test_test_symbols_contains_all_tokens(self, bybit_config):
        """Verify test_symbols includes all 5 required tokens."""
        test_symbols = set(bybit_config["bybit"]["test_symbols"])

        # Convert symbols to base token names (e.g., "BTCUSDT" -> "BTC")
        tokens_in_config = {sym.replace("USDT", "") for sym in test_symbols}

        missing = EXPECTED_TOKENS - tokens_in_config
        assert not missing, f"Missing tokens in test_symbols: {missing}"

        extra = tokens_in_config - EXPECTED_TOKENS
        assert not extra, f"Unexpected extra tokens in test_symbols: {extra}"

    def test_test_symbols_has_correct_format(self, bybit_config):
        """Verify test_symbols uses correct format (TOKENUSDT)."""
        test_symbols = bybit_config["bybit"]["test_symbols"]

        for symbol in test_symbols:
            assert symbol.endswith("USDT"), f"Symbol {symbol} should end with USDT"
            assert len(symbol) > 5, f"Symbol {symbol} seems too short"


class TestMarketRealismConfig:
    """Tests for config/market_realism.yaml."""

    @pytest.fixture
    def realism_config(self):
        """Load market_realism.yaml configuration."""
        config_path = (
            Path(__file__).parent.parent.parent / "config" / "market_realism.yaml"
        )
        with open(config_path) as f:
            return yaml.safe_load(f)

    def test_link_usdt_config_exists(self, realism_config):
        """Verify LINK/USDT configuration exists."""
        symbols = realism_config.get("symbols", {})
        assert "LINK/USDT" in symbols, "LINK/USDT configuration missing from symbols"

        link_config = symbols["LINK/USDT"]
        assert "slippage" in link_config, "LINK/USDT missing slippage config"
        assert "market_impact" in link_config, "LINK/USDT missing market_impact config"

    def test_bnb_usdt_config_exists(self, realism_config):
        """Verify BNB/USDT configuration exists."""
        symbols = realism_config.get("symbols", {})
        assert "BNB/USDT" in symbols, "BNB/USDT configuration missing from symbols"

        bnb_config = symbols["BNB/USDT"]
        assert "slippage" in bnb_config, "BNB/USDT missing slippage config"
        assert "market_impact" in bnb_config, "BNB/USDT missing market_impact config"

    def test_link_usdt_has_required_fields(self, realism_config):
        """Verify LINK/USDT has all required fields."""
        link_config = realism_config["symbols"]["LINK/USDT"]

        # Check slippage fields
        slippage = link_config["slippage"]
        assert "base_slippage_bps" in slippage
        assert "max_slippage_bps" in slippage
        assert isinstance(slippage["base_slippage_bps"], (int, float))
        assert isinstance(slippage["max_slippage_bps"], (int, float))

        # Check market_impact fields
        impact = link_config["market_impact"]
        assert "base_coefficient" in impact
        assert isinstance(impact["base_coefficient"], (int, float))

    def test_bnb_usdt_has_required_fields(self, realism_config):
        """Verify BNB/USDT has all required fields."""
        bnb_config = realism_config["symbols"]["BNB/USDT"]

        # Check slippage fields
        slippage = bnb_config["slippage"]
        assert "base_slippage_bps" in slippage
        assert "max_slippage_bps" in slippage
        assert isinstance(slippage["base_slippage_bps"], (int, float))
        assert isinstance(slippage["max_slippage_bps"], (int, float))

        # Check market_impact fields
        impact = bnb_config["market_impact"]
        assert "base_coefficient" in impact
        assert isinstance(impact["base_coefficient"], (int, float))


class TestOhlcvIngestionDefaults:
    """Tests for scripts/run_ohlcv_ingestion.py default symbols."""

    def test_default_symbols_include_all_tokens(self):
        """Verify default SYMBOLS env var includes all 5 tokens."""
        script_path = (
            Path(__file__).parent.parent.parent / "scripts" / "run_ohlcv_ingestion.py"
        )

        with open(script_path) as f:
            content = f.read()

        # Find the default SYMBOLS string (handles multi-line format)
        import re

        # Match get_env_var( "SYMBOLS", "value" ) pattern across lines
        match = re.search(
            r'get_env_var\(\s*"SYMBOLS"\s*,\s*"([^"]+)"', content, re.DOTALL
        )
        assert match, "Could not find SYMBOLS default in run_ohlcv_ingestion.py"

        default_symbols = match.group(1)
        # Remove any newlines and extra whitespace
        default_symbols = re.sub(r"\s+", "", default_symbols)
        symbols_list = [s.strip() for s in default_symbols.split(",")]

        # Convert to base token names
        tokens_in_defaults = {sym.replace("/USDT", "") for sym in symbols_list}

        missing = EXPECTED_TOKENS - tokens_in_defaults
        assert not missing, f"Missing tokens in default SYMBOLS: {missing}"

        # Verify format is correct (TOKEN/USDT)
        for sym in symbols_list:
            assert sym.endswith("/USDT"), f"Symbol {sym} should use /USDT format"


class TestTokenUniverseCompleteness:
    """Cross-cutting tests for token universe consistency."""

    def test_all_configs_have_consistent_tokens(self):
        """Verify all configuration files reference the same token set."""
        # This test ensures we don't have drift between config files
        bybit_path = (
            Path(__file__).parent.parent.parent / "config" / "bybit_endpoints.yaml"
        )
        realism_path = (
            Path(__file__).parent.parent.parent / "config" / "market_realism.yaml"
        )
        ingestion_path = (
            Path(__file__).parent.parent.parent / "scripts" / "run_ohlcv_ingestion.py"
        )

        # Load bybit tokens
        with open(bybit_path) as f:
            bybit_config = yaml.safe_load(f)
        bybit_tokens = {
            sym.replace("USDT", "") for sym in bybit_config["bybit"]["test_symbols"]
        }

        # Load realism tokens
        with open(realism_path) as f:
            realism_config = yaml.safe_load(f)
        realism_tokens = {
            sym.replace("/USDT", "") for sym in realism_config.get("symbols", {}).keys()
        }

        # Load ingestion defaults
        with open(ingestion_path) as f:
            ingestion_content = f.read()
        import re

        match = re.search(
            r'get_env_var\(\s*"SYMBOLS"\s*,\s*"([^"]+)"',
            ingestion_content,
            re.DOTALL,
        )
        assert match, "Could not find SYMBOLS default"
        default_symbols = match.group(1)
        default_symbols = re.sub(r"\s+", "", default_symbols)
        ingestion_tokens = {
            sym.strip().replace("/USDT", "") for sym in default_symbols.split(",")
        }

        # Verify expected tokens are in all configs
        for config_name, tokens in [
            ("bybit_endpoints.yaml", bybit_tokens),
            ("market_realism.yaml", realism_tokens),
            ("run_ohlcv_ingestion.py", ingestion_tokens),
        ]:
            missing = EXPECTED_TOKENS - tokens
            assert not missing, f"{config_name} missing tokens: {missing}"
