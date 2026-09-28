"""/add-dir 命令：会话级追加工作目录（对标 Claude Code）。

安全语义在 utils/safety.py 的多根注册表：validate_path 对所有已注册根放行，
主 workspace 的既有比较逻辑不动；额外根用带 os.sep 守卫的前缀比较
（根 D:\\proj 不放行 D:\\projects）。PROTECTED_PATHS 与穿越检查不放松。
"""

import os
from typing import List

from .base import CommandHandler, CommandResult


class AddDirHandler(CommandHandler):
    """/add-dir <path>：注册额外工作目录；无参数时列出当前全部工作根。"""

    commands: List[str] = ["/add-dir"]

    async def handle(self, ctx) -> CommandResult:
        from ...utils.safety import (
            add_workspace_root,
            get_workspace_roots,
        )

        raw = (ctx.args or "").strip().strip('"').strip("'")
        if not raw:
            roots = get_workspace_roots()
            lines = ["当前工作根："]
            for i, r in enumerate(roots):
                tag = "（主）" if i == 0 else ""
                lines.append(f"  {r}{tag}")
            lines.append("用法：/add-dir <目录> 追加工作目录（会话级，主根不改动）")
            return CommandResult(handled=True, message="\n".join(lines))

        expanded = os.path.expanduser(raw)
        ok, reason = add_workspace_root(expanded)
        if not ok:
            return CommandResult(handled=True, error=f"/add-dir 失败：{reason}")

        if reason == "already":
            return CommandResult(
                handled=True,
                message=f"目录已注册过：{os.path.abspath(expanded)}",
            )

        return CommandResult(
            handled=True,
            message=(
                f"已追加工作目录：{os.path.abspath(expanded)}\n"
                "该目录下的文件读写自此按工作区内路径放行（会话级；"
                "保护路径与穿越检查不受影响）。用 /add-dir 查看全部工作根。"
            ),
        )
