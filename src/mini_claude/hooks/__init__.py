"""Hooks support (P3-1) - 用户自配的工具调用前后钩子。

事件：PreToolUse / PostToolUse / Stop，配置在 ~/.mini-claude/hooks.json
或 <工作区>/.mini-claude/hooks.json（形态对齐 Claude Code）。
"""

from .config import HookCommand, HookConfig, HookRule, load_hooks_config
from .dispatcher import HookDispatcher, get_hook_dispatcher, reset_hook_dispatcher
from .runner import HookOutcome, run_hook_command

__all__ = [
    "HookCommand",
    "HookConfig",
    "HookRule",
    "load_hooks_config",
    "HookDispatcher",
    "get_hook_dispatcher",
    "reset_hook_dispatcher",
    "HookOutcome",
    "run_hook_command",
]
