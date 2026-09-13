# Mini Claude Code 项目规范

## 项目概述

基于 LangGraph 状态机与 LiteLLM 统一接口的多 Agent CLI 编程助手。

**核心特性**:
- THINK→PLAN→ACT→OBSERVE 四阶段状态机循环
- 支持 Claude/OpenAI/DeepSeek/Gemini/Ollama 五种模型提供商
- 21个工具：文件操作、命令执行、Web搜索、Agent协作
- 子 Agent 并行执行 + 文件锁机制
- SQLite 会话持久化 + REPL 交互

## 安全约束

### 命令白名单禁止项

以下命令/flag 已从白名单移除，不可恢复：
- `python -c` / `python3 -c` — 允许任意代码执行
- `node -e` — 允许任意代码执行
- `find -exec` — 允许任意命令执行
- `python -m subprocess/os/sys/ctypes/runpy/http.server/webbrowser/telnetlib/ftplib` — 模块级黑名单（匹配模块本身及其任意父包，带点条目如 `http.server` 同样生效）
- `pip install` / `pip3 install` / `pip -r/-e`（含 `python -m pip ...` 形式）— 供应链敞口，进 confirmation（拒+文案，与 `pip uninstall` 对称，ISSUE-019）
- `python <带目录成分的.py>` 在工作区外拒绝（`validate_path`）；纯文件名放行是刻意保留的旧行为，改白名单时别顺手堵死

### 文件操作安全

- `edit_file` 使用 `check_file_write`（非 `check_file_read`），阻止编辑工作区外文件
- `web_fetch` 阻断 SSRF：禁止 localhost、私有 IP、link-local、file:// 协议；域名通过 `socket.getaddrinfo()` 预解析 IP 防 DNS 重绑定；手动重定向循环（最多 5 跳），每跳校验目标地址
- 文件写入使用 temp+rename 原子操作，防止进程崩溃导致文件损坏
- Windows symlink 检查使用 `pathlib.resolve()`，正确处理 8.3 短名称
- Shell 注入检查覆盖 `|`, `>`, `>>`, `&`（`&&` 与裸 `&`）, `<`, `^`, `(`, `)` 元字符（引号感知，引号内放行）

### 子代理隔离

- 子代理白名单定义在 `SpawnAgentTool.ALLOWED_TOOLS` 类常量（非硬编码）
- 子代理模式使用 `contextvars` 实现 asyncio 协程级隔离，无竞态条件
- 子代理禁止 `run_command`、`spawn_agent`、`spawn_parallel`

### Checkpoint 与会话

- `graph.py` 使用 `AsyncSqliteSaver`（SQLite 持久化），路径由 `settings.session_db_path` 决定
- `build_agent_graph()` 只能在**运行中的事件循环**里调用（saver 构造执行 `get_running_loop()`），同步上下文调用抛 RuntimeError
- 进程退出必须 `await close_checkpoint_connections()`（`repl.run_graph` 的 finally 已接）——aiosqlite worker 线程非 daemon 且被登记表强引用，漏关 = 解释器退出挂死
- 子代理必须用 `build_agent_graph_no_checkpoint()`（不带 checkpoint），不可用主 graph
- REPL 启动时检测 SQLite checkpoint，提示用户是否恢复上次会话
- 不可改回 `MemorySaver` — 进程退出后状态丢失，`/resume` 命令失效

### 工具降级

- `ToolRegistry.execute()` 集成了 `ToolDegradation` — 连续失败 3 次自动跳过工具
- 工具执行成功/失败会自动记录到降级管理器
- 10 分钟后自动重置失败计数
- 修改工具执行逻辑时不可移除降级检查

### CLI 约束

- `ask --json` 只打最终 JSON 一行（中间输出全静默），失败打 `{"error": ...}` 再 exit 1
- 任何退出路径（ask/repl/未来新入口）都要进 `finally` 清后台进程 + 关 checkpoint 连接

## LangGraph 约束

- `AgentState.messages` 是 `Annotated[List[BaseMessage], add]`（累加语义）：节点**只能返回增量**，返回全量列表会把已有消息再拼一份（用户消息被复制、SystemMessage 错位——2026-09-04 修过一次，见 issues/ISSUE-014）
- 系统提示与 skills **不写入** `state["messages"]`：由 `act_node` 在每次 LLM 调用时经 `build_system_messages()` 前置（不进持久化历史、不被摘要/截断吃掉）
- 工具错误检测禁止对消息正文做自然语言关键词匹配（会误判正常中文输出、放大注入文本），只认结构化标记——见 `observe._is_tool_error_message`（`Error` 前缀 / 包裹边界 / 固定异常前缀）

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
- [ ] 改动 `agent/nodes/` 或 `graph.py` 后必须跑 `tests/test_integration/test_graph_checkpoint.py`（节点级测试看不到 reducer 合并后的状态与 checkpointer 装配）
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
