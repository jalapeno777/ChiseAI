"""Configuration settings for the autonomous control plane.

ST-NS-038: Circuit Breaker Registry & Unified Telemetry
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


@dataclass
class RedisConfig:
    """Redis configuration."""

    host: str = "chiseai-redis"
    port: int = 6380
    db: int = 0
    password: str | None = None
    socket_timeout: float = 5.0
    socket_connect_timeout: float = 5.0

    @classmethod
    def from_env(cls) -> RedisConfig:
        """Load from environment variables."""
        return cls(
            host=os.getenv("ACP_REDIS_HOST", "chiseai-redis"),
            port=int(os.getenv("ACP_REDIS_PORT", "6380")),
            db=int(os.getenv("ACP_REDIS_DB", "0")),
            password=os.getenv("ACP_REDIS_PASSWORD") or None,
            socket_timeout=float(os.getenv("ACP_REDIS_TIMEOUT", "5.0")),
            socket_connect_timeout=float(os.getenv("ACP_REDIS_CONNECT_TIMEOUT", "5.0")),
        )


@dataclass
class PostgreSQLConfig:
    """PostgreSQL configuration for backup/long-term storage."""

    host: str = "chiseai-postgres"
    port: int = 5434
    database: str = "chiseai"
    user: str = "chiseai"
    password: str = "chiseai"

    @property
    def connection_string(self) -> str:
        """Get SQLAlchemy connection string."""
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"

    @classmethod
    def from_env(cls) -> PostgreSQLConfig:
        """Load from environment variables."""
        return cls(
            host=os.getenv("ACP_POSTGRES_HOST", "chiseai-postgres"),
            port=int(os.getenv("ACP_POSTGRES_PORT", "5434")),
            database=os.getenv("ACP_POSTGRES_DB", "chiseai"),
            user=os.getenv("ACP_POSTGRES_USER", "chiseai"),
            password=os.getenv("ACP_POSTGRES_PASSWORD", "chiseai"),
        )


@dataclass
class InfluxDBConfig:
    """InfluxDB configuration for telemetry."""

    host: str = "host.docker.internal"
    port: int = 18087
    bucket: str = "chiseai"
    org: str = "chiseai"
    token: str = "chiseai-token"

    @property
    def url(self) -> str:
        """Get InfluxDB URL."""
        return f"http://{self.host}:{self.port}"

    @classmethod
    def from_env(cls) -> InfluxDBConfig:
        """Load from environment variables."""
        return cls(
            host=os.getenv("ACP_INFLUXDB_HOST", "host.docker.internal"),
            port=int(os.getenv("ACP_INFLUXDB_PORT", "18087")),
            bucket=os.getenv("ACP_INFLUXDB_BUCKET", "chiseai"),
            org=os.getenv("ACP_INFLUXDB_ORG", "chiseai"),
            token=os.getenv("ACP_INFLUXDB_TOKEN", "chiseai-token"),
        )


@dataclass
class TelemetryConfig:
    """Telemetry configuration."""

    flush_interval_seconds: float = 15.0
    batch_size: int = 100
    enabled: bool = True

    @classmethod
    def from_env(cls) -> TelemetryConfig:
        """Load from environment variables."""
        return cls(
            flush_interval_seconds=float(
                os.getenv("ACP_TELEMETRY_FLUSH_INTERVAL", "15.0")
            ),
            batch_size=int(os.getenv("ACP_TELEMETRY_BATCH_SIZE", "100")),
            enabled=os.getenv("ACP_TELEMETRY_ENABLED", "true").lower() == "true",
        )


@dataclass
class Settings:
    """Unified settings for the autonomous control plane."""

    redis: RedisConfig = None  # type: ignore
    postgres: PostgreSQLConfig = None  # type: ignore
    influxdb: InfluxDBConfig = None  # type: ignore
    telemetry: TelemetryConfig = None  # type: ignore

    # Circuit breaker registry settings
    cb_registry_key_prefix: str = "acp:circuit_breaker:"
    cb_telemetry_measurement: str = "circuit_breaker_state"
    cb_health_check_interval: float = 30.0

    # API settings
    api_host: str = (
        "0.0.0.0"  # nosec B104 - 0.0.0.0 binding is standard for containerized services
    )
    api_port: int = 8000
    api_reload: bool = False

    def __post_init__(self) -> None:
        """Initialize sub-configs if not provided."""
        if self.redis is None:
            self.redis = RedisConfig.from_env()
        if self.postgres is None:
            self.postgres = PostgreSQLConfig.from_env()
        if self.influxdb is None:
            self.influxdb = InfluxDBConfig.from_env()
        if self.telemetry is None:
            self.telemetry = TelemetryConfig.from_env()

    @classmethod
    def from_env(cls) -> Settings:
        """Load all settings from environment."""
        return cls(
            redis=RedisConfig.from_env(),
            postgres=PostgreSQLConfig.from_env(),
            influxdb=InfluxDBConfig.from_env(),
            telemetry=TelemetryConfig.from_env(),
            cb_registry_key_prefix=os.getenv(
                "ACP_CB_KEY_PREFIX", "acp:circuit_breaker:"
            ),
            cb_telemetry_measurement=os.getenv(
                "ACP_CB_MEASUREMENT", "circuit_breaker_state"
            ),
            cb_health_check_interval=float(os.getenv("ACP_CB_HEALTH_INTERVAL", "30.0")),
            api_host=os.getenv(
                "ACP_API_HOST", "0.0.0.0"
            ),  # nosec B104 - 0.0.0.0 binding is standard for containerized services
            api_port=int(os.getenv("ACP_API_PORT", "8000")),
            api_reload=os.getenv("ACP_API_RELOAD", "false").lower() == "true",
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "redis": {
                "host": self.redis.host,
                "port": self.redis.port,
                "db": self.redis.db,
            },
            "postgres": {
                "host": self.postgres.host,
                "port": self.postgres.port,
                "database": self.postgres.database,
            },
            "influxdb": {
                "host": self.influxdb.host,
                "port": self.influxdb.port,
                "bucket": self.influxdb.bucket,
            },
            "telemetry": {
                "flush_interval_seconds": self.telemetry.flush_interval_seconds,
                "enabled": self.telemetry.enabled,
            },
        }


# Global settings instance
settings = Settings.from_env()
