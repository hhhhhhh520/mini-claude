"""/memory 命令（收敛批次④C）：查看与追加 CLAUDE.md 记忆。

- `/memory`            列出记忆文件（用户级/项目级/CLAUDE.local.md）与行数
- `/memory add <文本>`  向项目级 CLAUDE.md 追加一条记忆（立即持久，下回合生效）
"""

from typing import List

from .base import CommandHandler, CommandResult


class MemoryCommandHandler(CommandHandler):
    """查看与追加 CLAUDE.md 记忆。"""

    commands: List[str] = ["/memory"]

    async def handle(self, ctx) -> CommandResult:
        from pathlib import Path

        from ...config.settings import settings
        from ...utils.claudemd import append_project_memory

        args = (ctx.args or "").strip()
        parts = args.split(None, 1)

        if parts and parts[0].lower() == "add":
            text = parts[1].strip() if len(parts) > 1 else ""
            if not text:
                return CommandResult(handled=True, error="用法：/memory add <要记住的内容>")
            try:
                path = append_project_memory(text)
            except Exception as e:
                return CommandResult(handled=True, error=f"写入记忆失败：{e}")
            return CommandResult(
                handled=True,
                message=f"已写入项目记忆（{path}）——下一回合起对所有会话生效。",
            )

        home = Path.home() / ".mini-claude" / "CLAUDE.md"
        project = Path(settings.workspace_root) / "CLAUDE.md" if settings.workspace_root else None
        local = (
            Path(settings.workspace_root) / "CLAUDE.local.md" if settings.workspace_root else None
        )

        lines = ["记忆文件（加载顺序：用户级 → 项目级 → CLAUDE.local.md）："]
        for label, path in (("用户级", home), ("项目级", project), ("本地", local)):
            if path is None:
                continue
            if path.is_file():
                count = sum(1 for _ in path.open(encoding="utf-8", errors="replace"))
                lines.append(f"  [{label}] {path}（{count} 行）")
            else:
                lines.append(f"  [{label}] {path}（不存在）")
        lines.append("追加记忆：/memory add <内容>，或在输入框用 # 内容")
        return CommandResult(handled=True, message="\n".join(lines))
