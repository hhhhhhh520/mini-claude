"""PermissionManager（P3-2）：模式 + 规则 + 会话放行的单一裁决点。

裁决顺序（ PLAN 文档定死）：
    deny > ask > allow > 模式默认
与 safety.py 的关系：白名单是安全底线（独立、始终生效），这里是用户意愿层。
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple, Union

from ..config.settings import settings
from ..utils.logger import get_logger
from .mode import PermissionMode
from .rules import Rule, match_rule, parse_rules, primary_arg

logger = get_logger("mini_claude.permissions.manager")

EDIT_TOOLS = {"write_file", "edit_file", "force_write"}
MUTATING_TOOLS = EDIT_TOOLS | {"run_command", "run_background"}
MCP_PREFIX = "mcp__"


@dataclass
class Decision:
    action: str  # "allow" | "ask" | "deny"
    reason: str = ""


class PermissionAskRequired(Exception):
    """权限裁决为 ask，需用户确认后重试。

    Attributes:
        tool: 工具名
        arg: 主参数（用于会话内放行键）
    """

    def __init__(self, tool: str, arg: str):
        self.tool = tool
        self.arg = arg
        super().__init__(f"Permission ask required: {tool}:{arg}")


class PlanApprovalRequired(Exception):
    """plan 模式下 exit_plan_mode 提交计划，需用户批准（收敛批次③C）。

    Attributes:
        plan: 提交的计划文本（展示给用户）
    """

    def __init__(self, plan: str):
        self.plan = plan
        super().__init__("Plan approval required")


def _ask_key(tool: str, arg: str) -> str:
    return f"{tool}:{arg}"


class PermissionManager:
    """会话级权限管理器（规则从 settings.json 加载，模式运行时可切）。"""

    def __init__(
        self,
        allow_rules: Optional[List[Rule]] = None,
        deny_rules: Optional[List[Rule]] = None,
        ask_rules: Optional[List[Rule]] = None,
        mode: PermissionMode = PermissionMode.DEFAULT,
        enabled: bool = True,
    ):
        self.allow_rules = allow_rules or []
        self.deny_rules = deny_rules or []
        self.ask_rules = ask_rules or []
        self.mode = mode
        self.enabled = enabled
        self._session_approved: set = set()

    # ---------- 模式 ----------

    def set_mode(self, mode: PermissionMode) -> None:
        self.mode = mode

    def cycle_mode(self) -> PermissionMode:
        from .mode import next_mode

        self.mode = next_mode(self.mode)
        return self.mode

    # ---------- 会话放行 ----------

    def approve_session(self, tool: str, arg: str = "") -> None:
        self._session_approved.add(_ask_key(tool, arg))

    # ---------- 裁决 ----------

    def decide(self, tool_name: str, tool_args: dict) -> Decision:
        if not self.enabled:
            return Decision("allow", "权限系统关闭")

        # 1. deny：任何模式都不可越过
        for rule in self.deny_rules:
            if match_rule(rule, tool_name, tool_args):
                return Decision(
                    "deny",
                    f"匹配 deny 规则: {rule.tool}" + (f":{rule.pattern}" if rule.pattern else ""),
                )

        # 2. ask：优先于 allow（保守优先）。bypass 跳过；accept_edits 对编辑类
        #    工具跳过；会话已放行跳过。
        for rule in self.ask_rules:
            if match_rule(rule, tool_name, tool_args):
                if self.mode == PermissionMode.BYPASS:
                    break
                if self.mode == PermissionMode.ACCEPT_EDITS and tool_name in EDIT_TOOLS:
                    break
                key = _ask_key(tool_name, primary_arg(tool_name, tool_args))
                if key in self._session_approved:
                    break
                return Decision(
                    "ask",
                    f"匹配 ask 规则: {rule.tool}" + (f":{rule.pattern}" if rule.pattern else ""),
                )

        # 3. allow：显式放行优先于模式默认（plan 模式下也生效）
        for rule in self.allow_rules:
            if match_rule(rule, tool_name, tool_args):
                return Decision("allow", f"匹配 allow 规则: {rule.tool}")

        # 4. 模式默认
        if self.mode == PermissionMode.PLAN:
            is_mutating = tool_name in MUTATING_TOOLS or tool_name.startswith(MCP_PREFIX)
            if is_mutating:
                return Decision("deny", "plan 模式只读，禁止修改类操作")

        return Decision("allow")

    # ---------- 加载 ----------

    @classmethod
    def load(
        cls, workspace_root: Union[str, Path, None] = None, home_dir: Union[str, Path, None] = None
    ) -> "PermissionManager":
        allow: List[str] = []
        deny: List[str] = []
        ask: List[str] = []
        warnings: List[str] = []

        home = Path(home_dir) if home_dir else Path.home()
        candidates: List[Tuple[str, Path]] = [("user", home / ".mini-claude" / "settings.json")]
        if workspace_root:
            candidates.append(("project", Path(workspace_root) / ".mini-claude" / "settings.json"))

        for label, path in candidates:
            if not path.is_file():
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as e:
                warnings.append(f"{label} 级权限配置 {path} 读取失败：{e}")
                continue
            perms = data.get("permissions", {}) if isinstance(data, dict) else {}
            if not isinstance(perms, dict):
                warnings.append(f"{label} 级权限配置的 permissions 字段必须是对象")
                continue
            allow.extend(perms.get("allow", []) or [])
            deny.extend(perms.get("deny", []) or [])
            ask.extend(perms.get("ask", []) or [])

        for w in warnings:
            logger.warning("permission config warning", warning=w)

        enabled = getattr(settings, "permissions_enabled", True)
        return cls(
            allow_rules=parse_rules(allow),
            deny_rules=parse_rules(deny),
            ask_rules=parse_rules(ask),
            enabled=enabled,
        )


_manager: Optional[PermissionManager] = None


def get_permission_manager() -> PermissionManager:
    """全局权限管理器单例（规则在首访时从磁盘加载）。"""
    global _manager
    if _manager is None:
        _manager = PermissionManager.load(settings.workspace_root)
    return _manager


def reset_permission_manager() -> None:
    global _manager
    _manager = None
