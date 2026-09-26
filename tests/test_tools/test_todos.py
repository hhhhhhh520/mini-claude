"""todo_write 工具与状态联动测试（P1-1）

覆盖：
1. validate_todos 校验规则（状态枚举、唯一 in_progress、去重、空清单=清空）
2. TodoWriteTool 工具本身（schema、成功/失败输出、注册进 registry）
3. act 执行链把校验通过的清单写进 state_extras（全量替换语义）
"""

import pytest
from unittest.mock import MagicMock

from mini_claude.tools.todos import TodoWriteTool, validate_todos


VALID_TWO = [
    {"content": "写实现", "status": "completed"},
    {"content": "补测试", "status": "in_progress", "active_form": "正在补测试"},
    {"content": "跑回归", "status": "pending"},
]


class TestValidateTodos:
    """validate_todos 校验规则"""

    def test_valid_list_no_errors(self):
        assert validate_todos(VALID_TWO) == []

    def test_empty_list_is_clear_operation(self):
        """空清单合法 = 清空所有 todo"""
        assert validate_todos([]) == []

    def test_invalid_status_rejected(self):
        errors = validate_todos([{"content": "x", "status": "done"}])
        assert errors and "status" in errors[0]

    def test_missing_status_rejected(self):
        errors = validate_todos([{"content": "x"}])
        assert errors and "status" in errors[0]

    def test_empty_content_rejected(self):
        errors = validate_todos([{"content": "", "status": "pending"}])
        assert errors and "content" in errors[0]

    def test_two_in_progress_rejected(self):
        errors = validate_todos(
            [
                {"content": "a", "status": "in_progress"},
                {"content": "b", "status": "in_progress"},
            ]
        )
        assert errors and "in_progress" in " ".join(errors)

    def test_zero_in_progress_rejected(self):
        errors = validate_todos(
            [
                {"content": "a", "status": "completed"},
                {"content": "b", "status": "pending"},
            ]
        )
        assert errors and "in_progress" in " ".join(errors)

    def test_duplicate_content_rejected(self):
        errors = validate_todos(
            [
                {"content": "同一条", "status": "completed"},
                {"content": "同一条", "status": "in_progress"},
            ]
        )
        assert errors and "重复" in " ".join(errors)

    def test_non_list_rejected(self):
        assert validate_todos("not a list")
        assert validate_todos(None)
        assert validate_todos({"todos": []})

    def test_item_not_dict_rejected(self):
        assert validate_todos(["write tests"])

    def test_error_messages_are_counted_not_raised(self):
        """多条违规一起报，不抛异常"""
        errors = validate_todos(
            [{"content": "", "status": "bad"}, {"content": "", "status": "bad"}]
        )
        assert len(errors) >= 2


class TestTodoWriteTool:
    """工具本身"""

    def test_registered_in_registry(self):
        from mini_claude.tools import list_tools

        assert "todo_write" in list_tools()

    def test_not_in_subagent_whitelist(self):
        """todo 属主会话状态，不进子代理白名单（计划红线）"""
        from mini_claude.tools.agent_spawn import SpawnAgentTool, SpawnParallelTool

        assert "todo_write" not in SpawnAgentTool.ALLOWED_TOOLS
        assert "todo_write" not in SpawnParallelTool.ALLOWED_TOOLS

    def test_schema_requires_todos_array(self):
        tool = TodoWriteTool()
        assert tool.parameters["type"] == "object"
        assert "todos" in tool.parameters["properties"]
        assert tool.parameters["required"] == ["todos"]

    @pytest.mark.asyncio
    async def test_execute_valid_returns_summary(self):
        result = await TodoWriteTool().execute(todos=VALID_TWO)
        assert "Error" not in result
        assert "1" in result  # 1 in_progress
        assert "补测试" in result

    @pytest.mark.asyncio
    async def test_execute_clear_returns_confirmation(self):
        result = await TodoWriteTool().execute(todos=[])
        assert "Error" not in result

    @pytest.mark.asyncio
    async def test_execute_invalid_returns_error_not_raise(self):
        result = await TodoWriteTool().execute(
            todos=[
                {"content": "a", "status": "in_progress"},
                {"content": "b", "status": "in_progress"},
            ]
        )
        assert result.startswith("Error")
        assert "in_progress" in result


class TestExecuteToolsTodosState:
    """act 执行链：校验通过的清单进 state_extras，全量替换"""

    @pytest.mark.asyncio
    async def _run(self, tool_calls):
        from mini_claude.agent.nodes.act import _execute_tools

        degr_manager = MagicMock()
        degr_manager.tool.should_skip.return_value = False
        metrics_collector = MagicMock()
        new_messages = []
        return await _execute_tools(tool_calls, degr_manager, metrics_collector, new_messages, None)

    @pytest.mark.asyncio
    async def test_valid_todo_write_yields_state_extras(self):
        import json

        calls = [{"name": "todo_write", "args": json.dumps({"todos": VALID_TWO})}]
        new_messages, early_return, step_success, state_extras = await self._run(calls)

        assert step_success is True
        assert state_extras.get("todos") == VALID_TWO
        assert any("todo" in (m.content or "").lower() for m in new_messages)

    @pytest.mark.asyncio
    async def test_invalid_todo_write_leaves_state_untouched(self):
        import json

        calls = [
            {
                "name": "todo_write",
                "args": json.dumps(
                    {
                        "todos": [
                            {"content": "a", "status": "in_progress"},
                            {"content": "b", "status": "in_progress"},
                        ]
                    }
                ),
            }
        ]
        new_messages, _, _, state_extras = await self._run(calls)

        assert "todos" not in state_extras
        joined = "\n".join(m.content for m in new_messages)
        assert "Error" in joined and "in_progress" in joined

    @pytest.mark.asyncio
    async def test_unrelated_tool_yields_no_todos_key(self):
        calls = [{"name": "list_dir", "args": {}}]
        _, _, _, state_extras = await self._run(calls)

        assert "todos" not in state_extras

    @pytest.mark.asyncio
    async def test_second_write_replaces_not_appends(self):
        """两次提交：extras 携带的是完整新清单（act 端按全量替换合并）"""
        import json

        first = [{"name": "todo_write", "args": json.dumps({"todos": VALID_TWO})}]
        _, _, _, extras1 = await self._run(first)

        second = [
            {
                "name": "todo_write",
                "args": json.dumps({"todos": [{"content": "新任务", "status": "in_progress"}]}),
            }
        ]
        _, _, _, extras2 = await self._run(second)

        assert extras1["todos"] == VALID_TWO
        assert extras2["todos"] == [{"content": "新任务", "status": "in_progress"}]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
