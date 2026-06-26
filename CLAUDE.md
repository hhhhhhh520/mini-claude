# Mini Claude Code 项目规范

## 项目概述

基于 LangGraph 状态机与 LiteLLM 统一接口的多 Agent CLI 编程助手。

**核心特性**:
- THINK→PLAN→ACT→OBSERVE 四阶段状态机循环
- 支持 Claude/OpenAI/DeepSeek/Gemini/Ollama 五种模型提供商
- 18个工具：文件操作、命令执行、Web搜索、Agent协作
- 子 Agent 并行执行 + 文件锁机制
- SQLite 会话持久化 + REPL 交互

## 安全约束

### 命令白名单禁止项

以下命令/flag 已从白名单移除，不可恢复：
- `python -c` / `python3 -c` — 允许任意代码执行
- `node -e` — 允许任意代码执行
- `find -exec` — 允许任意命令执行

### 文件操作安全

- `edit_file` 使用 `check_file_write`（非 `check_file_read`），阻止编辑工作区外文件
- `web_fetch` 阻断 SSRF：禁止 localhost、私有 IP、link-local、file:// 协议
- 文件写入使用 temp+rename 原子操作，防止进程崩溃导致文件损坏
- Windows symlink 检查使用 `pathlib.resolve()`，正确处理 8.3 短名称

### 子代理隔离

- 子代理白名单定义在 `SpawnAgentTool.ALLOWED_TOOLS` 类常量（非硬编码）
- 子代理模式使用 `contextvars` 实现 asyncio 协程级隔离，无竞态条件
- 子代理禁止 `run_command`、`spawn_agent`、`spawn_parallel`

### Checkpoint 与会话

- `graph.py` 使用 `AsyncSqliteSaver`（SQLite 持久化），路径由 `settings.session_db_path` 决定
- 子代理必须用 `build_agent_graph_no_checkpoint()`（不带 checkpoint），不可用主 graph
- REPL 启动时检测 SQLite checkpoint，提示用户是否恢复上次会话
- 不可改回 `MemorySaver` — 进程退出后状态丢失，`/resume` 命令失效

### 工具降级

- `ToolRegistry.execute()` 集成了 `ToolDegradation` — 连续失败 3 次自动跳过工具
- 工具执行成功/失败会自动记录到降级管理器
- 10 分钟后自动重置失败计数
- 修改工具执行逻辑时不可移除降级检查

## 问题修复原则（强制）

以下规则不可违反：

### 1. 发现报错立即修复
- 每次运行命令后必须检查输出
- 看到 Error/Exception/Traceback 必须立即处理
- 不允许跳过、忽略、或说"稍后处理"

### 2. 测试必须覆盖实际场景
- 单元测试通过不代表功能正常
- 必须运行端到端测试验证实际功能

### 3. 追根溯源
- 遇到问题必须找到根本原因
- 不允许表面修补（如只改提示词而不改逻辑）
- 必须在 issues/ 目录记录根本原因

## 测试清单

每次修改后必须测试：
- [ ] 单元测试：`pytest tests/ -v`
- [ ] 单文件创建
- [ ] 多文件创建
- [ ] 并行执行 (plan_parallel + execute_parallel)

## 问题记录

所有问题记录在 `issues/` 目录，格式：
```markdown
# 问题简述
> 创建时间: YYYY-MM-DD
> 状态: 🟢 已解决 / 🔴 未解决

## 问题描述
## 出现原因（根本原因）
## 解决方案
## 相关文件
```
