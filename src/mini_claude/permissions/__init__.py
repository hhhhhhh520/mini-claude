"""Permissions support (P3-2) - 四模式 + allow/ask/deny 规则的细粒度权限。"""

from .manager import (
    Decision,
    PermissionAskRequired,
    PermissionManager,
    get_permission_manager,
    reset_permission_manager,
)
from .mode import PermissionMode, describe, next_mode
from .rules import Rule, match_rule, parse_rules, primary_arg

__all__ = [
    "Decision",
    "PermissionAskRequired",
    "PermissionManager",
    "get_permission_manager",
    "reset_permission_manager",
    "PermissionMode",
    "describe",
    "next_mode",
    "Rule",
    "match_rule",
    "parse_rules",
    "primary_arg",
]
