"""MCP http server 的 auth（OAuth）配置解析测试。

配置形态：
    {"type": "http", "url": "...", "auth": "oauth"}                        简写
    {"type": "http", "url": "...", "auth": {"mode": "oauth",
        "scope": "read", "callback": "local|paste", "client_name": "..."}}  全量
约束：
- auth 仅 http transport 有效；stdio 带 auth 给 warning 但不整条拒绝
- auth 值非法（非 "oauth" / 非法 dict）→ 该 server 跳过并警告（不静默）
- auth 键本身不得进"未知字段"警告
"""

import json

from mini_claude.mcp.config import load_mcp_config


def _write(tmp_path, servers):
    cfg_dir = tmp_path / ".mini-claude"
    cfg_dir.mkdir(exist_ok=True)
    (cfg_dir / "mcp.json").write_text(json.dumps({"mcpServers": servers}), encoding="utf-8")
    return cfg_dir


def test_auth_string_form_parsed(tmp_path):
    _write(tmp_path, {"remote": {"type": "http", "url": "https://x.example/mcp", "auth": "oauth"}})
    configs, warnings = load_mcp_config(workspace_root=tmp_path)
    assert not warnings, warnings
    cfg = configs["remote"]
    assert cfg.auth is not None
    assert cfg.auth.mode == "oauth"
    assert cfg.auth.scope == ""
    assert cfg.auth.callback == "local"  # 默认本地回调（超时转粘贴兜底）
    assert cfg.auth.client_name == "mini-claude"


def test_auth_dict_form_parsed(tmp_path):
    _write(
        tmp_path,
        {
            "remote": {
                "type": "http",
                "url": "https://x.example/mcp",
                "auth": {
                    "mode": "oauth",
                    "scope": "mcp:read mcp:write",
                    "callback": "paste",
                    "client_name": "my-agent",
                },
            }
        },
    )
    configs, warnings = load_mcp_config(workspace_root=tmp_path)
    assert not warnings, warnings
    auth = configs["remote"].auth
    assert auth.mode == "oauth"
    assert auth.scope == "mcp:read mcp:write"
    assert auth.callback == "paste"
    assert auth.client_name == "my-agent"


def test_auth_key_not_reported_unknown(tmp_path):
    _write(tmp_path, {"remote": {"type": "http", "url": "https://x.example/mcp", "auth": "oauth"}})
    _, warnings = load_mcp_config(workspace_root=tmp_path)
    assert not any("auth" in w for w in warnings), warnings


def test_auth_without_key_is_none(tmp_path):
    _write(tmp_path, {"remote": {"type": "http", "url": "https://x.example/mcp"}})
    configs, warnings = load_mcp_config(workspace_root=tmp_path)
    assert not warnings, warnings
    assert configs["remote"].auth is None


def test_auth_invalid_value_skips_server(tmp_path):
    _write(tmp_path, {"remote": {"type": "http", "url": "https://x.example/mcp", "auth": "basic"}})
    configs, warnings = load_mcp_config(workspace_root=tmp_path)
    assert "remote" not in configs
    assert warnings, "非法 auth 值必须给 warning 而非静默"


def test_auth_invalid_callback_skips_server(tmp_path):
    _write(
        tmp_path,
        {
            "remote": {
                "type": "http",
                "url": "https://x.example/mcp",
                "auth": {"mode": "oauth", "callback": "websocket"},
            }
        },
    )
    configs, warnings = load_mcp_config(workspace_root=tmp_path)
    assert "remote" not in configs
    assert warnings


def test_auth_unknown_mode_skips_server(tmp_path):
    _write(
        tmp_path,
        {"remote": {"type": "http", "url": "https://x.example/mcp", "auth": {"mode": "mtls"}}},
    )
    configs, warnings = load_mcp_config(workspace_root=tmp_path)
    assert "remote" not in configs
    assert warnings


def test_auth_on_stdio_ignored_with_warning(tmp_path):
    _write(tmp_path, {"local": {"command": "echo", "auth": "oauth"}})
    configs, warnings = load_mcp_config(workspace_root=tmp_path)
    assert "local" in configs, "stdio 带 auth 只忽略字段，不整条拒绝"
    assert configs["local"].auth is None
    assert any("auth" in w for w in warnings), warnings


def test_auth_scope_must_be_string(tmp_path):
    _write(
        tmp_path,
        {"remote": {"type": "http", "url": "https://x.example/mcp", "auth": {"scope": 42}}},
    )
    configs, warnings = load_mcp_config(workspace_root=tmp_path)
    assert "remote" not in configs
    assert warnings
