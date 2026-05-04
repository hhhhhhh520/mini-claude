"""System prompts for different model providers."""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

from mini_claude.config.settings import ModelProvider


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
    }

    for key, info in FEATURE_VERSIONS.items():
        display_name = display_names.get(key, key.replace("_", " ").title())
        version_str = f" v{info['version']}" if include_version else ""

        if include_features and info.get("features"):
            features_str = ", ".join(
                feature_display.get(f, f.replace("_", " ").title())
                for f in info["features"]
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
            ("web_search", "Web Search", "Search the web using DuckDuckGo for up-to-date information"),
            ("web_fetch", "Web Fetch", "Retrieve and analyze web content"),
        ],
        "agent_collaboration": [
            ("spawn", "Sub-Agents", "Spawn specialized agents for parallel task execution"),
            ("parallel", "Parallel Execution", "Run multiple independent tasks concurrently"),
            ("aggregate", "Agent Management", "Monitor and retrieve results from spawned agents"),
        ],
        "token_management": [
            ("budget", "Budget Control", "Monitor and enforce token usage limits"),
            ("summarize", "Summary Compression", "Automatically compress conversations when approaching limits"),
        ],
        "session_management": [
            ("save", "Save/Load", "Persist and restore conversation sessions"),
            ("resume", "Resume", "Continue from previous conversation states"),
        ],
    }

    display_names = {
        "file_operations": "File Operations",
        "command_execution": "Command Execution",
        "web_capabilities": "Web Capabilities",
        "agent_collaboration": "Agent Collaboration",
        "token_management": "Token Management",
        "session_management": "Session Management",
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
"""


# Build BASE_PROMPT at module load time for backward compatibility
BASE_PROMPT = _build_base_prompt()


def get_system_prompt(provider: ModelProvider) -> str:
    """Get provider-specific system prompt.

    The date placeholder is replaced on every call to ensure the date is always current,
    even for long-running REPL sessions that span midnight.
    """
    now = datetime.now(timezone.utc)
    today_str = now.strftime("%Y年%m月%d日 (%A)")
    prompt = BASE_PROMPT.replace("{DATE_PLACEHOLDER}", today_str)

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
    """Get prompt for sub-agent."""
    return f"""You are a file writer. Your ONLY job is to create files using write_file tool.

Task: {task}

{f"Context: {context}" if context else ""}

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
    """Get prompt for planning phase."""
    return f"""Given the following task, create a step-by-step execution plan.

Task: {task}

Available tools:
- read_file, write_file, edit_file: File operations
- list_dir, search_files, search_content: Navigation
- run_command: Execute shell commands (use sparingly)
- plan_parallel, execute_parallel: Parallel task execution
- spawn_agent: Launch sub-agents

IMPORTANT: Always prefer using tools over shell commands.

Provide a numbered list of steps. For steps that can run in parallel, mark them with [PARALLEL]."""
