"""权限规则解析与匹配（P3-2；收敛批次③A 对齐 Claude Code `Tool(specifier)`）。

规则形态（并存）：
- `工具名`                仅按工具名匹配（任意参数）
- `工具名:模式`           遗留形态：主参数 glob（fnmatch，大小写敏感）
- `工具名(specifier)`     本体形态，按工具类别解释 specifier：
  - `run_command(git diff:*)` / `run_background(...)`——命令前缀（`:*` 后缀）
    或精确匹配（无 `:*`）
  - `edit_file(src/**)` / `read_file(~/x)` / `force_write(//C:/x)` 等
    路径工具——路径 glob（相对工作区；`~/` 家目录展开；`//` 前缀=绝对路径）
  - `web_fetch(domain:example.com)`——域名匹配（含子域）
  - 其余工具（含 mcp__*）——specifier 规则不命中（同遗留 ":" 规则）

主参数映射：run_command/run_background → command；read/write/edit/force_write → path；
其余无主参数。
"""

import fnmatch
import os
import re
import urllib.parse
from dataclasses import dataclass
from typing import Dict, List, Optional

from ..config.settings import settings

_PRIMARY_ARG_KEYS: Dict[str, str] = {
    "run_command": "command",
    "run_background": "command",
    "write_file": "path",
    "edit_file": "path",
    "force_write": "path",
    "read_file": "path",
    "list_dir": "path",
}

_COMMAND_TOOLS = {"run_command", "run_background"}
_PATH_TOOLS = {"read_file", "write_file", "edit_file", "force_write", "list_dir"}

_PAREN_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\((.*)\)$")


@dataclass
class Rule:
    tool: str
    pattern: str = None  # 遗留 ":" 形态的 glob（None = 仅按名匹配）
    specifier: Optional[str] = None  # 括号形态的 specifier（None = 非括号规则）


def primary_arg(tool_name: str, tool_args: dict) -> str:
    key = _PRIMARY_ARG_KEYS.get(tool_name)
    if not key:
        return ""
    value = tool_args.get(key) if isinstance(tool_args, dict) else None
    return value if isinstance(value, str) else ""


def parse_rules(raw_rules: List) -> List[Rule]:
    """解析规则列表；空串/缺名/非字符串静默跳过（配置脏数据不应崩主链路）。

    括号形态优先于 ":"（`Bash(a:b)` 不会被拆成 Bash/a:b）。
    """
    rules: List[Rule] = []
    for raw in raw_rules or []:
        if not isinstance(raw, str):
            continue
        text = raw.strip()
        if not text:
            continue

        paren = _PAREN_RE.match(text)
        if paren:
            rules.append(Rule(tool=paren.group(1), specifier=paren.group(2).strip()))
            continue

        if ":" in text:
            tool, pattern = text.split(":", 1)
            if not tool.strip():
                continue
            rules.append(Rule(tool=tool.strip(), pattern=pattern))
        else:
            rules.append(Rule(tool=text, pattern=None))
    return rules


def match_rule(rule: Rule, tool_name: str, tool_args: dict) -> bool:
    """规则是否命中本次调用。"""
    if rule.tool != tool_name:
        return False
    if rule.specifier is not None:
        return _match_specifier(rule.tool, rule.specifier, tool_args)
    if rule.pattern is None:
        return True
    return fnmatch.fnmatchcase(primary_arg(tool_name, tool_args), rule.pattern)


def _match_specifier(tool: str, spec: str, tool_args: dict) -> bool:
    """按工具类别解释 specifier（本体形态）。"""
    if not spec:
        return False
    if tool in _COMMAND_TOOLS:
        command = primary_arg(tool, tool_args)
        if spec.endswith(":*"):
            return command.startswith(spec[: -len(":*")])
        return command == spec

    if tool == "web_fetch":
        if not spec.startswith("domain:"):
            return False
        domain = spec[len("domain:") :].lower().strip()
        url = str(tool_args.get("url", "")) if isinstance(tool_args, dict) else ""
        host = (urllib.parse.urlparse(url).hostname or "").lower()
        return host == domain or host.endswith("." + domain)

    if tool in _PATH_TOOLS:
        return _match_path_spec(spec, tool_args)
    return False


def _match_path_spec(spec: str, tool_args: dict) -> bool:
    """路径 specifier 匹配：相对工作区 glob / ~/ 家目录 / // 绝对路径。

    全部候选用 posix 形态（/ 分隔）对比，避免 Windows 反斜杠与 pattern
    斜杠混合导致的假阴性；路径匹配用大小写不敏感的 fnmatch（Windows 语义）。
    """

    def _posix(p: str) -> str:
        return os.path.normpath(p).replace("\\", "/")

    path = str(tool_args.get("path", "")) if isinstance(tool_args, dict) else ""
    if not path:
        return False

    pattern = spec
    if pattern.startswith("//"):
        pattern = pattern[1:]  # 本体用 // 表示绝对路径；本地只需去掉一层
    elif pattern.startswith("~/"):
        pattern = os.path.expanduser(pattern)

    posix_pattern = _posix(pattern)
    candidates = [path, os.path.abspath(path)]
    if not os.path.isabs(pattern):
        try:
            candidates.append(os.path.relpath(os.path.abspath(path), settings.workspace_root))
        except ValueError:
            pass
    return any(fnmatch.fnmatch(_posix(c), posix_pattern) for c in candidates)
