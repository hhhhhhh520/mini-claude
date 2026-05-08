"""Tests for profile command handler."""

import pytest
from unittest.mock import MagicMock, patch

from mini_claude.cli.commands.profile_handler import ProfileCommandHandler
from mini_claude.cli.commands.base import CommandContext, CommandResult
from mini_claude.utils.profile import UserProfile


class TestProfileCommandHandler:
    """Tests for ProfileCommandHandler."""

    def setup_method(self):
        """Set up test fixtures."""
        self.handler = ProfileCommandHandler()

    def test_commands_list(self):
        """Test command list."""
        assert "/profile" in self.handler.commands

    @pytest.mark.asyncio
    async def test_view_profile(self):
        """Test viewing profile."""
        profile = UserProfile(
            preferred_model="test-model",
            preferred_language="en-US",
            recent_projects=["/path/1"],
            common_workflows=["workflow1"],
            custom_prompts={"prompt1": "content1"},
        )

        session = MagicMock()
        session._profile = profile
        session._load_profile = MagicMock()

        display = MagicMock()
        display.console = MagicMock()

        ctx = CommandContext(
            session=session,
            command="/profile",
            args="",
            display=display,
        )

        result = await self.handler.handle(ctx)
        assert result.handled is True
        assert result.error is None

    @pytest.mark.asyncio
    async def test_set_model(self):
        """Test setting model."""
        profile = UserProfile()

        session = MagicMock()
        session._profile = profile
        session._save_profile = MagicMock(return_value=True)

        display = MagicMock()
        display.console = MagicMock()

        ctx = CommandContext(
            session=session,
            command="/profile",
            args="model gpt-4",
            display=display,
        )

        result = await self.handler.handle(ctx)
        assert result.handled is True
        assert profile.preferred_model == "gpt-4"

    @pytest.mark.asyncio
    async def test_set_language(self):
        """Test setting language."""
        profile = UserProfile()

        session = MagicMock()
        session._profile = profile
        session._save_profile = MagicMock(return_value=True)

        display = MagicMock()
        display.console = MagicMock()

        ctx = CommandContext(
            session=session,
            command="/profile",
            args="language zh-CN",
            display=display,
        )

        result = await self.handler.handle(ctx)
        assert result.handled is True
        assert profile.preferred_language == "zh-CN"

    @pytest.mark.asyncio
    async def test_clear_profile(self):
        """Test clearing profile."""
        profile = UserProfile(
            preferred_model="custom-model",
            recent_projects=["/path"],
        )

        manager = MagicMock()
        manager.clear_profile = MagicMock()
        manager.load_profile = MagicMock(return_value=UserProfile())

        session = MagicMock()
        session._profile = profile
        session._get_profile_manager = MagicMock(return_value=manager)

        display = MagicMock()
        display.console = MagicMock()

        ctx = CommandContext(
            session=session,
            command="/profile",
            args="clear",
            display=display,
        )

        result = await self.handler.handle(ctx)
        assert result.handled is True
        manager.clear_profile.assert_called_once()

    @pytest.mark.asyncio
    async def test_invalid_usage(self):
        """Test invalid usage shows help."""
        session = MagicMock()
        session._profile = UserProfile()

        display = MagicMock()
        display.console = MagicMock()

        ctx = CommandContext(
            session=session,
            command="/profile",
            args="invalid-arg",
            display=display,
        )

        result = await self.handler.handle(ctx)
        assert result.handled is True
        assert "Usage" in result.message
