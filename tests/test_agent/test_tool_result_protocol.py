"""工具结果协议测试（ISSUE-026）。

对齐 OpenAI 函数调用协议的线格式（wire format）：
- 工具结果必须以 role=tool（LangChain ``ToolMessage``）携带 ``tool_call_id`` 回传，
  不得再以 ``HumanMessage``（线上 role=user）文本回传；
- assistant 历史消息必须携带 ``tool_calls``，不得剥掉。

违反协议的后果（2026-09-28 真 key 实测）：Qwen 类网关按消息形状判定函数调用模式，
形状偏离后从第二轮起丢失 function calling 状态，退化为原生 ``<tool_call>`` XML
文本输出，工具实际不再执行（详见 issues/ISSUE-026）。
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from mini_claude.agent.nodes._act_helpers import (
    convert_message,
    execute_single_tool,
    parse_tool_calls,
)
from mini_claude.agent.nodes._shared import PathConfirmationRequired


def _stub_deps():
    degr = MagicMock()
    degr.tool.should_skip.return_value = False
    degr.tool.get_replacement.return_value = None
    metrics = MagicMock()
    return degr, metrics


class TestConvertMessageWireFormat:
    """convert_message：LangChain 消息 → LiteLLM 线上 dict"""

    def test_tool_message_maps_to_role_tool(self):
        msg = ToolMessage(content="ok", name="read_file", tool_call_id="call_1")
        d = convert_message(msg)
        assert d["role"] == "tool"
        assert d["tool_call_id"] == "call_1"
        assert d["content"] == "ok"

    def test_ai_message_keeps_tool_calls(self):
        msg = AIMessage(
            content="",
            tool_calls=[{"id": "call_1", "name": "read_file", "args": {"path": "a.txt"}}],
        )
        d = convert_message(msg)
        assert d["role"] == "assistant"
        assert d["tool_calls"][0]["id"] == "call_1"
        assert d["tool_calls"][0]["type"] == "function"
        assert d["tool_calls"][0]["function"]["name"] == "read_file"
        assert json.loads(d["tool_calls"][0]["function"]["arguments"]) == {"path": "a.txt"}

    def test_ai_message_without_tool_calls_has_no_key(self):
        d = convert_message(AIMessage(content="hi"))
        assert "tool_calls" not in d

    def test_human_message_unchanged(self):
        assert convert_message(HumanMessage(content="q")) == {"role": "user", "content": "q"}


class TestParseToolCallIds:
    """parse_tool_calls：id 必须非空（role=tool 回传靠它配对）"""

    def test_missing_id_gets_fallback(self):
        raw = [{"name": "read_file", "arguments": "{}", "id": ""}]
        parsed = parse_tool_calls(raw)
        assert parsed[0]["id"], "空 id 必须生成回退 id，否则协议不完整"

    def test_existing_id_preserved(self):
        raw = [{"name": "read_file", "arguments": "{}", "id": "call_x"}]
        assert parse_tool_calls(raw)[0]["id"] == "call_x"


class TestExecuteSingleToolProtocol:
    """execute_single_tool：所有分支的回传必须是 ToolMessage"""

    @pytest.mark.asyncio
    async def test_success_returns_tool_message_with_call_id(self):
        degr, metrics = _stub_deps()
        with patch("mini_claude.tools.execute_tool", AsyncMock(return_value="文件内容")):
            msgs, state_update = await execute_single_tool(
                "read_file",
                {"path": "a.txt"},
                degr,
                metrics,
                lambda name, args: MagicMock(),
                [],
                tool_call_id="call_9",
            )
        assert state_update is None
        msg = msgs[-1]
        assert isinstance(msg, ToolMessage)
        assert msg.tool_call_id == "call_9"
        assert msg.name == "read_file"
        assert msg.content == "文件内容"
        assert msg.status == "success"

    @pytest.mark.asyncio
    async def test_error_returns_tool_message_status_error(self):
        degr, metrics = _stub_deps()
        with patch(
            "mini_claude.tools.execute_tool",
            AsyncMock(side_effect=ValueError("bad param")),
        ):
            msgs, _ = await execute_single_tool(
                "read_file",
                {"path": "a.txt"},
                degr,
                metrics,
                lambda name, args: MagicMock(),
                [],
                tool_call_id="call_9",
            )
        msg = msgs[-1]
        assert isinstance(msg, ToolMessage)
        assert msg.status == "error"
        assert "参数错误" in msg.content

    @pytest.mark.asyncio
    async def test_degradation_skip_returns_tool_message(self):
        degr, metrics = _stub_deps()
        degr.tool.should_skip.return_value = True
        degr.tool.get_replacement.return_value = None
        msgs, _ = await execute_single_tool(
            "run_command",
            {"command": "ls"},
            degr,
            metrics,
            lambda name, args: MagicMock(),
            [],
            tool_call_id="call_7",
        )
        msg = msgs[-1]
        assert isinstance(msg, ToolMessage)
        assert msg.tool_call_id == "call_7"
        assert "被跳过" in msg.content

    @pytest.mark.asyncio
    async def test_confirmation_pending_is_tool_message_not_error(self):
        """确认挂起走 ToolMessage，且不得被标成 error（observe 错误检测依赖此区分）"""
        degr, metrics = _stub_deps()
        exc = PathConfirmationRequired(path="/etc/hosts", reason="受保护路径")
        with patch("mini_claude.tools.execute_tool", AsyncMock(side_effect=exc)):
            msgs, state_update = await execute_single_tool(
                "write_file",
                {"path": "/etc/hosts", "content": "x"},
                degr,
                metrics,
                lambda name, args: MagicMock(),
                [],
                tool_call_id="call_5",
            )
        msg = msgs[-1]
        assert isinstance(msg, ToolMessage)
        assert msg.tool_call_id == "call_5"
        assert msg.status == "success", "确认挂起不是执行错误，status=error 会被 observe 误判"
        assert "路径确认请求" in msg.content
        assert state_update is not None and "stop_reason" in state_update
