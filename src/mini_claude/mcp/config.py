"""MCP 配置加载（P2；B2 扩展 HTTP transport）。

配置形态对齐 Claude Code：
    stdio: {"mcpServers": {"<name>": {"command": "...", "args": [...], "env": {...}, "trusted": false}}}
    http:  {"mcpServers": {"<name>": {"type": "http", "url": "https://...", "headers": {...}, "trusted": false}}}
也接受无 mcpServers 包裹的扁平形态。搜索顺序：用户级 ~/.mini-claude/mcp.json
→ 项目级 <workspace_root>/.mini-claude/mcp.json（同名 server 项目级覆盖）。

transport 推断：type 缺省时有 command → stdio（向后兼容）、有 url → http。
v1 支持 stdio + streamable http；type=sse 等显式拒绝（给 warning，不静默）。

server 名会进入工具名 mcp__<server>__<tool>，只允许 [a-zA-Z0-9_-]，
非法名拒绝并给 warning（不静默改写，配置问题应让用户看见）。
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

from ..utils.logger import get_logger

logger = get_logger("mini_claude.mcp.config")

_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_VALID_KEYS = {"command", "args", "env", "trusted", "type", "url", "headers"}
_SUPPORTED_TRANSPORTS = ("stdio", "http")


@dataclass
class McpServerConfig:
    """单个 MCP server 的启动配置。"""

    name: str
    command: str = ""
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    trusted: bool = False  # True 时工具自动放行，不走确认通道
    transport: str = "stdio"  # stdio | http
    url: str = ""  # http transport 的 endpoint
    headers: Dict[str, str] = field(default_factory=dict)  # http 附加头（如鉴权）


def _candidate_paths(
    workspace_root: Optional[Union[str, Path]], home_dir: Optional[Union[str, Path]]
) -> List[Tuple[str, Path]]:
    home = Path(home_dir) if home_dir else Path.home()
    paths: List[Tuple[str, Path]] = [("user", home / ".mini-claude" / "mcp.json")]
    if workspace_root:
        paths.append(("project", Path(workspace_root) / ".mini-claude" / "mcp.json"))
    return paths


def _parse_servers(data: dict, source: str, warnings: List[str]) -> Dict[str, dict]:
    """提取 server 定义：兼容 mcpServers 包裹与扁平两种形态。"""
    if "mcpServers" in data:
        servers = data.get("mcpServers")
        if not isinstance(servers, dict):
            warnings.append(f"{source}: mcpServers 必须是对象，已忽略该文件")
            return {}
        return servers
    return data


def load_mcp_config(
    workspace_root: Optional[Union[str, Path]] = None,
    home_dir: Optional[Union[str, Path]] = None,
) -> Tuple[Dict[str, McpServerConfig], List[str]]:
    """加载并合并 MCP server 配置。

    Returns:
        (configs, warnings)：configs 按 server 名索引；warnings 是
        面向用户的中文提示（文件坏、条目非法等），调用方应展示而非吞掉。
    """
    merged: Dict[str, dict] = {}
    warnings: List[str] = []

    for label, path in _candidate_paths(workspace_root, home_dir):
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            warnings.append(f"{label} 级配置 {path} 读取失败，已跳过：{e}")
            continue
        if not isinstance(data, dict):
            warnings.append(f"{label} 级配置 {path} 顶层必须是对象，已跳过")
            continue

        servers = _parse_servers(data, str(path), warnings)
        merged.update(servers)  # 后读的（项目级）覆盖先读的（用户级）

    configs: Dict[str, McpServerConfig] = {}
    for name, entry in merged.items():
        if not isinstance(name, str) or not _NAME_RE.match(name):
            warnings.append(f"server 名 {name!r} 非法（只允许字母/数字/下划线/连字符），已跳过")
            continue
        if not isinstance(entry, dict):
            warnings.append(f"server {name!r} 的配置必须是对象，已跳过")
            continue

        unknown = set(entry) - _VALID_KEYS
        if unknown:
            warnings.append(f"server {name!r} 含未知字段 {sorted(unknown)}，已忽略")

        # transport 判定：显式 type 优先；缺省按字段推断（command→stdio、url→http）
        declared = entry.get("type")
        has_command = isinstance(entry.get("command"), str) and entry["command"].strip()
        has_url = isinstance(entry.get("url"), str) and entry["url"].strip()
        if declared is not None:
            if declared not in _SUPPORTED_TRANSPORTS:
                warnings.append(
                    f"server {name!r} 的 type={declared!r} 不支持"
                    f"（v1 仅支持 {'/'.join(_SUPPORTED_TRANSPORTS)}），已跳过"
                )
                continue
            transport = declared
        elif has_url:
            transport = "http"
        elif has_command:
            transport = "stdio"
        else:
            warnings.append(f"server {name!r} 缺少 command 或 url，已跳过")
            continue

        url = ""
        headers: Dict[str, str] = {}
        command = ""
        args: List[str] = []
        env: Dict[str, str] = {}

        if transport == "http":
            if not has_url:
                warnings.append(f"server {name!r} 为 http transport 但缺少 url，已跳过")
                continue
            url = entry["url"]
            if not (url.startswith("http://") or url.startswith("https://")):
                warnings.append(f"server {name!r} 的 url 必须是 http/https：{url!r}，已跳过")
                continue
            raw_headers = entry.get("headers", {})
            if not isinstance(raw_headers, dict) or not all(
                isinstance(k, str) and isinstance(v, str) for k, v in raw_headers.items()
            ):
                warnings.append(f"server {name!r} 的 headers 必须是字符串到字符串的映射，已跳过")
                continue
            headers = raw_headers
        else:
            command = entry.get("command")
            if not isinstance(command, str) or not command.strip():
                warnings.append(f"server {name!r} 缺少 command，已跳过")
                continue

            args = entry.get("args", [])
            env = entry.get("env", {})
            if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
                warnings.append(f"server {name!r} 的 args 必须是字符串数组，已跳过")
                continue
            if not isinstance(env, dict) or not all(
                isinstance(k, str) and isinstance(v, str) for k, v in env.items()
            ):
                warnings.append(f"server {name!r} 的 env 必须是字符串到字符串的映射，已跳过")
                continue

        configs[name] = McpServerConfig(
            name=name,
            command=command,
            args=args,
            env=env,
            trusted=bool(entry.get("trusted", False)),
            transport=transport,
            url=url,
            headers=headers,
        )

    return configs, warnings
