"""图级线格式测试（ISSUE-026）：捕获第二轮 LLM 调用实际收到的消息序列。

这是能抓到「多轮工具链泄漏」的那类测试：fake provider 记录每次调用收到的
messages，断言第二轮起线上格式完整——assistant 消息携带 tool_calls、工具结果
以 role=tool + tool_call_id 紧随其后。旧实现（结果以 role=user 文本回传、
assistant 剥掉 tool_calls）在本测试下必红。
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mini_claude.agent.nodes.act import act_node
from mini_claude.agent.nodes import _shared
from mini_claude.agent.state import create_initial_state


def _fake_llm_response(content: str, tool_calls):
    return {"content": content, "tool_calls": tool_calls}


@pytest.fixture
def _isolated_llm(monkeypatch):
    from mini_claude.config.settings import settings
    from mini_claude.utils.safety import get_rate_limiter

    monkeypatch.setattr(get_rate_limiter(), "check_limit", lambda *a, **k: True)

    degr = MagicMock()
    degr.model.get_current_model.return_value = settings.default_model
    degr.backoff = SimpleNamespace(max_retries=0, reset=lambda: None, wait=AsyncMock())
    degr.tool.should_skip.return_value = False
    degr.tool.get_replacement.return_value = None
    import mini_claude.agent.nodes.act as act_mod

    monkeypatch.setattr(act_mod, "get_degradation_manager", lambda: degr)


@pytest.mark.asyncio
async def test_second_round_sees_role_tool_and_assistant_tool_calls(_isolated_llm):
    """第二轮 LLM 调用必须收到：assistant(tool_calls) → role=tool(tool_call_id)

    act_node 一次调用只发一次 LLM 请求；图的多轮 = observe→think→act 再入。
    这里连续两次调用 act_node 并前传 state，等价复现图内第二轮。
    """
    captured = []

    async def fake_stream(messages=None, tools=None, **kwargs):
        captured.append(list(messages or []))
        if len(captured) == 1:
            return _fake_llm_response(
                "",
                [
                    {
                        "id": "call_1",
                        "name": "read_file",
                        "arguments": json.dumps({"path": "notes/a.txt"}),
                    }
                ],
            )
        return _fake_llm_response("读取完成", None)

    with (
        patch.object(_shared.llm_provider, "chat_stream_with_tools", side_effect=fake_stream),
        patch.object(_shared.llm_provider, "chat", side_effect=fake_stream),
        patch(
            "mini_claude.tools.execute_tool",
            AsyncMock(return_value="alpha"),
        ) as fake_exec,
    ):
        state = create_initial_state("读取 notes/a.txt 的内容")
        first = await act_node(state)
        second = await act_node({**state, **first})

    assert fake_exec.await_count == 1, "第一轮应执行一次工具"
    assert len(captured) >= 2, "第二轮 act_node 应再发一次 LLM 调用"

    second_round = captured[1]
    assistant_idx = None
    for i, m in enumerate(second_round):
        if m.get("role") == "assistant" and m.get("tool_calls"):
            assistant_idx = i
            assert m["tool_calls"][0]["id"] == "call_1"
            assert m["tool_calls"][0]["function"]["name"] == "read_file"
            break
    assert assistant_idx is not None, "assistant 历史消息不得剥掉 tool_calls"

    tool_msgs = [
        m for m in second_round if m.get("role") == "tool" and m.get("tool_call_id") == "call_1"
    ]
    assert tool_msgs, "工具结果必须以 role=tool + tool_call_id 回传（而非 role=user 文本）"
    assert tool_msgs[0]["content"] == "alpha"
    assert second_round.index(tool_msgs[0]) > assistant_idx, "role=tool 必须紧跟对应 assistant 之后"

    # 第二轮的产出应包含最终回答
    assert second["messages"][-1].content == "读取完成"


@pytest.mark.asyncio
async def test_tool_result_not_sent_as_user_text(_isolated_llm):
    """回归锚点：工具结果不得再以 role=user 文本（"Tool xxx result: ..."）回传"""
    captured = []

    async def fake_stream(messages=None, tools=None, **kwargs):
        captured.append(list(messages or []))
        if len(captured) == 1:
            return _fake_llm_response(
                "",
                [
                    {
                        "id": "call_2",
                        "name": "list_dir",
                        "arguments": json.dumps({"path": "."}),
                    }
                ],
            )
        return _fake_llm_response("完成", None)

    with (
        patch.object(_shared.llm_provider, "chat_stream_with_tools", side_effect=fake_stream),
        patch.object(_shared.llm_provider, "chat", side_effect=fake_stream),
        patch("mini_claude.tools.execute_tool", AsyncMock(return_value="a.txt")),
    ):
        state = create_initial_state("列出目录")
        first = await act_node(state)
        await act_node({**state, **first})

    assert len(captured) >= 2, "第二轮 act_node 应再发一次 LLM 调用"
    user_tool_texts = [
        m
        for m in captured[1]
        if m.get("role") == "user" and str(m.get("content", "")).startswith("Tool ")
    ]
    assert not user_tool_texts, "工具结果不得以 role=user 文本回传（ISSUE-026 根因）"
