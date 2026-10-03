# Mini Claude Code 项目规范

## 项目概述

基于 LangGraph 状态机与 LiteLLM 统一接口的多 Agent CLI 编程助手。

**核心特性**:
- THINK→PLAN→ACT→OBSERVE 四阶段状态机循环
- 支持 Claude/OpenAI/DeepSeek/Gemini/Ollama 五种模型提供商
- 22个内置工具：文件操作、命令执行、Web搜索、Agent协作、任务清单；另有 MCP 动态工具（mcp__ 前缀）
- Hooks（PreToolUse/PostToolUse/Stop）与权限（四模式+allow/ask/deny）都在 ToolRegistry.execute 单一裁决点收口
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

### 敏感路径守卫（2026-10-02 拍板）

- `SENSITIVE_PATH_PATTERNS`（safety.py，检查在白名单之前，双命令工具共用 `validate_command` 单点生效）：命令文本命中 `.env`（example/sample/template/dist 模板变体放行）/`.ssh`/`id_rsa`/`id_ed25519`/`mcp-auth`/`*.pem`/`credentials` 即硬拒——密钥与凭据文件禁止经命令通道访问
- **已知边界（刻意接受，勿"顺手修复"）**：路径沙箱只约束文件工具；命令通道对非敏感的沙箱外文件仍可读（对标本体是权限制而非硬沙箱，REPL 危险命令走 ask 门槛）。`.env` 真密钥已由守卫硬拒；要进一步收紧读面属安全策略变更，需单独评审

### 文件操作安全

- `/rewind` 的代码回退依赖 `utils/file_history.py` 会话日志：**只有走 `_atomic_write` 的三个工具（write/edit/force_write）被记录**，run_command 等侧门修改与跨会话修改不在恢复范围（诚实边界，勿对外夸大）；日志同路径只记最早一次、回放即消费；`_atomic_write` 里 `record_before_write` 必须在任何写动作之前，且失败静默（旁路设施不弄断写入）

- `edit_file` 使用 `check_file_write`（非 `check_file_read`），阻止编辑工作区外文件
- 多工作目录（`/add-dir`）：额外根注册在 `safety._additional_roots`（会话级），`validate_path` 三处 workspace 比较点以 OR 并入；主 workspace 的既有比较逻辑不动，额外根走 `_within_roots`（**必须带 os.sep 守卫**——根 `D:\proj` 不得放行 `D:\projects`）；PROTECTED_PATHS 与穿越检查不因多根放松
- `web_fetch` 阻断 SSRF：禁止 localhost、私有 IP、link-local、file:// 协议；域名通过 `socket.getaddrinfo()` 预解析 IP 防 DNS 重绑定；手动重定向循环（最多 5 跳），每跳校验目标地址
- 文件写入使用 temp+rename 原子操作，防止进程崩溃导致文件损坏
- Windows symlink 检查使用 `pathlib.resolve()`，正确处理 8.3 短名称
- Shell 注入检查覆盖 `|`, `>`, `>>`, `&`（`&&` 与裸 `&`）, `<`, `^`, `(`, `)` 元字符（引号感知，引号内放行）

### 子代理隔离

- 子代理白名单定义在 `SpawnAgentTool.ALLOWED_TOOLS` 类常量（非硬编码）
- 子代理模式使用 `contextvars` 实现 asyncio 协程级隔离，无竞态条件
- 子代理禁止 `run_command`、`spawn_agent`、`spawn_parallel`

### Hooks 与权限约束

- ToolRegistry.execute 裁决链顺序（收敛批次①）：**PreToolUse hook 先于权限门**——hook 可 deny 阻断、`permissionDecision=allow` 免确认（跳过 ask）、**`permissionDecision=ask` 强制确认**（无视规则/模式直接走确认通道）、`updatedInput` 改写入参（喂给权限匹配与执行）；多值同现时 deny > ask > allow；hook 的 allow/ask 只有前置于权限门才有意义，改顺序前先想清楚
- `permissionDecision="ask"` 已支持（收敛批次②A 补全，三值语义无分歧）；payload 带 session_id/permission_mode/cwd，子进程有 `$CLAUDE_PROJECT_DIR`

- Hooks 事件面十事件（PreToolUse/PostToolUse/Stop/UserPromptSubmit/Notification/SubagentStop/SessionStart/SessionEnd/PreCompact/SubagentStart）；hook 失败/超时不阻断主链路（UserPromptSubmit/SubagentStop 的 exit 2 阻断除外）。尾部四事件均非阻断：SessionStart 的 stdout/`hookSpecificOutput.additionalContext` 注入会话级上下文（repl 存 `_session_hook_context`，每回合与 UserPromptSubmit 上下文合并进 `hook_context`）；SessionEnd/PreCompact/SubagentStart 只触发不判断
- `AgentState.hook_context` 是**全量替换语义**：`create_turn_increment` 每轮必须带值（空串=清空上一轮注入），act 经 `build_system_messages(hook_context=...)` 前置、不进持久化历史——漏带值会让 checkpoint 沿用旧回合的注入

- 挂点只在 `ToolRegistry.execute()`（与降级管理器同位置）；子代理跳过双门（有自己的白名单）
- 裁决顺序固定 deny > ask > allow > 模式默认，改顺序前先跑 test_manager.py 的顺序测试
- hook 命令经 shell 执行且超时强杀——hook 是用户受信配置，不走安全白名单（白名单管 LLM）
- 权限 ask / MCP 确认 / 路径确认都汇入 pending_confirmation_path，前缀路由收敛在 utils/confirmations.py，加新前缀先改这里
- 新的退出资源（连接/子进程）必须进 run_graph 的 finally

### MCP 约束

- SDK 严格 pin `mcp>=1.30.0,<2.0.0`——2.x 改了公开 API（FastMCP→MCPServer），未验证不跟（ISSUE-024 同款纪律）
- MCP 工具默认走确认通道（McpConfirmationRequired → WAITING_CONFIRMATION → 'yes' 放行）；`trusted: true` 的 server 自动放行
- 连接的 stdio 子进程 + anyio 任务非 daemon 级资源：`run_graph` 的 finally 必须调 `close_mcp_connections()`
- 子代理白名单（两处 ALLOWED_TOOLS）不得加入 mcp__ 工具
- 放行记录只存会话内存，重启后重新确认——这是刻意设计，别"优化"成持久化
- **连接失败的异常翻译是红线**：授权流/初始化在 SDK 任务组内失败时，原始异常被取消风暴顶掉（伪装成 "Cancelled via cancel scope" 或含取消成员的异常组）——`_open_connection` 收口必须吞次生异常保原始异常、经 `_extract_connect_failure` 还原真实原因后包成 `McpConnectError`/`McpOAuthError`；裸放 CancelledError 会穿透 connect_all 炸掉主链路（实测）。收口 aclose 只能在进入连接的同一任务里直接 await（ISSUE-029 同族）
- **OAuth（http server 的 auth 配置）**：复用 SDK `OAuthClientProvider`（PKCE/动态注册/RFC 9728 发现/刷新都在 SDK 内），本项目只做回调交互（mcp/oauth.py：本地回环 server + OOB 粘贴兜底）、token 文件落盘（mcp/token_store.py，SDK 无关纯 I/O）与装配；授权 URL 展示靠 `_default_notify`（可注入）；mcp/token_store.py 与 mcp/oauth.py 顶层不得 import mcp——CI 无 SDK 环境必须可收集

- **ask 模式与 REPL 共用系统消息装配**：`build_system_messages` 在 `llm/prompts.py`（含 `<env>` 环境块：沙箱根/OS/shell 习惯）。ask/cli 层从这里导入，**不得从 `agent.nodes._shared` 导入**——那是 agent 层内部件，层级错位（它曾有导入期 LLMProvider 单例副作用并引发跨测试污染，2026-10-03 已改懒加载拔根，红线保留为层级纪律）
- **`llm_provider` 是懒加载单例（2026-10-03）**：任何模块**不得在 import 期按名绑定** `from ._shared import llm_provider`——懒加载下绑到的是 None，运行即炸；必须经 `get_llm_provider()` 访问器取用（/model 热切换重建单例，ISSUE-024 同款纪律）。测试注入走 `cli.main._build_ask_llm` 缝或按属性 patch `_shared.llm_provider`，不全局替换 LLMProvider 类
- 确认类异常（PathConfirmationRequired/McpConfirmationRequired/PermissionAskRequired）在 ask 模式经 `_execute_ask_tool` 翻译成可读工具错误回流 LLM——ask 无法交互确认，裸抛即炸循环

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

### 依赖与 CI 约束

- 装包一律带锁合面：`pip install -e ".[dev]" -c constraints.txt`，与 CI 完全一致；升级依赖是显式动作（改 pin → 本地两层全绿 + 不可达端点全绿 → 推送盯 CI）
- web 工具必须用 `tools/_http.py` 的共享 httpx client：**每次新建 AsyncClient 会同步加载 SSL 证书库（~0.2s），在事件循环上就是全局冻结**；新增占用资源的退出清理（client/checkpoint/MCP/后台进程）一律挂进 repl 与 ask 的 finally 清理链
- CI 有 integration 层 job（每次 push 跑，`OPENAI_BASE_URL` 指向不可达端口）：integration 层测试承诺全 mock，打真网即红——新增 integration 测试必须遵守该承诺
- `config/settings` 只允许 `settings/` 包一个实体，禁止再造同名 `.py` shim（曾因双名并存 + `config/__init__` re-export 实例，导致 `import ...settings as m` 拿到 Settings 实例而非模块、py3.10 mock 字符串目标解析错乱）

## LangGraph 约束

- `AgentState.messages` 是 `Annotated[List[BaseMessage], add]`（累加语义）：节点**只能返回增量**，返回全量列表会把已有消息再拼一份（用户消息被复制、SystemMessage 错位——2026-09-04 修过一次，见 issues/ISSUE-014）
- **缩减持久化历史只有一条路：播种新 thread**（`/compact` 的做法）：messages 挂裸 `add`，`aupdate_state` 走同一 reducer 只能拼接；压缩结果写入全新 thread_id 即纯替换，旧线程 checkpoint 链保留，会话切换后 `_rewind_configurable` 必须作废。act 内 `handle_token_budget` 的自动压缩只作用于当次 prompt，**不回写 checkpoint**
- 摘要/截断产物的近端尾部可能切在 assistant(tool_calls) 与 tool 结果中间——持久化前必须修剪孤儿 tool 结果（`compact_handler._drop_orphan_tool_results`），否则违反下一条线格式红线
- **Task v2（tools/tasks.py）的 state.tasks 是唯一事实源**：全量替换语义（与 todos 同纪律，不进 turn increment）；工具拿不到 state，act 每轮派发前把 state.tasks 传入 execute_single_tool、变更经 `state_extras["tasks"]` 全量替换回 state；模块级 store 只服务 ask 无 checkpoint 场景，**act 每轮必须用 state.tasks 覆盖 store**（rewind 分叉才不会发散）。task_create/task_update/task_list/task_get 在 execute_single_tool 特化分支处理，不走通用 execute_tool
- **工具结果一律 `ToolMessage` 回传（role=tool + tool_call_id + status），禁止 HumanMessage 文本**；assistant 历史消息必须携带 tool_calls 不许剥（ISSUE-026：Qwen 类网关按消息形状判定函数调用模式，形状偏离即从第二轮起退化为 `<tool_call>` 正文）。确认挂起标 `status="success"`（挂起不是执行错误）；改工具循环必须含"真 key 多步任务 E2E 无泄漏"验收
- checkpoint 序列化类型必须注册 serde 白名单（`graph.py` JsonPlusSerializer `allowed_msgpack_modules`），CI 已开 `LANGGRAPH_STRICT_MSGPACK=true`——往 state 塞新自定义类型时同步注册，否则 CI 硬失败（ISSUE-027）
- 系统提示与 skills **不写入** `state["messages"]`：由 `act_node` 在每次 LLM 调用时经 `build_system_messages()` 前置（不进持久化历史、不被摘要/截断吃掉）
- CLAUDE.md 加载链与 @import（utils/claudemd.py）：用户级 → 项目级 → CLAUDE.local.md；`@path` 引用最多 5 跳防环；**改展开逻辑必须保持两个语义**——总量字符预算全局共享递减、缺失引用原文保留
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
