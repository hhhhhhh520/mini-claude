"""Monitoring settings: health checks, tracing, alerts, and notifications.

This module provides monitoring-related configuration:
- Health check server settings
- OpenTelemetry tracing configuration
- Alert thresholds and webhook settings
- Notification channels and SMTP settings
- Tool cache configuration
"""

from typing import Optional, List

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class MonitoringSettings(BaseSettings):
    """Monitoring and observability configuration settings.

    This class handles:
    - Health check endpoint settings
    - OpenTelemetry tracing configuration
    - Alert thresholds for failures, latency, token budget
    - Notification channels and SMTP email settings
    - Tool cache settings for performance
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Health Check settings
    health_check_enabled: bool = Field(default=True)
    health_check_port: int = Field(default=8080)
    health_check_host: str = Field(default="0.0.0.0")
    health_check_path: str = Field(default="/health")

    # Tool Cache settings
    tool_cache_enabled: bool = Field(default=True)
    tool_cache_ttl_seconds: int = Field(default=300)
    tool_cache_max_size: int = Field(default=100)
    tool_cache_tools: List[str] = Field(default=[
        "read_file",
        "list_dir",
        "search_files",
        "search_content",
    ])

    # Tracing settings (OpenTelemetry)
    tracing_enabled: bool = Field(default=False)
    tracing_exporter: str = Field(default="console")
    tracing_service_name: str = Field(default="mini-claude")
    tracing_otlp_endpoint: str = Field(default="http://localhost:4317")
    tracing_sample_rate: float = Field(default=1.0)
    tracing_file_path: str = Field(default="logs/traces.json")

    # Alert settings
    alert_enabled: bool = Field(default=True)
    alert_failure_rate_threshold: float = Field(default=0.2)
    alert_latency_threshold_seconds: float = Field(default=5.0)
    alert_token_budget_threshold: float = Field(default=0.8)
    alert_webhook_url: Optional[str] = None

    # Notification settings
    notification_enabled: bool = Field(default=False)
    notification_channels: List[str] = Field(default=["webhook", "email"])
    notification_min_level: str = Field(default="error")

    # SMTP settings for email notifications
    smtp_host: Optional[str] = None
    smtp_port: int = Field(default=587)
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_from: Optional[str] = None
    smtp_to: List[str] = Field(default=[])
    smtp_use_tls: bool = Field(default=True)

    @field_validator("health_check_port")
    @classmethod
    def validate_health_check_port(cls, v: int) -> int:
        """Validate health_check_port is valid."""
        if not 1 <= v <= 65535:
            raise ValueError(f"health_check_port must be between 1 and 65535, got {v}")
        return v

    @field_validator("tracing_exporter")
    @classmethod
    def validate_tracing_exporter(cls, v: str) -> str:
        """Validate tracing_exporter is a supported type."""
        valid_exporters = ["console", "otlp", "file"]
        if v.lower() not in valid_exporters:
            raise ValueError(f"tracing_exporter must be one of {valid_exporters}, got '{v}'")
        return v.lower()

    @field_validator("tracing_sample_rate")
    @classmethod
    def validate_tracing_sample_rate(cls, v: float) -> float:
        """Validate sample rate is between 0 and 1."""
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"tracing_sample_rate must be between 0 and 1, got {v}")
        return v

    @field_validator("alert_failure_rate_threshold", "alert_token_budget_threshold")
    @classmethod
    def validate_threshold_ratio(cls, v: float) -> float:
        """Validate threshold ratio is between 0 and 1."""
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"threshold must be between 0 and 1, got {v}")
        return v

    @field_validator("notification_min_level")
    @classmethod
    def validate_notification_min_level(cls, v: str) -> str:
        """Validate notification_min_level is a valid level."""
        valid_levels = ["info", "warning", "error", "critical"]
        if v.lower() not in valid_levels:
            raise ValueError(f"notification_min_level must be one of {valid_levels}, got '{v}'")
        return v.lower()

    @field_validator("smtp_port")
    @classmethod
    def validate_smtp_port(cls, v: int) -> int:
        """Validate SMTP port is valid."""
        if not 1 <= v <= 65535:
            raise ValueError(f"smtp_port must be between 1 and 65535, got {v}")
        return v

    @model_validator(mode="after")
    def validate_tracing_dependencies(self) -> "MonitoringSettings":
        """Validate tracing configuration dependencies."""
        if self.tracing_enabled and self.tracing_exporter == "otlp":
            if not self.tracing_otlp_endpoint:
                raise ValueError(
                    "tracing_otlp_endpoint must be configured when tracing_exporter is 'otlp'"
                )
        return self


__all__ = ["MonitoringSettings"]