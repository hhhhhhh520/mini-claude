"""Hook 事件分发器（P3-1，事件面 P5 对齐 Claude Code）。

语义（对齐 Claude Code hooks）：
- PreToolUse：exit 0 放行；exit 2 阻断（stderr 为原因）；stdout JSON
  {"decision":"block","reason":...} 也阻断；其他非零/超时 = 非阻断错误（放行+记日志）
- PostToolUse：stdout JSON {"replacement": "..."} 替换工具输出；不可阻断
- Stop：只触发不判断
- UserPromptSubmit：exit 2 / decision=block 阻断该输入（stderr/reason 展示给用户）；
  exit 0 纯 stdout 或 hookSpecificOutput.additionalContext 注入回合上下文
- Notification：只触发不判断（确认请求等需用户注意的时刻）
- SubagentStop：exit 2 / decision=block 阻断子代理收工（原因喂回继续）
"""

import json
from typing import Dict, List, Optional, Tuple

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

    async def dispatch_user_prompt_submit(
        self, prompt: str, thread_id: str = ""
    ) -> Tuple[bool, str, str]:
        """UserPromptSubmit：裁决用户输入。

        Returns:
            (blocked, reason, additional_context)
            blocked=True 时 reason 展示给用户、本轮不进 Agent；
            additional_context 注入本回合 system 上下文。
        """
        if not getattr(settings, "hooks_enabled", False):
            return False, "", ""
        outcomes = await self._run_all(
            "UserPromptSubmit", "", {"prompt": prompt, "thread_id": thread_id}
        )
        context_parts: List[str] = []
        for outcome in outcomes:
            if outcome.timed_out:
                logger.warning("UserPromptSubmit hook timed out")
                continue
            if outcome.stdout.strip().startswith("{"):
                try:
                    data = json.loads(outcome.stdout)
                except json.JSONDecodeError:
                    data = {}
                if data.get("decision") == "block":
                    return True, str(data.get("reason", "被 UserPromptSubmit hook 阻断")), ""
                hook_out = data.get("hookSpecificOutput") or {}
                if hook_out.get("hookEventName") == "UserPromptSubmit" and isinstance(
                    hook_out.get("additionalContext"), str
                ):
                    context_parts.append(hook_out["additionalContext"])
                    continue
            if outcome.exit_code == 2:
                reason = outcome.stderr.strip() or "被 UserPromptSubmit hook 阻断"
                return True, reason, ""
            if outcome.exit_code == 0 and outcome.stdout.strip():
                # 对齐 Claude Code "stdout added to context"
                context_parts.append(outcome.stdout.strip())
            elif outcome.exit_code != 0:
                logger.warning(
                    "UserPromptSubmit hook non-blocking error", exit_code=outcome.exit_code
                )
        return False, "", "\n\n".join(context_parts)

    async def dispatch_notification(self, message: str, thread_id: str = "") -> None:
        """Notification：只触发不判断，任何异常都吞掉。"""
        if not getattr(settings, "hooks_enabled", False):
            return
        try:
            await self._run_all("Notification", "", {"message": message, "thread_id": thread_id})
        except Exception as e:
            logger.warning("Notification hook dispatch failed", error=str(e))

    async def dispatch_subagent_stop(
        self, agent_id: str, agent_task: str, result_summary: str, thread_id: str = ""
    ) -> Tuple[bool, str]:
        """SubagentStop：裁决子代理收工。返回 (blocked, reason)。"""
        if not getattr(settings, "hooks_enabled", False):
            return False, ""
        outcomes = await self._run_all(
            "SubagentStop",
            "",
            {
                "agent_id": agent_id,
                "agent_task": agent_task,
                "result_summary": result_summary[:500],
                "thread_id": thread_id,
            },
        )
        for outcome in outcomes:
            if outcome.timed_out:
                logger.warning("SubagentStop hook timed out", agent_id=agent_id)
                continue
            if outcome.stdout.strip().startswith("{"):
                try:
                    data = json.loads(outcome.stdout)
                except json.JSONDecodeError:
                    data = {}
                if data.get("decision") == "block":
                    return True, str(data.get("reason", "被 SubagentStop hook 阻断"))
            if outcome.exit_code == 2:
                return True, outcome.stderr.strip() or "被 SubagentStop hook 阻断"
            if outcome.exit_code != 0:
                logger.warning("SubagentStop hook non-blocking error", exit_code=outcome.exit_code)
        return False, ""


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
