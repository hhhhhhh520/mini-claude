"""Command handler base classes and registry for REPL commands.

This module implements the Command Pattern for handling REPL slash commands.
Each command is encapsulated in a handler class that can be independently tested
and easily extended.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..repl import REPLSession


@dataclass
class CommandContext:
    """Context passed to command handlers.

    Contains all the state and utilities a command handler might need.
    """

    session: "REPLSession"
    command: str
    args: str
    display: Any  # Display module

    # Convenience properties from session
    @property
    def messages(self) -> List[Dict[str, Any]]:
        """Get session messages."""
        return self.session.messages

    @messages.setter
    def messages(self, value: List[Dict[str, Any]]) -> None:
        """Set session messages."""
        self.session.messages = value

    @property
    def thread_id(self) -> str:
        """Get thread ID."""
        return self.session.thread_id

    @thread_id.setter
    def thread_id(self, value: str) -> None:
        """Set thread ID."""
        self.session.thread_id = value

    @property
    def running(self) -> bool:
        """Check if session is running."""
        return self.session.running

    @running.setter
    def running(self, value: bool) -> None:
        """Set running state."""
        self.session.running = value


@dataclass
class CommandResult:
    """Result of command execution.

    Attributes:
        handled: Whether the command was handled (True stops further processing)
        message: Optional message to display
        error: Optional error message
        exit_repl: Whether to exit the REPL
    """

    handled: bool = True
    message: Optional[str] = None
    error: Optional[str] = None
    exit_repl: bool = False


class CommandHandler(ABC):
    """Abstract base class for command handlers.

    Each handler is responsible for one or more related commands.
    Implementations should be stateless where possible.
    """

    # Commands this handler can process (e.g., ["/help", "/?"])
    commands: List[str] = []

    @abstractmethod
    async def handle(self, ctx: CommandContext) -> CommandResult:
        """Handle the command.

        Args:
            ctx: Command context with session state and utilities

        Returns:
            CommandResult indicating what happened
        """
        pass

    def can_handle(self, command: str) -> bool:
        """Check if this handler can process the command.

        Args:
            command: The command string (lowercased, e.g., "/help")

        Returns:
            True if this handler can process the command
        """
        return command in self.commands

    def get_help_text(self) -> str:
        """Get help text for this handler's commands.

        Returns:
            Multi-line help text describing the commands
        """
        return ""


class CommandRegistry:
    """Registry for command handlers.

    Manages registration and dispatch of commands to appropriate handlers.
    """

    def __init__(self):
        self._handlers: List[CommandHandler] = []
        self._command_map: Dict[str, CommandHandler] = {}

    def register(self, handler: CommandHandler) -> None:
        """Register a command handler.

        Args:
            handler: The handler to register
        """
        self._handlers.append(handler)
        for cmd in handler.commands:
            self._command_map[cmd] = handler

    def get_handler(self, command: str) -> Optional[CommandHandler]:
        """Get the handler for a command.

        Args:
            command: The command to look up

        Returns:
            The handler if found, None otherwise
        """
        return self._command_map.get(command)

    def get_all_handlers(self) -> List[CommandHandler]:
        """Get all registered handlers."""
        return self._handlers.copy()

    def get_all_commands(self) -> List[str]:
        """Get all registered commands."""
        return list(self._command_map.keys())


# Global registry instance
_registry: Optional[CommandRegistry] = None


def get_command_registry() -> CommandRegistry:
    """Get or create the global command registry."""
    global _registry
    if _registry is None:
        _registry = CommandRegistry()
        # Import and register all handlers
        from . import profile_handler, session_handler, metrics_handler
        from . import cache_handler, config_handler, log_handler
        from . import alert_handler, help_handler, skill_handler

        for handler_class in [
            profile_handler.ProfileCommandHandler,
            session_handler.SessionCommandHandler,
            metrics_handler.MetricsCommandHandler,
            cache_handler.CacheCommandHandler,
            config_handler.ConfigCommandHandler,
            log_handler.LogCommandHandler,
            alert_handler.AlertCommandHandler,
            help_handler.HelpCommandHandler,
            skill_handler.SkillCommandHandler,
        ]:
            _registry.register(handler_class())

    return _registry


async def dispatch_command(
    session: "REPLSession",
    command: str,
    display: Any,
) -> bool:
    """Dispatch a command to the appropriate handler.

    Args:
        session: The REPL session
        command: The full command string (e.g., "/help")
        display: The display module for output

    Returns:
        True if command was handled, False otherwise
    """
    from .base import CommandContext

    registry = get_command_registry()
    cmd_lower = command.lower()

    # Extract command and args
    parts = command.split(None, 1)
    cmd_part = parts[0].lower() if parts else cmd_lower
    args = parts[1] if len(parts) > 1 else ""

    # Get handler
    handler = registry.get_handler(cmd_part)
    if handler is None:
        return False

    # Create context and execute
    ctx = CommandContext(
        session=session,
        command=cmd_part,
        args=args,
        display=display,
    )

    result = await handler.handle(ctx)

    # Handle result
    if result.error:
        display.console.print(f"[red]{result.error}[/]")
    elif result.message:
        display.console.print(result.message)

    if result.exit_repl:
        session.running = False

    return result.handled
