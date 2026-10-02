<div align="center">

# Mini Claude Code

**迷你版 Claude Code** — 工具调用 + 主从多 Agent 并发，在一个 CLI 里跑完整开发循环。

[![Python](https://img.shields.io/badge/Python-3.12-blue)](https://www.python.org)
[![Tests](https://img.shields.io/badge/Tests-2136%20collected-brightgreen)](tests/)
[![Tools](https://img.shields.io/badge/Tools-28-orange)](#可用工具28个)
[![Models](https://img.shields.io/badge/Models-Claude%20%7C%20OpenAI%20%7C%20Gemini%20%7C%20DeepSeek%20%7C%20Ollama-green)](#特性)

</div>

## 特性

- **工具调用**：支持文件操作、命令执行、Web搜索等工具
- **主Agent + 子Agent并发**：主Agent保持对话连贯性，可启动多个子Agent并行处理
- **文件锁机制**：支持多Agent安全并行开发同一项目，自动检测冲突
- **多模型支持**：Claude / OpenAI / Gemini / DeepSeek / Ollama
- **混合CLI模式**：REPL交互 + 命令行参数
- **安全设计**：命令白名单（禁止 `python -c`/`node -e`/`find -exec`）、路径验证、SSRF 防护、原子文件写入
- **会话持久化**：SQLite checkpoint + 启动时恢复提示，支持 `/resume` 断点续跑
- **工具降级**：连续失败 3 次自动跳过工具，10 分钟后自动恢复
- **Skills 系统**：从 `~/.mini-claude/skills/` 加载 SKILL.md，支持 `/skill` 调用和自动匹配
- **任务清单**：`todo_write` 维护会话 todo；Task v2（`task_create/update/list/get`）支持多任务、依赖边（防环）与委派——主代理 `task_update(owner=<agent_id>)` 指派、子代理认领推进（对齐 Claude Code Task 系统）；清单**跨会话落盘**（`<工作区>/.mini-claude/tasks.json`，重启新会话自动接续，resume 以 checkpoint 为准）
- **项目记忆**：自动加载 `~/.mini-claude/CLAUDE.md`、工作区 `CLAUDE.md` 与 `CLAUDE.local.md` 作为持久约定；支持 `@path` 引用展开（5 跳防环，含代码文件）（`CLAUDE_MD_ENABLED` 可关）
- **MCP 支持**：接入 Model Context Protocol 服务器（stdio + streamable HTTP），远端工具以 `mcp__<server>__<tool>` 动态注册，默认走确认通道；http server 支持 OAuth 2.0 授权码 + PKCE（401 自动触发、token 落盘自动刷新）；resources/prompts 经 `mcp_list_resources`/`mcp_read_resource`/`mcp_list_prompts`/`mcp_get_prompt` 只读访问（对齐 Claude Code 生态）
- **Hooks**：PreToolUse/PostToolUse/Stop/UserPromptSubmit/Notification/SubagentStop/SessionStart/SessionEnd/PreCompact/SubagentStart 十事件（对齐 Claude Code 事件面），用户自配 shell 命令（stdin JSON / exit 2 阻断 / replacement 替换 / additionalContext 注入），超时强杀
- **细粒度权限**：default/accept_edits/plan/bypass 四模式（shift+tab 循环）+ allow/ask/deny 规则——支持 Claude Code 的 `Tool(specifier)` 语法：`run_command(git diff:*)` 命令前缀、`edit_file(src/**)` 路径 glob、`web_fetch(domain:x)` 域名（与遗留 `tool:pattern` 并存），deny > ask > allow > 模式默认；plan 模式配 `exit_plan_mode` 审批流（批准即转执行）
- **会话回退**：`/rewind` 列出回合边界 checkpoint，支持 `[chat|code|both]` 三种范围——对话分叉重跑之外还能**恢复文件**（write/edit/force_write 的修改按快照时间戳回放：改写恢复、新建删除；会话内日志，侧门修改除外）
- **上下文压缩**：`/compact [指令]` 手动压缩会话历史（LLM 摘要 + 新线程播种，旧 checkpoint 链保留；自定义指令透传摘要提示词）；**auto-compact** 回合前预算超限自动压缩落盘（`AUTO_COMPACT_ENABLED` 可关，60s 冷却）
- **多工作目录**：`/add-dir <目录>` 会话级追加工作根（路径校验对所有已注册根放行，保护路径与穿越检查不放松）
- **后台任务**：`run_background` 输出落盘，`task_output`/`task_kill` 读取与终止（对齐 BashOutput/KillShell）
- **模型热切换**：`/model <name>` 会话内即时切换（含子代理），`.env` 默认值不动
- **测试规模**：2215 个测试用例（2026-09-28 实测收集数）

## 安装

```bash
# 基础安装（CLI + 主 Agent 循环）
pip install -e .

# 推荐：一次装全（测试/搜索/向量/追踪/健康服务）
pip install -e ".[dev,web,vector,tracing,server]"

# 开发/改代码：带依赖锁合面，与 CI 的解析结果完全一致（constraints.txt 说明见文件头）
pip install -e ".[dev]" -c constraints.txt
```

缺件时命令会给中文指引而非 traceback：
`web_search` 需 `[web]`，`trace --enable` 需 `[tracing]`，
`serve-health` 需 `[server]`，向量记忆需 `[vector]`。

## 使用

### REPL模式

```bash
mini-claude
```

进入交互式环境，支持多轮对话和工具调用。

### 命令模式

```bash
# 简单问答
mini-claude ask "你好，介绍一下你自己"

# 文件操作
mini-claude ask "读取README.md文件"
mini-claude ask "列出src目录下的所有Python文件"

# Web搜索
mini-claude ask "搜索Python异步编程最佳实践"

# 代码分析
mini-claude ask "分析当前项目的代码结构"

# 完整主循环（多步工具/错误恢复，慢但能多轮）
mini-claude ask --full "并行创建三个 API 模块并自验"
```

| 模式 | 循环 | 单次内多轮 | 跨会话恢复 | 花费 | 用途 |
|------|------|-----------|-----------|------|------|
| `ask`（默认） | 快捷两步 | 否 | 否 | 便宜 | 问答、单批工具 |
| `ask --full` | 完整主图 | 是 | 否（无 checkpoint） | 贵 | 单条命令多步活 |
| REPL | 完整主图+会话 | 是 | 是 | 贵 | 日常干活 |

### 查看状态

```bash
mini-claude status
```

## 多Agent并行开发

mini-claude 支持多个 Agent 安全地并行开发同一个项目：

### 架构：主从模式

```
┌─────────────────────────────────────────────────────┐
│                    主 Agent                          │
│  (接收用户请求，规划任务，启动子Agent，汇总结果)      │
└─────────────────┬───────────────────────────────────┘
                  │ plan_parallel → execute_parallel
        ┌─────────┼─────────┬─────────┐
        ▼         ▼         ▼         ▼
   ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐
   │子Agent 1│ │子Agent 2│ │子Agent 3│ │子Agent N│
   │(独立执行)│ │(独立执行)│ │(独立执行)│ │(独立执行)│
   └─────────┘ └─────────┘ └─────────┘ └─────────┘
```

### 智能并行执行

使用 `plan_parallel` 和 `execute_parallel` 实现智能并行：

```
> 并行开发三个API模块：
1. 创建 src/api/user.py - 用户API
2. 创建 src/api/product.py - 产品API
3. 创建 src/api/order.py - 订单API
```

LLM 会自动调用：
1. `plan_parallel` - 分析依赖关系，检测文件冲突
2. `execute_parallel` - 按依赖层级并行执行
3. `aggregate_results` - 自动汇总所有结果

### 依赖管理

支持任务依赖声明：

```json
{
  "id": "task_1",
  "description": "创建数据库模型",
  "target_files": ["models.py"]
},
{
  "id": "task_2",
  "description": "创建API路由",
  "target_files": ["routes.py"],
  "depends_on": ["task_1"]  // 等待 task_1 完成
}
```

### 文件锁机制

- **读锁**：多个 Agent 可同时读取同一文件
- **写锁**：写文件时获取独占锁，阻止其他 Agent 同时写入
- **冲突检测**：写入前检查文件是否被其他 Agent 修改过

### 冲突处理

当检测到冲突时，会提示：

```
Error: Conflict detected - File was modified by another agent.
Original hash: a1b2c3d4..., Current hash: e5f6g7h8...
Use 'force_write' to overwrite.
```

使用 `force_write` 工具可以强制覆盖（谨慎使用）。

### 并行工具一览

| 工具 | 功能 |
|------|------|
| `plan_parallel` | 规划并行任务，分析依赖，检测冲突 |
| `execute_parallel` | 执行并行任务，自动汇总结果 |
| `parallel_status` | 查看执行进度和状态 |
| `aggregate_results` | 汇总所有任务结果 |
| `list_locks` | 查看所有活跃的文件锁 |
| `force_write` | 强制写入文件（忽略冲突） |

## Hooks 与权限

**Hooks**（`~/.mini-claude/hooks.json` 或 `<工作区>/.mini-claude/hooks.json`）：

```json
{
  "hooks": {
    "PreToolUse": [
      {"matcher": "run_command|write_file",
       "hooks": [{"type": "command", "command": "check.bat", "timeout": 15}]}
    ],
    "UserPromptSubmit": [
      {"hooks": [{"type": "command", "command": "inject-context.sh"}]}
    ],
    "SubagentStop": [
      {"hooks": [{"type": "command", "command": "review-gate.sh"}]}
    ]
  }
}
```

- payload 走 stdin；`PreToolUse` exit 2 或输出 `{"decision":"block","reason":...}` 阻断执行，结构化裁决 `{"hookSpecificOutput":{"permissionDecision":"allow|deny|ask","updatedInput":{...}}}` 可免确认/**强制确认**/拒绝/**改写工具入参**，payload 含 session_id/permission_mode/cwd（子进程另有 `$CLAUDE_PROJECT_DIR`）；`PostToolUse` 输出 `{"replacement": "..."}` 替换结果，`Stop` 在回合结束时触发；`UserPromptSubmit`（stdin 含 `prompt`）exit 2 / decision=block 拦截本轮输入，exit 0 的 stdout 或 `hookSpecificOutput.additionalContext` 注入本回合 system 上下文（不进持久化历史）；`Notification` 在工具请求确认时触发（stdin 含 `message`）；`SubagentStop`（stdin 含 `agent_id/agent_task/result_summary`）exit 2 / decision=block 让子代理带着原因继续（受迭代上限兜底）
- 尾部四事件均非阻断：`SessionStart`（stdin 含 `source: startup/resume`）stdout/`additionalContext` 注入**会话级**上下文（此后每回合都前置）；`SessionEnd`（stdin 含 `reason`）在 REPL 退出收口前触发；`PreCompact`（stdin 含 `trigger: manual/auto`）在 `/compact` 与自动摘要压缩前触发；`SubagentStart`（stdin 含 `agent_id/agent_task`）在子代理派生时触发
- 超时强杀；hook 失败不阻断主链路；子代理不触发

**权限**（`~/.mini-claude/settings.json` 或 `<工作区>/.mini-claude/settings.json`）：

```json
{"permissions": {"allow": ["run_command:git *"], "deny": ["run_command:rm *"], "ask": ["write_file:*"]}}
```

- 四模式 shift+tab 循环或 `/permissions <mode>`：default / accept_edits / plan（只读）/ bypass
- 裁决顺序 deny > ask > allow > 模式默认；ask 走确认通道（回复 yes 会话内放行）
- `/permissions` 查看状态，`/hooks` 查看已配 hook

## MCP 支持

REPL 启动时自动连接 `mcp.json` 里配置的 server（stdio 或 streamable HTTP），远端工具以 `mcp__<server>__<tool>` 注册进工具系统，LLM 可直接调用。

```bash
pip install -e ".[mcp]"        # 先装 SDK（pin 1.x）
```

配置文件（`~/.mini-claude/mcp.json` 或 `<工作区>/.mini-claude/mcp.json`，后者覆盖前者同名项，形态对齐 Claude Code）：

```json
{
  "mcpServers": {
    "fs": { "command": "uvx", "args": ["mcp-server-fs"], "trusted": false },
    "remote": { "type": "http", "url": "https://mcp.example.com/mcp", "headers": {"Authorization": "Bearer ..."} },
    "oauthed": { "type": "http", "url": "https://mcp.example.com/mcp", "auth": "oauth" }
  }
}
```

- **transport**：`type` 缺省时按字段推断（有 `command` → stdio 向后兼容、有 `url` → streamable HTTP）；`headers` 透传（放鉴权头）；`sse` 等其他类型 v1 显式拒绝并提示
- **OAuth（http server）**：`"auth": "oauth"`（或 `{"mode": "oauth", "scope": "mcp:read", "callback": "local|paste", "client_name": "..."}`）。连接遇 401 自动走 OAuth 2.0 授权码 + PKCE + 动态客户端注册（RFC 7591）+ 受保护资源发现（RFC 9728）：打印授权 URL → 浏览器回跳由本地回环回调 server 接住（`callback: "local"`，等待超时自动转手动粘贴）；`callback: "paste"` 用 OOB redirect_uri 全程手动粘贴完整回跳 URL——SSH/无浏览器环境的兜底路径。token 落盘 `~/.mini-claude/mcp-auth/<server>.json`（POSIX 0600），过期自动刷新，`/mcp` 状态可见授权与 token 摘要；授权失败/拒绝不阻断其他 server
- **resources/prompts**：server 连接后可用 `mcp_list_resources` / `mcp_read_resource`（server + uri）与 `mcp_list_prompts` / `mcp_get_prompt`（server + name + arguments）只读访问；prompt 可直接作斜杠命令键入——`/mcp__<server>__<prompt> [{json 参数}]` 展开注入输入流（对齐 Claude Code），均不走确认通道
- **确认通道**：未放行的 MCP 工具调用会暂停等待用户回复 `yes`（会话内放行）；`"trusted": true` 的 server 自动放行
- **REPL 命令**：`/mcp` 看状态（含 transport、endpoint 与 OAuth/token 摘要），`/mcp connect <name>` / `disconnect <name>` / `reload` 手动管理
- 子代理默认不可见 MCP 工具；`MCP_ENABLED=false` 可整体关闭

## 配置

复制 `.env.example` 为 `.env`，配置API密钥：

```env
# DeepSeek (默认)
OPENAI_API_KEY=your-deepseek-key
OPENAI_BASE_URL=https://api.deepseek.com

# 或使用其他模型
ANTHROPIC_API_KEY=your-claude-key
GOOGLE_API_KEY=your-gemini-key
```

## 可用工具（28个）

### 文件操作 (8个)
| 工具 | 功能 |
|------|------|
| `read_file` | 读取文件内容 |
| `write_file` | 写入文件（自动检测冲突） |
| `edit_file` | 编辑文件（自动检测冲突） |
| `force_write` | 强制写入文件（忽略冲突） |
| `list_dir` | 列出目录内容 |
| `search_files` | 按名称搜索文件 |
| `search_content` | 按内容搜索文件 |
| `list_locks` | 查看文件锁状态 |

### 命令执行 (4个)
| 工具 | 功能 |
|------|------|
| `run_command` | 执行Shell命令（工作目录与显式 export/set 的环境变量均跨调用持久） |
| `run_background` | 后台执行长时间命令 |
| `task_output` | 读取后台任务输出（对齐 BashOutput） |
| `task_kill` | 终止后台任务（对齐 KillShell） |

### Web (3个)
| 工具 | 功能 |
|------|------|
| `web_search` | Web搜索 |
| `web_fetch` | 抓取网页正文（含 SSRF 防护） |
| `weather` | 天气查询 |

### 任务清单 (5个)
| 工具 | 功能 |
|------|------|
| `todo_write` | 维护会话任务清单（全量提交，清单实时渲染给用户） |
| `task_create` | 创建任务（Task v2：编号、依赖边、可委派） |
| `task_update` | 更新任务状态/字段/依赖边/委派 owner（`deleted` 删除） |
| `task_list` | 列出全部任务（状态/owner/依赖） |
| `task_get` | 查看单个任务详情 |

### Agent协作 (8个)
| 工具 | 功能 |
|------|------|
| `spawn_agent` | 启动单个子Agent（`agent_type` 可选 `.mini-claude/agents/*.md` 自定义类型：专属提示词+工具白名单） |
| `spawn_parallel` | 并行启动多个子Agent（简单模式） |
| `list_agents` | 查看所有子Agent状态 |
| `get_result` | 获取子Agent结果 |
| `plan_parallel` | 规划并行任务（智能模式） |
| `execute_parallel` | 执行并行任务并自动汇总 |
| `parallel_status` | 查看并行执行状态 |
| `aggregate_results` | 汇总并行任务结果 |

## 架构

```
CLI Layer (main.py, repl.py)
    ↓
LLM Layer (LiteLLM Provider)
    ↓
Tool Layer (file_ops, bash, web_search, agent_spawn)
    ↓
Lock Layer (file_lock.py - 并发控制)
```

> 注：`web_fetch/weather/web_search` 为同步阻塞调用，单用户 CLI 下可接受；
> 并行 agent 高频抓取时会互拖，介意者请先用缓存或串行，异步化待排期。

## 项目结构

```
mini-claude/
├── src/mini_claude/
│   ├── cli/          # CLI入口 + 命令处理器
│   ├── agent/        # Agent核心（LangGraph状态机）
│   ├── tools/        # 工具层（22个工具）
│   ├── skills/       # Skills系统（加载/注册/调用）
│   ├── llm/          # LLM抽象层 + 系统提示词
│   ├── config/       # Pydantic配置管理
│   └── utils/        # 工具函数（含file_lock）
└── tests/            # 测试（1772 个用例）
```

## License

MIT
