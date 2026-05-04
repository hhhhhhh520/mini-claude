"""Logging settings: log levels, file paths, and format configuration.

This module provides logging-related configuration:
- Log level settings (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- Console, file, and JSON logging options
- Log file paths and rotation settings
- Audit logging configuration
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LoggingSettings(BaseSettings):
    """Logging configuration settings.

    This class handles:
    - Log level configuration
    - Console and file output settings
    - JSON structured logging for production
    - Log file paths and rotation settings
    - Audit logging for security
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Log level settings
    log_level: str = Field(default="INFO")
    log_to_console: bool = Field(default=True)
    log_to_file: bool = Field(default=True)
    log_to_json: bool = Field(default=False)

    # Log file paths
    log_file_path: str = Field(default="logs/mini_claude.log")
    log_json_path: str = Field(default="logs/mini_claude.json")
    log_audit_path: str = Field(default="logs/audit.log")

    # Log rotation settings
    log_max_bytes: int = Field(default=10 * 1024 * 1024)  # 10MB
    log_backup_count: int = Field(default=5)

    # Audit logging
    audit_enabled: bool = Field(default=True)

    @property
    def log_level_int(self) -> int:
        """Get log level as integer for logging module."""
        levels = {
            "DEBUG": 10,
            "INFO": 20,
            "WARNING": 30,
            "ERROR": 40,
            "CRITICAL": 50,
        }
        return levels.get(self.log_level.upper(), 20)

    @property
    def is_production_ready(self) -> bool:
        """Check if logging is configured for production."""
        return self.log_to_json and self.audit_enabled


__all__ = ["LoggingSettings"]