"""最小 MCP stdio server（E2E 专用）。

用官方 SDK 的 FastMCP 起一个 stdio server，提供 echo/add 两个工具，
供 tests/test_integration/test_mcp_stdio_e2e.py 做真子进程连接验证。
"""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("e2e-echo")


@mcp.tool()
def echo(text: str) -> str:
    """原样返回输入文本"""
    return text


@mcp.tool()
def add(a: int, b: int) -> int:
    """两数相加"""
    return str(a + b)


if __name__ == "__main__":
    mcp.run()
