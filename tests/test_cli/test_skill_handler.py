"""Tests for SkillCommandHandler."""

import pytest
from unittest.mock import MagicMock

from mini_claude.cli.commands.skill_handler import SkillCommandHandler
from mini_claude.cli.commands.base import CommandContext
from mini_claude.skills.models import Skill
from mini_claude.skills.registry import SkillRegistry
from pathlib import Path


@pytest.fixture
def handler():
    return SkillCommandHandler()


@pytest.fixture
def mock_ctx():
    """Create a mock CommandContext."""
    session = MagicMock()
    session._active_skill = None
    session._active_skill_args = ""
    display = MagicMock()
    display.console = MagicMock()
    ctx = CommandContext(
        session=session,
        command="/skills",
        args="",
        display=display,
    )
    return ctx


@pytest.fixture
def registry_with_skills(monkeypatch):
    """Create a registry with test skills."""
    registry = SkillRegistry()
    skills = [
        Skill(
            name="hello",
            description="Say hello to the user",
            body="# Hello\nGreet the user warmly",
            source_path=Path("/test/hello/SKILL.md"),
        ),
        Skill(
            name="review",
            description="Review code for issues",
            body="# Review\nCheck code quality",
            source_path=Path("/test/review/SKILL.md"),
        ),
    ]
    registry._skills = {s.name: s for s in skills}
    registry._loaded = True

    monkeypatch.setattr(
        "mini_claude.skills.registry.get_skill_registry",
        lambda: registry,
    )
    return registry


class TestSkillCommandHandler:
    """Test handler methods."""

    def test_commands_list(self, handler):
        assert "/skills" in handler.commands
        assert "/skill" in handler.commands

    @pytest.mark.asyncio
    async def test_list_skills(self, handler, mock_ctx, registry_with_skills):
        mock_ctx.command = "/skills"
        result = await handler.handle(mock_ctx)
        assert result.handled is True
        # Should have printed a table
        mock_ctx.display.console.print.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_skills_empty(self, handler, mock_ctx, monkeypatch):
        registry = SkillRegistry()
        registry._loaded = True
        monkeypatch.setattr(
            "mini_claude.skills.registry.get_skill_registry",
            lambda: registry,
        )
        mock_ctx.command = "/skills"
        result = await handler.handle(mock_ctx)
        assert result.handled is True
        assert "No skills" in result.message

    @pytest.mark.asyncio
    async def test_invoke_skill(self, handler, mock_ctx, registry_with_skills):
        mock_ctx.command = "/skill"
        mock_ctx.args = "hello world"
        result = await handler.handle(mock_ctx)
        assert result.handled is True
        assert mock_ctx.session._active_skill is not None
        assert mock_ctx.session._active_skill.name == "hello"
        assert mock_ctx.session._active_skill_args == "world"

    @pytest.mark.asyncio
    async def test_invoke_skill_no_args(self, handler, mock_ctx, registry_with_skills):
        mock_ctx.command = "/skill"
        mock_ctx.args = "hello"
        result = await handler.handle(mock_ctx)
        assert result.handled is True
        assert mock_ctx.session._active_skill.name == "hello"
        assert mock_ctx.session._active_skill_args == ""

    @pytest.mark.asyncio
    async def test_invoke_skill_not_found(self, handler, mock_ctx, registry_with_skills):
        mock_ctx.command = "/skill"
        mock_ctx.args = "nonexistent"
        result = await handler.handle(mock_ctx)
        assert result.handled is True
        assert result.error is not None
        assert "nonexistent" in result.error

    @pytest.mark.asyncio
    async def test_invoke_no_name(self, handler, mock_ctx, registry_with_skills):
        mock_ctx.command = "/skill"
        mock_ctx.args = ""
        result = await handler.handle(mock_ctx)
        assert result.handled is True
        assert "Usage" in result.message

    def test_help_text(self, handler):
        text = handler.get_help_text()
        assert "/skills" in text
        assert "/skill" in text
