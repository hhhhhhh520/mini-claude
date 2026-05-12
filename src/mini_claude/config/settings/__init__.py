"""Layered settings configuration module.

This module provides a modular configuration structure with settings
organized by functional domain. Each submodule handles a specific area:
- base_settings: Core environment, project paths, and enums
- llm_settings: LLM API keys, models, token budgets
- logging_settings: Logging levels, file paths, formats
- monitoring_settings: Health checks, tracing, alerts
- security_settings: Rate limiting, content filtering
"""

from mini_claude.config.settings.base_settings import (
    Environment,
    ModelProvider,
    VectorDBType,
    ConfigChange,
    ConfigReloadResult,
)
from mini_claude.config.settings.llm_settings import LLMSettings
from mini_claude.config.settings.logging_settings import LoggingSettings
from mini_claude.config.settings.monitoring_settings import MonitoringSettings
from mini_claude.config.settings.security_settings import SecuritySettings
from mini_claude.config.settings.composite_settings import (
    Settings,
    settings,
    register_config_callback,
    unregister_config_callback,
    clear_config_callbacks,
)

__all__ = [
    # Enums and data classes
    "Environment",
    "ModelProvider",
    "VectorDBType",
    "ConfigChange",
    "ConfigReloadResult",
    # Settings classes
    "LLMSettings",
    "LoggingSettings",
    "MonitoringSettings",
    "SecuritySettings",
    "Settings",
    "settings",
    # Callback functions
    "register_config_callback",
    "unregister_config_callback",
    "clear_config_callbacks",
]
