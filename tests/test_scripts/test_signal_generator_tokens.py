"""Tests for signal generator token universe.

This module verifies that the continuous signal generator
includes all required tokens in its symbol list.
"""

from pathlib import Path

import pytest

# Expected token universe (minimum active set)
EXPECTED_TOKENS = {"BTC", "ETH", "SOL", "LINK", "BNB"}


class TestSignalGeneratorTokens:
    """Tests for scripts/continuous_signal_generator.py token configuration."""

    @pytest.fixture
    def signal_generator_content(self):
        """Load signal generator script content."""
        script_path = (
            Path(__file__).parent.parent.parent
            / "scripts"
            / "continuous_signal_generator.py"
        )
        with open(script_path) as f:
            return f.read()

    def test_symbols_list_contains_all_tokens(self, signal_generator_content):
        """Verify symbols list includes all 5 required tokens."""
        import re

        # Find the symbols list definition
        # Look for: symbols = [ ... ]
        pattern = r"symbols\s*=\s*\[(.*?)\]"
        match = re.search(pattern, signal_generator_content, re.DOTALL)
        assert match, "Could not find symbols list in continuous_signal_generator.py"

        symbols_block = match.group(1)

        # Extract individual symbol tuples
        # Pattern matches: ("TOKEN/USDT", ...)
        symbol_pattern = r'\("([^"]+)/USDT"'
        symbols_found = re.findall(symbol_pattern, symbols_block)

        tokens_found = set(symbols_found)

        missing = EXPECTED_TOKENS - tokens_found
        assert not missing, f"Missing tokens in symbols list: {missing}"

        extra = tokens_found - EXPECTED_TOKENS
        assert not extra, f"Unexpected extra tokens in symbols list: {extra}"

    def test_symbols_list_has_correct_format(self, signal_generator_content):
        """Verify symbols list uses correct format."""
        import re

        pattern = r"symbols\s*=\s*\[(.*?)\]"
        match = re.search(pattern, signal_generator_content, re.DOTALL)
        symbols_block = match.group(1)

        # Each entry should be a tuple: ("SYMBOL", price, trend)
        entry_pattern = r'\("([^"]+)",\s*([\d.]+),\s*"(up|down)"\)'
        entries = re.findall(entry_pattern, symbols_block)

        assert len(entries) >= 5, (
            f"Expected at least 5 symbol entries, found {len(entries)}"
        )

        for symbol, price, trend in entries:
            assert symbol.endswith("/USDT"), f"Symbol {symbol} should end with /USDT"
            assert float(price) > 0, f"Price for {symbol} should be positive"
            assert trend in ["up", "down"], (
                f"Trend for {symbol} should be 'up' or 'down'"
            )

    def test_btc_eth_sol_link_bnb_all_present(self, signal_generator_content):
        """Explicitly verify each required token is present."""
        import re

        pattern = r"symbols\s*=\s*\[(.*?)\]"
        match = re.search(pattern, signal_generator_content, re.DOTALL)
        symbols_block = match.group(1)

        # Check for each specific token
        required_pairs = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "LINK/USDT", "BNB/USDT"]

        for pair in required_pairs:
            assert pair in symbols_block, (
                f"Required token pair {pair} not found in symbols list"
            )

    def test_symbols_list_structure(self, signal_generator_content):
        """Verify the symbols list has proper Python list structure."""
        import re

        # Check for proper list syntax
        assert "symbols = [" in signal_generator_content, (
            "Missing symbols list definition"
        )

        # Find the list
        pattern = r"symbols\s*=\s*\[(.*?)\]"
        match = re.search(pattern, signal_generator_content, re.DOTALL)
        assert match, "Could not parse symbols list"

        symbols_block = match.group(1)

        # Count commas to estimate number of entries (n entries = n-1 commas between items)
        comma_count = symbols_block.count("),")
        assert comma_count >= 4, (
            f"Expected at least 5 symbol entries (4+ commas), found {comma_count + 1}"
        )

        # Verify the matched text ends with closing bracket (regex includes it)
        assert match.group(0).endswith("]"), "List should close with ]"


class TestSignalGeneratorIntegration:
    """Integration tests for signal generator configuration."""

    def test_signal_generator_symbols_match_bybit_config(self):
        """Verify signal generator tokens align with bybit_endpoints.yaml."""
        # Load signal generator
        sg_path = (
            Path(__file__).parent.parent.parent
            / "scripts"
            / "continuous_signal_generator.py"
        )
        with open(sg_path) as f:
            sg_content = f.read()

        # Load bybit config
        import yaml

        bybit_path = (
            Path(__file__).parent.parent.parent / "config" / "bybit_endpoints.yaml"
        )
        with open(bybit_path) as f:
            bybit_config = yaml.safe_load(f)

        # Extract tokens from signal generator
        import re

        pattern = r"symbols\s*=\s*\[(.*?)\]"
        match = re.search(pattern, sg_content, re.DOTALL)
        symbols_block = match.group(1)
        symbol_pattern = r'\("([^"]+)/USDT"'
        sg_tokens = set(re.findall(symbol_pattern, symbols_block))

        # Extract tokens from bybit config
        bybit_tokens = {
            sym.replace("USDT", "") for sym in bybit_config["bybit"]["test_symbols"]
        }

        # They should match
        assert sg_tokens == bybit_tokens, (
            f"Signal generator tokens {sg_tokens} don't match bybit config tokens {bybit_tokens}"
        )

    def test_all_tokens_have_valid_price_data(self):
        """Verify each token has a reasonable base price configured."""
        sg_path = (
            Path(__file__).parent.parent.parent
            / "scripts"
            / "continuous_signal_generator.py"
        )
        with open(sg_path) as f:
            sg_content = f.read()

        import re

        pattern = r"symbols\s*=\s*\[(.*?)\]"
        match = re.search(pattern, sg_content, re.DOTALL)
        symbols_block = match.group(1)

        # Extract all symbol entries with prices
        entry_pattern = r'\("([^"]+)/USDT",\s*([\d.]+),\s*"(up|down)"\)'
        entries = re.findall(entry_pattern, symbols_block)

        # Verify reasonable price ranges (sanity check)
        expected_price_ranges = {
            "BTC": (10000, 200000),  # BTC typically $10k-$200k
            "ETH": (500, 10000),  # ETH typically $500-$10k
            "SOL": (10, 500),  # SOL typically $10-$500
            "LINK": (5, 100),  # LINK typically $5-$100
            "BNB": (100, 2000),  # BNB typically $100-$2k
        }

        for token, price_str, trend in entries:
            price = float(price_str)
            if token in expected_price_ranges:
                min_price, max_price = expected_price_ranges[token]
                assert min_price <= price <= max_price, (
                    f"{token} price {price} outside expected range ({min_price}-{max_price})"
                )
