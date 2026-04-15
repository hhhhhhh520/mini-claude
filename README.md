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

### 文件锁机制

- **读锁**：多个 Agent 可同时读取同一文件
- **写锁**：写文件时获取独占锁，阻止其他 Agent 同时写入
- **冲突检测**：写入前检查文件是否被其他 Agent 修改过

### 并行开发示例

```
> 并行开发三个功能：
1. 在 src/api/ 创建 user.py 处理用户API
2. 在 src/api/ 创建 product.py 处理产品API
3. 在 src/api/ 创建 order.py 处理订单API
```

每个子 Agent 会独立工作，文件锁确保不会互相覆盖。

### 冲突处理

当检测到冲突时，会提示：

```
Error: Conflict detected - File was modified by another agent.
Original hash: a1b2c3d4..., Current hash: e5f6g7h8...
Use 'force_write' to overwrite.
```

使用 `force_write` 工具可以强制覆盖（谨慎使用）。

### 锁管理工具

| 工具 | 功能 |
|------|------|
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

## 可用工具

| 工具 | 功能 |
|------|------|
| `read_file` | 读取文件内容 |
| `write_file` | 写入文件（自动检测冲突） |
| `edit_file` | 编辑文件（自动检测冲突） |
| `list_dir` | 列出目录内容 |
| `search_files` | 按名称搜索文件 |
| `search_content` | 按内容搜索文件 |
| `run_command` | 执行Shell命令 |
| `web_search` | Web搜索 |
| `spawn_agent` | 启动单个子Agent |
| `spawn_parallel` | 并行启动多个子Agent |
| `list_agents` | 查看所有子Agent状态 |
| `get_result` | 获取子Agent结果 |
| `list_locks` | 查看文件锁状态 |
| `force_write` | 强制写入文件 |

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
