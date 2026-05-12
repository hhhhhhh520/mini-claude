"""Tests for session command handler."""

import pytest
from unittest.mock import MagicMock, patch

from mini_claude.cli.commands.session_handler import SessionCommandHandler
from mini_claude.cli.commands.base import CommandContext


class TestSessionCommandHandler:
    """Tests for SessionCommandHandler."""

    def setup_method(self):
        """Set up test fixtures."""
        self.handler = SessionCommandHandler()

    def test_commands_list(self):
        """Test command list."""
        assert "/save" in self.handler.commands
        assert "/load" in self.handler.commands
        assert "/resume" in self.handler.commands
        assert "/sessions" in self.handler.commands
        assert "/interrupted" in self.handler.commands
        assert "/reset" in self.handler.commands
        assert "/thread" in self.handler.commands

    @pytest.mark.asyncio
    async def test_reset_session(self):
        """Test resetting session."""
        session = MagicMock()
        session.messages = [{"role": "user", "content": "test"}]

        display = MagicMock()
        display.console = MagicMock()

        ctx = CommandContext(
            session=session,
            command="/reset",
            args="",
            display=display,
        )

        result = await self.handler.handle(ctx)
        assert result.handled is True
        assert session.messages == []

    @pytest.mark.asyncio
    async def test_switch_thread(self):
        """Test switching thread."""
        session = MagicMock()
        session.thread_id = "default"
        session.messages = [{"role": "user", "content": "test"}]

        display = MagicMock()
        display.console = MagicMock()

        ctx = CommandContext(
            session=session,
            command="/thread",
            args="new-thread",
            display=display,
        )

        result = await self.handler.handle(ctx)
        assert result.handled is True
        assert session.thread_id == "new-thread"

    @pytest.mark.asyncio
    async def test_load_missing_session(self):
        """Test loading missing session."""
        session = MagicMock()

        display = MagicMock()
        display.console = MagicMock()

        ctx = CommandContext(
            session=session,
            command="/load",
            args="missing-id",
            display=display,
        )

        with patch(
            "mini_claude.cli.commands.session_handler.get_session_manager"
        ) as mock_get_manager:
            mock_manager = MagicMock()
            mock_manager.load_session.return_value = (None, None)
            mock_get_manager.return_value = mock_manager

            result = await self.handler.handle(ctx)
            assert result.handled is True
            assert "not found" in result.message

    @pytest.mark.asyncio
    async def test_load_missing_arg(self):
        """Test /load without argument shows error."""
        session = MagicMock()

        display = MagicMock()
        display.console = MagicMock()

        ctx = CommandContext(
            session=session,
            command="/load",
            args="",
            display=display,
        )

        result = await self.handler.handle(ctx)
        assert result.handled is True
        assert "Usage" in result.message

    @pytest.mark.asyncio
    async def test_thread_missing_arg(self):
        """Test /thread without argument shows error."""
        session = MagicMock()

        display = MagicMock()
        display.console = MagicMock()

        ctx = CommandContext(
            session=session,
            command="/thread",
            args="",
            display=display,
        )

        result = await self.handler.handle(ctx)
        assert result.handled is True
        assert "Usage" in result.message

    @pytest.mark.asyncio
    async def test_resume_missing_arg(self):
        """Test /resume without argument shows error."""
        session = MagicMock()

        display = MagicMock()
        display.console = MagicMock()

        ctx = CommandContext(
            session=session,
            command="/resume",
            args="",
            display=display,
        )

        result = await self.handler.handle(ctx)
        assert result.handled is True
        assert "Usage" in result.message
