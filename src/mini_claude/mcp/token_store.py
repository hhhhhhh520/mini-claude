"""MCP OAuth token 落盘存储（SDK 无关——纯文件 I/O）。

形态：~/.mini-claude/mcp-auth/<server>.json（server 名已由配置层校验，
只含 [A-Za-z0-9_-]，无路径穿越面）：
    {"server", "client_info", "tokens", "obtained_at", "expires_at"}

安全语义：
- POSIX 上写后 chmod 0600（仅属主可读）；Windows 无对应语义，尽力而为
- 坏 JSON 当空处理（get_* 返回 None），不炸主链路；下次写入覆盖

接口对齐 mcp.client.auth.TokenStorage 协议（dict 出入）；pydantic 模型
靠 model_dump 鸭子类型兼容——本模块不 import mcp，保证无 SDK 环境可测。
"""

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional, Union

from ..utils.logger import get_logger

logger = get_logger("mini_claude.mcp.token_store")


def token_file_path(server_name: str, home_dir: Optional[Union[str, Path]] = None) -> Path:
    """单 server 的 token 文件路径：~/.mini-claude/mcp-auth/<server>.json。"""
    home = Path(home_dir) if home_dir else Path.home()
    return home / ".mini-claude" / "mcp-auth" / f"{server_name}.json"


def _to_plain(data: Any) -> Dict[str, Any]:
    """pydantic 模型 → dict；dict 原样返回；其他类型拒绝。"""
    if isinstance(data, dict):
        return data
    dump = getattr(data, "model_dump", None)
    if callable(dump):
        return dump(mode="json")
    raise TypeError(
        f"token/client_info 载荷必须是 dict 或 pydantic 模型，得到 {type(data).__name__}"
    )


class FileTokenStorage:
    """TokenStorage 协议的文件实现（每 server 一个文件）。

    dict 出入；mcp SDK 侧由 oauth.py 的适配层负责 pydantic 转换。
    """

    def __init__(self, server_name: str, home_dir: Optional[Union[str, Path]] = None):
        self.server_name = server_name
        self.path = token_file_path(server_name, home_dir)

    # ---------- 读写 ----------

    def _read_all(self) -> Dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(
                "MCP token 文件读取失败，按空处理",
                server=self.server_name,
                path=str(self.path),
                error=str(e),
            )
            return {}
        return data if isinstance(data, dict) else {}

    def _write_all(self, data: Dict[str, Any]) -> None:
        data["server"] = self.server_name
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)
        self._restrict_permissions()

    def _restrict_permissions(self) -> None:
        if os.name == "nt":
            return  # Windows 无 POSIX 权限语义，尽力而为
        try:
            os.chmod(self.path, 0o600)
        except OSError as e:
            logger.warning("MCP token 文件 chmod 失败", server=self.server_name, error=str(e))

    # ---------- TokenStorage 协议 ----------

    async def get_tokens(self) -> Optional[Dict[str, Any]]:
        return self._read_all().get("tokens")

    async def set_tokens(self, tokens: Any) -> None:
        plain = _to_plain(tokens)
        data = self._read_all()
        data["tokens"] = plain
        data["obtained_at"] = time.time()
        expires_in = plain.get("expires_in")
        data["expires_at"] = (
            data["obtained_at"] + expires_in if isinstance(expires_in, (int, float)) else None
        )
        self._write_all(data)

    async def get_client_info(self) -> Optional[Dict[str, Any]]:
        return self._read_all().get("client_info")

    async def set_client_info(self, client_info: Any) -> None:
        data = self._read_all()
        data["client_info"] = _to_plain(client_info)
        self._write_all(data)

    async def clear(self) -> None:
        """清除该 server 的落盘凭据（幂等）。"""
        try:
            self.path.unlink()
        except FileNotFoundError:
            return
        except OSError as e:
            logger.warning("MCP token 文件删除失败", server=self.server_name, error=str(e))

    # ---------- 状态展示 ----------

    def snapshot(self) -> Optional[Dict[str, Any]]:
        """同步摘要（/mcp status 用）：无文件返回 None，不读不写。"""
        data = self._read_all()
        if not data:
            return None
        return {
            "has_tokens": data.get("tokens") is not None,
            "has_client_info": data.get("client_info") is not None,
            "obtained_at": data.get("obtained_at"),
            "expires_at": data.get("expires_at"),
        }
