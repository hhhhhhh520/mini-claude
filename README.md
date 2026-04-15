# Mini Claude Code

一个迷你版 Claude Code，支持工具调用和多Agent并发处理复杂任务。

## 特性

- **工具调用**：支持文件操作、命令执行、Web搜索等工具
- **主Agent + 子Agent并发**：主Agent保持对话连贯性，可启动多个子Agent并行处理
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
| `write_file` | 写入文件 |
| `edit_file` | 编辑文件 |
| `list_dir` | 列出目录内容 |
| `search_files` | 按名称搜索文件 |
| `search_content` | 按内容搜索文件 |
| `run_command` | 执行Shell命令 |
| `web_search` | Web搜索 |

## 架构

```
CLI Layer (main.py, repl.py)
    ↓
LLM Layer (LiteLLM Provider)
    ↓
Tool Layer (file_ops, bash, web_search, agent_spawn)
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
│   └── utils/        # 工具函数
└── tests/            # 单元测试
```

## License

MIT
