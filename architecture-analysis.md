# Mini Claude Code 架构分析报告

> 分析时间: 2026-04-30
> 项目路径: D:\my project\mini-claude

---

## 架构分层概览

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLI Layer (入口层)                        │
│  main.py (Click CLI)  │  repl.py (交互式REPL)  │  display.py    │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                        Agent Layer (Agent层)                     │
│    graph.py (LangGraph状态机)  │  nodes.py (节点: Think/Plan/Act/Observe)  │
│    state.py (状态定义)  │  subagent.py (子Agent管理)  │  coordinator.py │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                       Services Layer (服务层)                    │
│    llm/provider.py (LiteLLM统一接口)  │  llm/prompts.py (提示词)  │
│    utils/safety.py (安全检查)  │  utils/file_lock.py (文件锁)    │
│    utils/session.py (会话持久化)  │  utils/memory.py (已弃用)    │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                        Tools Layer (工具层)                      │
│  tools/base.py (基类+注册表)                                      │
│  ├─ tools/file_ops.py (文件操作: read/write/edit/list/search)    │
│  ├─ tools/bash.py (命令执行)                                      │
│  ├─ tools/web_search.py (网络搜索)                                │
│  ├─ tools/agent_spawn.py (子Agent生成)                            │
│  └─ tools/parallel.py (并行执行规划)                              │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                        Config Layer (配置层)                     │
│    config/settings.py (Pydantic配置)  │  .env (环境变量)         │
└─────────────────────────────────────────────────────────────────┘
```

---

## 详细分层说明

### 1. CLI Layer (入口层)

| 文件 | 职责 | 核心功能 |
|------|------|----------|
| `cli/main.py` | CLI入口点 | Click命令定义、REPL启动、单次问答 |
| `cli/repl.py` | 交互式REPL | LangGraph状态机驱动、命令处理、会话历史 |
| `cli/display.py` | 输出展示 | Rich格式化、流式输出、工具调用展示 |

**依赖关系:**
- CLI → Agent (调用LangGraph状态机)
- CLI → Config (读取配置)
- CLI → Tools (执行工具)

---

### 2. Agent Layer (Agent层)

| 文件 | 职责 | 核心功能 |
|------|------|----------|
| `agent/graph.py` | LangGraph状态机 | THINK→PLAN→ACT→OBSERVE循环定义 |
| `agent/nodes.py` | 图节点实现 | think_node, plan_node, act_node, observe_node |
| `agent/state.py` | 状态定义 | AgentState TypedDict，会话状态管理 |
| `agent/subagent.py` | 子Agent管理 | SubAgentManager，并发信号量控制 |
| `agent/coordinator.py` | 并行协调器 | 任务依赖分析、拓扑排序、结果聚合 |

**依赖关系:**
- Agent → LLM Services (调用LLM)
- Agent → Tools (执行工具)
- Agent → Config (读取配置)

**关键设计:**
- LangGraph状态机驱动，支持checkpointer持久化
- 子Agent通过信号量控制并发数(默认3个)
- 任务依赖通过拓扑排序确定执行顺序

---

### 3. Services Layer (服务层)

| 文件 | 职责 | 核心功能 |
|------|------|----------|
| `llm/provider.py` | LLM统一接口 | LiteLLM封装，支持Claude/OpenAI/DeepSeek/Gemini/Ollama |
| `llm/prompts.py` | 提示词管理 | 系统提示词、子Agent提示词、规划提示词 |
| `utils/safety.py` | 安全检查 | 命令验证、路径验证、危险操作拦截 |
| `utils/file_lock.py` | 文件锁管理 | 读写锁、冲突检测、版本追踪 |
| `utils/session.py` | 会话持久化 | SQLite存储、会话加载/保存 |

**依赖关系:**
- Services → Config (读取配置)
- Services独立于Agent，可被多层调用

**关键设计:**
- LiteLLM统一多个LLM提供商API
- 文件锁支持读写分离、乐观锁冲突检测
- 安全检查拦截危险命令和路径穿越攻击

---

### 4. Tools Layer (工具层)

| 文件 | 职责 | 工具列表 |
|------|------|----------|
| `tools/base.py` | 工具基类+注册表 | BaseTool, ToolRegistry |
| `tools/file_ops.py` | 文件操作 | read_file, write_file, edit_file, list_dir, search_files, search_content, list_locks, force_write |
| `tools/bash.py` | 命令执行 | run_command, run_background |
| `tools/web_search.py` | 网络搜索 | web_search (DuckDuckGo) |
| `tools/agent_spawn.py` | 子Agent生成 | spawn_agent, list_agents, get_result, spawn_parallel |
| `tools/parallel.py` | 并行执行 | plan_parallel, execute_parallel, parallel_status, aggregate_results |

**依赖关系:**
- Tools → Services (安全检查、文件锁)
- Tools → Config (工作空间路径)

**关键设计:**
- 工具注册表模式，支持动态注册
- 文件工具集成锁机制，支持多Agent并发写
- 子Agent工具限制工具集，防止无限递归

---

### 5. Config Layer (配置层)

| 文件 | 职责 | 核心功能 |
|------|------|----------|
| `config/settings.py` | Pydantic配置 | API密钥、模型设置、Agent参数、工作空间 |

**配置项:**
- API密钥: Anthropic, OpenAI, Google
- 模型设置: default_model, ollama_base_url
- Agent参数: max_sub_agents(3), max_iterations(10), max_subagent_iterations(5)
- 会话设置: auto_save_enabled, session_db_path
- 工作空间: workspace_root

---

## 依赖图

```
CLI Layer
    │
    ├──▶ Agent Layer
    │        │
    │        ├──▶ Services Layer
    │        │        │
    │        │        └──▶ Config Layer
    │        │
    │        └──▶ Tools Layer
    │                 │
    │                 └──▶ Services Layer
    │
    └──▶ Config Layer
```

---

## 核心数据流

### 用户请求处理流程

```
用户输入 (CLI)
    │
    ▼
REPLSession.run_graph()
    │
    ▼
LangGraph State Machine
    │
    ├──▶ THINK: 分析请求，加载系统提示
    │
    ├──▶ PLAN: 制定执行计划
    │
    ├──▶ ACT: 调用LLM，执行工具
    │        │
    │        ├──▶ LLMProvider.chat_stream_with_tools()
    │        │
    │        └──▶ execute_tool() → ToolRegistry.execute()
    │
    ├──▶ OBSERVE: 处理结果，决定是否继续
    │
    └──▶ 循环或结束
```

### 并行Agent执行流程

```
spawn_parallel / execute_parallel
    │
    ▼
ParallelCoordinator.analyze_dependencies()
    │
    ▼
拓扑排序 → 执行层级
    │
    ▼
asyncio.gather() 并发执行
    │
    ├──▶ Agent 1: build_agent_graph_no_checkpoint()
    ├──▶ Agent 2: build_agent_graph_no_checkpoint()
    └──▶ Agent N: build_agent_graph_no_checkpoint()
    │
    ▼
aggregate_results() 结果聚合
```

---

## 文件统计

| 层 | 文件数 | 主要职责 |
|----|--------|----------|
| CLI Layer | 3 | 用户交互入口 |
| Agent Layer | 5 | 状态机与并发控制 |
| Services Layer | 5 | LLM、安全、锁、会话 |
| Tools Layer | 6 | 16个工具实现 |
| Config Layer | 1 | 配置管理 |
| **总计** | **20** | - |

---

## 技术栈

| 类别 | 技术 |
|------|------|
| 状态机框架 | LangGraph |
| LLM统一接口 | LiteLLM |
| CLI框架 | Click + prompt-toolkit |
| 输出格式化 | Rich |
| 配置管理 | Pydantic Settings |
| 数据持久化 | SQLite (aiosqlite) |
| 异步框架 | asyncio |

---

## 设计亮点

1. **LangGraph状态机**: THINK→PLAN→ACT→OBSERVE循环，清晰的状态流转
2. **多LLM支持**: 通过LiteLLM统一Claude/OpenAI/DeepSeek/Gemini/Ollama
3. **并发Agent**: 信号量控制并发数，依赖拓扑排序，结果自动聚合
4. **文件锁机制**: 读写锁分离，乐观锁冲突检测，版本追踪
5. **安全检查**: 危险命令拦截，路径穿越防护，Shell注入检测
6. **流式输出**: 支持LLM token流式输出，实时展示思考过程

---

## 改进建议

1. **memory.py已弃用**: 可考虑删除，统一使用session.py
2. **测试覆盖**: 当前tests目录主要包含__init__.py，可增加单元测试
3. **日志系统**: 当前使用print调试，可引入logging模块
4. **错误处理**: 部分异常处理可更细化，提供更友好的错误提示
