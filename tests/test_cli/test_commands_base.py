"""Tests for command handler base classes."""

import pytest

from mini_claude.cli.commands.base import (
    CommandHandler,
    CommandContext,
    CommandResult,
    CommandRegistry,
)


class MockHandler(CommandHandler):
    """Mock handler for testing."""

    commands = ["/test", "/t"]

    async def handle(self, ctx: CommandContext) -> CommandResult:
        """Handle test command."""
        if ctx.args == "error":
            return CommandResult(handled=True, error="Test error")
        if ctx.args == "exit":
            return CommandResult(handled=True, exit_repl=True)
        return CommandResult(handled=True, message=f"Test: {ctx.args}")


class TestCommandResult:
    """Tests for CommandResult."""

    def test_default_values(self):
        """Test default values."""
        result = CommandResult()
        assert result.handled is True
        assert result.message is None
        assert result.error is None
        assert result.exit_repl is False

    def test_custom_values(self):
        """Test custom values."""
        result = CommandResult(
            handled=False,
            message="test",
            error="err",
            exit_repl=True,
        )
        assert result.handled is False
        assert result.message == "test"
        assert result.error == "err"
        assert result.exit_repl is True


class TestCommandHandler:
    """Tests for CommandHandler."""

    def test_can_handle(self):
        """Test can_handle method."""
        handler = MockHandler()
        assert handler.can_handle("/test") is True
        assert handler.can_handle("/t") is True
        assert handler.can_handle("/other") is False

    def test_get_help_text(self):
        """Test get_help_text returns empty by default."""
        handler = MockHandler()
        assert handler.get_help_text() == ""

    @pytest.mark.asyncio
    async def test_handle_returns_result(self):
        """Test handle returns CommandResult."""
        handler = MockHandler()
        ctx = CommandContext(
            session=None,
            command="/test",
            args="hello",
            display=None,
        )
        result = await handler.handle(ctx)
        assert isinstance(result, CommandResult)
        assert result.message == "Test: hello"


class TestCommandRegistry:
    """Tests for CommandRegistry."""

    def test_register_handler(self):
        """Test registering a handler."""
        registry = CommandRegistry()
        handler = MockHandler()
        registry.register(handler)

        assert registry.get_handler("/test") is handler
        assert registry.get_handler("/t") is handler
        assert registry.get_handler("/other") is None

    def test_get_all_handlers(self):
        """Test getting all handlers."""
        registry = CommandRegistry()
        handler = MockHandler()
        registry.register(handler)

        handlers = registry.get_all_handlers()
        assert len(handlers) == 1
        assert handlers[0] is handler

    def test_get_all_commands(self):
        """Test getting all commands."""
        registry = CommandRegistry()
        handler = MockHandler()
        registry.register(handler)

        commands = registry.get_all_commands()
        assert "/test" in commands
        assert "/t" in commands
