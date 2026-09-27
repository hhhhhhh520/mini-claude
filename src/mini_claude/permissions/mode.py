"""权限模式（P3-2）。

default / accept_edits / plan / bypass，shift+tab 循环（对齐 Claude Code）。
"""

from enum import Enum


class PermissionMode(str, Enum):
    DEFAULT = "default"
    ACCEPT_EDITS = "accept_edits"
    PLAN = "plan"
    BYPASS = "bypass"


_CYCLE = [
    PermissionMode.DEFAULT,
    PermissionMode.ACCEPT_EDITS,
    PermissionMode.PLAN,
    PermissionMode.BYPASS,
]

_DESCRIPTIONS = {
    PermissionMode.DEFAULT: "默认：按已有确认流程执行",
    PermissionMode.ACCEPT_EDITS: "自动接受文件编辑（ask 规则对编辑类工具失效）",
    PermissionMode.PLAN: "只读计划：修改类工具被拒",
    PermissionMode.BYPASS: "跳过询问（deny 规则仍生效）",
}


def next_mode(current: PermissionMode) -> PermissionMode:
    """shift+tab 循环的下一个模式。"""
    idx = _CYCLE.index(current)
    return _CYCLE[(idx + 1) % len(_CYCLE)]


def describe(mode: PermissionMode) -> str:
    return _DESCRIPTIONS[mode]
