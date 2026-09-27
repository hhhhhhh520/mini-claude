"""/permissions 与 /hooks 命令（P3）：查看/切换权限模式、查看 hook 配置。"""

from typing import TYPE_CHECKING, List

from .base import CommandHandler, CommandResult

if TYPE_CHECKING:
    pass


class PermissionCommandHandler(CommandHandler):
    """权限与 hook 管理命令。

    /permissions            查看当前模式 + 规则计数 + 会话放行数
    /permissions <mode>     切换模式（default/accept_edits/plan/bypass）
    /hooks                  查看已配置的 hook（事件/matcher/命令/超时）
    """

    commands: List[str] = ["/permissions", "/hooks"]

    async def handle(self, ctx) -> CommandResult:
        cmd = (ctx.command or "").lower()
        if cmd == "/hooks":
            return self._handle_hooks()

        args = (ctx.args or "").strip()
        from ...permissions.manager import get_permission_manager
        from ...permissions.mode import PermissionMode, describe

        perm = get_permission_manager()

        if not args:
            return CommandResult(handled=True, message=self._format_status(perm))

        try:
            mode = PermissionMode(args.lower())
        except ValueError:
            valid = "/".join(m.value for m in PermissionMode)
            return CommandResult(
                handled=True, error=f"未知模式 {args!r}（可选: {valid}，或按 shift+tab 循环）"
            )
        perm.set_mode(mode)
        return CommandResult(handled=True, message=f"权限模式 → {mode.value}（{describe(mode)}）")

    def _format_status(self, perm) -> str:
        from ...permissions.mode import describe

        lines = [
            f"权限模式: {perm.mode.value}（{describe(perm.mode)}）",
            f"规则: deny={len(perm.deny_rules)} ask={len(perm.ask_rules)} "
            f"allow={len(perm.allow_rules)}",
            f"会话内已放行: {len(perm._session_approved)} 项",
            "shift+tab 循环切换模式；规则配置在 .mini-claude/settings.json 的 permissions 字段",
        ]
        return "\n".join(lines)

    def _handle_hooks(self) -> CommandResult:
        from ...hooks.dispatcher import get_hook_dispatcher

        dispatcher = get_hook_dispatcher()
        entries = dispatcher.config.entries
        if not entries:
            return CommandResult(
                handled=True,
                message=(
                    "未配置任何 hook。\n"
                    "在 ~/.mini-claude/hooks.json 或 <工作区>/.mini-claude/hooks.json 写入：\n"
                    '{"hooks": {"PreToolUse": [{"matcher": "run_command", '
                    '"hooks": [{"type": "command", "command": "..."}]}]}}\n'
                    "重启会话后生效（事件: PreToolUse/PostToolUse/Stop）。"
                ),
            )

        lines = ["已配置 hooks:"]
        for event, rules in entries.items():
            for rule in rules:
                for h in rule.hooks:
                    matcher = rule.matcher or "(全部工具)"
                    lines.append(
                        f"  {event}  matcher={matcher}  cmd={h.command}  timeout={h.timeout:g}s"
                    )
        return CommandResult(handled=True, message="\n".join(lines))
