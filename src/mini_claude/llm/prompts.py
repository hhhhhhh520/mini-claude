"""System prompts for different model providers."""

import os
import platform
import re
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

from mini_claude.config.settings import ModelProvider, settings

logger = logging.getLogger(__name__)


# =============================================================================
# Prompt Injection Protection - Security Architecture
# =============================================================================

# Dangerous patterns that may indicate prompt injection attempts
# These patterns are designed to be conservative to avoid false positives
# while catching common injection techniques
PROMPT_INJECTION_PATTERNS: List[str] = [
    # Instruction override attempts
    r"ignore\s+(all\s+)?(previous|prior)\s+(instructions?|prompts?)",
    r"forget\s+(everything|all)\s*(above|before)?",
    r"disregard\s+(all\s+)?(previous|prior)\s+(instructions?|rules?)",
    # Role/identity manipulation
    r"you\s+are\s+now\s+",
    r"act\s+as\s+(if\s+you\s+are|a)",
    r"pretend\s+(to\s+be|you\s+are)",
    r"simulate\s+(being|a)",
    # System/assistant role injection
    r"system\s*:",
    r"assistant\s*:",
    r"<\s*system\s*>",
    r"<\s*assistant\s*>",
    # Instruction tag manipulation
    r"<\s*instructions?\s*>",
    r"<\s*\/\s*instructions?\s*>",
    r"\[instructions?\]",
    r"\[\/instructions?\]",
    # Output manipulation
    r"output\s+only\s*:",
    r"respond\s+with\s*:",
    r"your\s+response\s+must\s+be",
    # Common jailbreak phrases
    r"DAN\s+mode",
    r"do\s+anything\s+now",
    r"ignore\s+all\s+restrictions",
    r"bypass\s+(all\s+)?(restrictions|filters)",
]

# Compiled regex for performance (compiled at module load)
_COMPILED_INJECTION_PATTERNS: List[re.Pattern] = [
    re.compile(pattern, re.IGNORECASE) for pattern in PROMPT_INJECTION_PATTERNS
]

# Delimiter markers for user input isolation
USER_INPUT_START_MARKER = "[USER_TASK_START]"
USER_INPUT_END_MARKER = "[USER_TASK_END]"


def sanitize_user_input(text: str, max_length: int = 10000) -> str:
    """
    Sanitize user input to prevent prompt injection attacks.

    This function wraps user input in delimiter markers and performs
    basic validation to detect and log potential injection attempts.

    SECURITY DESIGN:
    1. Length limiting prevents resource exhaustion
    2. Pattern detection logs suspicious inputs for monitoring
    3. Delimiter wrapping helps LLM distinguish user content from instructions
    4. The function does NOT modify content - it wraps and monitors only

    Args:
        text: User input text to sanitize
        max_length: Maximum allowed length in characters (default: 10000)

    Returns:
        Sanitized text wrapped in delimiter markers

    Raises:
        ValueError: If text is empty or exceeds max_length

    Note:
        Detection of injection patterns does NOT raise an exception.
        Instead, it logs a warning for security monitoring. The input
        is still processed but wrapped in delimiters for isolation.
    """
    # 1. Validate input is not empty
    if not text or not text.strip():
        raise ValueError("Input text cannot be empty")

    # 2. Length validation
    if len(text) > max_length:
        raise ValueError(f"Input text exceeds maximum length of {max_length} characters")

    # 3. Detect potential injection attempts
    detected_patterns = _detect_injection_attempt(text)
    if detected_patterns:
        logger.warning(
            "Potential prompt injection detected. Patterns: %s",
            ", ".join(detected_patterns),
        )
        # Log the suspicious input (truncated for security)
        logger.debug("Suspicious input (first 100 chars): %s", text[:100])

    # 4. Wrap in delimiter markers for isolation
    # The markers help LLM distinguish user content from instructions
    sanitized = f"{USER_INPUT_START_MARKER}\n{text}\n{USER_INPUT_END_MARKER}"

    return sanitized


def _detect_injection_attempt(text: str) -> List[str]:
    """
    Check if text matches known injection patterns.

    This is an internal function used by sanitize_user_input.

    Args:
        text: Text to analyze

    Returns:
        List of pattern descriptions that matched (empty if no matches)
    """
    detected: List[str] = []

    for i, pattern in enumerate(_COMPILED_INJECTION_PATTERNS):
        match = pattern.search(text)
        if match:
            # Use the original pattern string as identifier
            # Extract a readable part of the matched text
            matched_text = match.group(0)
            detected.append(f"Pattern {i + 1}: '{matched_text}'")

    return detected


# Feature version tracking - centralized record of all capabilities
FEATURE_VERSIONS: Dict[str, Dict[str, Any]] = {
    "file_operations": {
        "version": "1.0",
        "features": ["read", "write", "edit", "search"],
        "description": "File operations including read, write, edit, and search",
    },
    "command_execution": {
        "version": "1.0",
        "features": ["shell_commands", "background_tasks"],
        "description": "Command execution with safety checks and background task support",
    },
    "web_capabilities": {
        "version": "1.0",
        "features": ["web_search", "web_fetch"],
        "description": "Web search via DuckDuckGo and content fetching",
    },
    "agent_collaboration": {
        "version": "1.5",
        "features": ["spawn", "parallel", "aggregate"],
        "description": "Sub-agent spawning, parallel execution, and result aggregation",
    },
    "token_management": {
        "version": "2.0",
        "features": ["counter", "budget", "summarize"],
        "description": "Token counting, budget control, and automatic summarization",
    },
    "session_management": {
        "version": "1.0",
        "features": ["save", "load", "resume"],
        "description": "Session persistence and restoration",
    },
    "skills_system": {
        "version": "1.0",
        "features": ["load", "invoke", "auto_match"],
        "description": "Skill loading from markdown files, slash command invocation, and automatic description matching",
    },
}


def get_feature_summary(include_version: bool = True, include_features: bool = True) -> str:
    """Generate a dynamic feature summary for system prompts.

    Args:
        include_version: Whether to include version numbers in output
        include_features: Whether to include feature lists in output

    Returns:
        Formatted string describing all capabilities
    """
    lines = []

    # Mapping from feature keys to display names
    display_names = {
        "file_operations": "File Operations",
        "command_execution": "Command Execution",
        "web_capabilities": "Web Capabilities",
        "agent_collaboration": "Agent Collaboration",
        "token_management": "Token Management",
        "session_management": "Session Management",
        "skills_system": "Skills System",
    }

    # Feature display names for sub-items
    feature_display = {
        "read": "Read",
        "write": "Write",
        "edit": "Edit",
        "search": "Search",
        "shell_commands": "Shell Commands",
        "background_tasks": "Background Tasks",
        "web_search": "Web Search",
        "web_fetch": "Web Fetch",
        "spawn": "Sub-Agents",
        "parallel": "Parallel Execution",
        "aggregate": "Agent Management",
        "counter": "Token Counter",
        "budget": "Budget Control",
        "summarize": "Summary Compression",
        "save": "Save/Load",
        "load": "Load",
        "resume": "Resume",
        "invoke": "Invoke",
        "auto_match": "Auto Match",
    }

    for key, info in FEATURE_VERSIONS.items():
        display_name = display_names.get(key, key.replace("_", " ").title())
        version_str = f" v{info['version']}" if include_version else ""

        if include_features and info.get("features"):
            features_str = ", ".join(
                feature_display.get(f, f.replace("_", " ").title()) for f in info["features"]
            )
            lines.append(f"- **{display_name}**{version_str}: {features_str}")
        else:
            lines.append(f"- **{display_name}**{version_str}: {info.get('description', '')}")

    return "\n".join(lines)


def get_feature_list_markdown() -> str:
    """Generate markdown-formatted feature list for detailed documentation."""
    sections = []

    # Feature details mapping - use display names that match expected output
    feature_details = {
        "file_operations": [
            ("read", "Read", "Read file contents with optional line range"),
            ("write", "Write", "Create new files or overwrite existing ones"),
            ("edit", "Edit", "Make precise text replacements in files"),
            ("search", "Search", "Find files by pattern and search text content"),
        ],
        "command_execution": [
            ("shell_commands", "Shell Commands", "Execute system commands with safety checks"),
            ("background_tasks", "Background Tasks", "Run long-running tasks asynchronously"),
        ],
        "web_capabilities": [
            (
                "web_search",
                "Web Search",
                "Search the web using DuckDuckGo for up-to-date information",
            ),
            ("web_fetch", "Web Fetch", "Retrieve and analyze web content"),
        ],
        "agent_collaboration": [
            ("spawn", "Sub-Agents", "Spawn specialized agents for parallel task execution"),
            ("parallel", "Parallel Execution", "Run multiple independent tasks concurrently"),
            ("aggregate", "Agent Management", "Monitor and retrieve results from spawned agents"),
        ],
        "token_management": [
            ("budget", "Budget Control", "Monitor and enforce token usage limits"),
            (
                "summarize",
                "Summary Compression",
                "Automatically compress conversations when approaching limits",
            ),
        ],
        "session_management": [
            ("save", "Save/Load", "Persist and restore conversation sessions"),
            ("resume", "Resume", "Continue from previous conversation states"),
        ],
        "skills_system": [
            ("load", "Load Skills", "Discover and load skills from ~/.mini-claude/skills/"),
            ("invoke", "Invoke Skills", "Use /skill <name> to invoke a loaded skill"),
            ("auto_match", "Auto Match", "Automatically match skills by description"),
        ],
    }

    display_names = {
        "file_operations": "File Operations",
        "command_execution": "Command Execution",
        "web_capabilities": "Web Capabilities",
        "agent_collaboration": "Agent Collaboration",
        "token_management": "Token Management",
        "session_management": "Session Management",
        "skills_system": "Skills System",
    }

    for key, info in FEATURE_VERSIONS.items():
        display_name = display_names.get(key, key.replace("_", " ").title())
        section_lines = [f"### {display_name}"]

        if key in feature_details:
            for feat_key, feat_display, feat_desc in feature_details[key]:
                section_lines.append(f"- **{feat_display}**: {feat_desc}")

        sections.append("\n".join(section_lines))

    return "\n\n".join(sections)


def update_feature_version(
    feature_name: str,
    version: Optional[str] = None,
    features: Optional[List[str]] = None,
    description: Optional[str] = None,
) -> None:
    """Update or add a feature version entry.

    This function allows new features to be registered dynamically.

    Args:
        feature_name: The feature key (e.g., "file_operations")
        version: New version string (e.g., "1.1")
        features: List of feature capabilities
        description: Human-readable description

    Raises:
        ValueError: If feature_name is empty
    """
    if not feature_name:
        raise ValueError("feature_name cannot be empty")

    if feature_name not in FEATURE_VERSIONS:
        FEATURE_VERSIONS[feature_name] = {
            "version": version or "1.0",
            "features": features or [],
            "description": description or "",
        }
    else:
        if version is not None:
            FEATURE_VERSIONS[feature_name]["version"] = version
        if features is not None:
            FEATURE_VERSIONS[feature_name]["features"] = features
        if description is not None:
            FEATURE_VERSIONS[feature_name]["description"] = description


def _build_base_prompt() -> str:
    """Build the base prompt with dynamically injected feature list."""
    return f"""You are Mini Claude Code, an intelligent programming assistant.

**Today's date: {{DATE_PLACEHOLDER}}** — Use this for all time-sensitive queries (weather, news, etc.).

## Self-Identity

I am Mini Claude Code, an intelligent programming assistant designed to help developers with coding tasks through natural language interaction. My core capabilities include:

{get_feature_list_markdown()}

{{SKILLS_PLACEHOLDER}}

### CLI Commands
Users can interact with the CLI using these commands. When appropriate, inform users about these:

| Command | Description |
|---------|-------------|
| `/tokens` | View detailed token usage statistics |
| `/status` | Show session status (messages, thread ID, token usage) |
| `/help` | Display help information with all commands |
| `/reset` | Clear conversation history |
| `/save [name]` | Save current session (default: "default") |
| `/load <name>` | Load a saved session |
| `/resume <id>` | Resume a saved thread |
| `/sessions` | List all saved sessions |
| `/clear` | Clear the screen |
| `/exit` | Exit the program |
| `/skills` | List all available skills |
| `/skill <name> [args]` | Invoke a skill by name |

## IMPORTANT: You MUST use tools to accomplish tasks. NEVER output shell commands or code blocks for execution.

You have access to the following tools:

### File Operations
- read_file(path, start_line?, end_line?): Read file contents
- write_file(path, content): Create or overwrite a file
- edit_file(path, old_text, new_text): Edit a file by replacing text
- list_dir(path?): List directory contents
- search_files(pattern, path?): Search files by glob pattern
- search_content(query, pattern?, path?): Search text in files

### Command Execution
- run_command(command): Execute a shell command (use sparingly)

### Parallel Execution
- plan_parallel(tasks): Plan parallel tasks with dependency analysis
- execute_parallel(auto_aggregate?): Execute planned tasks in parallel
- parallel_status(): Check execution status
- aggregate_results(format?): Aggregate all results

### Agent Management
- spawn_agent(task, context?, agent_id?): Spawn a sub-agent
- spawn_parallel(tasks): Spawn multiple agents in parallel
- list_agents(): List active sub-agents
- get_result(agent_id, wait?): Get sub-agent result

### Web Capabilities
- web_search(query, num_results?): Search the web using DuckDuckGo
- web_fetch(url, max_length?): Fetch and extract content from a web page

### Weather
- weather(city, days?): Get current weather and forecast for a city. **Use this for ALL weather queries - do NOT use web_search for weather.**

### Task Checklist
- todo_write(todos): Maintain the session task checklist. Pass the COMPLETE list each time; items are {{content, status: pending|in_progress|completed, active_form?}}. Exactly ONE item must be in_progress while you work. Use it for multi-step tasks (3+ steps) so the user sees progress; skip it for trivial requests. Pass an empty list to clear it.

### MCP Tools (dynamic)
- Tools named mcp__SERVER__TOOL come from connected MCP servers (user can manage via /mcp). When one matches the task, use it like any other tool. Calling an unapproved MCP tool will pause for user confirmation - that is expected, tell the user to reply yes to allow it.

## Rules:
1. ALWAYS use tools (read_file, write_file, edit_file) for file operations
2. NEVER output shell commands like `cat`, `echo`, `ls` - use tools instead
3. NEVER output code blocks expecting them to be executed
4. For parallel tasks, use plan_parallel -> execute_parallel workflow
5. **IMPORTANT: After web_search, ALWAYS use web_fetch on the most relevant result URL to get detailed information.** Search snippets alone are usually insufficient. For time-sensitive queries (weather, news, prices), always fetch the actual page.
6. **For weather queries: use the `weather` tool directly.** Do NOT use web_search for weather - the weather tool gets real-time forecast data via API.
7. **NEVER re-fetch the same URL twice.** If a fetched page doesn't have the needed info, try a different URL or inform the user what you found.
8. **If web_search returns no useful results, try at most 2 different search queries.** Then report what you found (or didn't find) to the user.
9. Report results clearly after tool execution
10. **After reading a file, ALWAYS provide a summary explaining what the file is, its purpose, and key contents.** Never just show the content without explanation.
11. **For multi-step tasks, maintain the checklist with todo_write** — mark each item in_progress right before starting it and completed immediately after finishing. Keep exactly one in_progress.

## Examples:

WRONG - Do NOT do this:
```
ls -la workspace/
cat file.txt
echo "content" > file.txt
```

CORRECT - Use tools instead:
- Use list_dir tool to list directory
- Use read_file tool to read file
- Use write_file tool to create file
- Use edit_file tool to modify file

## Working Guidelines (follow these in every task)

### Task management
- For any task with 3+ steps, record progress with `todo_write` (session
  checklist) or `task_create` / `task_update` (task list with dependencies
  and delegation). Keep exactly one item in_progress and mark items
  completed as soon as they are done — do not batch-update at the end.
- Parallelizable independent work: delegate with `task_update(owner=<agent_id>)`
  plus `spawn_agent`. Sub-agents finish by setting their task status.

### Tool hygiene
- Prefer dedicated tools over `run_command` (read_file > cat, list_dir > ls).
- `edit_file` requires exact old_text — read the file section first, then edit.
- Use `search_content` / `search_files` to locate code before reading files.
- Very large tool outputs are truncated (a note shows the original size);
  narrow your query instead of re-reading everything.

### Runtime facts
- `run_command` working directory persists across calls: `cd` in one call
  carries into the next. Environment variables persist only when you
  explicitly `export VAR=value` (or `set` on Windows) as a standalone command.
- plan mode is read-only: research first, then submit your complete plan
  with `exit_plan_mode` for user approval.

### Code change discipline
- Make focused changes only — no unrelated refactors, no speculative
  abstractions, no TODO stubs left behind.
- Match the surrounding code's style and idioms.
- If the project has tests for what you changed, run them before declaring done.

### Communication
- Lead with the outcome, then details. Be concise and direct.
- Say plainly when something is uncertain or failed — never claim success
  without evidence.
- Use the same language the user writes in.
"""


# Build BASE_PROMPT at module load time for backward compatibility
BASE_PROMPT = _build_base_prompt()


def build_env_block() -> str:
    """构造 <env> 环境事实块（对齐 Claude Code 的 env 注入）。

    2026-10-02 真机实测的教训：系统提示词不含环境信息时，模型会猜工作区
    路径（/workspace）、在 Windows cmd 里用 ls/pwd，把工具轮数预算全部烧在
    环境适应上。REPL 图路径与 ask 模式共用 get_system_prompt，env 块在此
    单点注入。
    """
    from ..utils.safety import get_workspace_roots

    roots = get_workspace_roots()
    primary = roots[0]
    lines = [
        "<env>",
        f"working_directory: {primary}",
        "  （读写沙箱根：相对路径基于此；沙箱外路径默认需要确认，ask 模式下直接拒绝）",
    ]
    if len(roots) > 1:
        lines.append(f"additional_directories: {', '.join(roots[1:])}")
    if os.name == "nt":
        lines.append(
            "shell: cmd —— 没有 ls/pwd/cat：列目录用 dir，搜索用 findstr，"
            "跨盘切目录用 cd /d，运行 Python 用 python"
        )
    else:
        lines.append("shell: /bin/sh —— ls/pwd/grep 等常规工具可用")
    lines.append(f"platform: {platform.system()} {platform.release()}")
    lines.append("</env>")
    return "\n".join(lines)


def build_system_messages(hook_context: str = "") -> list:
    """构造前置给 LLM 的系统消息（LiteLLM 格式）：系统提示 + CLAUDE.md + skills + hook 注入.

    刻意**不写入** state["messages"]：messages 字段是 `Annotated[List, add]`
    累加语义，把系统提示塞进去再由 think 返回全量列表，会导致用户消息被复制、
    SystemMessage 落到 HumanMessage 之后（见 ISSUE：reducer 消息重复）。
    系统提示应在每次 LLM 调用时前置，永远完整、永远在最前、不进持久化历史。

    Args:
        hook_context: UserPromptSubmit hook 注入的回合级上下文（空串=无注入）。
            与系统提示同一前置通道：每次 LLM 调用都在场、当回合结束即失效
            （下一轮增量带空串清空），不进持久化历史。

    位置说明：本函数原在 agent/nodes/_shared.py，2026-10-02 迁入——ask 模式
    接入系统提示时不能拖进 _shared 的导入期 LLMProvider 单例副作用（见
    _shared 转发层的注释）。
    """
    from ..utils.claudemd import load_claude_md

    provider = settings.get_model_provider()
    system_msgs = [{"role": "system", "content": get_system_prompt(provider)}]

    # Inject CLAUDE.md project/user memory (P1-2)——与 skills 同一通道：
    # 每次调用前置、不进持久化历史、失效不阻断主链路。
    if getattr(settings, "claude_md_enabled", False):
        try:
            claude_md = load_claude_md(settings.workspace_root)
            if claude_md:
                system_msgs.append(
                    {
                        "role": "system",
                        "content": (
                            "以下约定来自 CLAUDE.md（用户级与项目级记忆），"
                            "在本会话中必须始终遵守：\n\n" + claude_md
                        ),
                    }
                )
        except Exception as e:
            logger.debug("claudemd injection failed: %s", e)

    # UserPromptSubmit hook 注入的回合级上下文（P5 对齐 Claude Code）
    hook_ctx = (hook_context or "").strip()
    if hook_ctx:
        system_msgs.append(
            {
                "role": "system",
                "content": ("以下内容来自 UserPromptSubmit hook（仅本回合有效）：\n\n" + hook_ctx),
            }
        )

    # Inject skills as a dedicated system message（小模型更关注近期上下文，
    # 但系统消息本就整体前置，这里保持与旧行为一致的完整 skill 说明）。
    try:
        from mini_claude.skills.registry import get_skill_registry

        registry = get_skill_registry()
        skills = [s for s in registry.list_skills() if s.model_invocable]
        if skills:
            parts = [
                "IMPORTANT: You have the following skills available. "
                "A skill is a set of specialized instructions you should follow "
                "when the user's request matches. DO NOT search for skills on disk — "
                "they are already loaded here:\n"
            ]
            for skill in skills:
                parts.append(f"--- Skill: {skill.name} ---")
                if skill.description:
                    parts.append(f"Trigger: {skill.description}")
                if skill.body:
                    parts.append(skill.body)
                parts.append("")
            parts.append(
                "To use a skill, tell the user you are following it and apply its instructions. "
                "You can also suggest the user type /skill <name> to explicitly activate one."
            )
            system_msgs.append({"role": "system", "content": "\n".join(parts)})
    except Exception as e:  # skills 失效不应阻断主链路，但必须可见
        logger.debug("skills injection failed: %s", e)

    return system_msgs


def get_system_prompt(provider: ModelProvider) -> str:
    """Get provider-specific system prompt.

    The date placeholder is replaced on every call to ensure the date is always current,
    even for long-running REPL sessions that span midnight.
    """
    now = datetime.now(timezone.utc)
    # Use ASCII format to avoid encoding issues on Windows
    today_str = now.strftime("%Y-%m-%d (%A)")
    prompt = BASE_PROMPT.replace("{DATE_PLACEHOLDER}", today_str)

    # Inject available skills into the placeholder
    try:
        from mini_claude.skills.registry import get_skill_registry

        registry = get_skill_registry()
        skill_prompt = registry.get_skill_prompt()
        prompt = prompt.replace("{SKILLS_PLACEHOLDER}", skill_prompt)
    except Exception:
        prompt = prompt.replace("{SKILLS_PLACEHOLDER}", "")

    # 环境事实块（工作区根/OS/shell 习惯）——所有 provider 分支共享，
    # 必须在分支拼接之前附加，CLAUDE/OpenAI 等各自的追加段才会跟在 env 之后
    prompt = f"{prompt}\n\n{build_env_block()}"

    if provider == ModelProvider.CLAUDE:
        # Claude prefers XML-style instructions
        return f"""{prompt}

<instructions>
1. Think through the problem before acting
2. ALWAYS call tools - never output shell commands
3. Wait for tool results before continuing
4. For complex tasks, use plan_parallel then execute_parallel
5. Summarize what you've done when complete
</instructions>

<critical_rules>
- You are a TOOL-USING agent, not a code generator
- When asked to create/edit files, use write_file or edit_file tools
- When asked to read files, use read_file tool
- When asked to list directories, use list_dir tool
- NEVER output shell commands or code blocks for execution
</critical_rules>"""

    elif provider == ModelProvider.OPENAI:
        # OpenAI prefers Markdown
        return f"""{prompt}

## Instructions
1. Think through the problem before acting
2. ALWAYS call tools - never output shell commands
3. Wait for tool results before continuing
4. For complex tasks, use plan_parallel then execute_parallel
5. Summarize what you've done when complete

## Critical Rules
- You are a TOOL-USING agent, not a code generator
- When asked to create/edit files, use write_file or edit_file tools
- When asked to read files, use read_file tool
- NEVER output shell commands or code blocks for execution"""

    elif provider == ModelProvider.GEMINI:
        # Gemini works well with structured text
        return f"""{prompt}

Instructions:
1. Think through the problem before acting
2. ALWAYS call tools - never output shell commands
3. Wait for tool results before continuing
4. For complex tasks, use plan_parallel then execute_parallel
5. Summarize what you've done when complete

Critical Rules:
- You are a TOOL-USING agent, not a code generator
- Use write_file/edit_file for file operations
- NEVER output shell commands or code blocks"""

    elif provider == ModelProvider.DEEPSEEK:
        # DeepSeek specific prompt
        return f"""{prompt}

## 执行规则
1. 思考问题后再行动
2. **在调用工具之前，先用简短的文字说明你要做什么**
3. 必须使用工具完成任务，不要输出shell命令
4. 等待工具返回结果后再继续
5. 复杂任务使用 plan_parallel → execute_parallel
6. 完成后总结执行结果

## 重要提醒
- 你是工具调用Agent，不是代码生成器
- 创建/编辑文件必须使用 write_file 或 edit_file 工具
- 读取文件必须使用 read_file 工具
- 列出目录必须使用 list_dir 工具
- 禁止输出 shell 命令或代码块让用户执行

## 创建文件的规则
- 当用户要求"开发"、"创建"、"生成"文件时，先简短说明计划，然后直接使用 write_file 工具创建文件
- 不要先读取不存在的文件，不要只是列出目录
- 如果需要创建多个文件（如 HTML + CSS + JS），逐个创建
- 每次调用 write_file 时，提供完整的文件内容

## 任务完成判断（关键）
- **收到工具结果后，判断任务是否完成**
- 如果用户要求"读取并总结/告诉我"，收到文件内容后**直接输出总结**，不要再次调用工具
- 如果用户要求"创建文件"，文件创建成功后输出结果，不要反复读取
- **禁止重复调用同一工具获取相同结果** - 如果工具已成功返回内容，直接使用该内容
- 只读操作（read_file, list_dir）成功后，通常意味着任务完成，应该输出结果而非继续调用工具"""

    else:
        # Default for Ollama and others
        return prompt


def get_subagent_prompt(task: str, context: str = "") -> str:
    """Get prompt for sub-agent.

    User inputs are sanitized to prevent prompt injection attacks.
    The sanitizer wraps inputs in delimiter markers and logs
    suspicious patterns for security monitoring.

    Args:
        task: The task description (user-provided, will be sanitized)
        context: Optional context information (user-provided, will be sanitized)

    Returns:
        Sanitized prompt for sub-agent execution
    """
    # Sanitize user-provided inputs
    sanitized_task = sanitize_user_input(task)
    sanitized_context = sanitize_user_input(context) if context else ""

    return f"""You are a file writer. Your ONLY job is to create files using write_file tool.

Task: {sanitized_task}

{f"Context: {sanitized_context}" if sanitized_context else ""}

CRITICAL RULES:
1. You MUST call write_file tool IMMEDIATELY
2. You MUST provide BOTH arguments: path AND content
3. Example: write_file(path="file.html", content="<html>...</html>")

FORBIDDEN:
- Calling write_file() without arguments
- Calling write_file with only path
- Outputting text instead of calling tool
- Calling read_file or list_dir first

Call write_file NOW with complete arguments."""


def get_planning_prompt(task: str) -> str:
    """Get prompt for planning phase.

    User inputs are sanitized to prevent prompt injection attacks.
    The sanitizer wraps inputs in delimiter markers and logs
    suspicious patterns for security monitoring.

    Args:
        task: The task to plan (user-provided, will be sanitized)

    Returns:
        Sanitized prompt for planning
    """
    # Sanitize user-provided input
    sanitized_task = sanitize_user_input(task)

    return f"""Given the following task, create a step-by-step execution plan.

Task: {sanitized_task}

Available tools:
- read_file, write_file, edit_file: File operations
- list_dir, search_files, search_content: Navigation
- run_command: Execute shell commands (use sparingly)
- plan_parallel, execute_parallel: Parallel task execution
- spawn_agent: Launch sub-agents

IMPORTANT: Always prefer using tools over shell commands.

Provide a numbered list of steps. For steps that can run in parallel, mark them with [PARALLEL]."""
