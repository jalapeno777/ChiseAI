"""Configuration for data quality monitoring.

Provides configuration classes and environment-based setup for
data quality monitoring components.

For ST-DATA-004: Data Quality Monitoring - Freshness + Gaps
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from monitoring.data_quality import DataSource, SourceConfig


@dataclass
class DataQualityConfig:
    """Configuration for data quality monitoring.

    Attributes:
        # Source Configuration
        binance_symbols: Symbols to monitor for Binance
        bybit_symbols: Symbols to monitor for Bybit
        bitget_symbols: Symbols to monitor for Bitget
        timeframes: Timeframes to monitor

        # Freshness Configuration
        freshness_threshold_seconds: Default freshness threshold
        freshness_alert_cooldown: Cooldown between freshness alerts

        # Gap Detection Configuration
        gap_detection_enabled: Whether gap detection is enabled
        gap_detection_window_seconds: Target detection latency

        # Discord Alert Configuration
        discord_webhook_url: Discord webhook URL for alerts
        discord_alerts_channel: Channel for data quality alerts
        discord_recovery_notices: Whether to send recovery notices

        # Grafana/InfluxDB Configuration
        influx_url: InfluxDB URL
        influx_token: InfluxDB token
        influx_org: InfluxDB organization
        influx_bucket: InfluxDB bucket for data quality metrics

        # Monitoring Intervals
        monitoring_interval_seconds: Interval for continuous monitoring
        enable_continuous_monitoring: Whether to run continuous monitoring
    """

    # Source Configuration
    binance_symbols: list[str] = field(
        default_factory=lambda: ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
    )
    bybit_symbols: list[str] = field(
        default_factory=lambda: ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
    )
    bitget_symbols: list[str] = field(
        default_factory=lambda: ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
    )
    timeframes: list[str] = field(default_factory=lambda: ["1m", "5m", "15m", "1h"])

    # Freshness Configuration
    freshness_threshold_seconds: float = 300.0  # 5 minutes
    freshness_alert_cooldown: float = 60.0  # 1 minute

    # Gap Detection Configuration
    gap_detection_enabled: bool = True
    gap_detection_window_seconds: float = 60.0  # 60 second detection

    # Discord Alert Configuration
    discord_webhook_url: str | None = None
    discord_alerts_channel: str = "alerts"
    discord_recovery_notices: bool = True

    # Grafana/InfluxDB Configuration
    influx_url: str = "http://localhost:8086"
    influx_token: str = ""
    influx_org: str = "chiseai"
    influx_bucket: str = "data_quality"

    # Monitoring Intervals
    monitoring_interval_seconds: float = 60.0
    enable_continuous_monitoring: bool = True

    @classmethod
    def from_env(cls) -> DataQualityConfig:
        """Create configuration from environment variables.

        Environment Variables:
            # Source Configuration
            DQ_BINANCE_SYMBOLS: Comma-separated list of Binance symbols
            DQ_BYBIT_SYMBOLS: Comma-separated list of Bybit symbols
            DQ_BITGET_SYMBOLS: Comma-separated list of Bitget symbols
            DQ_TIMEFRAMES: Comma-separated list of timeframes

            # Freshness Configuration
            DQ_FRESHNESS_THRESHOLD_SECONDS: Freshness threshold (default 300)
            DQ_FRESHNESS_ALERT_COOLDOWN: Alert cooldown (default 60)

            # Gap Detection
            DQ_GAP_DETECTION_ENABLED: Enable gap detection (default true)
            DQ_GAP_DETECTION_WINDOW: Detection window in seconds (default 60)

            # Discord Configuration
            DQ_DISCORD_WEBHOOK_URL: Discord webhook URL
            DQ_DISCORD_ALERTS_CHANNEL: Alerts channel name (default alerts)
            DQ_DISCORD_RECOVERY_NOTICES: Send recovery notices (default true)

            # InfluxDB Configuration
            DQ_INFLUX_URL: InfluxDB URL (default http://localhost:8086)
            DQ_INFLUX_TOKEN: InfluxDB token
            DQ_INFLUX_ORG: InfluxDB org (default chiseai)
            DQ_INFLUX_BUCKET: InfluxDB bucket (default data_quality)

            # Monitoring
            DQ_MONITORING_INTERVAL: Monitoring interval in seconds (default 60)
            DQ_ENABLE_CONTINUOUS_MONITORING: Enable continuous monitoring (default true)

        Returns:
            DataQualityConfig instance
        """

        def parse_symbols(env_var: str, default: list[str]) -> list[str]:
            """Parse comma-separated symbols from env."""
            value = os.getenv(env_var)
            if value:
                return [s.strip() for s in value.split(",")]
            return default

        def parse_timeframes(env_var: str, default: list[str]) -> list[str]:
            """Parse comma-separated timeframes from env."""
            value = os.getenv(env_var)
            if value:
                return [t.strip() for t in value.split(",")]
            return default

        def parse_bool(env_var: str, default: bool) -> bool:
            """Parse boolean from env."""
            value = os.getenv(env_var)
            if value is None:
                return default
            return value.lower() in ("true", "1", "yes", "on")

        def parse_float(env_var: str, default: float) -> float:
            """Parse float from env."""
            value = os.getenv(env_var)
            if value is None:
                return default
            try:
                return float(value)
            except ValueError:
                return default

        return cls(
            # Source Configuration
            binance_symbols=parse_symbols(
                "DQ_BINANCE_SYMBOLS",
                ["BTC/USDT", "ETH/USDT", "SOL/USDT"],
            ),
            bybit_symbols=parse_symbols(
                "DQ_BYBIT_SYMBOLS",
                ["BTC/USDT", "ETH/USDT", "SOL/USDT"],
            ),
            bitget_symbols=parse_symbols(
                "DQ_BITGET_SYMBOLS",
                ["BTC/USDT", "ETH/USDT", "SOL/USDT"],
            ),
            timeframes=parse_timeframes(
                "DQ_TIMEFRAMES",
                ["1m", "5m", "15m", "1h"],
            ),
            # Freshness Configuration
            freshness_threshold_seconds=parse_float(
                "DQ_FRESHNESS_THRESHOLD_SECONDS",
                300.0,
            ),
            freshness_alert_cooldown=parse_float(
                "DQ_FRESHNESS_ALERT_COOLDOWN",
                60.0,
            ),
            # Gap Detection
            gap_detection_enabled=parse_bool(
                "DQ_GAP_DETECTION_ENABLED",
                True,
            ),
            gap_detection_window_seconds=parse_float(
                "DQ_GAP_DETECTION_WINDOW",
                60.0,
            ),
            # Discord Configuration
            discord_webhook_url=os.getenv("DQ_DISCORD_WEBHOOK_URL"),
            discord_alerts_channel=os.getenv(
                "DQ_DISCORD_ALERTS_CHANNEL",
                "alerts",
            ),
            discord_recovery_notices=parse_bool(
                "DQ_DISCORD_RECOVERY_NOTICES",
                True,
            ),
            # InfluxDB Configuration
            influx_url=os.getenv(
                "DQ_INFLUX_URL",
                os.getenv("INFLUXDB_URL", "http://host.docker.internal:18087"),
            ),
            influx_token=os.getenv("DQ_INFLUX_TOKEN", ""),
            influx_org=os.getenv("DQ_INFLUX_ORG", "chiseai"),
            influx_bucket=os.getenv("DQ_INFLUX_BUCKET", "data_quality"),
            # Monitoring
            monitoring_interval_seconds=parse_float(
                "DQ_MONITORING_INTERVAL",
                60.0,
            ),
            enable_continuous_monitoring=parse_bool(
                "DQ_ENABLE_CONTINUOUS_MONITORING",
                True,
            ),
        )

    def get_source_configs(self) -> list[SourceConfig]:
        """Get source configurations from this config.

        Returns:
            List of SourceConfig for enabled sources
        """
        configs = []

        if self.binance_symbols:
            configs.append(
                SourceConfig(
                    source=DataSource.BINANCE,
                    symbols=self.binance_symbols,
                    timeframes=self.timeframes,
                    freshness_threshold_seconds=self.freshness_threshold_seconds,
                    gap_detection_enabled=self.gap_detection_enabled,
                    enabled=True,
                )
            )

        if self.bybit_symbols:
            configs.append(
                SourceConfig(
                    source=DataSource.BYBIT,
                    symbols=self.bybit_symbols,
                    timeframes=self.timeframes,
                    freshness_threshold_seconds=self.freshness_threshold_seconds,
                    gap_detection_enabled=self.gap_detection_enabled,
                    enabled=True,
                )
            )

        if self.bitget_symbols:
            configs.append(
                SourceConfig(
                    source=DataSource.BITGET,
                    symbols=self.bitget_symbols,
                    timeframes=self.timeframes,
                    freshness_threshold_seconds=self.freshness_threshold_seconds,
                    gap_detection_enabled=self.gap_detection_enabled,
                    enabled=True,
                )
            )

        return configs

    def to_dict(self) -> dict[str, Any]:
        """Convert configuration to dictionary.

        Returns:
            Configuration dictionary
        """
        return {
            "sources": {
                "binance": {
                    "symbols": self.binance_symbols,
                    "enabled": bool(self.binance_symbols),
                },
                "bybit": {
                    "symbols": self.bybit_symbols,
                    "enabled": bool(self.bybit_symbols),
                },
                "bitget": {
                    "symbols": self.bitget_symbols,
                    "enabled": bool(self.bitget_symbols),
                },
                "timeframes": self.timeframes,
            },
            "freshness": {
                "threshold_seconds": self.freshness_threshold_seconds,
                "alert_cooldown": self.freshness_alert_cooldown,
            },
            "gap_detection": {
                "enabled": self.gap_detection_enabled,
                "window_seconds": self.gap_detection_window_seconds,
            },
            "discord": {
                "alerts_channel": self.discord_alerts_channel,
                "recovery_notices": self.discord_recovery_notices,
                "webhook_configured": self.discord_webhook_url is not None,
            },
            "influxdb": {
                "url": self.influx_url,
                "org": self.influx_org,
                "bucket": self.influx_bucket,
                "token_configured": bool(self.influx_token),
            },
            "monitoring": {
                "interval_seconds": self.monitoring_interval_seconds,
                "continuous_enabled": self.enable_continuous_monitoring,
            },
        }


@dataclass
class FreshnessThresholdConfig:
    """Per-source freshness threshold configuration.

    Allows different thresholds per data source.
    """

    default_threshold_seconds: float = 300.0
    source_thresholds: dict[DataSource, float] = field(default_factory=dict)

    def get_threshold(self, source: DataSource) -> float:
        """Get threshold for a specific source.

        Args:
            source: Data source

        Returns:
            Threshold in seconds
        """
        return self.source_thresholds.get(source, self.default_threshold_seconds)

    def set_threshold(self, source: DataSource, threshold_seconds: float) -> None:
        """Set threshold for a specific source.

        Args:
            source: Data source
            threshold_seconds: Threshold in seconds
        """
        self.source_thresholds[source] = threshold_seconds

    @classmethod
    def from_env(cls) -> FreshnessThresholdConfig:
        """Create from environment variables.

        Environment Variables:
            DQ_FRESHNESS_THRESHOLD_DEFAULT: Default threshold (default 300)
            DQ_FRESHNESS_THRESHOLD_BINANCE: Binance threshold
            DQ_FRESHNESS_THRESHOLD_BYBIT: Bybit threshold
            DQ_FRESHNESS_THRESHOLD_BITGET: Bitget threshold

        Returns:
            FreshnessThresholdConfig instance
        """
        import os

        default = float(os.getenv("DQ_FRESHNESS_THRESHOLD_DEFAULT", "300.0"))

        source_thresholds = {}

        binance_threshold = os.getenv("DQ_FRESHNESS_THRESHOLD_BINANCE")
        if binance_threshold:
            source_thresholds[DataSource.BINANCE] = float(binance_threshold)

        bybit_threshold = os.getenv("DQ_FRESHNESS_THRESHOLD_BYBIT")
        if bybit_threshold:
            source_thresholds[DataSource.BYBIT] = float(bybit_threshold)

        bitget_threshold = os.getenv("DQ_FRESHNESS_THRESHOLD_BITGET")
        if bitget_threshold:
            source_thresholds[DataSource.BITGET] = float(bitget_threshold)

        return cls(
            default_threshold_seconds=default,
            source_thresholds=source_thresholds,
        )
