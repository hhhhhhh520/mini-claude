"""act 链级 Task 工具测试：state 进出 + 子代理白名单。

架构契约（对齐 todo_write 先例）：
- act 每轮派发前把 state.tasks 传给 execute_single_tool；任务变更经
  state_extras["tasks"] 全量替换回 state（不早退，同轮多工具继续）
- 校验失败：增量里没有 tasks 键，state 旧值保留，错误以 ToolMessage 回流
- 子代理白名单含 task_list/task_get/task_update（委派闭环），不含 task_create
"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from mini_claude.agent.state import create_initial_state, create_turn_increment


def _call(name, args):
    return [{"id": "call_1", "name": name, "arguments": json.dumps(args)}]


@pytest.mark.asyncio
async def test_act_node_task_create_persists_full_list():
    from mini_claude.agent.nodes import act as act_mod

    state = create_initial_state("建个任务")
    with patch.object(
        act_mod,
        "_call_llm_with_retry",
        new=AsyncMock(
            return_value=("", _call("task_create", {"subject": "写模块", "description": "实现"}))
        ),
    ):
        result = await act_mod.act_node(state)

    tasks = result["tasks"]
    assert len(tasks) == 1 and tasks[0]["subject"] == "写模块" and tasks[0]["status"] == "pending"
    # 工具结果回流给 LLM（含任务编号，后续 update 靠它引用）
    tool_msg = [m for m in result["messages"] if m.type == "tool"]
    assert tool_msg and "#1" in tool_msg[0].content and tool_msg[0].status == "success"


@pytest.mark.asyncio
async def test_act_node_task_update_replaces_state():
    from mini_claude.agent.nodes import act as act_mod

    state = create_initial_state("推进任务")
    state["tasks"] = [
        {
            "id": "1",
            "subject": "写模块",
            "description": "d",
            "status": "pending",
            "blocks": [],
            "blocked_by": [],
        }
    ]
    with patch.object(
        act_mod,
        "_call_llm_with_retry",
        new=AsyncMock(
            return_value=("", _call("task_update", {"task_id": "1", "status": "completed"}))
        ),
    ):
        result = await act_mod.act_node(state)

    assert result["tasks"][0]["status"] == "completed"
    assert len(result["tasks"]) == 1


@pytest.mark.asyncio
async def test_act_node_invalid_update_omits_tasks_key():
    """未知 task_id：增量里没有 tasks 键，state 旧值保留，错误回流。"""
    from mini_claude.agent.nodes import act as act_mod

    state = create_initial_state("推进任务")
    old = [
        {
            "id": "1",
            "subject": "写模块",
            "description": "d",
            "status": "pending",
            "blocks": [],
            "blocked_by": [],
        }
    ]
    state["tasks"] = old
    with patch.object(
        act_mod,
        "_call_llm_with_retry",
        new=AsyncMock(
            return_value=("", _call("task_update", {"task_id": "99", "status": "completed"}))
        ),
    ):
        result = await act_mod.act_node(state)

    assert "tasks" not in result
    tool_msg = [m for m in result["messages"] if m.type == "tool"]
    assert tool_msg and tool_msg[0].status == "error" and "99" in tool_msg[0].content


@pytest.mark.asyncio
async def test_two_creates_in_same_round_both_persist():
    """同轮多次任务操作：第二轮 create 必须看到第一轮的变更（轮内同步）。"""
    from mini_claude.agent.nodes import act as act_mod

    state = create_initial_state("建两个任务")
    calls = [
        {
            "id": "c1",
            "name": "task_create",
            "arguments": json.dumps({"subject": "甲", "description": "d"}),
        },
        {
            "id": "c2",
            "name": "task_create",
            "arguments": json.dumps({"subject": "乙", "description": "d"}),
        },
    ]
    with patch.object(act_mod, "_call_llm_with_retry", new=AsyncMock(return_value=("", calls))):
        result = await act_mod.act_node(state)

    assert [t["subject"] for t in result["tasks"]] == ["甲", "乙"]
    assert len(result["messages"]) == 3  # ai + 2 tool


@pytest.mark.asyncio
async def test_create_turn_increment_omits_tasks():
    """tasks 跨回合保留（不进 turn increment），与 todos 同纪律。"""
    increment = create_turn_increment("下一轮")
    assert "tasks" not in increment


def test_initial_state_has_empty_tasks():
    assert create_initial_state("x")["tasks"] == []


def test_subagent_whitelist_covers_task_tools():
    from mini_claude.tools.agent_spawn import SUBAGENT_ALLOWED_TOOLS

    for t in ("task_list", "task_get", "task_update"):
        assert t in SUBAGENT_ALLOWED_TOOLS, f"子代理委派闭环需要 {t}"


def test_task_tools_registered():
    from mini_claude.tools import get_all_tools

    names = {t["name"] for t in get_all_tools()}
    assert {"task_create", "task_update", "task_list", "task_get"} <= names
