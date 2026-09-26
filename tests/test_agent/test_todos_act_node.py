"""act_node 级 todo 全量替换语义测试（P1-1）

红线：todos 是全量替换字段（不挂 add reducer）。本文件锁定
"act 节点返回的 todos 增量是完整清单"这一契约，配合 LangGraph
非 Annotated 字段的 last-value-wins 合并语义，构成替换闭环。
"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from mini_claude.agent.state import create_initial_state


FIRST_LIST = [
    {"content": "旧任务A", "status": "completed"},
    {"content": "旧任务B", "status": "in_progress"},
]
SECOND_LIST = [{"content": "新任务", "status": "in_progress", "active_form": "正在做新任务"}]


def _todo_write_calls(todos):
    return [{"id": "call_1", "name": "todo_write", "arguments": json.dumps({"todos": todos})}]


@pytest.mark.asyncio
async def test_act_node_returns_full_todos_increment():
    """act_node 的增量必须携带完整清单，而非 diff"""
    from mini_claude.agent.nodes import act as act_mod

    state = create_initial_state("做个多步任务")
    with patch.object(
        act_mod,
        "_call_llm_with_retry",
        new=AsyncMock(return_value=("", _todo_write_calls(FIRST_LIST))),
    ):
        result = await act_node_safe(act_mod, state)

    assert result["todos"] == FIRST_LIST
    # 工具结果要回流给 LLM（下一轮它才知道提交成功）
    assert any(m.content and "Todos updated" in m.content for m in result["messages"])


@pytest.mark.asyncio
async def test_act_node_second_write_is_full_replacement():
    """第二次提交返回的是新清单整体（非追加）"""
    from mini_claude.agent.nodes import act as act_mod

    state = create_initial_state("继续")
    state["todos"] = FIRST_LIST

    with patch.object(
        act_mod,
        "_call_llm_with_retry",
        new=AsyncMock(return_value=("", _todo_write_calls(SECOND_LIST))),
    ):
        result = await act_node_safe(act_mod, state)

    assert result["todos"] == SECOND_LIST
    assert result["todos"] != FIRST_LIST


@pytest.mark.asyncio
async def test_act_node_invalid_write_omits_todos_key():
    """校验失败：增量里根本没有 todos 键，state 旧值得以保留"""
    from mini_claude.agent.nodes import act as act_mod

    bad = [
        {"content": "a", "status": "in_progress"},
        {"content": "b", "status": "in_progress"},
    ]
    state = create_initial_state("继续")
    state["todos"] = FIRST_LIST

    with patch.object(
        act_mod, "_call_llm_with_retry", new=AsyncMock(return_value=("", _todo_write_calls(bad)))
    ):
        result = await act_node_safe(act_mod, state)

    assert "todos" not in result


async def act_node_safe(act_mod, state):
    """隔离 display 与 LLM 调用，跑真 act_node 逻辑"""
    with patch.object(act_mod, "get_rate_limiter") as mock_rl:
        mock_rl.return_value.check_limit.return_value = True
        return await act_mod.act_node(state)
