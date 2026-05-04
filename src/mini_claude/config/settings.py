"""Settings configuration module - backward compatible entry point.

This module provides backward compatibility by re-exporting all settings
from the new layered configuration structure under settings/ directory.

All configuration items remain accessible from this module:
    from mini_claude.config.settings import Settings, settings

The actual implementation is in:
- settings/base_settings.py: Environment, enums, base config
- settings/llm_settings.py: LLM, API keys, tokens
- settings/logging_settings.py: Logging configuration
- settings/monitoring_settings.py: Health checks, tracing, alerts
- settings/security_settings.py: Rate limiting, vector db, profiles
- settings/composite_settings.py: Unified Settings class
"""

# Import all components from the layered settings module
from mini_claude.config.settings.base_settings import (
    ModelProvider,
    VectorDBType,
    Environment,
    ConfigChange,
    ConfigReloadResult,
)
from mini_claude.config.settings.composite_settings import (
    Settings,
    settings,
    register_config_callback,
    unregister_config_callback,
    clear_config_callbacks,
    _config_callbacks,
)

# Re-export all public items for backward compatibility
__all__ = [
    # Enums
    "ModelProvider",
    "VectorDBType",
    "Environment",
    # Data classes
    "ConfigChange",
    "ConfigReloadResult",
    # Main settings
    "Settings",
    "settings",
    # Callback functions
    "register_config_callback",
    "unregister_config_callback",
    "clear_config_callbacks",
]
