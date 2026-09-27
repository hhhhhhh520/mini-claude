"""Hook 事件分发器（P3-1）。

语义（对齐 Claude Code hooks）：
- PreToolUse：exit 0 放行；exit 2 阻断（stderr 为原因）；stdout JSON
  {"decision":"block","reason":...} 也阻断；其他非零/超时 = 非阻断错误（放行+记日志）
- PostToolUse：stdout JSON {"replacement": "..."} 替换工具输出；不可阻断
- Stop：只触发不判断
"""

from typing import Dict, List, Optional

from ..config.settings import settings
from ..utils.logger import get_logger
from .config import HookConfig, load_hooks_config
from .runner import run_hook_command

logger = get_logger("mini_claude.hooks.dispatcher")


class HookDispatcher:
    """按事件分发 hook 命令（runner 可注入，测试用）。"""

    def __init__(self, config: HookConfig, runner=None, cwd: Optional[str] = None):
        self.config = config
        self._runner = runner or run_hook_command
        self._cwd = cwd

    async def _run_all(self, event: str, tool_name: str, payload_extra: Dict) -> List:
        rules = self.config.entries.get(event, [])
        outcomes = []
        for rule in rules:
            if not rule.matches(tool_name):
                continue
            payload = {"event": event, "tool_name": tool_name, **payload_extra}
            for hook_cmd in rule.hooks:
                try:
                    outcome = await self._runner(
                        hook_cmd.command, payload, timeout=hook_cmd.timeout, cwd=self._cwd
                    )
                except Exception as e:
                    logger.warning("hook runner raised", command=hook_cmd.command, error=str(e))
                    continue
                outcomes.append(outcome)
        return outcomes

    async def dispatch_pre_tool_use(
        self, tool_name: str, tool_input: Dict, thread_id: str = ""
    ) -> Optional[str]:
        """返回阻断原因（str）或 None（放行）。"""
        if not getattr(settings, "hooks_enabled", False):
            return None
        outcomes = await self._run_all(
            "PreToolUse", tool_name, {"tool_input": tool_input, "thread_id": thread_id}
        )
        for outcome in outcomes:
            if outcome.timed_out:
                logger.warning("PreToolUse hook timed out", tool=tool_name)
                continue
            # stdout JSON decision=block（优先级高于 exit code 语义）
            if outcome.stdout.strip().startswith("{"):
                try:
                    import json

                    data = json.loads(outcome.stdout)
                    if data.get("decision") == "block":
                        return str(data.get("reason", "被 PreToolUse hook 阻断"))
                except json.JSONDecodeError:
                    pass
            if outcome.exit_code == 2:
                reason = outcome.stderr.strip() or "被 PreToolUse hook 阻断"
                return reason
            if outcome.exit_code != 0:
                logger.warning(
                    "PreToolUse hook non-blocking error",
                    tool=tool_name,
                    exit_code=outcome.exit_code,
                )
        return None

    async def dispatch_post_tool_use(
        self, tool_name: str, tool_input: Dict, tool_result: str, thread_id: str = ""
    ) -> Optional[str]:
        """返回替换后的输出（str）或 None（保持原样）。"""
        if not getattr(settings, "hooks_enabled", False):
            return None
        outcomes = await self._run_all(
            "PostToolUse",
            tool_name,
            {"tool_input": tool_input, "tool_result": tool_result, "thread_id": thread_id},
        )
        replacement = None
        for outcome in outcomes:
            if outcome.timed_out or outcome.exit_code != 0:
                continue
            if outcome.stdout.strip().startswith("{"):
                try:
                    import json

                    data = json.loads(outcome.stdout)
                    if isinstance(data.get("replacement"), str):
                        replacement = data["replacement"]
                except json.JSONDecodeError:
                    pass
        return replacement

    async def dispatch_stop(self, reason: str, last_message: str, thread_id: str = "") -> None:
        """Stop 事件：只触发不判断，任何异常都吞掉。"""
        if not getattr(settings, "hooks_enabled", False):
            return
        try:
            await self._run_all(
                "Stop", "", {"reason": reason, "last_message": last_message, "thread_id": thread_id}
            )
        except Exception as e:
            logger.warning("Stop hook dispatch failed", error=str(e))


_dispatcher: Optional[HookDispatcher] = None


def get_hook_dispatcher() -> HookDispatcher:
    """全局分发器单例（首次访问时从磁盘加载配置）。"""
    global _dispatcher
    if _dispatcher is None:
        config, warnings = load_hooks_config(settings.workspace_root)
        for w in warnings:
            logger.warning("hooks config warning", warning=w)
        _dispatcher = HookDispatcher(config, cwd=settings.workspace_root)
    return _dispatcher


def reset_hook_dispatcher() -> None:
    global _dispatcher
    _dispatcher = None
