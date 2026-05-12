"""Composite settings: aggregates all sub-settings into a unified Settings class.

This module provides the main Settings class that:
- Combines all sub-settings modules
- Provides unified access to all configuration
- Handles cross-field validation
- Supports hot reload functionality
- Manages config change callbacks
"""

import os
from pathlib import Path
from threading import Lock
from typing import Optional, List, Set, Callable, Dict, Any, TYPE_CHECKING

from pydantic import model_validator

from .base_settings import (
    ConfigChange,
    ConfigReloadResult,
    BaseEnvironmentSettings,
)
from .llm_settings import LLMSettings
from .logging_settings import LoggingSettings
from .monitoring_settings import MonitoringSettings
from .security_settings import SecuritySettings

if TYPE_CHECKING:
    from ..validation import ValidationResult


class Settings(
    BaseEnvironmentSettings,
    LLMSettings,
    LoggingSettings,
    MonitoringSettings,
    SecuritySettings,
):
    """Unified settings class combining all configuration domains.

    This class aggregates:
    - Base environment settings (environment, workspace)
    - LLM settings (API keys, models, tokens)
    - Logging settings (levels, paths, formats)
    - Monitoring settings (health checks, tracing, alerts)
    - Security settings (rate limiting, vector db, profiles)

    Cross-field validation ensures configuration consistency.
    """

    # Track loaded env files
    _loaded_env_files: Set[str] = set()

    @model_validator(mode="after")
    def validate_production_security(self) -> "Settings":
        """Validate production environment has required security settings."""
        if self.environment == "prod":
            errors = []

            if not self.audit_enabled:
                errors.append("audit_enabled must be True in production environment")

            if not self.log_to_json:
                errors.append("log_to_json must be True in production environment")

            if not self.rate_limit_enabled:
                errors.append("rate_limit_enabled must be True in production environment")

            if not self.health_check_enabled:
                errors.append("health_check_enabled must be True in production environment")

            if self.log_level.upper() == "DEBUG":
                errors.append("log_level must not be DEBUG in production environment")

            if errors:
                raise ValueError(
                    "Production environment security validation failed:\n"
                    + "\n".join(f"  - {e}" for e in errors)
                )

        return self

    @model_validator(mode="after")
    def validate_cross_field_dependencies(self) -> "Settings":
        """Validate cross-field dependencies."""
        # token_warn_ratio should be less than token_budget_ratio
        if self.token_warn_ratio >= self.token_budget_ratio:
            import logging

            logging.getLogger(__name__).warning(
                f"token_warn_ratio ({self.token_warn_ratio}) should be less than "
                f"token_budget_ratio ({self.token_budget_ratio})"
            )

        # Production environment validation
        if self.environment.lower() == "prod":
            if self.alert_enabled and not self.alert_webhook_url:
                import logging

                logging.getLogger(__name__).warning(
                    "Production environment should have alert_webhook_url configured"
                )

        return self

    def validate_configuration(self) -> "ValidationResult":
        """Validate configuration settings comprehensively.

        Returns:
            ValidationResult containing all warnings and errors
        """
        from ..validation import validate_configuration

        return validate_configuration(self)

    def reload(self, env_file: Optional[str] = None) -> "ConfigReloadResult":
        """Reload configuration from .env file.

        Args:
            env_file: Optional path to a specific .env file.
                      If None, uses the default .env file.

        Returns:
            ConfigReloadResult with reload status and changes.
        """
        try:
            old_values = self._capture_current_values()

            env_path = Path(env_file or self.model_config.get("env_file", ".env"))
            if not env_path.exists():
                return ConfigReloadResult(
                    success=False,
                    error=f"Environment file not found: {env_path}",
                )

            new_values = self._read_env_file(env_path)
            changes = self._detect_changes(old_values, new_values)

            if changes:
                try:
                    new_settings = Settings(**new_values)
                    for key, value in new_values.items():
                        if hasattr(self, key):
                            setattr(self, key, getattr(new_settings, key))

                    self._update_env_vars()

                except Exception as validation_error:
                    return ConfigReloadResult(
                        success=False,
                        error=f"Validation failed: {validation_error}",
                    )

            result = ConfigReloadResult(success=True, changes=changes)
            _notify_config_callbacks(result)

            return result

        except Exception as e:
            return ConfigReloadResult(
                success=False,
                error=f"Reload failed: {e}",
            )

    def _capture_current_values(self) -> Dict[str, Any]:
        """Capture current configuration values."""
        values = {}
        for field_name in Settings.model_fields.keys():
            if hasattr(self, field_name):
                values[field_name] = getattr(self, field_name)
        return values

    def _read_env_file(self, env_path: Path) -> Dict[str, Any]:
        """Read and parse .env file into a dictionary."""
        values = {}
        field_names_lower = {name.lower(): name for name in Settings.model_fields.keys()}

        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                if "=" in line:
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip()

                    if value.startswith('"') and value.endswith('"'):
                        value = value[1:-1]
                    elif value.startswith("'") and value.endswith("'"):
                        value = value[1:-1]

                    key_lower = key.lower()

                    if key_lower in field_names_lower:
                        actual_key = field_names_lower[key_lower]
                        field_info = Settings.model_fields[actual_key]

                        if field_info.annotation is bool or (
                            hasattr(field_info.annotation, "__origin__")
                            and field_info.annotation.__origin__ is bool
                        ):
                            value = value.lower() in ("true", "1", "yes", "on")
                        elif field_info.annotation is int or (
                            hasattr(field_info.annotation, "__origin__")
                            and field_info.annotation.__origin__ is int
                        ):
                            try:
                                value = int(value)
                            except ValueError:
                                pass
                        elif field_info.annotation is float or (
                            hasattr(field_info.annotation, "__origin__")
                            and field_info.annotation.__origin__ is float
                        ):
                            try:
                                value = float(value)
                            except ValueError:
                                pass
                        elif (
                            hasattr(field_info.annotation, "__origin__")
                            and field_info.annotation.__origin__ is list
                        ):
                            if value:
                                value = [v.strip() for v in value.split(",")]
                        key = actual_key

                    values[key] = value

        return values

    def _detect_changes(
        self, old_values: Dict[str, Any], new_values: Dict[str, Any]
    ) -> List[ConfigChange]:
        """Detect configuration changes between old and new values."""
        changes = []
        old_values_lower = {k.lower(): (k, v) for k, v in old_values.items()}

        for key, new_value in new_values.items():
            key_lower = key.lower()
            if key_lower not in old_values_lower:
                continue

            actual_key, old_value = old_values_lower[key_lower]

            if isinstance(old_value, list) and isinstance(new_value, list):
                if old_value != new_value:
                    changes.append(
                        ConfigChange(key=actual_key, old_value=old_value, new_value=new_value)
                    )
            elif old_value != new_value:
                changes.append(
                    ConfigChange(key=actual_key, old_value=old_value, new_value=new_value)
                )

        return changes

    def _update_env_vars(self) -> None:
        """Update environment variables for LiteLLM after reload."""
        if self.openai_api_key:
            os.environ["OPENAI_API_KEY"] = self.openai_api_key
        if self.openai_base_url:
            os.environ["OPENAI_BASE_URL"] = self.openai_base_url
        if self.anthropic_api_key:
            os.environ["ANTHROPIC_API_KEY"] = self.anthropic_api_key

    def register_callback(self, callback: Callable[["ConfigReloadResult"], None]) -> None:
        """Register a callback to be called when configuration changes."""
        register_config_callback(callback)

    def unregister_callback(self, callback: Callable[["ConfigReloadResult"], None]) -> bool:
        """Unregister a previously registered callback."""
        return unregister_config_callback(callback)

    def get_reloadable_fields(self) -> List[str]:
        """Get list of fields that can be hot-reloaded."""
        return list(Settings.model_fields.keys())


# === Module-level callback management ===
_config_callbacks: List[Callable[[ConfigReloadResult], None]] = []
_config_callback_lock = Lock()


def register_config_callback(callback: Callable[[ConfigReloadResult], None]) -> None:
    """Register a callback for configuration changes (module-level)."""
    with _config_callback_lock:
        _config_callbacks.append(callback)


def unregister_config_callback(callback: Callable[[ConfigReloadResult], None]) -> bool:
    """Unregister a callback (module-level)."""
    with _config_callback_lock:
        try:
            _config_callbacks.remove(callback)
            return True
        except ValueError:
            return False


def _notify_config_callbacks(result: ConfigReloadResult) -> None:
    """Notify all registered callbacks about configuration changes."""
    with _config_callback_lock:
        for callback in _config_callbacks:
            try:
                callback(result)
            except Exception as e:
                import logging

                logging.getLogger("mini_claude.config").warning(f"Config callback failed: {e}")


def clear_config_callbacks() -> None:
    """Clear all registered callbacks (for testing)."""
    with _config_callback_lock:
        _config_callbacks.clear()


# Global settings instance
settings = Settings()

# Set environment variables for LiteLLM
if settings.openai_api_key:
    os.environ["OPENAI_API_KEY"] = settings.openai_api_key
if settings.openai_base_url:
    os.environ["OPENAI_BASE_URL"] = settings.openai_base_url
if settings.anthropic_api_key:
    os.environ["ANTHROPIC_API_KEY"] = settings.anthropic_api_key


__all__ = [
    "Settings",
    "settings",
    "register_config_callback",
    "unregister_config_callback",
    "clear_config_callbacks",
]
