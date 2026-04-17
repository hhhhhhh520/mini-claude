# Mini Claude Code

一个迷你版 Claude Code，支持工具调用和多Agent并发处理复杂任务。

## 特性

- **工具调用**：支持文件操作、命令执行、Web搜索等工具
- **主Agent + 子Agent并发**：主Agent保持对话连贯性，可启动多个子Agent并行处理
- **文件锁机制**：支持多Agent安全并行开发同一项目，自动检测冲突
- **多模型支持**：Claude / OpenAI / Gemini / DeepSeek / Ollama
- **混合CLI模式**：REPL交互 + 命令行参数
- **安全设计**：命令白名单、路径验证、用户确认机制

## 安装

```bash
pip install -e .
```

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
```

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

## 可用工具（18个）

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

### 命令执行 (2个)
| 工具 | 功能 |
|------|------|
| `run_command` | 执行Shell命令 |
| `run_background` | 后台执行长时间命令 |

### Web搜索 (1个)
| 工具 | 功能 |
|------|------|
| `web_search` | Web搜索 |

### Agent协作 (7个)
| 工具 | 功能 |
|------|------|
| `spawn_agent` | 启动单个子Agent |
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

## 项目结构

```
mini-claude/
├── src/mini_claude/
│   ├── cli/          # CLI入口
│   ├── agent/        # Agent核心（LangGraph）
│   ├── tools/        # 工具层
│   ├── llm/          # LLM抽象层
│   ├── config/       # 配置管理
│   └── utils/        # 工具函数（含file_lock）
└── tests/            # 单元测试
```

## License

MIT
