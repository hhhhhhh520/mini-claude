# Mini Claude Code 项目进度

> 创建时间: 2026-04-13
> 最后更新: 2026-04-14 (LangGraph流程修复)

## 项目概述
**项目地址**: D:\my project\mini-claude
**技术选型**: LangGraph + LiteLLM + Rich + Prompt Toolkit
**目标**: 构建一个迷你版Claude Code，支持多Agent并发处理
**当前状态**: ✅ 全部待办事项已完成

## 当前进度

### ✅ 已完成
| 阶段 | 内容 | 完成日期 |
|------|------|----------|
| Phase 1 | 项目结构初始化 | 2026-04-13 |
| Phase 1 | CLI入口实现（REPL + 命令模式） | 2026-04-13 |
| Phase 1 | LiteLLM多模型集成 | 2026-04-13 |
| Phase 2 | Agent核心实现（LangGraph状态机） | 2026-04-13 |
| Phase 3 | 工具层实现（文件/命令/Agent协作） | 2026-04-13 |
| Phase 4 | 子Agent并发管理 | 2026-04-13 |
| Phase 5 | 单元测试（8/8通过） | 2026-04-13 |
| 配置 | DeepSeek API集成 | 2026-04-13 |
| 修复 | Windows终端编码问题 | 2026-04-13 |
| 修复 | REPL多行输入问题 | 2026-04-14 |
| **TASK-000** | **CLI集成LangGraph状态机** | 2026-04-14 |
| **TASK-001** | **LangGraph循环逻辑优化** | 2026-04-14 |
| **TASK-002** | **工具调用集成到对话流** | 2026-04-14 |
| **TASK-003** | **添加Web搜索工具** | 2026-04-14 |
| **TASK-004** | **会话持久化（SQLite）** | 2026-04-14 |
| **TASK-005** | **文档完善** | 2026-04-14 |

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
| `web_search` | Web搜索（DuckDuckGo） |

## 使用方式

```bash
# REPL交互模式
mini-claude

# 单次问答（支持工具调用）
mini-claude ask "读取README.md文件"
mini-claude ask "搜索Python异步编程最佳实践"

# 查看状态
mini-claude status
```

## 修改历史

### 2026-04-14 LangGraph流程修复
**完成任务**: 启用完整LangGraph状态机流程

**修改文件**:
- src/mini_claude/cli/main.py - 启用 `run_graph()` 替代 `run_simple()`
- src/mini_claude/agent/nodes.py - 修复多轮工具调用和规划逻辑

**修改内容**:
1. `main.py:47` - 改用 LangGraph 状态机模式
2. `act_node` - 根据工具调用和迭代次数决定 `should_continue`
3. `plan_node` - 实现关键词检测和执行计划生成
4. `observe_node` - 检查待处理工具调用，支持多轮迭代

**验收结果**: ✅ 测试全部通过 (8/8)

### 2026-04-14 朝廷工作流完成全部待办事项
**完成任务**:
1. TASK-000: CLI集成LangGraph状态机
2. TASK-001: LangGraph循环逻辑优化
3. TASK-002: 工具调用集成到对话流
4. TASK-003: 添加Web搜索工具
5. TASK-004: 会话持久化（SQLite）
6. TASK-005: 文档完善

**修改文件**:
- src/mini_claude/cli/main.py - 工具调用集成
- src/mini_claude/cli/repl.py - REPL工具调用 + 会话管理
- src/mini_claude/tools/web_search.py - 新增Web搜索工具
- src/mini_claude/utils/session.py - 新增会话持久化
- README.md - 文档更新

**验收结果**: ✅ 通过 (评分: B+)

### 2026-04-13 项目初始化
**修改文件**: 全部核心文件
**修改内容**: 完成MVP版本实现

## 重要决策记录
| 决策 | 选择 | 原因 | 日期 |
|------|------|------|------|
| Agent框架 | LangGraph | 状态机编排，原生支持循环/并行/持久化 | 2026-04-13 |
| LLM抽象 | LiteLLM | 统一接口支持多模型 | 2026-04-13 |
| CLI框架 | Rich + Prompt Toolkit | 富文本显示 + 多行输入 | 2026-04-13 |
| Agent架构 | 主Agent + 可并发子Agent | 保持对话连贯性，支持并行处理 | 2026-04-13 |
| 默认模型 | DeepSeek | 用户提供的API密钥 | 2026-04-13 |
| **工具调用** | **简化模式** | **绕过LangGraph状态传递问题** | 2026-04-14 |
| **Web搜索** | **DuckDuckGo** | **无需API密钥** | 2026-04-14 |
| **会话持久化** | **SQLite** | **轻量级，易于管理** | 2026-04-14 |

## 后续优化建议

1. **高优先级**: 研究LangGraph状态传递机制，修复根本问题
2. **中优先级**: 添加代码分析工具
3. **低优先级**: 添加更多Web工具（如网页抓取）
