"""hooks.json 配置加载（P3-1）。

形态对齐 Claude Code：
{
  "hooks": {
    "PreToolUse": [{"matcher": "<regex>", "hooks": [{"type": "command",
                    "command": "...", "timeout": 30}]}]
  }
}
- matcher 为空/缺失 = 匹配全部工具；否则按正则 search 匹配工具名
- v1 仅支持 type=command
- 用户级 + 项目级同类事件条目拼接（不去重，执行顺序即配置顺序）
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

from ..utils.logger import get_logger

logger = get_logger("mini_claude.hooks.config")

VALID_EVENTS = (
    "PreToolUse",
    "PostToolUse",
    "Stop",
    "UserPromptSubmit",
    "Notification",
    "SubagentStop",
    "SessionStart",
    "SessionEnd",
    "PreCompact",
    "SubagentStart",
)
DEFAULT_TIMEOUT = 30.0
_MAX_TIMEOUT = 300.0


@dataclass
class HookCommand:
    """单条 hook 命令。"""

    command: str
    timeout: float = DEFAULT_TIMEOUT


@dataclass
class HookRule:
    """事件下的一条规则：matcher + 若干命令。"""

    matcher: str = ""
    hooks: List[HookCommand] = field(default_factory=list)

    def matches(self, tool_name: str) -> bool:
        if not self.matcher:
            return True
        try:
            return re.search(self.matcher, tool_name) is not None
        except re.error:
            logger.warning("invalid hook matcher regex", matcher=self.matcher)
            return False


@dataclass
class HookConfig:
    """事件 → 规则列表。"""

    entries: Dict[str, List[HookRule]] = field(default_factory=dict)


def _parse_rule(entry: dict, warnings: List[str], source: str) -> Optional[HookRule]:
    if not isinstance(entry, dict):
        warnings.append(f"{source}: hook 规则必须是对象，已跳过")
        return None
    hooks_raw = entry.get("hooks", [])
    if not isinstance(hooks_raw, list):
        warnings.append(f"{source}: hooks 必须是数组，已跳过")
        return None

    parsed: List[HookCommand] = []
    for h in hooks_raw:
        if not isinstance(h, dict) or h.get("type") != "command":
            warnings.append(f"{source}: 仅支持 type=command 的 hook，已跳过")
            continue
        command = h.get("command")
        if not isinstance(command, str) or not command.strip():
            warnings.append(f"{source}: hook 缺少 command，已跳过")
            continue
        try:
            timeout = float(h.get("timeout", DEFAULT_TIMEOUT))
        except (TypeError, ValueError):
            timeout = DEFAULT_TIMEOUT
        timeout = min(max(timeout, 1.0), _MAX_TIMEOUT)
        parsed.append(HookCommand(command=command, timeout=timeout))

    if not parsed:
        return None
    matcher = entry.get("matcher", "")
    if not isinstance(matcher, str):
        warnings.append(f"{source}: matcher 必须是字符串，已按空处理")
        matcher = ""
    return HookRule(matcher=matcher, hooks=parsed)


def load_hooks_config(
    workspace_root: Optional[Union[str, Path]] = None,
    home_dir: Optional[Union[str, Path]] = None,
) -> Tuple[HookConfig, List[str]]:
    """加载并合并用户级/项目级 hooks.json。

    Returns:
        (config, warnings)
    """
    home = Path(home_dir) if home_dir else Path.home()
    candidates: List[Tuple[str, Path]] = [("user", home / ".mini-claude" / "hooks.json")]
    if workspace_root:
        candidates.append(("project", Path(workspace_root) / ".mini-claude" / "hooks.json"))

    entries: Dict[str, List[HookRule]] = {}
    warnings: List[str] = []

    for label, path in candidates:
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            warnings.append(f"{label} 级 hooks 配置 {path} 读取失败，已跳过：{e}")
            continue
        hooks_raw = data.get("hooks", {}) if isinstance(data, dict) else {}
        if not isinstance(hooks_raw, dict):
            warnings.append(f"{label} 级 hooks 配置的 hooks 字段必须是对象，已跳过")
            continue

        for event, rules_raw in hooks_raw.items():
            if event not in VALID_EVENTS:
                warnings.append(
                    f"{label} 级配置含未知事件 {event!r}（支持 {'/'.join(VALID_EVENTS)}），已跳过"
                )
                continue
            if not isinstance(rules_raw, list):
                warnings.append(f"{label} 级配置事件 {event} 的规则必须是数组，已跳过")
                continue
            for i, rule_raw in enumerate(rules_raw):
                rule = _parse_rule(rule_raw, warnings, f"{label}:{event}[{i}]")
                if rule is not None:
                    entries.setdefault(event, []).append(rule)

    return HookConfig(entries=entries), warnings
