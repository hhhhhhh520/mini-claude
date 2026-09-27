"""权限规则解析与匹配（P3-2）。

规则形态：
- `工具名`          仅按工具名匹配（任意参数）
- `工具名:模式`     工具名匹配 且 主参数 glob 匹配（fnmatch，大小写敏感）

主参数映射：run_command/run_background → command；read/write/edit/force_write → path；
其余（含 mcp__ 工具）无主参数，模式规则只对名字生效（":" 规则不匹配）。
"""

import fnmatch
from dataclasses import dataclass
from typing import Dict, List

_PRIMARY_ARG_KEYS: Dict[str, str] = {
    "run_command": "command",
    "run_background": "command",
    "write_file": "path",
    "edit_file": "path",
    "force_write": "path",
    "read_file": "path",
}


@dataclass
class Rule:
    tool: str
    pattern: str = None  # None = 仅按名匹配


def primary_arg(tool_name: str, tool_args: dict) -> str:
    key = _PRIMARY_ARG_KEYS.get(tool_name)
    if not key:
        return ""
    value = tool_args.get(key) if isinstance(tool_args, dict) else None
    return value if isinstance(value, str) else ""


def parse_rules(raw_rules: List) -> List[Rule]:
    """解析规则列表；空串/缺名/非字符串静默跳过（配置脏数据不应崩主链路）。"""
    rules: List[Rule] = []
    for raw in raw_rules or []:
        if not isinstance(raw, str):
            continue
        text = raw.strip()
        if not text:
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
    if rule.pattern is None:
        return True
    return fnmatch.fnmatchcase(primary_arg(tool_name, tool_args), rule.pattern)
