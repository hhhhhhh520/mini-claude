"""CLAUDE.md auto-loading (P1-2).

对齐 Claude Code 的项目记忆机制（简化版）：
- 用户级：~/.mini-claude/CLAUDE.md
- 项目级：<workspace_root>/CLAUDE.md
- 合并顺序：用户级在前、项目级在后
- 单文件与总量都有字符上限，超限截断并留标记
- 任何读取问题都不抛异常（坏编码用 replace 解码，缺失返回空串）

加载结果由 build_system_messages() 前置给 LLM，不进持久化对话历史
（与 skills 同一注入通道，见 CLAUDE.md 架构红线）。
"""

import logging
from pathlib import Path
from typing import Optional, Union

logger = logging.getLogger(__name__)

CLAUDE_MD_MAX_FILE_CHARS = 65_536
CLAUDE_MD_MAX_TOTAL_CHARS = 131_072
_TRUNCATION_MARKER = "\n\n[... CLAUDE.md 内容超限已截断 ...]"


def _read_capped(path: Path) -> str:
    """读取单个 CLAUDE.md，超限截断；读不了返回空串。"""
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        logger.debug("CLAUDE.md unreadable", path=str(path), error=str(e))
        return ""
    if len(content) > CLAUDE_MD_MAX_FILE_CHARS:
        content = content[:CLAUDE_MD_MAX_FILE_CHARS] + _TRUNCATION_MARKER
    return content


def load_claude_md(
    workspace_root: Optional[Union[str, Path]] = None,
    home_dir: Optional[Union[str, Path]] = None,
) -> str:
    """加载并合并用户级与项目级 CLAUDE.md。

    Args:
        workspace_root: 项目工作区根目录；None 时跳过项目级
        home_dir: 用户主目录；None 用 Path.home()（测试可注入）

    Returns:
        合并后的约定文本；无任何文件时返回空串。
    """
    parts: list = []
    total_budget = CLAUDE_MD_MAX_TOTAL_CHARS

    home = Path(home_dir) if home_dir else Path.home()
    candidates = [
        ("user", home / ".mini-claude" / "CLAUDE.md"),
    ]
    if workspace_root:
        candidates.append(("project", Path(workspace_root) / "CLAUDE.md"))

    for label, path in candidates:
        remaining = total_budget - sum(len(p) for p in parts)
        if remaining <= 0:
            logger.warning("CLAUDE.md total cap reached, skip %s level", label)
            break
        content = _read_capped(path)
        if not content:
            continue
        if len(content) > remaining:
            content = content[:remaining] + _TRUNCATION_MARKER
        parts.append(content)

    return "\n\n".join(parts)
