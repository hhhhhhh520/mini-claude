"""CLAUDE.md auto-loading (P1-2, @import P5).

对齐 Claude Code 的项目记忆机制：
- 用户级：~/.mini-claude/CLAUDE.md
- 项目级：<workspace_root>/CLAUDE.md + <workspace_root>/CLAUDE.local.md（个人本地补充）
- 合并顺序：用户级在前、项目级在后、local 最后
- @import 语法：@path / @./x（相对包含文件目录）、@~/x（用户主目录）、@/abs；
  嵌套引用最多跟随 5 跳，visited 防环，缺失原文保留，代码文件引原始内容
- 单文件与总量都有字符上限，超限截断并留标记
- 任何读取问题都不抛异常（坏编码用 replace 解码，缺失返回空串）

加载结果由 build_system_messages() 前置给 LLM，不进持久化对话历史
（与 skills 同一注入通道，见 CLAUDE.md 架构红线）。
"""

import logging
import re
from pathlib import Path
from typing import Optional, Union

logger = logging.getLogger(__name__)

CLAUDE_MD_MAX_FILE_CHARS = 65_536
CLAUDE_MD_MAX_TOTAL_CHARS = 131_072
_TRUNCATION_MARKER = "\n\n[... CLAUDE.md 内容超限已截断 ...]"

MAX_IMPORT_DEPTH = 5
# @ 前不能是词字符（防 user@example.com 误伤）也不能是 @；
# 其余（空格/行首/标点/全角标点）均可作为引用起点
_IMPORT_TOKEN_RE = re.compile(r"(?<![\w@])@([^\s@]+)")


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


def _resolve_import_path(spec: str, base_dir: Path, home_dir: Path) -> Path:
    """解析 @ 引用：@~/x → 用户主目录；@/x → 绝对路径；其余相对包含文件目录。"""
    if spec.startswith("~/"):
        return (home_dir / spec[2:]).resolve()
    candidate = Path(spec)
    if candidate.is_absolute():
        return candidate.resolve()
    return (base_dir / spec).resolve()


def _expand_imports(
    content: str,
    base_dir: Path,
    home_dir: Path,
    depth: int,
    visited: set,
    budget: dict,
) -> str:
    """展开 content 中行内 @path 引用为被引文件内容。

    - 被引文件同样走 _read_capped（单文件 64KB 上限），并递归展开其引用
    - 嵌套最多 MAX_IMPORT_DEPTH 跳；visited（按解析后绝对路径）防环
    - budget["remaining"] 为全局剩余字符预算，耗尽即截断停机（防超大引用）
    - 引用缺失/路径非法：原文保留（不警告不打断，@user@example.com 类文本不受影响）
    """
    if depth >= MAX_IMPORT_DEPTH:
        return content

    parts: list = []
    last_end = 0
    for m in _IMPORT_TOKEN_RE.finditer(content):
        spec = m.group(1)
        try:
            path = _resolve_import_path(spec, base_dir, home_dir)
        except (OSError, ValueError):
            continue
        key = str(path)
        if key in visited or not path.is_file():
            continue
        if budget["remaining"] <= 0:
            break
        visited.add(key)
        included = _read_capped(path)
        if len(included) > budget["remaining"]:
            included = included[: budget["remaining"]] + _TRUNCATION_MARKER
            budget["remaining"] = 0
        else:
            budget["remaining"] -= len(included)
        expanded = _expand_imports(included, path.parent, home_dir, depth + 1, visited, budget)
        parts.append(content[last_end : m.start()])
        parts.append(expanded)
        last_end = m.end()
    parts.append(content[last_end:])
    return "".join(parts)


def load_claude_md(
    workspace_root: Optional[Union[str, Path]] = None,
    home_dir: Optional[Union[str, Path]] = None,
) -> str:
    """加载并合并用户级与项目级 CLAUDE.md（含 @import 展开与 CLAUDE.local.md）。

    合并顺序：用户级 ~/.mini-claude/CLAUDE.md → 项目级 CLAUDE.md →
    项目级 CLAUDE.local.md（个人本地补充，一般 gitignore）。
    三份内容中的 @path 引用递归展开（最多 5 跳、防环、共享总字符预算）。

    Args:
        workspace_root: 项目工作区根目录；None 时跳过项目级
        home_dir: 用户主目录；None 用 Path.home()（测试可注入）

    Returns:
        合并后的约定文本；无任何文件时返回空串。
    """
    parts: list = []
    home = Path(home_dir) if home_dir else Path.home()
    candidates = [
        ("user", home / ".mini-claude" / "CLAUDE.md"),
    ]
    if workspace_root:
        candidates.append(("project", Path(workspace_root) / "CLAUDE.md"))
        candidates.append(("project-local", Path(workspace_root) / "CLAUDE.local.md"))

    budget = {"remaining": CLAUDE_MD_MAX_TOTAL_CHARS}
    visited: set = set()

    for label, path in candidates:
        if budget["remaining"] <= 0:
            logger.warning("CLAUDE.md total cap reached, skip %s level", label)
            break
        content = _read_capped(path)
        if not content:
            continue
        if len(content) > budget["remaining"]:
            content = content[: budget["remaining"]] + _TRUNCATION_MARKER
            budget["remaining"] = 0
            parts.append(content)
            continue
        budget["remaining"] -= len(content)
        content = _expand_imports(content, path.parent, home, 0, visited, budget)
        parts.append(content)

    return "\n\n".join(parts)


def append_project_memory(text: str, workspace_root=None) -> str:
    """向项目级 CLAUDE.md 追加一条记忆（/memory add 与 `#` 快速追加共用）。

    文件不存在时创建（带最小头注释）。返回写入的文件路径；任何 IO 失败
    抛给调用方展示（记忆是用户显式动作，失败应当可见）。
    """
    from ..config.settings import settings

    root = Path(workspace_root) if workspace_root else Path(settings.workspace_root)
    path = root / "CLAUDE.md"
    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "# CLAUDE.md\n\n<!-- 项目记忆：本文件每次会话自动加载给 LLM -->\n",
            encoding="utf-8",
        )
    text = text.strip()
    if not text:
        raise ValueError("记忆内容为空")
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"\n- {text}\n")
    return str(path)
