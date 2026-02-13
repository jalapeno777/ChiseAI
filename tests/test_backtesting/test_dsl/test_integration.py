"""Tests for DSL integration (end-to-end)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import pytest
import tempfile
import yaml

from src.backtesting.dsl import (
    StrategyDSL,
    DSLValidator,
    StrategySubmission,
    compute_dsl_fingerprint,
    diff_configs,
    configs_equal,
    submit_strategy,
    validate_strategy,
)
from src.backtesting.dsl.models import (
    StrategyCategory,
    Timeframe,
    MarketType,
    EntryLogic,
)


class TestDSLIntegration:
    """Integration tests for complete DSL workflow."""

    def test_full_workflow_valid_strategy(self):
        """Test complete workflow with valid strategy."""
        # Create a valid strategy
        config = {
            "metadata": {
                "name": "IntegrationTest",
                "version": "1.0.0",
                "category": "grid",
                "timeframes": ["1h", "4h"],
            },
            "universe": {
                "symbols": [
                    {
                        "symbol": "BTCUSDT",
                        "exchange": "bybit",
                        "market_type": "perpetual",
                    }
                ]
            },
            "signals": {
                "entry_logic": "confluence",
                "indicators": [
                    {
                        "name": "rsi",
                        "type": "rsi",
                        "parameters": {"period": 14},
                        "conditions": [
                            {"operator": "lt", "threshold": 30, "direction": "long"}
                        ],
                    }
                ],
                "confluence": {
                    "enabled": True,
                    "min_score": 0.65,
                },
            },
            "exits": {
                "stop_loss": {
                    "enabled": True,
                    "type": "atr_based",
                    "atr_multiplier": 1.5,
                },
                "take_profit": {"enabled": True, "type": "r_based", "r_multiple": 2.0},
            },
            "sizing": {
                "method": "risk_percent",
                "risk_percent": {
                    "enabled": True,
                    "percent": 1.0,
                    "max_position_percent": 10.0,
                },
            },
            "execution_policy": {
                "order_types": {"entry": "limit", "exit": "market"},
            },
            "risk_rules": {
                "position_limits": {
                    "max_position_size_usd": 50000,
                    "max_position_percent": 10.0,
                    "max_leverage": 1.0,
                },
                "daily_limits": {
                    "max_daily_loss_percent": 2.0,
                },
            },
        }

        # Step 1: Validate
        validator = DSLValidator()
        validation_result = validator.validate(config)
        assert validation_result.is_valid is True

        # Step 2: Submit
        submission = StrategySubmission()
        submission_result = submission.submit(config)
        assert submission_result.success is True
        assert submission_result.is_valid is True

        # Step 3: Check fingerprint
        fingerprint = compute_dsl_fingerprint(config)
        assert len(fingerprint) == 64
        assert submission_result.fingerprint == fingerprint

    def test_full_workflow_invalid_strategy(self):
        """Test complete workflow with invalid strategy."""
        # Create an invalid strategy (high leverage)
        config = {
            "metadata": {
                "name": "InvalidStrategy",
                "version": "1.0.0",
            },
            "universe": {"symbols": [{"symbol": "BTCUSDT", "exchange": "bybit"}]},
            "signals": {},
            "exits": {},
            "sizing": {},
            "execution_policy": {},
            "risk_rules": {
                "position_limits": {
                    "max_leverage": 5.0,  # Exceeds 3.0 limit
                }
            },
        }

        # Submit should fail due to safety violation
        result = submit_strategy(config)

        assert result.success is False
        assert result.is_valid is False
        assert len(result.safety_errors) > 0

        # Check field-level error
        leverage_errors = [
            e for e in result.safety_errors if "max_leverage" in e.field_path
        ]
        assert len(leverage_errors) >= 1
        assert leverage_errors[0].value == 5.0

    def test_yaml_file_workflow(self):
        """Test workflow with YAML file."""
        config = {
            "metadata": {
                "name": "YAMLTest",
                "version": "1.0.0",
                "category": "momentum",
            },
            "universe": {"symbols": [{"symbol": "ETHUSDT", "exchange": "bybit"}]},
            "signals": {
                "entry_logic": "single_indicator",
                "indicators": [
                    {
                        "name": "ema_cross",
                        "type": "ema",
                        "parameters": {"fast_period": 9, "slow_period": 21},
                        "conditions": [
                            {"operator": "cross_above", "direction": "long"}
                        ],
                    }
                ],
            },
            "exits": {
                "stop_loss": {"enabled": True, "type": "fixed", "fixed_percent": 2.0},
            },
            "sizing": {"method": "fixed_usd", "fixed_usd": 1000},
            "execution_policy": {
                "order_types": {"entry": "market", "exit": "market"},
            },
            "risk_rules": {
                "position_limits": {"max_leverage": 1.0},
            },
        }

        # Write to temp file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config, f)
            temp_path = f.name

        try:
            # Load from YAML
            dsl = StrategyDSL.from_yaml(temp_path)

            assert dsl.metadata.name == "YAMLTest"
            assert dsl.metadata.category == StrategyCategory.MOMENTUM
            assert len(dsl.universe.symbols) == 1
            assert dsl.universe.symbols[0].symbol == "ETHUSDT"

        finally:
            Path(temp_path).unlink()

    def test_reproducibility_same_config_same_fingerprint(self):
        """Test that same config produces same fingerprint."""
        config1 = {
            "metadata": {"name": "Test", "version": "1.0.0"},
            "universe": {"symbols": [{"symbol": "BTC", "exchange": "bybit"}]},
            "signals": {},
            "exits": {},
            "sizing": {},
            "execution_policy": {},
            "risk_rules": {},
        }

        config2 = {
            "metadata": {"name": "Test", "version": "1.0.0"},
            "universe": {"symbols": [{"symbol": "BTC", "exchange": "bybit"}]},
            "signals": {},
            "exits": {},
            "sizing": {},
            "execution_policy": {},
            "risk_rules": {},
        }

        fp1 = compute_dsl_fingerprint(config1)
        fp2 = compute_dsl_fingerprint(config2)

        assert fp1 == fp2

    def test_diff_shows_changes(self):
        """Test that diff correctly identifies changes."""
        config1 = {
            "metadata": {"name": "Strategy_v1", "version": "1.0.0"},
            "universe": {"symbols": [{"symbol": "BTC", "exchange": "bybit"}]},
            "signals": {},
            "exits": {},
            "sizing": {},
            "execution_policy": {},
            "risk_rules": {},
        }

        config2 = config1.copy()
        config2["metadata"] = config1["metadata"].copy()
        config2["metadata"]["name"] = "Strategy_v2"
        config2["metadata"]["version"] = "1.1.0"

        diff = diff_configs(config1, config2)

        assert diff.has_changes is True
        assert len(diff.modifications) == 2

        # Check that name change is detected
        name_changes = [m for m in diff.modifications if m.path == "metadata.name"]
        assert len(name_changes) == 1
        assert name_changes[0].old_value == "Strategy_v1"
        assert name_changes[0].new_value == "Strategy_v2"

    def test_configs_equal_detects_equality(self):
        """Test configs_equal function."""
        config1 = {
            "metadata": {"name": "Test", "version": "1.0.0"},
            "universe": {"symbols": [{"symbol": "BTC", "exchange": "bybit"}]},
            "signals": {},
            "exits": {},
            "sizing": {},
            "execution_policy": {},
            "risk_rules": {},
        }

        config2 = {
            "metadata": {"name": "Test", "version": "1.0.0"},
            "universe": {"symbols": [{"symbol": "BTC", "exchange": "bybit"}]},
            "signals": {},
            "exits": {},
            "sizing": {},
            "execution_policy": {},
            "risk_rules": {},
        }

        config3 = {
            "metadata": {"name": "Different", "version": "1.0.0"},
            "universe": {"symbols": [{"symbol": "BTC", "exchange": "bybit"}]},
            "signals": {},
            "exits": {},
            "sizing": {},
            "execution_policy": {},
            "risk_rules": {},
        }

        assert configs_equal(config1, config2) is True
        assert configs_equal(config1, config3) is False

    def test_field_level_error_reporting(self):
        """Test field-level error reporting for UI."""
        config = {
            "metadata": {
                "name": "",  # Missing required
                "version": "",  # Missing required
            },
            "universe": {
                "symbols": [],  # Empty - should error
            },
            "signals": {},
            "exits": {},
            "sizing": {},
            "execution_policy": {},
            "risk_rules": {},
        }

        result = validate_strategy(config)

        # Should have errors for specific fields
        name_errors = result.get_errors_for_field("metadata.name")
        version_errors = result.get_errors_for_field("metadata.version")
        symbol_errors = result.get_errors_for_field("universe.symbols")

        assert len(name_errors) == 1
        assert len(version_errors) == 1
        assert len(symbol_errors) == 1

        # Verify error structure
        error = name_errors[0]
        assert error.field_path == "metadata.name"
        assert error.message is not None
        assert error.constraint is not None

    def test_safety_constraints_enforced(self):
        """Test that safety constraints are enforced."""
        config = {
            "metadata": {"name": "Unsafe", "version": "1.0.0"},
            "universe": {"symbols": [{"symbol": "BTC", "exchange": "bybit"}]},
            "signals": {
                "confluence": {
                    "enabled": True,
                    "min_score": 0.3,  # Below 0.5 minimum
                }
            },
            "exits": {},
            "sizing": {},
            "execution_policy": {},
            "risk_rules": {
                "position_limits": {
                    "max_leverage": 5.0,  # Above 3.0 maximum
                    "max_position_percent": 150.0,  # Above 100% maximum
                }
            },
        }

        result = submit_strategy(config)

        assert result.success is False

        # Check all safety violations
        safety_paths = [e.field_path for e in result.safety_errors]

        assert any("max_leverage" in p for p in safety_paths)
        assert any("max_position_percent" in p for p in safety_paths)
        assert any("min_score" in p for p in safety_paths)
