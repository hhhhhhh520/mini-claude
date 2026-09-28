"""MCP streamable HTTP transport 真 E2E（本机回环，无外部网络）。

进程内 uvicorn 挂 FastMCP 的 streamable_http_app（mcp SDK 自带依赖链），
走完整链路：HTTP 连接 → 工具发现 → 桥接注册 → 放行 → 调用 →
resources/prompts 读取 → 断连。

CI 不装 [mcp] extra：importorskip 整文件跳过；本地两层验证必跑。
"""

import asyncio
import json
import socket

import pytest

pytest.importorskip("mcp")
pytest.importorskip("uvicorn")

from mini_claude.mcp.config import load_mcp_config  # noqa: E402
from mini_claude.mcp.manager import get_mcp_manager, reset_mcp_manager  # noqa: E402
from mini_claude.tools import execute_tool, list_tools, tool_registry  # noqa: E402


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
async def http_server():
    """进程内起 FastMCP streamable HTTP server，返回 endpoint url。"""
    import uvicorn
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP("http-e2e", host="127.0.0.1", port=0)

    @mcp.tool()
    def echo(text: str) -> str:
        """原样返回输入文本"""
        return text

    @mcp.resource("echo://greeting")
    def greeting() -> str:
        return "你好，HTTP"

    @mcp.prompt()
    def review(code: str) -> str:
        return f"请审查这段代码：{code}"

    app = mcp.streamable_http_app()
    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    task = asyncio.get_running_loop().create_task(server.serve())
    for _ in range(100):
        if server.started:
            break
        await asyncio.sleep(0.05)
    assert server.started, "uvicorn 未能在 5s 内启动"
    try:
        yield f"http://127.0.0.1:{port}/mcp"
    finally:
        server.should_exit = True
        await task


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    reset_mcp_manager()
    for name in list(tool_registry.list_tools()):
        if name.startswith("mcp"):
            tool_registry.unregister(name)


@pytest.mark.asyncio
async def test_http_connect_tool_call_resource_prompt(http_server, tmp_path):
    cfg_dir = tmp_path / ".mini-claude"
    cfg_dir.mkdir()
    (cfg_dir / "mcp.json").write_text(
        json.dumps({"mcpServers": {"remote": {"type": "http", "url": http_server}}}),
        encoding="utf-8",
    )
    configs, warnings = load_mcp_config(workspace_root=tmp_path)
    assert not warnings, warnings

    mgr = get_mcp_manager()
    mgr._configs = configs
    mgr._config_loaded = True

    await mgr.connect_server("remote")
    assert "mcp__remote__echo" in list_tools()

    mgr.approve_tool("remote", "echo")
    out = await execute_tool("mcp__remote__echo", {"text": "ping"})
    assert out == "ping"

    # resources / prompts 全局工具
    resources = await execute_tool("mcp_list_resources", {})
    assert "echo://greeting" in resources
    content = await execute_tool(
        "mcp_read_resource", {"server": "remote", "uri": "echo://greeting"}
    )
    assert "你好，HTTP" in content
    prompts = await execute_tool("mcp_list_prompts", {})
    assert "review" in prompts
    prompt = await execute_tool(
        "mcp_get_prompt",
        {"server": "remote", "name": "review", "arguments": {"code": "print(1)"}},
    )
    assert "请审查这段代码" in prompt and "print(1)" in prompt

    await mgr.disconnect_server("remote")
    assert "mcp__remote__echo" not in list_tools()
