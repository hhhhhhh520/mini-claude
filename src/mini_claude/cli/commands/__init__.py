"""Command handlers package for REPL commands.

This package contains modular command handlers for the REPL.
Each handler is responsible for a related group of commands.

Handlers:
    - HelpCommandHandler: /help, /?, /exit, /quit, /q, /clear, /model
    - ProfileCommandHandler: /profile
    - SessionCommandHandler: /save, /load, /resume, /sessions, /interrupted, /reset, /thread
    - MetricsCommandHandler: /status, /tokens, /metrics
    - CacheCommandHandler: /cache
    - ConfigCommandHandler: /reload-config, /config-watch
    - LogCommandHandler: /export-log
    - AlertCommandHandler: /alerts
"""

from .base import (
    CommandHandler,
    CommandContext,
    CommandResult,
    CommandRegistry,
    get_command_registry,
    dispatch_command,
)
from .profile_handler import ProfileCommandHandler
from .session_handler import SessionCommandHandler
from .metrics_handler import MetricsCommandHandler
from .cache_handler import CacheCommandHandler
from .config_handler import ConfigCommandHandler
from .log_handler import LogCommandHandler
from .alert_handler import AlertCommandHandler
from .help_handler import HelpCommandHandler

__all__ = [
    # Base classes
    "CommandHandler",
    "CommandContext",
    "CommandResult",
    "CommandRegistry",
    "get_command_registry",
    "dispatch_command",
    # Handlers
    "ProfileCommandHandler",
    "SessionCommandHandler",
    "MetricsCommandHandler",
    "CacheCommandHandler",
    "ConfigCommandHandler",
    "LogCommandHandler",
    "AlertCommandHandler",
    "HelpCommandHandler",
]
