"""收敛批次④B/④C 测试：系统提示词加厚 + 记忆命令。

④B 锁定关键引导段必须出现在 get_system_prompt 产物中（行为引导的
存在性，非逐字）。
④C 覆盖 /memory 列表与 add、# 快速追加（append_project_memory）。
"""

from pathlib import Path

import pytest

from mini_claude.llm.prompts import ModelProvider, get_system_prompt


@pytest.fixture
def memory_workspace(tmp_path, monkeypatch):
    from mini_claude.config.settings import settings

    monkeypatch.setattr(settings, "workspace_root", str(tmp_path))
    return tmp_path


class TestSystemPromptGuidelines:
    def test_working_guidelines_present(self):
        prompt = get_system_prompt(ModelProvider.OPENAI)
        assert "Working Guidelines" in prompt

    def test_task_management_guidance(self):
        prompt = get_system_prompt(ModelProvider.OPENAI)
        assert "todo_write" in prompt and "task_create" in prompt
        assert "in_progress" in prompt

    def test_runtime_facts_documented(self):
        prompt = get_system_prompt(ModelProvider.OPENAI)
        assert "persists across calls" in prompt, "cwd 持久化必须告知模型"
        assert "export" in prompt and "exit_plan_mode" in prompt

    def test_code_discipline_present(self):
        prompt = get_system_prompt(ModelProvider.OPENAI)
        assert "no unrelated refactors" in prompt
        assert "never claim success" in prompt.lower()

    def test_date_placeholder_replaced(self):
        prompt = get_system_prompt(ModelProvider.OPENAI)
        assert "{DATE_PLACEHOLDER}" not in prompt


class TestMemoryCommand:
    def test_registered(self):
        from mini_claude.cli.commands.base import get_command_registry

        assert get_command_registry().get_handler("/memory") is not None

    @pytest.mark.asyncio
    async def test_add_appends_to_project_claude_md(self, memory_workspace):
        from types import SimpleNamespace

        from mini_claude.cli.commands.base import CommandContext
        from mini_claude.cli.commands.memory_handler import MemoryCommandHandler
        from mini_claude.cli.display import display

        ctx = CommandContext(
            session=SimpleNamespace(), command="/memory", args="add 优先用 pytest", display=display
        )
        result = await MemoryCommandHandler().handle(ctx)
        assert result.error is None
        md = memory_workspace / "CLAUDE.md"
        assert md.is_file()
        assert "优先用 pytest" in md.read_text(encoding="utf-8")

    @pytest.mark.asyncio
    async def test_add_empty_rejected(self, memory_workspace):
        from types import SimpleNamespace

        from mini_claude.cli.commands.base import CommandContext
        from mini_claude.cli.commands.memory_handler import MemoryCommandHandler
        from mini_claude.cli.display import display

        ctx = CommandContext(
            session=SimpleNamespace(), command="/memory", args="add   ", display=display
        )
        result = await MemoryCommandHandler().handle(ctx)
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_list_shows_files(self, memory_workspace):
        from types import SimpleNamespace

        from mini_claude.cli.commands.base import CommandContext
        from mini_claude.cli.commands.memory_handler import MemoryCommandHandler
        from mini_claude.cli.display import display

        (memory_workspace / "CLAUDE.md").write_text("# CLAUDE.md\n- 规则一\n", encoding="utf-8")
        ctx = CommandContext(session=SimpleNamespace(), command="/memory", args="", display=display)
        result = await MemoryCommandHandler().handle(ctx)
        assert result.error is None
        assert "项目级" in result.message and "规则一" not in result.message
        assert str(memory_workspace / "CLAUDE.md") in result.message


class TestQuickAppend:
    def test_append_creates_with_header(self, memory_workspace):
        from mini_claude.utils.claudemd import append_project_memory

        path = append_project_memory("新约定", workspace_root=str(memory_workspace))
        content = Path(path).read_text(encoding="utf-8")
        assert "新约定" in content and "CLAUDE.md" in content

    def test_append_empty_raises(self, memory_workspace):
        from mini_claude.utils.claudemd import append_project_memory

        with pytest.raises(ValueError):
            append_project_memory("   ", workspace_root=str(memory_workspace))
