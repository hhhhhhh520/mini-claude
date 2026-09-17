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


class TestCheckPreviousSessionScoped:
    """P1-8：恢复提示只看当前 thread，别人的残留不打扰."""

    @pytest.mark.asyncio
    async def test_other_thread_does_not_trigger(self, tmp_path):
        import aiosqlite

        from mini_claude.cli.repl import REPLSession

        db = tmp_path / "s.db"
        async with aiosqlite.connect(db) as conn:
            await conn.execute(
                "CREATE TABLE checkpoints (thread_id TEXT, checkpoint_ns TEXT, "
                "checkpoint_id TEXT, parent_checkpoint_id TEXT, type TEXT, "
                "checkpoint BLOB, metadata BLOB)"
            )
            await conn.execute(
                "INSERT INTO checkpoints (thread_id) VALUES ('someone-else')"
            )
            await conn.commit()

        session = REPLSession()
        session.thread_id = "mine"
        with patch(
            "mini_claude.config.settings.settings.session_db_path", str(db)
        ):
            assert await session._check_previous_session() is False

    @pytest.mark.asyncio
    async def test_own_thread_triggers(self, tmp_path):
        import aiosqlite

        from mini_claude.cli.repl import REPLSession

        db = tmp_path / "s.db"
        async with aiosqlite.connect(db) as conn:
            await conn.execute(
                "CREATE TABLE checkpoints (thread_id TEXT, checkpoint_ns TEXT, "
                "checkpoint_id TEXT, parent_checkpoint_id TEXT, type TEXT, "
                "checkpoint BLOB, metadata BLOB)"
            )
            await conn.execute("INSERT INTO checkpoints (thread_id) VALUES ('mine')")
            await conn.commit()

        session = REPLSession()
        session.thread_id = "mine"
        with patch(
            "mini_claude.config.settings.settings.session_db_path", str(db)
        ):
            assert await session._check_previous_session() is True
