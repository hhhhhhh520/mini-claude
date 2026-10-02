"""可定义子代理（收敛批次③B，对齐 Claude Code .claude/agents/*.md）。

定义文件形态（frontmatter + 正文）：
    ---
    name: code-reviewer
    description: 代码质量与安全审查
    tools: read_file, search_content, search_files
    ---
    你是一名资深代码审查员……（正文 = 子代理的 system 提示词）

- 搜索顺序：用户级 ~/.mini-claude/agents/*.md → 项目级
  <workspace>/.mini-claude/agents/*.md（同名项目级覆盖）
- tools 缺省 = SUBAGENT_ALLOWED_TOOLS（共享白名单）；填了就以定义为准
  （校验：只保留 registry 里真实存在的工具名，防配置拼错静默失效）
- frontmatter 用逐行 `key: value` 微解析（不引 YAML 依赖；值里的逗号
  只在 tools 列表切分）

诚实边界：frontmatter 的 model 字段本仓库暂不支持（子代理走全局
provider），解析到时记 warning 忽略，不让配置静默失效。
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from ..tools.base import tool_registry
from ..tools.agent_spawn import SUBAGENT_ALLOWED_TOOLS
from ..utils.logger import get_logger

logger = get_logger("mini_claude.utils.agent_definitions")


@dataclass
class AgentDefinition:
    """一个可定义子代理类型。"""

    name: str
    description: str = ""
    body: str = ""
    tools: List[str] = field(default_factory=list)  # 空 = 默认白名单
    source: str = ""


def _parse_frontmatter(text: str) -> tuple:
    """拆 (frontmatter dict, body)；无 frontmatter 时 dict 为空。"""
    if not text.startswith("---"):
        return {}, text
    lines = text.splitlines()
    meta: Dict[str, str] = {}
    end = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end = i
            break
        if ":" in line and not line.startswith((" ", "\t")):
            key, _, value = line.partition(":")
            meta[key.strip().lower()] = value.strip()
    if end is None:
        return {}, text
    body = "\n".join(lines[end + 1 :]).strip()
    return meta, body


def _parse_tools(value: str, name: str) -> List[str]:
    """tools 字段：逗号分隔 → 校验 registry 真实存在（拼错不静默）。"""
    known = set(tool_registry.list_tools())
    out = []
    for item in value.replace("，", ",").split(","):
        tool = item.strip()
        if not tool:
            continue
        if tool not in known:
            logger.warning(
                "agent definition references unknown tool",
                agent=name,
                tool=tool,
            )
            continue
        out.append(tool)
    return out


def _load_file(path: Path) -> Optional[AgentDefinition]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        logger.warning("agent definition read failed", path=str(path), error=str(e))
        return None
    meta, body = _parse_frontmatter(text)
    name = meta.get("name") or path.stem
    defn = AgentDefinition(
        name=name,
        description=meta.get("description", ""),
        body=body,
        source=str(path),
    )
    tools_raw = meta.get("tools", "")
    defn.tools = _parse_tools(tools_raw, name) if tools_raw else list(SUBAGENT_ALLOWED_TOOLS)
    if meta.get("model"):
        logger.warning(
            "agent definition model field not supported yet (global provider)",
            agent=name,
        )
    return defn


def load_agent_definitions(
    workspace_root: Optional[str] = None, home_dir: Optional[str] = None
) -> Dict[str, AgentDefinition]:
    """扫描两级 agents 目录，返回 name → 定义（项目级覆盖用户级）。"""
    home = Path(home_dir) if home_dir else Path.home()
    candidates: List[Path] = [home / ".mini-claude" / "agents"]
    if workspace_root:
        candidates.append(Path(workspace_root) / ".mini-claude" / "agents")

    defs: Dict[str, AgentDefinition] = {}
    for base in candidates:
        if not base.is_dir():
            continue
        for md in sorted(base.glob("*.md")):
            defn = _load_file(md)
            if defn is None:
                continue
            defs[defn.name] = defn  # 后扫的（项目级）覆盖
    return defs


def get_agent_definition(name: str) -> Optional[AgentDefinition]:
    """按名取定义（每次现扫：定义文件可随时增改，无需重启）。"""
    from ..config.settings import settings

    return load_agent_definitions(settings.workspace_root).get(name)


def build_custom_agent_prompt(defn: AgentDefinition, task: str, context: str = "") -> str:
    """把定义正文与任务拼成子代理 prompt（任务经 sanitize_user_input）。"""
    from ..llm.prompts import sanitize_user_input

    sanitized_task = sanitize_user_input(task)
    sanitized_context = sanitize_user_input(context) if context else ""
    parts = [defn.body.strip(), f"Task: {sanitized_task}"]
    if sanitized_context:
        parts.append(f"Context: {sanitized_context}")
    return "\n\n".join(p for p in parts if p)


def resolve_agent_tools(defn: AgentDefinition) -> List[str]:
    """定义的工具白名单（load 时已校验存在性；空列表回退默认白名单）。"""
    return defn.tools or list(SUBAGENT_ALLOWED_TOOLS)


def available_agent_names() -> List[str]:
    from ..config.settings import settings

    return sorted(load_agent_definitions(settings.workspace_root).keys())
