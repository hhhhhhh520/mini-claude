"""MCP HTTP transport 配置解析测试。

配置形态（对齐 Claude Code）：
    {"mcpServers": {"<name>": {"type": "http", "url": "https://...", "headers": {...}}}}
type 缺省时按字段推断：有 command → stdio（向后兼容），有 url → http。
"""

import json

from mini_claude.mcp.config import McpServerConfig, load_mcp_config


def _write(tmp_path, servers):
    cfg_dir = tmp_path / ".mini-claude"
    cfg_dir.mkdir(exist_ok=True)
    (cfg_dir / "mcp.json").write_text(json.dumps({"mcpServers": servers}), encoding="utf-8")
    return cfg_dir


def test_http_server_parsed(tmp_path):
    _write(
        tmp_path,
        {"remote": {"type": "http", "url": "https://mcp.example.com/mcp", "trusted": True}},
    )
    configs, warnings = load_mcp_config(workspace_root=tmp_path)
    assert not warnings, warnings
    cfg = configs["remote"]
    assert cfg.transport == "http"
    assert cfg.url == "https://mcp.example.com/mcp"
    assert cfg.trusted is True


def test_url_implies_http_without_type(tmp_path):
    _write(tmp_path, {"remote": {"url": "http://127.0.0.1:9000/mcp"}})
    configs, warnings = load_mcp_config(workspace_root=tmp_path)
    assert not warnings, warnings
    assert configs["remote"].transport == "http"


def test_command_implies_stdio_backward_compat(tmp_path):
    _write(tmp_path, {"local": {"command": "uvx", "args": ["mcp-server-echo"]}})
    configs, warnings = load_mcp_config(workspace_root=tmp_path)
    assert not warnings, warnings
    cfg = configs["local"]
    assert cfg.transport == "stdio"
    assert cfg.command == "uvx"


def test_headers_parsed(tmp_path):
    _write(
        tmp_path,
        {
            "authed": {
                "type": "http",
                "url": "https://mcp.example.com/mcp",
                "headers": {"Authorization": "Bearer token123"},
            }
        },
    )
    configs, warnings = load_mcp_config(workspace_root=tmp_path)
    assert not warnings, warnings
    assert configs["authed"].headers == {"Authorization": "Bearer token123"}


def test_http_without_url_rejected(tmp_path):
    _write(tmp_path, {"broken": {"type": "http"}})
    configs, warnings = load_mcp_config(workspace_root=tmp_path)
    assert "broken" not in configs
    assert any("url" in w for w in warnings)


def test_non_http_scheme_rejected(tmp_path):
    _write(tmp_path, {"bad": {"type": "http", "url": "ftp://example.com"}})
    configs, warnings = load_mcp_config(workspace_root=tmp_path)
    assert "bad" not in configs
    assert any("http" in w.lower() for w in warnings)


def test_unsupported_type_rejected(tmp_path):
    """v1 范围：stdio + streamable http；sse 等显式拒绝不静默。"""
    _write(tmp_path, {"legacy": {"type": "sse", "url": "https://example.com/sse"}})
    configs, warnings = load_mcp_config(workspace_root=tmp_path)
    assert "legacy" not in configs
    assert warnings


def test_non_string_headers_rejected(tmp_path):
    _write(
        tmp_path,
        {"bad": {"type": "http", "url": "https://x.com/mcp", "headers": {"A": 1}}},
    )
    configs, warnings = load_mcp_config(workspace_root=tmp_path)
    assert "bad" not in configs
    assert any("headers" in w for w in warnings)


def test_mixed_stdio_and_http(tmp_path):
    _write(
        tmp_path,
        {
            "local": {"command": "uvx", "args": []},
            "remote": {"type": "http", "url": "https://mcp.example.com/mcp"},
        },
    )
    configs, warnings = load_mcp_config(workspace_root=tmp_path)
    assert not warnings, warnings
    assert configs["local"].transport == "stdio"
    assert configs["remote"].transport == "http"


def test_default_config_is_stdio():
    cfg = McpServerConfig(name="x", command="echo")
    assert cfg.transport == "stdio" and cfg.url == "" and cfg.headers == {}
