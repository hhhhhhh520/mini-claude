"""ask 模式工具执行错误语义测试。

背景（2026-10-02 真机实测）：ask 模式的工具循环对确认类异常零兜底——
PathConfirmationRequired（沙箱外路径）直接把 run_single 打崩成
"模型调用失败：跑 mini-claude doctor" 的顶层错误，而不是作为工具结果
回流给 LLM 让它改道。REPL 图路径（_act_helpers）有完整确认处理，ask 模式
必须同语义：无法交互确认就翻译成可读错误文本回流。

锁定契约：
- PathConfirmationRequired → 错误文本含路径、原因、沙箱根、/add-dir 出路
- McpConfirmationRequired → 含 server/tool
- PermissionAskRequired → 含工具名
- 正常结果原样透传（不被包装污染）
"""

import pytest

from mini_claude.cli import main as cli_main
from mini_claude.config.settings import settings
from mini_claude.mcp.bridge import McpConfirmationRequired
from mini_claude.permissions.manager import PermissionAskRequired
from mini_claude.utils.safety import PathConfirmationRequired


@pytest.mark.asyncio
async def test_path_confirmation_flows_back_as_tool_error(monkeypatch):
    async def raise_confirm(name, args):
        raise PathConfirmationRequired("D:/proj/src/x.py", "Path is outside workspace")

    monkeypatch.setattr(cli_main, "execute_tool", raise_confirm)
    result = await cli_main._execute_ask_tool("read_file", {"path": "D:/proj/src/x.py"})
    assert "D:/proj/src/x.py" in result
    assert "Path is outside workspace" in result
    assert str(settings.workspace_root) in result, "必须告知模型沙箱根在哪"
    assert "/add-dir" in result, "必须给出 REPL 出路"


@pytest.mark.asyncio
async def test_mcp_confirmation_flows_back_as_tool_error(monkeypatch):
    async def raise_mcp(name, args):
        raise McpConfirmationRequired(server="remote", tool="deploy")

    monkeypatch.setattr(cli_main, "execute_tool", raise_mcp)
    result = await cli_main._execute_ask_tool("mcp__remote__deploy", {})
    assert "remote" in result and "deploy" in result


@pytest.mark.asyncio
async def test_permission_ask_flows_back_as_tool_error(monkeypatch):
    async def raise_perm(name, args):
        raise PermissionAskRequired(tool="run_command", arg="rm -rf /")

    monkeypatch.setattr(cli_main, "execute_tool", raise_perm)
    result = await cli_main._execute_ask_tool("run_command", {"command": "rm -rf /"})
    assert "run_command" in result


@pytest.mark.asyncio
async def test_normal_result_passthrough(monkeypatch):
    async def ok(name, args):
        return "all good"

    monkeypatch.setattr(cli_main, "execute_tool", ok)
    assert await cli_main._execute_ask_tool("read_file", {"path": "a.txt"}) == "all good"


def test_ask_max_tool_rounds_setting_default():
    """轮数预算可配置，默认 25（10 连正常恢复循环都不够，实测）。"""
    assert settings.ask_max_tool_rounds == 25
