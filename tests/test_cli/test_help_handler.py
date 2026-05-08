"""Tests for help command handler."""

import pytest
from unittest.mock import MagicMock

from mini_claude.cli.commands.help_handler import HelpCommandHandler
from mini_claude.cli.commands.base import CommandContext, CommandResult


class TestHelpCommandHandler:
    """Tests for HelpCommandHandler."""

    def setup_method(self):
        """Set up test fixtures."""
        self.handler = HelpCommandHandler()

    def test_commands_list(self):
        """Test command list."""
        assert "/help" in self.handler.commands
        assert "/?" in self.handler.commands
        assert "/exit" in self.handler.commands
        assert "/quit" in self.handler.commands
        assert "/q" in self.handler.commands
        assert "/clear" in self.handler.commands
        assert "/model" in self.handler.commands

    @pytest.mark.asyncio
    async def test_exit_command(self):
        """Test exit command."""
        session = MagicMock()
        session.running = True

        display = MagicMock()
        display.console = MagicMock()

        ctx = CommandContext(
            session=session,
            command="/exit",
            args="",
            display=display,
        )

        result = await self.handler.handle(ctx)
        assert result.handled is True
        assert result.exit_repl is True

    @pytest.mark.asyncio
    async def test_quit_command(self):
        """Test quit command."""
        session = MagicMock()

        display = MagicMock()
        display.console = MagicMock()

        ctx = CommandContext(
            session=session,
            command="/quit",
            args="",
            display=display,
        )

        result = await self.handler.handle(ctx)
        assert result.handled is True
        assert result.exit_repl is True

    @pytest.mark.asyncio
    async def test_q_command(self):
        """Test q command."""
        session = MagicMock()

        display = MagicMock()
        display.console = MagicMock()

        ctx = CommandContext(
            session=session,
            command="/q",
            args="",
            display=display,
        )

        result = await self.handler.handle(ctx)
        assert result.handled is True
        assert result.exit_repl is True

    @pytest.mark.asyncio
    async def test_help_command(self):
        """Test help command."""
        session = MagicMock()

        display = MagicMock()
        display.console = MagicMock()

        ctx = CommandContext(
            session=session,
            command="/help",
            args="",
            display=display,
        )

        result = await self.handler.handle(ctx)
        assert result.handled is True
        assert result.exit_repl is False
        display.console.print.assert_called()

    @pytest.mark.asyncio
    async def test_clear_command(self):
        """Test clear command."""
        session = MagicMock()

        display = MagicMock()
        display.console = MagicMock()

        ctx = CommandContext(
            session=session,
            command="/clear",
            args="",
            display=display,
        )

        result = await self.handler.handle(ctx)
        assert result.handled is True
        display.console.clear.assert_called_once()

    @pytest.mark.asyncio
    async def test_model_command(self):
        """Test model command."""
        session = MagicMock()

        display = MagicMock()
        display.console = MagicMock()

        ctx = CommandContext(
            session=session,
            command="/model",
            args="gpt-4",
            display=display,
        )

        result = await self.handler.handle(ctx)
        assert result.handled is True
        assert "gpt-4" in result.message

    @pytest.mark.asyncio
    async def test_model_command_no_arg(self):
        """Test model command without argument."""
        session = MagicMock()

        display = MagicMock()
        display.console = MagicMock()

        ctx = CommandContext(
            session=session,
            command="/model",
            args="",
            display=display,
        )

        result = await self.handler.handle(ctx)
        assert result.handled is True
        assert "Usage" in result.message

    def test_get_help_text(self):
        """Test get_help_text returns content."""
        help_text = self.handler.get_help_text()
        assert "/help" in help_text
        assert "/exit" in help_text
