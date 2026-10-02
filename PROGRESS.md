# Mini Claude Code 项目进度

> 创建时间: 2026-04-13
> 最后更新: 2026-10-02 (双条目：MCP OAuth http transport；任务完成能力实测与四洞修复——
> ask 接入系统提示词+env 块、确认异常回流、轮数 25。测试收集 2304)

## 项目概述
**项目地址**: D:\my project\mini-claude
**技术选型**: LangGraph + LiteLLM + Rich + Prompt Toolkit
**目标**: 构建一个迷你版Claude Code，支持多Agent并发处理
**当前状态**: ⚠️ REPL 主链路已于 2026-09-04 修复；收集 1735 = 1691 passed / 4 failed / 40 skipped
> （4 个失败：3 个 `402 Insufficient Balance` 真实 API 依赖、1 个 `test_settings` 由本地
> gitignored `.env` 覆盖默认模型，均与本改动无关。此前的 `test_token_summary_generation`
> summarize 用例已修复转绿。）
> 覆盖率暂不可测（`pytest-cov` 未装，详见 2026-09-04 小节）。

> 此前长期记载的「1673 测试通过」「核心功能完成」不成立：`langgraph-checkpoint-sqlite`
> 未装入环境时 `pytest tests/` 在收集阶段即中断，一个测试都跑不完；装上后又暴露
> `build_agent_graph()` 的 checkpointer 装配错误（见下方 2026-09-04 小节）。
> 完整问题清单：`issues/ISSUE-012-0628Review修复失效项.md`

## 当前进度

### ✅ 已完成（按阶段汇总）

| 阶段 | 内容 | 完成日期 |
|------|------|----------|
| Phase 1-5 | 核心功能：CLI/LLM集成/状态机/工具层/子Agent并发/初始测试 | 2026-04-13 ~ 2026-04-17 |
| P0 系列 | Token预算/结构化日志/对话摘要压缩 | 2026-04-30 ~ 2026-05-01 |
| P1 系列 | 自动降级/长期记忆/Reflexion反思/系统提示自我认知 | 2026-05-02 |
| P2 系列 | Prometheus指标/健康检查/安全过滤/速率限制/工具缓存/依赖管理/链路追踪/告警 | 2026-05-02 |
| P3 系列 | 错误通知/断点续跑/日志导出/用户建议/配置热更新/多环境/集成测试/压力测试/混沌测试/回归测试 | 2026-05-03 |
| P0 安全 | 命令白名单/Prompt注入防护/子代理run_command移除 | 2026-05-10 |
| CI修复 | Windows 8.3路径/mock问题/编码问题 | 2026-05-12 |
| 新功能 | Skills系统（加载/注册/调用/自动匹配） | 2026-05-13 |
| Bug修复 | 流式输出重复显示 | 2026-05-13 |
| 代码审查 | 7项修复（mock路径/死代码/返回值检查/CI过滤/断言加强） | 2026-06-18 |
| **代码审查** | **14项修复（安全漏洞/逻辑错误/功能缺陷/测试质量）** | **2026-06-25** |
| **待办修复** | **11项修复（并发安全/数据一致性/LLM健壮性/功能接入）** | **2026-06-26** |
| **第三轮审查** | **11项修复（测试回归/安全加固/死代码/逻辑错误）** | **2026-06-26** |
| **CI 修复** | **4项修复（依赖缺失/Windows 短路径/测试适配）** | **2026-06-26** |
| **多角度审查** | **5项修复（错误检测死代码/SSRF DNS重绑定/测试断言/进程清理/模块黑名单）** | **2026-06-26** |
| **多角度Review** | **8项修复（shell元字符/SSRF重定向/eval正则/模块黑名单/死代码清理/依赖修正/错误脱敏）** | **2026-06-28** |
| **主链路修复** | **checkpointer 装配错误 + 9 个图级契约测试 + 连接生命周期收尾** | **2026-09-04** |
| **补齐 06-28 遗漏** | **4 项 ❌：python -m 带点黑名单 / 裸 & 元字符 / observe 信任边界 / 回归脚本悬空引用** | **2026-09-04** |
| **对话正确性** | **reducer 消息重复 + summarize 用例未触发压缩（两处真逻辑缺陷）** | **2026-09-04** |
| **对标加固** | **constraints.txt 依赖锁合面 + CI integration 层 job（不可达端点护栏）+ 删 settings.py 死 shim** | **2026-09-28** |

### ⏳ 进行中

| 任务 | 状态 | 说明 |
|------|------|------|
| 假测试清理 | 待继续 | 部分测试断言过于宽泛或验证自身常量 |
| 覆盖率重测 | pytest-cov 未装，覆盖率不可测 | 先 `pip install -e ".[dev]"` 补齐 dev 依赖，再建覆盖率基线 |

### 📋 待办

| 优先级 | 任务 | 说明 |
|--------|------|------|
| 中 | 假测试清理 | ~52 个虚弱测试（弱断言/无断言/验证 Python 机制），待逐个加固 |
| 中 | 覆盖率重测 | 09-14 起 `pyproject` 已补 `vector/tracing/server` extras 与 `tiktoken` 硬依赖；本地先 `pip install -e ".[dev]"` 建基线，再卡 `fail_under=60` |
| 低 | caplog 测试顺序问题 | `init_logging()` 设 `propagate=False` 致后跑的 36 个 `test_prompts` 收不到 caplog；`pytest tests/test_utils tests/test_llm/test_prompts.py` 可复现 |
| 低 | reflect_node 异常吞没 | 非关键节点，但应至少记 ERROR 日志 |
| 低 | 无测试覆盖模块 | ~15 个源模块无测试（`observe.py`、`web_fetch.py` 等核心路径优先） |
| 低 | ~~同步 HTTP~~ | 已结（2026-09-28）：web 三件套全部异步化（httpx 共享 client + to_thread），见当日节 |

## 2026-10-02 任务完成能力实测与四洞修复（ask 模式对齐）

**起因**：2×2 真机实测（qwen3.8-flash，有无环境提示 × FizzBuzz 自验证任务/源码定位任务）
暴露四个洞——修复前无提示两任务全败（代码一次写对，10 轮预算烧在环境试错上）。

### 四个洞与修复

| 洞 | 修复 |
|---|---|
| ① 系统提示词无环境信息（OS/shell/工作区路径）——模型猜 `/workspace`、在 cmd 用 ls/pwd | prompts.py 新增 `build_env_block()`（`<env>`：沙箱根/额外根/OS/shell 习惯），挂进 `get_system_prompt`，REPL 与 ask 同源生效 |
| ② **ask 模式完全没有系统提示词**（无 BASE_PROMPT/CLAUDE.md/skills） | run_single 改用 `build_system_messages()` 装配（hooks 消息保持独立标注） |
| ③ 确认类异常在 ask 裸抛炸穿循环（PathConfirmationRequired → 顶层"模型调用失败"） | `_execute_ask_tool` 就地翻译三类确认异常（Path/Mcp/Permission）为可读工具错误：含路径、原因、沙箱根、/add-dir 出路 |
| ④ max_tool_rounds=10 硬编码，恢复循环预算不足 | settings 新增 `ask_max_tool_rounds`（默认 25），超限提示带具体数字 |

### 修复后真机复测（2×2 全绿）

- 任务 A（FizzBuzz 自验证，无提示）：❌ → ✅ 一次通过（写→跑→验证第15行→汇报）
- 任务 B（源码定位 result_clip，无提示）：崩溃 → ✅ 沙箱拒绝回流后模型改道
  临时脚本读取，答出 `_NOTE_RESERVE=120` 等真读过的细节并自清理
- 注：路径沙箱只约束文件工具，run_command 命令通道可读沙箱外文件——预存边界，非本次引入

### 修②时引入又根治的坑（实踩教训，重要）

- ask 首次 import `agent.nodes._shared` 发生在测试把 `LLMProvider` 打补丁的窗口内，
  `_shared` **模块导入期**的 `llm_provider = LLMProvider()` 把假 provider 铸进全局单例，
  污染同进程后续所有图测试（test_cli 20 errors，单跑全过——典型导入序敏感）。
- **根治**：`build_system_messages` 整体迁往 `llm/prompts.py`（提示词装配不依赖 LLM
  机制，架构上本就该在那），`_shared` 留薄转发兼容图路径调用方；ask 只依赖 llm 层。
- 教训：**模块导入期副作用 + 测试补丁窗口 = 跨测试污染**；诊断靠 git stash 对照
  （先怀疑预存问题、用 stash 证伪）+ 单跑/合跑二分。
- 另：早前强杀 E2E 压测循环留下的僵尸 python 进程持有锁，曾让 pytest 挂 20 分钟——
  排查挂死先 `tasklist` 查僵尸进程。

### 实测数字（两层四场景）

- CI 筛选层：常态/不可达 **2219 passed / 44 skipped**（新增 13：env 块 8 + ask 错误语义 5）
- integration 层：常态/不可达 **157 passed / 1 skipped**
- ruff check/format 双清；提交前经 git stash 对照证明 test_cli 污染为本次引入并根治

### 附：敏感路径守卫（同日拍板落地）

- 拍板背景：任务 B 复测暴露路径沙箱只约束文件工具，命令通道可读沙箱外文件
  （模型改道命令通道读到了沙箱外源码；`.env` 真 key 恰在沙箱外）
- 方案：`SENSITIVE_PATH_PATTERNS`（safety.py，白名单之前单点生效）硬拒
  `.env`（模板变体放行）/.ssh/id_rsa/id_ed25519/mcp-auth/*.pem/credentials；
  通用读面缺口如实文档化为已知边界（对标本体是权限制非硬沙箱）
- 测试：16 条红→绿（拒绝面 10 + 工具层 2 + 放行面 4——放行面只用白名单内命令，
  type/copy/dir 预存就不在白名单）

## 2026-10-02 MCP OAuth（http transport，对齐 Claude Code 401 自动授权流）

**范围**：仅 streamable HTTP（stdio 不做 OAuth）；SDK pin 1.x 不变。授权码 + PKCE + 动态客户端注册（RFC 7591）+ 受保护资源发现（RFC 9728，401/WWW-Authenticate 触发）+ 过期刷新全部复用 SDK `OAuthClientProvider`（httpx.Auth），本项目只做三件事：回调交互、token 文件落盘、按配置装配。

### 落地内容

| 项 | 说明 |
|---|---|
| config（mcp/config.py） | http server 新增 `auth`：`"oauth"` 简写或 `{"mode": "oauth", "scope", "callback": "local\|paste", "client_name"}`；非法值跳过该 server 并 warning（不静默）；stdio 带 auth 只忽略字段 |
| token 落盘（mcp/token_store.py） | `FileTokenStorage`——SDK 无关纯 I/O（无 SDK 环境可测），`~/.mini-claude/mcp-auth/<server>.json`，POSIX 0600（Windows 尽力而为），坏 JSON 按空处理；pydantic 模型经 `model_dump` 鸭子兼容，SDK 侧转换在 oauth.py 适配层 |
| OAuth 适配器（mcp/oauth.py） | `build_oauth_provider`：local 模式起 `McpCallbackServer`（127.0.0.1 临时端口，打印授权 URL，future 在 start() 即建防回跳竞态）等待超时自动转手动粘贴；paste 模式用 OOB（`urn:ietf:wg:oauth:2.0:oob`）全程手动粘贴完整回跳 URL（裸 code 过不了 SDK state 校验）；绑定失败自动回退 paste |
| manager 接线 | `_open_connection` http+auth 时装配 provider 传 `auth=`，aclose 挂进连接的 AsyncExitStack；`token_home` 可注入（测试不碰真 home）；status() 增加 `auth`/`auth_token` 字段；`/mcp` 状态显示授权标签 |
| 异常翻译（实测必要） | 授权流/初始化在 SDK 任务组内失败时原始异常被取消风暴顶掉——收口吞次生异常保原始异常 + `_extract_connect_failure` 鸭子特征提取（异常组 3.11 内建/3.10 backport，不能按名 import）+ oauth 侧 `last_error` 记录真实原因 → `McpOAuthError`/`McpConnectError`；纯 CancelledError 也按连接失败呈现（连接阶段无自然取消源），否则穿透 connect_all 炸主链路（实测） |

### 实测数字（两层四场景，最终代码态复测）

- CI 筛选层：常态 **2207 passed / 43 skipped**、不可达模拟 **2207 passed / 43 skipped**（新增 54：config 9 + token_store 13 + oauth 适配器 22 + manager 接线 10）
- integration 层：常态 **157 passed / 1 skipped**、不可达模拟 **157 passed / 1 skipped**（新增 5：全流程 local 回调 / paste OOB / 过期刷新（expires_in=1 真刷新）/ 用户拒绝快失败 / 无 auth 对 OAuth server 错误隔离）
- E2E 假 IdP：FastMCP `auth_server_provider` 实现协议 9 方法 + `AuthSettings(issuer_url/resource_server_url)`——SDK 原生挂 /.well-known/PRM、AS metadata、/register、/authorize、/token；"浏览器"由 notify 捕获授权 URL 后真 GET（302 回跳真打到本地回调 server）

### 已知边界（诚实记录）：MCP E2E 家族的跨测试顺序脆弱性

- **现象**：同一 pytest 进程内，先跑"全流程 local 回调"+"过期刷新"两条 E2E（共同点：
  本地回调 server + 真实工具调用），再连**任何**新 MCP server（哪怕普通无 auth server），
  initialize 会**永久挂起**（anyio/uvicorn/SDK 收口碎片化，探针证实毒源在 SDK 层而非
  mini-claude 封装——裸 SDK 复现路径未走通，归属未定论）。
- **产品侧缓解**：无交互流的 http 连接 initialize 加 30s 上限（`_HTTP_CONNECT_TIMEOUT_SECONDS`）——
  挂死变 `McpConnectError("连接超时(30s 无进展)")`；带 OAuth 的连接不设限（首次 401 进
  交互式授权，用户开浏览器可能超 30s）。
- **触发面评估**：标准两层命令按文件名字母序（test_mcp_http_e2e 在 test_mcp_oauth_e2e
  **之前**）永不触发该顺序；CI integration job 无 [mcp] SDK，两文件整体跳过。仅手工
  乱序局部跑两条 E2E 文件可复现。
- **验证**：毒序 trio 由"永久挂"变为 42s 快速失败；标准两层常态/不可达四场景终态复测全绿。

### 实踩教训

- **SDK `OAuthClientProvider(timeout=...)` 参数只存不用**（1.30 实测）——流程超时必须自己实现（回调 server wait_code 自带超时）
- **`athrow(): asynchronous generator is already running` + "exit cancel scope in a different task"**：授权流异常（用户拒绝/401）穿过 streamablehttp_client 的 anyio 任务组后，`stack.aclose()` 的次生异常会顶掉原始异常，最终到达调用方的是 `anyio.WouldBlock` 或链式 CancelledError—— hence 上述异常翻译层（ISSUE-029 同族，收口同任务纪律不变）
- **httpx 1.x 对 302 的 urn Location 无条件做 redirect request 构建**（`follow_redirects=False` 也炸 `InvalidURL`）——测试模拟"浏览器跟到 OOB 地址栏"必须手工 socket GET
- **FastMCP 服务端 OAuth**：`auth_server_provider` 必须与 `auth=AuthSettings(...)` 同时给（二者缺一 raise）；`resource_server_url` 设置后会自动挂 PRM 路由并在 401 带 WWW-Authenticate
- **ruff F821 `BaseExceptionGroup`**：项目支持 3.10（异常组是 3.11 内建）——按 `exceptions` 属性鸭子特征识别，勿按名 import backport
- 回调 server 的 future 必须在 `start()` 创建而非等待时——浏览器回跳可能早于 `callback_handler` 被等待
- **pytest 管道里 `EXIT=$?` 拿的是 tail 的退出码**——`timeout N pytest | tail` 后判断 124/0 会被骗；探针/排查时要用 `-rf` 或直接看输出
- 同一进程反复 OAuth 连接后 SDK 任务组可僵死挂住后续 initialize（见上"已知边界"）——无交互路径一律限时，交互路径（浏览器授权）不可限时

## 2026-09-28 目标批次①：web 三件套异步化 + 白名单去重 + coverage job 激活（对标 Claude Code）

### 交付
- **web_fetch/web_search/weather 异步化**（对标本体的非阻塞 web 工具）：
  - fetch/weather：requests → `httpx.AsyncClient`，手动重定向逐跳 SSRF 检查保持；
    错误映射换 httpx 异常族
  - search：ddgs 是同步库，整块 `asyncio.to_thread` 卸载（线程池零阻塞）
  - **新增 `tools/_http.py` 共享 client**：实测 `httpx.AsyncClient()` 每次构造会
    **同步加载 SSL 证书库 ~0.22s**（Windows），发生在事件循环上等于每次 web 调用
    全局冻结所有协程——比同步 requests 更隐蔽；共享实例摊薄成本 + 连接复用，
    关闭挂进 repl/ask 既有 finally 清理链（CLAUDE.md 退出纪律）
  - fetch 的 SSRF 检查（含 getaddrinfo）经 `asyncio.to_thread`，DNS 慢解析不再卡 loop
- **子代理白名单去重**：`SUBAGENT_ALLOWED_TOOLS` 单一事实源，SpawnAgentTool/
  SpawnParallelTool 共用（PLAN backlog 项兑现）
- **coverage job 激活**：原 `if: pull_request` 与 integration 同款"从不运行"盲区；
  现随 push 跑，marker 表达式对齐 unit job（旧表达式会连真网 e2e 一起跑，
  激活即翻车）；基线实测 **70%**（branch coverage），`fail_under=60` 留足余量

### 验证
- 先红后绿：新增 6 测（`test_tools/test_web_async.py`）——两个并发不阻塞测试在旧实现下
  红（fetch 串行特征 0.8s+ / search 实测 1.2s），行为契约保持（SSRF 重定向拦截、
  正文解析、wttr.in JSON）
- 两层回归：不可达端点 1923/0 + 151/0；真 key 同数全绿；ruff 双检干净
- 真网 E2E：web_fetch 真实抓取 docs.python.org 异步页解析正常；web_search 在本机
  网络不可用（ddgs 后端 Brave/DDG/Google 全部超时——环境所限非代码问题，旧实现
  同样不通），Agent 优雅降级直接 fetch 已知 URL

### 实踩教训
- httpx.AsyncClient 构造的 SSL 证书库加载是**同步阻塞**（Windows ~0.22s）：
  "换成 async 库"不等于"非阻塞"，构造/析构同样要审
- 重定向拦截测试在旧 requests 路径的 stub 必须用 CaseInsensitiveDict
  （requests 的 headers 本就是大小写不敏感），否则 302 的 Location 查找失真

## 2026-09-28 目标批次②：Hooks 事件面对齐 Claude Code（3→6 事件）

### 交付
- **UserPromptSubmit**：exit 2 / `decision=block` 拦截本轮输入（REPL 跳过回合 /
  ask exit 1）；exit 0 纯 stdout 或 `hookSpecificOutput.additionalContext` 注入
  回合上下文——走新 `AgentState.hook_context` 字段 → `build_system_messages()`
  前置（与系统提示同一通道，**不进持久化历史**，遵守架构红线）。ask 与 REPL
  双入口接线；ask 拦截置于 display 之前（被拦截输入不显示 Thinking），且直接
  print 错误（_show_error 会附误导性"模型调用失败"提示）
- **Notification**：工具请求确认（路径/MCP/权限三通道汇合点）时触发，只通知不判断
- **SubagentStop**：子代理写入完成收工前触发，exit 2 / decision=block → 原因作为
  消息喂回、子代理继续（max_iterations 兜底）；hook 异常不阻断收工
- `VALID_EVENTS` 扩到 6；测试 20 条先红后绿（事件裁决语义 12 + agent 接线 8）

### 验证
- 两层回归四场景全绿：不可达端点+严格 msgpack 1943/0 + 151/0；真 key 同数
- 真 key E2E：hooks.json 配 `echo` hook → 真实 LLM 准确答出注入的暗号
  （注入链路端到端）；`exit 2` hook → ask 打印拦截错误并 exit 1
- `hook_context` 为**全量替换语义**：每轮增量必须带值（空串=清空），
  否则 checkpoint 沿用旧值——已写入 CLAUDE.md 红线

### 实踩教训
- **相对导入层级**：`agent/nodes/` 下引 hooks 要 `...hooks.dispatcher`（三级）——
  写成两级会解析到不存在的 `agent.hooks`，且被自己写的 try/except 吞掉，
  表现为"hook 静默失效"（测试当场抓住）
- 测试 patch 函数级 `from x import y` 的导入，目标必须是**源模块** `x`，
  patch 使用方模块属性打不进去（observe 的 SubagentStop 桩最初就打偏了）

## 2026-09-28 目标批次③：CLAUDE.md @import + CLAUDE.local.md + Stop hook 阻断续跑

### 交付
- **@import 语法**（`utils/claudemd.py`）：`@path` / `@./x`（相对包含文件目录）、
  `@~/x`（用户主目录）、`@/abs`；嵌套跟随最多 5 跳（对齐本体"5 hops"）；
  visited 防环；缺失/路径非法原文保留；代码文件引原始内容；正则用
  `(?<![\w@])` 负向断言防 user@example.com 误伤（全角标点后可引用）
- **CLAUDE.local.md**：项目级个人补充（一般 gitignore），加载顺序
  用户级 → 项目 CLAUDE.md → CLAUDE.local.md
- 总字符预算改为**全局共享递减**：三份入口 + 全部 import 展开共同消耗
  CLAUDE_MD_MAX_TOTAL_CHARS，超大引用被截断停机（防撑爆）
- **Stop hook 阻断续跑**：`dispatch_stop` 返回 (blocked, reason)，
  exit 2 / decision=block → repl 自动以原因作为继续指令再跑一回合；
  payload 带 `stop_hook_active` 供 hook 自查（对齐本体防死循环约定），
  repl 侧"单回合只续跑一次"硬顶；继续回合的 Stop hook 仍触发但不再续跑
- 唯一记录在案的事件语义分歧就此清零（六事件全部具备本体的阻断语义）

### 验证
- 先红后绿：claudemd 新增 11 测（相对/裸 @/嵌套/深度上限/`@~/`/绝对路径/
  防环/缺失保留/代码文件/CLAUDE.local.md×2）+ Stop 阻断契约 5 测
- 链路零成本验证：workspace 配 @import + CLAUDE.local.md → load_claude_md
  展开标记齐全且顺序正确
- 两层回归四场景 + ruff 双检（数值见提交信息）
- 模型层说明：小模型对注入约定的服从度有限（已有记录），链路正确性
  以函数级断言为准

### 实踩教训
- heredoc 写含 \n 转义的测试代码再次损坏字符串——老老实实 Read+Edit
  （纪律条目第二次被自己验证）
| 高 | 工具结果回传格式 | ~~`HumanMessage`→`ToolMessage`~~ 已结（2026-09-28，ISSUE-026） |
| 中 | checkpoint msgpack 白名单 | ~~StopReason 未注册~~ 已结（2026-09-28，ISSUE-027，CI 已开严格模式） |
| 低 | LiteLLM cost map SSL 噪音 | 远程拉取证书验证失败回退本地备份（等待已无，纯警告）；可设 LITELLM_LOCAL_MODEL_COST_MAP=True 消音 |

> 2026-09-13 已结：ISSUE-015（ask 退出码）、ISSUE-016（health/tool-deps 退出码）、
> ISSUE-017/018/020/021（ask-json/debug/后台清理/转义/tool-deps-json）、ISSUE-019（pip/区外脚本）。
> 2026-09-14 已结：P0 安装缺件指引、health 分级+doctor、`--json` 提纯、logs 去跟踪、model 诚实化；
> P1 `ask --full`、报错中文 hint、会话恢复按 thread。
> 2026-09-14 夜（真 Key 联调）：TokenRhythm 网关接通（`qwen3.8-flash`，`/models` 实测 ID 落定），
> 修网关路由（未知模型跟 `OPENAI_BASE_URL` 走，不再误判 ollama），修 `--full --json` 图节点输出污染
> （执行期 stdout→stderr，单测锁定），真火验证：问答/单工具/建文件/双文件 E2E 全 rc 0 纯 JSON。
> 2026-09-17 提交前审查（pre-commit-audit 三层 subagent）修复：`.env.example` 默认值注释矛盾、
> README `--full` "恢复"不实、litellm 启动拉远程 cost map 空等 8 秒、3 处 hint 未 escape、
> health 测试真联网（81 秒→毫秒）、`TestAPIKeyValidation` 未隔离本机 .env（假红）。

## 2026-09-28 真机核心体验实测（真 key，qwen3.8-flash @ TokenRhythm 网关）

| 演示 | 结果 | 用时 |
|---|---|---|
| ask 简单问答（流式） | ✅ 回答正确 | 12.9s（含启动） |
| ask 工具调用（建文件+运行） | ⚠️ write_file 成功且内容正确；第 2 轮 run_command 泄漏为文本未执行（ISSUE-026） | 16.8s |
| ask 多步任务（两文件+列目录） | ⚠️ 两个 write_file 成功；第 3 轮 list_dir 泄漏（同 ISSUE-026）；todo 未触发属模型判断 | 13.6s |
| ask --json（纯问答） | ✅ 单行纯净 JSON | 12.1s |
| ask --json（工具任务） | ✅ 内部调 list_dir，stdout 仍单行纯净 JSON | — |
| CLAUDE.md 项目记忆 | ✅ 注入链路零成本逐环验证（开关/路径/系统消息第 2 条）；演示中小模型未执行约定标记——机制通，执行力看模型 | — |
| 多轮+rewind 真 key E2E | ✅ 无复制/分叉正确/连接收口 ALL PASS（18.8s） | — |

**结论**：单轮问答、单工具、--json、会话记忆/rewind 全部可用；多轮工具链被 ISSUE-026 卡脖子
（第 2 轮起工具调用退化为正文），是该模型下核心体验的最大短板，修复方案已入档待实施。

## 2026-09-28 ISSUE-026/027 修复：工具结果 ToolMessage 协议 + checkpoint serde 白名单

### 交付
- **ISSUE-026（协议正确性）**：工具结果从 HumanMessage(role=user) 全部改回
  `ToolMessage`(role=tool + tool_call_id + status)；assistant 历史消息携带 tool_calls
  不再剥离（`convert_message` 线格式转换）；`execute_single_tool` 全部 9 分支协议化，
  确认挂起标 success 防 observe 误判；`parse_tool_calls` 空 id 回退；子代理收集器、
  REPL/token 统计同步适配；ask 单发路径重写为完整工具循环（旧实现第二次调用不带
  tools 且重复 append assistant）
- **ISSUE-027（前向兼容）**：`build_agent_graph` 显式 serde 白名单
  `('mini_claude.agent.state','StopReason')`；CI unit/integration 两 job 注入
  `LANGGRAPH_STRICT_MSGPACK=true`——未注册类型从此 CI 直接红（本地全量严格模式验证过）
- 新增 14 条测试先红后绿：单元协议 12（`test_tool_result_protocol.py`）+
  图级线格式捕获 2（`test_tool_protocol_wire.py`，fake provider 记录第二轮实际收到的
  消息序列——**能抓到"多轮泄漏"的那类测试**）+ serde 2（`test_checkpoint_serde.py`）

### 验证
- 不可达端点 + 无 .env + 严格 msgpack：CI 筛选层 1917 passed / 0 failed；
  integration 层 151 passed / 1 skipped（收集 1984→1998）
- 真 key 两层同数全绿（1917/0 + 151/0）
- **真网多步任务验收**（此前泄漏同款任务）：6+ 轮工具调用全部真实执行
  （write_file/run_command/read_file/todo_write×4），零 `<tool_call>` 正文泄漏，
  todo 四轮流转正确，38s 完成——单轮体验短板变长板

### 实踩教训
- act_node 一次调用只发一次 LLM 请求，"多轮"发生在图迭代间——写线格式测试要
  两次调用 act_node 前传 state（或跑图），不能指望单次调用返回两轮
- `_is_tool_error_message` 泛化时确认挂起不能标 status="error"，否则确认流程
  被当成错误进 handle_error（协议字段有语义，不能凭直觉标）

## 2026-09-27 P1 快赢包落地：todo_write + CLAUDE.md 项目记忆（PLAN_对标ClaudeCode差距收敛 Phase 1）

背景：CI 修复后（ISSUE-023/024）启动对齐 Claude Code 的差距收敛，先做感知最强的两项。
设计依据：`ANALYSIS_对标ClaudeCode差距.md`；实现前研读 free-code 逆向源码的对应模块
（仅参考架构与语义，未搬运任何代码）。

### P1-1 todo_write 任务清单

- 数据模型：`AgentState.todos`（**全量替换语义**，刻意不挂 `add` reducer——todo_write
  每次提交完整清单，act 返回的增量直接覆盖旧值，避免 ISSUE-014 类消息复制问题在 todo 上重演）。
- 工具：`tools/todos.py` 的 `TodoWriteTool` + `validate_todos`（状态枚举、非空清单恰好一个
  in_progress、content 去重、空清单=清空）。工具无状态：校验失败返回 Error 文本让 LLM 自纠，
  校验通过由 act 执行链写 state（工具拿不到 state 是既有架构）。
- act 接线：`_execute_tools` 返回值从 3 元组扩为 4 元组（新增 `state_extras`），
  todo_write 校验通过时写入 `state_extras["todos"]` 并**当场渲染**（`display.show_todos`，
  内容 escape——LLM 生成文本，ISSUE-020 同款纪律）；act_node 把 extras 合并进返回增量。
  提前返回（确认/错误）路径同样携带已产生的 extras，不丢提交。
- 渲染：✓ completed / → in_progress（优先 active_form）/ ○ pending。
- 提示词：工具清单加 Task Checklist 小节 + Rule 11（何时建清单、何时标状态）。
- 红线遵守：未加入两份子代理白名单（`SpawnAgentTool`/`SpawnParallelTool`，测试锁定）。

### P1-2 CLAUDE.md 自动加载

- 加载器：`utils/claudemd.py` `load_claude_md(workspace_root, home_dir)`——
  用户级 `~/.mini-claude/CLAUDE.md` + 项目级 `<workspace_root>/CLAUDE.md`，
  用户级在前；单文件 64KB、总量 128KB 截断留标记；坏编码 replace 解码；缺失返回空串。
- 注入：`build_system_messages()` 在系统提示后、skills 前插入，`claude_md_enabled`
  开关（`CLAUDE_MD_ENABLED` 环境变量，默认开）。加载/注入异常只 debug 日志，不阻断主链路。
- 不进持久化对话历史（与 skills 同通道），`/resume` 后约定依然生效。

### 验证

- 新增 40 测：工具级 21（含"不进子代理白名单"守卫）+ act_node 级 3（全量替换契约）
  + display 4（含转义）+ claudemd 12（合并顺序/截断/开关/异常不阻断）。
- 图级契约：`tests/test_integration/test_graph_checkpoint.py` 13 条全过（CLAUDE.md 要求）。
- CI 等效全量筛选（无 .env）：1750 passed / 40 skipped / 0 failed（2026-09-27 实测，收集 1831）。
- 教训×2：① f-string 提示词里写字面 `{content...}` 会被当格式化字段，
  必须双写 `{{...}}`（本轮实踩，收集期 NameError）；② 测试断言子串时注意
  active_form 包含 content 的情况。

## 2026-09-27 P2 MCP 客户端落地（PLAN_对标ClaudeCode差距收敛 Phase 2）

### 交付
- `src/mini_claude/mcp/`：`config.py`（mcp.json 加载/合并/校验，形态对齐 Claude Code）、
  `bridge.py`（远端工具→BaseTool 适配，`mcp__<server>__<tool>` 命名 + 确认门槛）、
  `manager.py`（AsyncExitStack 托管连接生命周期，connect_all 单点失败不扩散）
- 确认通道：复用路径确认状态机——`McpConfirmationRequired` → execute_single_tool 转
  `WAITING_CONFIRMATION` + `pending_confirmation_path="mcp:<server>:<tool>"` →
  REPL 'yes' 分支经 `approve_confirmation_key` 放行（会话内存，重启重问）
- `/mcp [connect|disconnect|reload]` 命令 + REPL 启动自动连接（失败逐个提示不阻断）+
  finally `close_mcp_connections()`（stdio 子进程非 daemon，与 checkpoint 同级退出纪律）
- pyproject：`mcp` extra + dev 同步；子代理白名单不收 mcp 工具（守卫测试锁定）

### 关键决策
1. **SDK pin 1.x**（`>=1.30.0,<2.0.0`）：mcp 2.x 刚改公开 API（FastMCP→MCPServer），
   实测 import 即报错并附迁移指南——ISSUE-024 教训直接复用，未验证不跟。
2. **bridge 不 import SDK**：session 鸭子类型，缺 SDK 时模块可导入、单测可跑；
   只有 manager 的 `_open_connection` 真用 SDK，缺件给中文指引（McpSDKMissingError）。
3. **状态复用而非新造**：确认走 pending_confirmation_path（mcp: 前缀区分），
   放行/拒约/observe 保留全都不动既有状态机。

### 验证
- 新增 43 测（config 11 / bridge 10 / manager 13 / 命令 6 / act 确认通道 3）。
- **真 stdio E2E ×2（Windows 实测）**：仓库内 echo_server.py（官方 SDK FastMCP）真子进程
  连接→发现→注册→确认门槛拦截→放行调用→int 参数往返→干净注销/重连
- CI 等效全量（无 .env）：1793 passed / 40 skipped / 0 failed（收集 1874）。dev extras 已含 mcp，CI 三平台真跑 E2E。
- 真 Key E2E：ask --full --json 下真 LLM 调用 mcp__e2e__echo 回显成功，stdout 纯净（--json 重定向含 MCP 连接提示）。

### 实踩教训
- 项目混用两种 logger：`logging.getLogger`（标准）不支持 kwargs 风格
  `logger.warning("...", server=x)`（StructuredLogger 专属）——新模块一律
  `utils.logger.get_logger`，本轮在 manager 实踩 TypeError。

## 2026-09-27 P3 Hooks + 细粒度权限落地（PLAN_对标ClaudeCode差距收敛 Phase 3）

### 交付
- `src/mini_claude/hooks/`：config（hooks.json 加载合并）+ runner（shell 子进程、
  stdin JSON、超时强杀收尸）+ dispatcher（PreToolUse 阻断/PostToolUse 替换/Stop 通知）
- `src/mini_claude/permissions/`：四模式（default/accept_edits/plan/bypass，shift+tab 循环）
  + allow/ask/deny 规则（glob 匹配主参数：run_command→command、文件工具→path）
- 双门收口在 ToolRegistry.execute 单一裁决点（权限门→降级→PreHook→执行→PostHook），
  子代理跳过双门；deny 直接返回 Error 文本让 LLM 自纠，ask 抛 PermissionAskRequired
  走 WAITING_CONFIRMATION 通道（键 perm:<tool>:<arg>）
- 确认键前缀路由收敛到 utils/confirmations.py（普通路径 / mcp: / perm:）
- /permissions（查看/切模式）+ /hooks（查看配置）命令；HOOKS_ENABLED/PERMISSIONS_ENABLED 开关

### 关键决策
1. 裁决顺序 deny > ask > allow > 模式默认（ask 保守优先于 allow）——首版写成
   allow 先于 ask，被顺序测试当场抓红后改正（测试先行的价值实证）。
2. hook runner 绝不抛异常：spawn 失败/超时/编码全部转非零 outcome，
   阻断语义只认 exit 2 与 JSON decision=block，其他一律放行+记日志。
3. 三种确认（路径/MCP/权限）共用 pending_confirmation_path 状态机，
   前缀分发收敛一处，REPL 'yes' 分支零感知。

### 验证
- 新增 81 测（hooks 24 / permissions 27 / registry 双门 7 / 确认通道 4 / 命令 7 / ... ）
- CI 等效全量（无 .env）：见提交记录（收集 1955）
- 真 Key E2E：① deny 规则拦 weather——回答含"权限拒绝（匹配 deny 规则: weather）"；
  ② PreToolUse hook 真阻断 run_command——回答含"被 PreToolUse hook 阻断：E2E-HOOK-BLOCK"；
  ③ accept_edits 行为由单测锁定

### 勘误（2026-09-27 晚，外部复核触发）

外部实跑同一条 DoD 命令得 1901 passed / 2 failed（TestNetworkErrorRecovery），
本条推翻上文的"1903 passed / 0 failed"验收结论：

1. **Mock 打偏（根因）**：那两个测试 patch 的是 `nodes/llm_provider` 向后兼容
   re-export，act 经 `get_llm_provider()` 取实例——patch 从未生效，测试在打真实
   API（真 key 下还会烧额度）。这正是 ISSUE-023 遗留清单里自己写明"应改为
   patch act 取例处"却一直未修的债。
2. **我的 1903 绿是环境运气**：回归跑时 .env 被移走，真实端点快速返回认证错误
   "恰好喂饱"断言；外部带真 key 复跑即红。把端点改成不可达，connection 测试
   假绿、timeout 测试仍红——结果随网络状态翻转。
3. **"全量"名不副实**：1903 是 CI 筛选层（unit 等 marker 过滤）；integration 层
   另有 21 条。两层合计才是全量。

### 勘误修复

- TestNetworkErrorRecovery 重写：patch `_shared.llm_provider` 的 **chat 与
  chat_stream_with_tools 双方法**（流式开关决定走哪条，漏一个就漏到真网）+
  旁路降级管理器（防 fallback 污染 + 消除退避等待）；超时测试改走确定性
  TimeoutError 路径（旧 slow_response+wait_for 从未真正测过 act）
- 不可达端点实验顺带挖出**同款假 mock**：test_reflect_node_integration 标称
  integration（mocked）实则打真实 LLM——已 mock 单例 chat 返回合法 reflection JSON
- 三场景验证（真 key / 端点不可达 / 不可达+无 .env）结果一致，9s 内完成，无网络等待
- 不可达端点下全两层：1944 passed / 3 failed → 3 条全为 `@pytest.mark.e2e`
  （明示真实 API 依赖，marker 体系正确管理，不可达下按设计失败）
- 文档口径更正：**"CI 筛选层"与"integration 层"分开计数，合称全量**；
  DoD 命令见 PLAN 更新

## 2026-09-13 mini-claude ISSUE-017~021 五连修——LLM 会改写命令串导致 glob 不命中；
  按工具名 deny（如 weather）才是确定性验证。

## 2026-09-27 P4 rewind + 打磨落地（PLAN_对标ClaudeCode差距收敛 Phase 4 收官）

### 交付
- P4-1 `/rewind`：get_state_history 列回合边界快照（next∈{('think',),()}）→ `/rewind <n>`
  暂存快照 configurable → 下一轮输入带 checkpoint_id 增量分叉重跑；旧分支保留在
  checkpoint 链，可再次回退
- **顺手修掉潜伏多轮 bug（重要）**：REPL 旧逻辑每轮传全量历史，实测带 checkpointer 时
  旧消息被 add-reducer 整段复制（'第一轮'存两份，ISSUE-014 多轮版）。新 `create_turn_increment`
  统一增量传参；todos 刻意不在增量里（跨回合状态）
- P4-2 `task_output`/`task_kill` 工具：run_background 输出改文件重定向（顺带修掉
  PIPE 写满卡死子进程的隐患），读尾部/列任务/终止
- P4-3 确认流程 unified diff：write/edit/force_write 触发路径确认时 reason 附变更预览
  （新建文件标注、60 行截断）
- P4-4 `/model` 热切换：改造占位——settings.default_model + `_shared.rebuild_llm_provider`，
  act 改经 `get_llm_provider()` 访问器取实例（import 期绑定会失联，ISSUE-024 同款）

### 验证
- 新增 29 测（fork 契约 4 / task 工具 7 / diff 预览 6 / model 切换 5 / rewind 命令 6 + 增量形状）
- CI 等效全量（无 .env）：1903 passed / 40 skipped / 0 failed（收集 1984）
- 真 Key E2E：真 LLM 两轮（1+1/2+2）无复制 → 分叉回第一轮结束 → 旧 2+2 丢弃、新 3+3 接入
  → close_checkpoint_connections 收口，进程干净退出

### 实踩教训
- 测试轮询子进程退出必须 `await asyncio.sleep`——同步 time.sleep 阻塞事件循环，
  退出回调得不到调度，returncode 永不更新（表现为"任务永远 running"）
- 全量回归中网络型测试可能把降级管理器推到 fallback 模型，后续 fake-LLM 图测试
  被迫走真实 provider 分支（无 key 即炸）——图级 fake 测试统一旁路降级管理器
- E2E 里按快照内容（而非列表序号）选取 fork 边界，避免对 checkpoint 排序的隐式依赖

## 2026-09-28 对标收敛批次④：bash env 持久化 + 系统提示词加厚 + 记忆快捷面

### 交付
- **④A bash env 跨调用持久化**（补完持久 shell 故事）：显式 `export K=V`
  （POSIX）/ `set K=V`（cmd）解析进会话 env，经 `create_subprocess_shell`
  的 **env= 参数**注入子进程；export/set 入白名单。
  **设计踩坑**：初版用 set 前缀注入——cmd 的 `%VAR%` 在整行解析期展开，
  同行 set 完 echo 拿到旧值（实测空输出）；改走子进程 env 后时序问题
  根除。诚实边界：脚本/子进程内的 export 对会话不可见
- **④B 系统提示词加厚**：BASE_PROMPT 注入 "Working Guidelines"——任务管理
  （3+ 步用 todo/task、恰一个 in_progress、委派闭环）、工具卫生
  （专用工具优先/先读后改/截断感知）、运行环境事实（cwd 持久、env 需
  显式 export、plan 只读 + exit_plan_mode）、代码纪律（不夹带重构/
  不留桩、跑测试再收工）、沟通（结论先行、不无证据宣称成功）
- **④C 记忆快捷面**：`/memory` 列出三级记忆文件与行数、`/memory add <文本>`
  追加项目 CLAUDE.md（`claudemd.append_project_memory`，缺文件建带头版）；
  REPL 输入 `# 内容` 快速追加记忆（不进对话不发给模型，对齐 Claude Code）

### 验证
- 定向：bash_env 9 + memory_and_prompt 11 全绿（env 设计返工一次后）
- 全量两层四场景 + ruff：CI 筛选层 **2149 passed / 42 skipped**（收集 2232，正常与
  不可达×严格 msgpack 一致）、integration 层 **152 passed / 1 skipped**（离线+正常
  各一遍）、ruff 全绿

### 实踩教训
- cmd 展开时机的第二课：%VAR% 同行 set 后立即消费拿旧值（解析期展开）——
  与批次③的 %CD% 坑同根，shell 语义类改动必须真跑子进程验证
- 命令处理器解析参数先 strip 再 startswith 会吃掉尾部空格，"add   " 判空
  失败——用 split(None, 1) 取词

## 2026-09-28 对标收敛批次③：权限 specifier / 可定义子代理 / plan 审批流 / bash cwd 持久化

### 交付
- **③A 权限规则 `Tool(specifier)` 语法**（对齐 Claude Code，与遗留
  `tool:pattern` 并存）：命令类 `run_command(git diff:*)` 前缀/精确；
  路径类 `edit_file(src/**)`、`read_file(~/x)`、`force_write(//C:/x)`
  glob（全 posix 归一对比，Windows 大小写不敏感）；`web_fetch(domain:x)`
  含子域。括号优先于 ":" 拆分
- **③B 可定义子代理** `utils/agent_definitions.py`：`.mini-claude/agents/*.md`
  frontmatter（name/description/tools）+ 正文=子代理提示词；两级扫描项目
  覆盖用户级；tools 逐名校验 registry 存在性（拼错不静默）；model 字段
  解析到即 warning 忽略（诚实边界：全局 provider）；spawn_agent 新参
  agent_type，未知类型报错回流，description 动态列出可用类型
- **③C plan 模式审批流**：`exit_plan_mode` 工具（非 MUTATING——plan 只读闸
  的唯一出闸口）→ `PlanApprovalRequired` → act 转 WAITING_CONFIRMATION
  （pending 键 "plan"）→ 用户 yes 经 route_confirmation_key 切 accept_edits
  开始执行；no 留在 plan 模式修订
- **③D bash cwd 会话持久化**：run_command 结束后取最终 cwd 存会话级，
  下条命令自动 `cd` 前缀起跑（run_background 同前缀不捕获）；
  `cd` 入白名单（allowed_args=2 容纳 cmd 的 /d）。诚实边界：env 不持久

### 两个 shell 陷阱（实测踩中，写进 _wrap_cwd_capture docstring）
- **cmd /c 遇内嵌换行只执行第一行**——`\r\n` 串联的哨兵命令被静默吞掉，
  表现为"命令成功但 cwd 永不更新"
- **cmd 的 %CD% 在整行解析时展开**——`cd /d "x" & echo %CD%` 拿到 cd 之前的
  老目录；改用 `cd`（无参，执行时打印）重定向临时文件回传
- 修法验证路径：先证"输出为空"（换行吞）→ 再证"捕获到老目录"（解析期
  展开）→ 各自对症

### 验证
- 定向：permissions 全家 52 + agent_definitions 8 + plan_approval 8 +
  bash_cwd 5 = 73 全绿
- 全量两层四场景 + ruff：CI 筛选层 **2134 passed / 40 skipped**（收集 2215，正常与
  不可达×严格 msgpack 一致）、integration 层 **152 passed / 1 skipped**（离线+正常
  各一遍）、ruff 全绿

## 2026-09-28 对标收敛批次②：hook ask 补全 + MCP prompts 斜杠命令化 + 工具结果上限 + Task 落盘

### 交付
- **②A hook 强制确认**：`HookVerdict.force_ask`——`permissionDecision: "ask"`
  无视规则/模式直接抛 PermissionAskRequired（三值语义补全，分歧点清零；
  ask 与 allow 同现时 allow 被忽略——deny > ask > allow 合并序）
- **②B MCP prompts 斜杠命令化**：`/mcp__<server>__<prompt> [{json 参数}]`
  命中已连接 server 的 prompt 即展开注入输入流（`get_prompt_expansion`
  无 role 前缀拼接）；未命中走原命令流程；manager 新增 expansion 变体
- **②C 工具结果尺寸统一上限**（对齐本体 maxResultSizeChars）：
  `utils/result_clip.py` 保头去尾 + 截断注记（含原始长度，LLM 可据此
  自我修正）；act（execute_single_tool）与 ask（run_single）两条链统一
  截断；`TOOL_RESULT_MAX_CHARS` 默认 24000
- **②D Task 清单跨会话落盘**：任务变更写透 `<workspace>/.mini-claude/
  tasks.json`；REPL **新会话**装载并随首个回合增量播种（`_apply_task_seed`
  用后即清）；**resume 以 checkpoint 为准不播种**（不回退）；崩溃窗口只丢
  最后一次变更

### 验证
- 定向：hooks/registry/tasks/persistence/global_tools/result_clip 122 全绿
- 全量两层四场景 + ruff：CI 筛选层 **2098 passed / 40 skipped**（收集 2179，正常与
  不可达×严格 msgpack 一致）、integration 层 **152 passed / 1 skipped**、ruff 全绿

### 实踩教训
- 仓库自定义 logger 只支持 kwarg 风格（`error=str(e)`），%s 位置参数会炸——
  手册里写过的坑再次命中，新文件照抄邻居调用样式
- 测试桩要完整覆盖被测路径的全部合作者（trace 要 nullcontext、degr 要
  record_success/record_failure）；`with` 语句在**类型**上找 `__enter__`，
  SimpleNamespace 实例属性无效
- 假阳性排查路径固化：①clean HEAD 复现判"是否回归"→②多跑看方差判
  "是否抖动"→③找边界外的隐藏成本（client 冷构造）

## 2026-09-28 对标收敛批次①：差距分析 Top3 落地（updatedInput / auto-compact 落盘 / rewind 代码回退）

### 背景
差距分析（对话记录）锁定"已有功能的深度差距"性价比前三：
①hook 能拦不能改/不能放；②auto-compact 只作用于当次 prompt 不落盘；
③/rewind 只回退对话不回退代码。本批次全部收敛。

### 交付
- **① PreToolUse 结构化裁决**（`HookVerdict{blocked, allow, updated_input}`）：
  - stdout JSON `hookSpecificOutput.permissionDecision` 三态——deny 阻断、
    **allow 免确认**（跳过权限 ask）、ask v1 不支持按放行（已知分歧点）；
    `updatedInput` **改写工具入参**，喂给权限匹配与执行（base.py 裁决链改为
    hook 前置于权限门——hook allow 才有意义）
  - payload 补本体字段：session_id/permission_mode/cwd；runner 注入
    `$CLAUDE_PROJECT_DIR`
- **② auto-compact 落盘**：`compact_session()` 从 CompactHandler 提取为共用
  核心；REPL 每回合前 `_maybe_auto_compact`——check_budget 超 warn 阈值即
  压缩播种新线程（tasks/todos 随迁，ISSUE-028 方案复用），60s 冷静期限频，
  `AUTO_COMPACT_ENABLED` 开关（默认开）。act 内 per-call 摘要保留为兜底
- **③ /rewind 代码回退**：`utils/file_history.py` 会话级文件日志——
  `_atomic_write`（write/edit/force_write 唯一汇聚点）写前记录原始状态，
  同路径只记最早一次；`/rewind <n> [chat|code|both]`（默认 chat 保持兼容）
  按快照 created_at 时间戳回放：改写恢复、新建删除、失败条目留待重试；
  回放即消费（单向回退）。诚实边界：进程内日志，跨会话与 run_command
  侧门修改不在恢复范围（模块 docstring 声明）

### 顺手修的测试健壮性
`test_web_fetch_concurrent_not_blocking` 假阳性（0.81s 假串行）：共享
httpx client 冷构造的 SSL 证书库加载（0.2-0.4s，随磁盘/Defender 状态漂移）
恰好落在首个 execute 的阻塞段，把并发 sleep 串行化。干净 HEAD 复现排除
回归后，测试计时前预热共享 client（与 to_thread 预热同理）。三连跑全绿。

### 验证
- 定向：hooks+registry+compact+auto-compact+rewind+file_history 471→477 全绿
- 全量两层四场景 + ruff：CI 筛选层 **2083 passed / 40 skipped**（收集 2164，
  正常与不可达×严格 msgpack 一致）、integration 层 **152 passed / 1 skipped**、
  ruff check/format 全绿

### 实踩教训
- `await x().y` 优先级：先取属性再 await——迁移断言要加括号
- LangGraph 快照时间戳在 `StateSnapshot.created_at`（文档化字段），
  metadata 里没有可靠的 ts；边界取不到时兜底"当前时间"= 安全侧（不恢复）
- anyio 的上一课再现：同族"平台约束"（cancel scope 同任务 / SSL 构造阻塞）
  单元替身测不出来，只能实测暴露
- 测试的计时断言要把"被测行为之外的一切成本"预热隔离，否则阈值没有余量

## 2026-09-28 批次 A+B 全功能实测（脚本驱动真实 REPL）——抓到并修复 2 个真实缺陷

### 实测方式
脚本驱动真实 REPL 主循环（`issues/e2e_driver.py`，本地保留不入库）：真实 LLM
（qwen3.8-flash 真 key）+ 真实 checkpointer + 真实 hook 子进程 + 真实 MCP server
（进程内 uvicorn 挂 FastMCP streamable_http_app 回环 + stdio echo_server 子进程），
12 条脚本化输入走完整产品路径；ask 模式单独验证工具循环。单元测试全绿 ≠ 产品能跑，
这轮实测的价值就是把"全绿"打回原形两次。

### 实测结果（全部真实发生）
- Hooks 四尾事件 **全部真实触发**（hook_events.log 物证）：SessionStart（MCP 连接后）、
  SubagentStart（spawn_agent 派生时）、PreCompact（/compact 前）、SessionEnd（finally）
- MCP：产品启动路径自动连接 HTTP + stdio 双 server（"MCP 已连接: remote, local"）；
  LLM 自主调用 mcp__remote__echo（HTTP，中文往返）✓、mcp_read_resource ✓、
  mcp__local__add=7（stdio）✓
- Task v2：task_create ×2、task_update(owner=subagent_001) 委派、task_list、
  spawn_agent + get_result 子代理闭环 ✓；ask 模式 store 路径（两轮工具循环）✓
- /add-dir：注册第二工作目录 + 新根内 read_file 免确认直读 ✓
- /compact：39 条消息 → 6 条（tokens 1282→333），自定义指令"只保留任务相关"生效
  （压缩后任务信息保留、非指令关注细节按指令丢弃），tasks/todos 随迁 ✓（修复①）

### 缺陷① /compact 播种新线程丢失 tasks/todos（实测前推演发现，ISSUE-028）
播种只写 messages——tasks/todos 是 state 跨回合字段，压缩后清单静默清空。
修复：seed 字典随迁非空 tasks/todos；回归测试
`test_compact_preserves_tasks_and_todos` 锁定。

### 缺陷② MCP 断连收口 CancelledError 冲出 REPL 退出链路（ISSUE-029）
run_graph finally → close_mcp_connections → stack.aclose()，stdio server 收口时
anyio 内部取消风暴抛 CancelledError（**BaseException**，穿透 except Exception），
Goodbye 之后甩用户一脸 traceback。两版错误修法被实测否定：
- wait_for 包 aclose：超时取消打进 anyio cancel scope，CancelledError 照样穿透
- 拆隔离任务 aclose：炸 "Attempted to exit cancel scope in a different task"
  ——anyio cancel scope 必须在进入它的同一任务退出
终版：**同任务直接 await + 吞 BaseException**（打开与关闭同在 main 任务，语义
合法；代价是超时不可控，已写进 disconnect_server docstring）。
回归：tests/test_mcp/test_disconnect_robustness.py（吞 CancelledError /
aclose 同任务断言 / close_all 单点失败不拖垮）。
教训：stdio E2E 的 fixture 只 reset 单例从没真正 aclose——清理路径要有
"真关闭"的集成测试，不能全靠注入替身。

### 模型观察（非缺陷，记录）
- 子代理最终答复质量一般（回显"执行计划"行）——委派闭环框架侧没问题
- 压缩后追问历史细节：模型正确执行了自定义指令的取舍，但表达绝对化
  （"从未读取过"）——qwen3.8-flash 对摘要的引用粒度粗，属模型能力边界

## 2026-09-28 对标批次 B：Task 系统 v2 + MCP HTTP transport + resources/prompts

### 交付
- **B1 Task v2**（`tools/tasks.py`，对标 TaskCreate/Update/List/Get，规格读 free-code
  只做参考未搬代码）：
  - Task 形状 {id, subject, description, active_form?, status, owner?, blocks[],
    blocked_by[]}；编号**只增不复用**（进程级高水位，删除后新建不回收旧号——
    对话历史里旧编号引用不产生歧义）；依赖边双向同步，禁自引用/重复边/成环（DFS）
  - 架构：**state.tasks 唯一事实源**（全量替换语义，与 todos 同纪律）。工具拿不到
    state，act 每轮派发前把 state.tasks 传入 execute_single_tool（新参 tasks/
    state_extras），变更经 state_extras["tasks"] 回写、轮内基线就地推进（同轮多次
    操作可见前序变更）+ show_tasks 当场渲染；不走通用 execute_tool（特化分支）
  - 模块级 store 只服务 ask 无 checkpoint 场景，act 每轮用 state.tasks 覆盖——
    rewind 分叉后 store 从新状态同步，不发散
  - 委派闭环：主代理 task_create + task_update(owner=agent_id) 指派 → spawn_agent →
    子代理 task_list/task_get/task_update 认领推进（白名单刻意不含 task_create）
- **B2 MCP HTTP transport**（config/manager）：
  - 配置 `{"type":"http","url":...,"headers":{...}}`；type 缺省按字段推断
    （command→stdio 向后兼容、url→http）；sse 等显式拒绝给 warning；url 必须
    http/https；headers 全字符串校验
  - `_open_connection` 按 transport 分支：http 走 SDK 1.30 的
    `streamablehttp_client(url, headers=...)`（三返回值），session/initialize/
    工具发现与 stdio 共路；桥接、确认通道、trusted 放行全部复用
- **B2 resources/prompts**（`mcp/global_tools.py`）：
  - 四个全局只读工具 mcp_list_resources/mcp_read_resource/mcp_list_prompts/
    mcp_get_prompt，聚合已连接 server；不走确认通道；连接路径上幂等注册
    （MCP 关闭时不占工具列表）；/mcp 状态行带 transport 与 endpoint
  - 真 E2E：进程内 uvicorn 挂 FastMCP streamable_http_app（回环端口），
    连接→工具发现→桥接→调用→资源→prompt(arguments 透传)→断连全链路

### 验证（全部实测）
- CI 筛选层：**2055 passed / 40 skipped / 41 deselected**（2:35；批次 B 新增 55 条，
  收集 2136）
- integration 层：**152 passed / 1 skipped**（26s；+1 为真 HTTP E2E，importorskip
  门控——CI 不装 [mcp] 自动跳过）
- 不可达端点 × 严格 msgpack 两层（.env 移走 + 127.0.0.1:9）：2055/40 + 152/1，
  与正常环境一致，.env 已还原
- ruff check/format 全绿

### 实踩教训
- 无 SDK 的传输层单测：`sys.modules` 注入假 `mcp` / `mcp.client.streamable_http` /
  `mcp.client.stdio` 三个模块——**manager 里 from X import Y 的每个子模块都要有假身**，
  漏一个就 ImportError 被兜底转成 McpSDKMissingError
- 注入连接的测试绕过了 connect_server，生产在连接路径注册的全局工具要显式补注册
- 测试先写后改实现时，断言要跟实现一起复核（列表渲染图标 ≠ 状态词，LLM 消费
  的工具结果要显式状态词）

## 2026-09-28 对标批次 A：/compact + Hooks 尾部四事件 + /add-dir（事件面收尾 6→10）

### 交付
- **A1 /compact 手动压缩**（`cli/commands/compact_handler.py`）：复用 act 自动压缩的
  `summarize_messages` 引擎，新增 `custom_instructions` 参数透传 `/compact <指令>`；
  PreCompact hook 在压缩前触发（trigger=manual）
- **A2 Hooks 尾部四事件**（SessionStart/SessionEnd/PreCompact/SubagentStart，6→10）：
  全部非阻断；SessionStart 的 stdout/additionalContext 注入会话级上下文（repl 存
  `_session_hook_context`，每回合与 UserPromptSubmit 上下文合并进 hook_context——
  全量替换语义不破坏）；接线点 SessionStart→repl 主循环前（MCP 连接后）、
  SessionEnd→run_graph finally（资源收口前）、PreCompact→handle_token_budget
  自动摘要前（trigger=auto，新增 thread_id 参数）、SubagentStart→agent_spawn 派生前；
  ask 模式同样接 SessionStart/SessionEnd（一次执行即一会话）
- **A3 /add-dir 多工作目录**（`add_dir_handler.py` + `safety.py` 多根注册表）：
  `_additional_roots` 存 resolve() 后真实路径（8.3 短路径先例），
  `validate_path` 三处 workspace 比较点以 OR 并入额外根（带 os.sep 守卫——
  根 `D:\proj` 不得放行 `D:\projects`）；主 workspace 比较逻辑逐字节不动，
  PROTECTED_PATHS 与穿越检查不放松

### 关键架构决策：压缩结果播种新 thread
`messages` 挂裸 `operator.add`，`aupdate_state` 走同一 reducer 只能**拼接**，永远无法
缩减持久化历史（act 内自动压缩只作用于当次 prompt，不回写 checkpoint）。/compact 的
做法：压缩结果写入全新 thread_id（空线程 add([]) 即纯替换），会话切换过去，旧线程
checkpoint 链保留可追溯，`_rewind_configurable` 跨线程作废。已写入 CLAUDE.md 红线。

### 验证（全部实测）
- CI 筛选层：**2000 passed / 40 skipped / 41 deselected**（2:35；新增 41 条
  = compact+tail_events 23 + multi_root/add_dir 18，收集 2081）
- integration 层：151 passed / 1 skipped（23s）
- 不可达端点模拟 CI（.env 移走 + 127.0.0.1:9 + 严格 msgpack）：两层同样全绿
  （2000/40 + 151/1），.env 已还原
- ruff check/format 全绿

### 实踩教训
- `settings.hooks_enabled` **默认 True**（base_settings.py）——"关闭态"测试必须显式
  钉死 `hooks_off` fixture，不能赌默认值
- 四目录合跑一次疑似挂起（墙钟 25 分钟 CPU 仅 28s），按目录二分全部正常（最快 8.6s），
  复跑组合 106s 绿——**偶发系统负载**，非代码问题；但由此发现各目录单独耗时基线
  （hooks+cli+utils 105s / agent 8.6s），异常时可先二分再怀疑改动
- `python -c` 带中文字面量做断言在 Windows（argv 编码）会假阴性——验证文件内容用
  sed/grep 可见输出，别赌 `python -c` 的中文比较
- heredoc 写文件禁令再验证一次：本次 PLAN 用 heredoc 侥幸没坏（纯文本替换），
  但断言工具链虚惊一场——维持"写代码一律 Read+Edit"纪律

## 2026-09-28 CI 信任链加固三件套（constraints / integration job / settings shim）

### 背景
勘误复盘（2026-09-27）暴露三类结构性隐患：① 依赖无上界（ISSUE-023 ruff、ISSUE-024 click
前科）；② integration 层在 CI 从不运行（job 仅 PR/dispatch 触发，而本仓库直推 master）——
"CI 绿但 integration 假 mock"盲区正是从这里漏网；③ `config/settings.py` shim 与
`settings/` 包同名并存，是 py3.10 mock 事故的混乱根源。

### 交付
- `constraints.txt`（新增）：18 个直接依赖 + 6 个 dev 工具 + 3 个强耦合传递依赖
  （langgraph-checkpoint/openai/typing-extensions）pin 到实测绿版本；升级=显式动作
  （改 pin → 本地全绿 → 推送盯 CI），纪律写进文件头
- CI（test.yml）：5 处安装步骤统一 `-c constraints.txt`（lint 的 ruff 版本同样收敛到
  单一事实源）；paths 触发器补 constraints.txt；**integration job 重做**——needs 从
  unit-tests 提前到 lint（并行提速）、触发放开到 push/PR/dispatch、加
  `OPENAI_BASE_URL=http://127.0.0.1:9` 不可达端点护栏（integration 层承诺全 mock，
  打真网即红）、`-m "not e2e"` 剔除真网用例（旧 job 若真在 CI 跑过，会连 2 条 e2e
  一起跑而翻车）
- 删除 `config/settings.py` 死 shim：`sys.modules` 实证包优先加载（`settings/__init__.py`），
  shim 独有符号（config 回调注册族）全仓零引用；"禁止再造同名 shim"写入 CLAUDE.md

### 验证（四场景全绿）
- 不可达端点 + 无 .env（= CI 环境）：CI 筛选层 1903 passed / 0 failed（2:32）；
  integration 层（= 新 CI job 原命令）149 passed / 1 skipped / 2 e2e 按设计剔除（0:35）
- 真 key：CI 筛选层 1903 passed / 0 failed（3:01）；integration 层 149 passed / 1 skipped（0:30）
- `pip install --dry-run -e ".[dev]" -c constraints.txt` 解析通过；ruff check/format
  全过（pinned 0.15.11，204 文件已格式化）

### 实踩教训
- `import a.b.c as m` 拿到的未必是模块：`config/__init__` re-export 了 `settings` 实例，
  父包属性被实例遮蔽——判断同名 shim 是否死代码要看 `sys.modules[...].__file__`，
  不能看 import 是否报错
- venv 里的依赖 ≠ CI 装的依赖（prometheus-client 本地根本没装、click 本地 8.1.8/CI 8.2.x）：
  "本地绿"与"CI 绿"之间此前没有共同合面，constraints 补的就是这个合面
- integration job 首跑：pytest 149/0 全绿但 job 退出 1——单层覆盖率 32.79% 必不达全局
  `fail_under=60`；本地验证命令没带 `--cov` 故未暴露。教训：**验证 CI 命令要逐字复刻**
  （含 cov 参数），修复用 `--cov-fail-under=0` 豁免单层门槛（run 36342879145 复跑全绿）

## 2026-09-13 mini-claude ISSUE-017~021 五连修



**触发**: ISSUE-015/016 收尾时开的单（见上节"死参数/预先存在的隐患"），本轮清掉。

### ISSUE-019 命令白名单三通道（先复现后修）
- **复现实锤**（只读探针）：`python evil.py` / `pip install requests` /
  `python -m pip install evil-pkg` 全部 PASS（`pip` 不在 `BLOCKED_PYTHON_MODULES` 里）。
- **修复**（`utils/safety.py`，与既有"确认=拒+confirmation 文案"约定对齐）：
  `CONFIRMATION_REQUIRED_PATTERNS` 加 `pip3?\s+install` / `pip3?\s+-[re]\b`
 （顺手把旧 `pip\s+uninstall` 扩成 `pip3?`，旧模式漏 pip3）；
  Step 7.6：`python`/`python3` 带目录成分的 `.py` 位置参数走工作区校验，
  区外拒；纯文件名放行（旧行为 + 官方示例能力保留）。
- **穷举比对**（35 条新旧对照）：差异仅预期的 10 条 PASS→BLOCK
 （含 `python ../x.py`、`pip3 uninstall` 两个此前漏网），其余 25 条零变化。
- **测试**：新 `tests/test_utils/test_safety_supply_chain.py` 13 条（6 红→13 绿）；
  `test_bash.py::test_validate_safe_pip_install` 按行为变更改断言（True→False+confirmation）。

### ISSUE-021 `tool-deps --json` 不存在工具（存在性检查前移）
- `tool_deps` 在 `--json` 分支前加同一出口：`--json` 下输出 `{"error": ...}`，
  非 json 下原友好文案，退出 1 不变。
- **测试**：新 `tests/test_cli/test_tool_deps_json_error.py` 3 条
  （2 CliRunner + 1 真实子进程断终端无 Traceback），3 红→3 绿。

### ISSUE-017/018/020（ask 联动，一起修）
- `--json`：成功只打最终 JSON 一行 `{"answer": ...}`（中间输出全静默），
  失败打 `{"error": ...}` 再 exit 1。
- `--debug`：`main()` 里 `init_logging()` 之前写 `settings.log_level = "DEBUG"`
  （与 repl 写 workspace 同构）；`ask` except 改 `logger.error(..., exc_info=True)`
  （`StructuredLogger` 无 `.exception` 方法，实踩）+ `--debug` 下终端 `traceback.print_exc()`。
- 018：在 `run_single()` 加 `finally` 调清理（与 `repl.run_graph` 同构；
  在循环内直接 await，无需另起 loop；SystemExit 穿过 finally，退出码不变）。
- `display.user_message` / `agent_message` 纯文本分支 / `show_error` 加
  `rich.markup.escape`（Markdown 渲染分支不动）。
- **测试**：新 `tests/test_cli/test_ask_json_debug.py` 10 条
  （含 1 真实子进程复核 `--json`），修复前 7 红 2 绿（守卫绿）→ 10 绿。
  附带教训：`sort`/`tail -f` 在 Windows cmd 下不可做长驻命令；
  同步 Popen 与 asyncio 的 `await proc.wait()` 不兼容——018 测试改用
  "登记活进程 + mock 清理计数"判别 finally 是否被调。

### 全量回归
`1725 passed / 40 skipped / 7 failed`——5 个预存（2 个 `402 Insufficient Balance` +
其余环境性）+ 2 个新增预存（`ls` 在 Windows cmd 下不存在，stash 对照证实与本改动无关）。
`TEST_PLAN.md`（06-28 历史手工计划，untracked）未动。`logs/` 无写脏。

## 2026-09-13 `ask` 失败退出码恒为 0（ISSUE-015）

**触发**: 2026-09-12 八项目启动验证发现——`mini-claude ask` 在 LLM 失败（key 欠费/网络错误）时
打印错误却以退出码 0 结束，脚本与 CI 会误判为成功。

### 根因

`cli/main.py` 的 `ask`：`except Exception` 只 `display.show_error()` + `return None`，
`asyncio.run(run_single())` 的返回值又被丢弃 → Click 正常返回 → 退出码 0。

### 修复

```python
except Exception as e:
    display.show_error(str(e))
    raise SystemExit(1)
```

选 `SystemExit` 而非 click 自带 `Exit`：项目内既有同类写法（`monitoring/metrics.py:547`）。
穿层用哨兵值实测：`SystemExit(7)` 经 `asyncio.run()` 得 7、经 `CliRunner` 记到 exit_code=7；
真实子进程跑生产代码（`SystemExit(1)`）得 1。（7 与 1 是两次不同实验，非同一次透传。）
另：`asyncio` 的收尾（cancel 挂起任务 / shutdown executor / close loop）在抛出时照常执行，
与旧 `return None` 路径逐字一致——本次改动只换了退出方式，未改变任何清理语义。

### 针对性测试（先红后绿）

新增 `tests/test_cli/test_ask_exit_code.py` 5 条：2 条判别（进程内 + **真实子进程**）、3 条守卫。
最终版测试在修复前实测 `2 failed, 3 passed`（判别用例红、守卫绿），修复后 `5 passed`。

### 顺带修正与发现

- **工单原判有误**：其建议的 `raise typer.Exit(code=1)` 及"参考 `main.py:49-52`"均不成立
  ——该项目用 `click`，`src/` 内 typer 零命中。照原方案会引入无用依赖。
- **同类问题 → 已一并修复（ISSUE-016）**：`health --json` 报告 unhealthy、`tool-deps <不存在的工具>`
  打印 `Error:` 时都仍退出 0。已按项目既有约定修好（见下）。
- **死参数（ISSUE-017）**：`ask --json` 的 `output_json` 声明后零引用；
  全局 `--debug` 写进 `ctx.obj` 后**全 `src/` 零读取**——两个"设计了但未集成"。
- `repl` 经查**不是问题**：错误按设计吞掉并继续交互循环。
- **预先存在的隐患（已开单，本次未改）**：ISSUE-018 `ask` 缺 `cleanup_all_background_processes()`
  → 后台子进程成孤儿（新旧退出路径行为一致，非本次引入）；ISSUE-019 命令白名单里
  `python <脚本>` / `pip install` 可通过校验（若 prompt 不可信则可达 RCE，**待复现后再修**）；
  ISSUE-020 `display` 未转义 rich markup、`ask` 的 except 丢弃 traceback。

### 同类两项一并修复（ISSUE-016）

`health` 与 `tool-deps` 是同一种"报了错却退 0"。约定**不自己发明**——照项目已有的
`monitoring/health.py:472`（HTTP handler `200 if overall == HEALTHY else 503`），
即非 HEALTHY 一律失败（`DEGRADED` 也算）。

新增 `tests/test_cli/test_exit_codes.py` 6 条（4 判别 + 2 守卫，用真实 `HealthReport` 对象构造），
修复前 `4 failed, 2 passed` → 修复后 `6 passed`。真实 CLI 复核：`health --json` → 1、
`tool-deps __no_such_tool__` → 1、`tool-deps read_file` → 0。

### 测试隔离教训

进程内用例必须 patch 掉 `init_logging`/`load_environment`——`init_logging()` 会给名为
`mini_claude` 的 logger 设 `propagate=False` 并替换其 handler，同会话后续用例的 `caplog`
便收不到日志，一次跑红 36 个 `test_prompts` 用例；子进程用例 cwd 必须设 `tmp_path`——
否则 `init_logging()` 会写脏 **git 跟踪**的 `logs/mini_claude.log`。两条都已实测踩到。
（另：cwd 不影响 `.env` 加载——`load_dotenv()` 走 `find_dotenv(usecwd=False)`，
从调用方文件向上查找。子进程因此改用**最小 env 白名单**，而非"剥掉某几个前缀"。）

## 2026-09-04 主图 checkpointer 装配错误修复

**触发**: 全量探索项目时发现「REPL 是主图唯一的**生产**调用方，但它在调用
`build_agent_graph()` → `compile()` 时直接抛 `TypeError`，一个真实请求都跑不了」。
（注：另一条调用路径 `context/providers.py:create_agent_graph` 当前无调用者。）

### 根因（追根溯源，非表面修补）

修复前的 `graph.py:109`（现 `:120-131`）把 `AsyncSqliteSaver.from_conn_string(path)`
的返回值直接传给 `graph.compile(checkpointer=...)`。而该方法在源码里是：

```python
@classmethod
@asynccontextmanager
async def from_conn_string(cls, conn_string: str) -> AsyncIterator[AsyncSqliteSaver]:
```

即它返回 `_AsyncGeneratorContextManager`，**不是 saver**。本环境（langgraph 1.1.9）**实测**：
`compile()` 当场校验并抛 `TypeError: Invalid checkpointer provided ...
Received _AsyncGeneratorContextManager` → `build_agent_graph()` 直接抛 → **REPL 启动即死**。

（另一个环境观察到的是：langgraph 1.0.x 的 `compile()` 不校验，推迟到 `ainvoke` 才
`AttributeError: ... 'get_next_version'`。**该形态为转述，本环境未装 1.0.x、未实测。**
`pyproject.toml:13` 的 `langgraph>=0.2.0` 无上界，所以具体失败形态会随版本漂移。）

**为什么存活 2 个月零 9 天**（引入于 `9d59f60 fix: #14 Checkpointer 改用 SQLite 持久化`）：
全仓库**没有任何测试调用过 `build_agent_graph()` / `get_agent_graph()`**——
`test_agent_flow.py`、`test_e2e_user_flow.py`、`agent_spawn.py`、`parallel.py` 全部走
`build_agent_graph_no_checkpoint()`。加上 `TEST_PLAN.md`（该文件**未纳入版本控制**）把
T009「REPL 启动」记为「❌ prompt_toolkit 非交互终端崩溃」而放弃，主链路自此无验证。

**真正的病根**：运行时/开发依赖从未按 `pyproject.toml` 完整安装（未 `pip install -e ".[dev]"`），
且 `langgraph` 无上界——这与本小节要修的缺陷属同一类「声明了却没装/没约束」。

### 修复

| 文件 | 改动 |
|------|------|
| `agent/graph.py:120-131` | 改为 `AsyncSqliteSaver(aiosqlite.connect(path))`。可行依据：`AsyncSqliteSaver` 的建表 `setup()` 在 `aget_tuple`/`alist`/`aput`/`aput_writes`/`aget_delta_channel_history` 五条读写路径里都会惰性 `await self.setup()`（已装包源码 `aio.py:360/452/530/583/636`），因此无需把调用方改造成 `async with`。新前提：`AsyncSqliteSaver.__init__` 执行 `asyncio.get_running_loop()`，**只能在运行中的事件循环里调** |
| `agent/graph.py` | 新增 `_checkpoint_conns` 登记（登记放在最后一步，失败不留孤儿）+ `close_checkpoint_connections()` |
| `agent/graph.py:208-215` | `get_agent_graph()` 改传 `settings.session_db_path`，与 `_check_previous_session()` 对齐，否则恢复提示与图写的库会分叉 |
| `cli/repl.py` | `run_graph()` 重构为 `try/finally`，finally 里统一做后台进程清理 + `close_checkpoint_connections()`——覆盖 `/exit`、Ctrl+D、Ctrl+C、`CancelledError` 等全部退出路径。**若只把 close 放在循环末尾，Ctrl+C 会让进程挂住（aiosqlite worker 线程非 daemon 且被登记表强引用，实测 `__del__` 永不触发，解释器退出挂死）** |
| `tests/test_integration/test_graph_checkpoint.py` | 新增 10 个用例（见下） |

### 针对性测试（先红后绿 + 变异检验）

新增 10 个用例。**修复前**当时已写的 7 条（3 组参数化 compile/ainvoke/persist + 重建读回）
**全红**（同一 `TypeError`）；其后随修复追加连接生命周期用例（含 1 条生产调用点用例），
最终 **10/10 全绿**。断言测**外部契约**而非实现细节：checkpointer 是
`BaseCheckpointSaver` 实例、`ainvoke` 跑完、SQLite 里真有该 thread 的 checkpoint 行、
重建图后仍能读回状态、REPL 退出时真的调了 close。

变异检验（三条，均只杀对应目标）：
1. `close` 改成「只清列表不关闭」→ 仅 `test_close_checkpoint_connections_actually_closes` 变红。
2. 去掉 `repl.py` finally 里的 close → 仅 `test_repl_exit_path_closes_connections` 变红。
3. `_agent_graph` 复位断言先显式建单例再判，避免「恒 None」的假绿；`test_close_is_idempotent`
   显式建图后断言「第一次 ≥1、第二次 ==0」，避免「空表上两次都 ==0」的恒真。

端到端验证（非 pytest）：`get_agent_graph()` → 真 `AsyncSqliteSaver` → 一轮图执行跑完 →
`sessions.db` 里 `checkpoints`/`writes` 表生成且有该 thread 行 → close 返回 1 → 进程干净退出。

### 顺带发现（未在本轮处理）

- 单轮对话观察到产生 **14 条消息**（当时一次探测值），是 `think.py` 返回全量消息列表与
  `state.py:108` 的 `Annotated[..., add]` reducer 冲突的结果（用户消息被复制、SystemMessage
  落到 HumanMessage 之后）。机理已用最小图复现：输入 `['HUMAN']` → 输出
  `['HUMAN','SYSTEM','HUMAN']`。
- 装上 `langgraph-checkpoint-sqlite` 后 `test_e2e_user_flow.py` 首次可被收集，暴露
  `test_token_summary_generation` 断言失败 `assert 4 < 4`——即 **summarize 策略压缩后
  消息数未减少**，此前因收集中断而完全不可见。
- 遗留 **5** 个失败：3 个是 `402 Insufficient Balance`（真实 API 依赖，其中
  `test_full_graph_execution` 的 `GraphRecursionError: limit of 10` 是 402 引发
  error→retry→act 空转的下游表现）；1 个是 `test_token_summary_generation`（summarize 真缺陷）；
  1 个是 `test_settings.py::test_existing_settings_unchanged`——本地 gitignored `.env` 的
  `DEFAULT_MODEL=deepseek-chat` 覆盖了码内默认 `deepseek-v4-flash`，属环境态、与本改动无关。
- **覆盖率目前不可测**：`pytest-cov` 已在 `pyproject.toml:36` dev extra 声明但 `.venv` 未装，
  `--cov` 直接报 `unrecognized arguments`，故 `coverage.fail_under=60` 从未生效。此前各小节
  记载的「覆盖率 66%」为历史值，未经本轮复核。

## 2026-09-04 补齐 06-28 遗漏的 4 项 ❌

`issues/ISSUE-012` 记录的 06-28 Review 失效项里，4 项安全/可靠性 ❌ 在本轮修复。
每项都按「先写会红的测试 → 修 → 变异检验」推进。

| ❌ | 根因 | 修复 | 测试 |
|---|------|------|------|
| 1 | `safety.py` 的 `.split(".")[0]` 把 `http.server` 截成 `http`，黑名单唯一带点条目永不命中 | 改为匹配模块本身及任意父包路径 | +6 用例；变异（改回顶级名）→ 3 用例变红 |
| 3 | 引号状态机只处理 `&&`/`&|`，裸 `&` 放行 → Windows `cmd.exe` 下任意命令执行 | 引号外补拦裸 `&`、`<`、`^`、`(`、`)` | +8 用例；实测 `echo ok & rd /s /q` 已拦 |
| 4 | observe 用中文关键词嗅探工具输出正文 → 正常输出误判 + 攻击者文本被 `handle_error` 升格为指令 | 改结构化识别（`Error` 前缀 / 包裹边界 / 固定异常前缀）；`handle_error` 用 `<<<>>>` 定界并标注为数据 | +5 用例；变异（加回关键词嗅探）→ 2 误判用例变红；3 个虚构格式旧测试改为真实格式 |
| 2 | `regression_runner.py` 被误删，`scripts/run_regression.py:20` 悬空 import，CI 每日回归 job 静默 no-op | 恢复该模块；`TEST_GROUPS` 去掉已不存在的 `test_chaos/test_e2e/test_stress`；修复 CI `Check for regressions` 里 `[ -f regression_*.json ]` 通配符不展开的坏守卫 | +4 用例锁「import 目标存在 + 组路径存在 + `total_failed` 字段」 |

**验证**：`pytest tests/` → **1687 passed / 5 failed / 40 skipped**（收集 1732）。
5 个失败与上一节完全一致（3 个 402 真实 API、1 个 summarize 真缺陷、1 个 `.env`
覆盖默认模型），无本轮引入的新回归。`ruff check` 全过，变异无残留。

**仍未处理（留待后续）**：❌5 文档数字已在主链路修复时更新；`bash.py:170` 异常回显、
`SHELL_CHAIN_CHARS` 死常量、可选依赖未落到 extras（ISSUE-012 表内 6/7/8）；
以及 CI `regression-tests` 的 `continue-on-error: true` 是否保留（政策决定，未擅动）。

## 2026-09-04 对话正确性：reducer 消息重复 + summarize 用例

### Bug 1：think_node 与 messages reducer 冲突（消息重复 / 系统提示错位）

**根因**：`state.py:108` 的 `messages` 是 `Annotated[List[BaseMessage], add]`（累加语义），
其余节点（act/observe/plan/retry/error_handling）都只返回**增量**。唯独 `think.py` 在
`iteration==0` 返回「`[SystemMessage] + 全量历史`」的**重排全量列表**。`add`-reducer 把
`existing + update` 拼接 → 用户消息被复制一份，且 SystemMessage 落到 HumanMessage 之后。
最小复现：输入 `['HUMAN']` → 输出 `['HUMAN','SYSTEM','HUMAN']`。

**修复**（架构上正确，非表面修补）：系统提示与 skills **不写入** `state["messages"]`，
改由 act 节点在每次 LLM 调用时前置。这是标准做法——系统提示本就不应进持久化对话历史：
- `_shared.py` 新增 `build_system_messages()`（系统提示 + skills，LiteLLM 格式）。
- `think.py` 移除 SystemMessage/skills 注入，`iteration==0` 只重置错误态、返回空 messages 增量。
- `act.py` 在 `handle_token_budget` 之后、LLM 调用之前 `litellm_messages = build_system_messages() + litellm_messages`
  ——系统提示永远完整（不被摘要/截断吃掉）、永远在最前、且不参与 add-reducer。

**测试**（先红后绿 + 变异检验）：
- 改写 4 个假设「think 注入 SystemMessage」的旧测试（`test_graph.py`×3、`test_agent_flow.py`×1）为新契约。
- `test_graph_checkpoint.py` 新增 2 条图级用例：`跑完一轮用户消息只出现一次且 SystemMessage 不进 state`、
  `系统提示在 LLM 调用第一条（捕获 chat 入参）`。
- 变异检验：把 think 改回「返回全量历史」→ 去重用例红（用户消息出现 2 次）。

### Bug 2：summarize 用例未触发压缩（`assert 4 < 4`）

**根因**：`test_token_summary_generation` 只喂 4 条消息，而 `summarize_messages` 保留
`keep_first(1)+keep_last(4)`，`len<=5` 直接早退原样返回——**根本没走到压缩逻辑**，属
「没测到被测行为」。压缩逻辑本身没坏：总数 ≥7 时中间段才被摘要、消息数才真正减少。

**修复**：用例改为喂 10 条消息，真正触发压缩，并强化断言（摘要文本非空、`压缩后 == 首1+摘要1+尾4 == 6`、
含 `[历史对话摘要]` 标记）。变异检验：让摘要不产出摘要消息 → 用例红。

**验证**：`pytest tests/` → **1691 passed / 4 failed / 40 skipped**（收集 1735）。
4 个失败全部是既有环境/402 问题，无本轮新回归。`ruff check` + `format` 全过，变异无残留。

## 2026-06-28 多角度 Review 修复（8项）

**触发**: 4 个专项 Agent 并行审查（安全/架构/测试/代码质量），发现 68 个问题，经真伪验证筛出 8 个值得修复。

### 安全加固（4项）
| # | 文件 | 问题 | 修复 |
|---|------|------|------|
| 1 | `utils/safety.py` | Shell 元字符 `|>><&` 未检查，`SHELL_CHAIN_CHARS` 定义但未使用 | 引号感知检查，引号外拦截 |
| 2 | `utils/safety.py` | `eval\s+` 正则不匹配 `eval(code)` | 改为 `eval[\s(]+` |
| 3 | `utils/safety.py` | `http.server` 未在模块黑名单中 | 加入 `http.server/webbrowser/telnetlib/ftplib` |
| 4 | `tools/web_fetch.py` | SSRF 重定向跟随不检查目标地址 | 手动重定向循环，每跳校验 + 5 跳限制 |

### 代码清理（2项）
| # | 文件 | 问题 | 修复 |
|---|------|------|------|
| 5 | 多文件 | 死代码 2028 行（chaos.py/regression_runner.py/testing/__init__.py） | 删除 |
| 6 | `pyproject.toml` | 缺 requests/PyYAML 依赖，langchain-anthropic 未使用 | 修正依赖声明 |

### 错误处理（2项）
| # | 文件 | 问题 | 修复 |
|---|------|------|------|
| 7 | `tools/file_ops.py` | edit_file 错误暴露文件内容前 200 字符 | 脱敏为文件名 + 建议 |
| 8 | `tools/bash.py` | 异常消息暴露内部详情 | 改为仅显示异常类型名 |

**测试结果**: 1673 passed, 4 failed（预已知网络/健康检查测试）

---

## 2026-06-26 第三轮代码审查修复（11项）

**触发**: 深度代码审查（代码质量+安全+测试+架构），3 个 Agent 并行分析，经源码验证确认 11 个真问题。

### P0 测试回归（2项）
| # | 文件 | 问题 | 修复 |
|---|------|------|------|
| 1 | `tests/test_stress.py` | coordinator 改 async 后测试未更新，2 个测试因未 await 失败 | fixture 改 async，加 await |
| 9 | `utils/memory.py` | `get_memory_manager()` 不设置 `memory_manager` 别名 | 别名定义前移，函数内同步赋值 |

### P1 安全 & 可靠性（4项）
| # | 文件 | 问题 | 修复 |
|---|------|------|------|
| 2 | `tools/bash.py` | RunBackgroundTool 进程从未跟踪，管道未消费 | 加 `_background_processes` 跟踪 + 清理函数 |
| 4 | `utils/__init__.py` | `generate_agent_id` 精度只到秒，同秒碰撞 | 加 UUID 后缀 |
| 5 | `llm/provider.py` | `chat_stream_with_tools` 直接访问 `choices[0]` 无空检查 | 加 `if not chunk.choices` 守卫 |
| 6 | `cli/repl.py` + `agent/nodes/think.py` | 3 处 `except Exception: pass` 吞没异常 | 改为 `logger.debug` 记录 |

### P2 代码质量（5项）
| # | 文件 | 问题 | 修复 |
|---|------|------|------|
| 7 | `utils/profile.py` + `cli/repl.py` | `_async_load`/`_async_save` 从未调用，`get_system_prompt` 结果丢弃 | 删除死代码 |
| 8 | `agent/routers.py` | 每次迭代重建 TaskComplexityAnalyzer | 缓存复杂度到 state |
| 10 | `tools/web_fetch.py` | SSRF 不防 IPv6 映射和十进制 IP | 补全检查 |
| 11 | `agent/nodes/check_completion.py` | `"COMPLETE" in "NOT COMPLETE"` 误判完成 | 改为 `answer.startswith("COMPLETE")` |
| — | `cli/repl.py` | 删除 `get_system_prompt` 后 `provider` 变量也成死代码 | 一并删除 |

**测试**: 1606 测试通过（修复前 1604 passed + 2 failed），覆盖率 66%

## 2026-06-26 CI 修复（4项）

**触发**: 推送到 GitHub 后 CI 失败，Windows 环境 64 个测试报错。

| # | 文件 | 问题 | 修复 |
|---|------|------|------|
| 1 | `pyproject.toml` | 缺少 `langgraph-checkpoint-sqlite` 依赖，CI 导入失败 | 添加依赖 |
| 2 | `utils/safety.py` | Windows 8.3 短路径（RUNNER~1）展开为长路径（runneradmin）被误判为 symlink | 用 `workspace_real` 比较，路径在工作区内不报错 |
| 3 | `tests/test_*.py` | `tempfile.TemporaryDirectory()` 返回短路径，与规范化后的工作区不匹配 | fixture 中 `Path(tmpdir).resolve()` 规范化 |
| 4 | `tests/test_integration/test_parallel_e2e.py` | coordinator 方法改 async 后测试未更新 | 加 `await` + `@pytest.mark.asyncio` |

**CI 状态**: ✓ Lint + ✓ Ubuntu (3.10/3.11/3.12) + ✓ Windows (3.10/3.11/3.12)

## 2026-06-26 多角度审查修复（5项）

**触发**: 5 个并行 Agent 分别从架构/安全/性能/测试/错误处理角度审查，产出 109 个 finding。经源码验证确认 5 个真问题（排除误报如 `python -c` 实际被分号检查拦截、`python -m subprocess` 无 `__main__.py` 是空操作）。

| # | 文件 | 问题 | 修复 |
|---|------|------|------|
| 1 | `agent/nodes/observe.py` | 中文错误消息（错误/失败/超时）不匹配 `"error:"` 检测，`StopReason.ERROR` 路径死代码 | 扩展匹配为 `("error:", "错误", "失败", "超时")` + `.lower()` |
| 2 | `tools/web_fetch.py` | SSRF 域名检查不解析 DNS，重绑定攻击可指向内网 | `requests.get()` 前 `socket.getaddrinfo()` 解析 IP 并检查 |
| 3 | `tests/test_*.py` | 7 处 `assert isinstance(is_safe, bool)` 恒真，安全回归失效 | 改为具体值断言 |
| 4 | `tools/bash.py` + `cli/repl.py` | `cleanup_all_background_processes()` 定义但从未调用，进程残留 | REPL 退出时调用清理 |
| 5 | `utils/safety.py` | `python -m` 无模块级限制，防御未来变化 | 新增 `BLOCKED_PYTHON_MODULES` 黑名单 |

**测试**: 1729 测试通过（0 个新增失败），覆盖率 66%

## 2026-06-25 代码审查修复（14项）

**触发**: 全面多角度代码审查（安全/核心逻辑/工具层/架构/测试质量），5个维度 111 个 finding，经源码验证后确认 31 个真问题。

**修复内容**:

### P0 安全修复（4项）
| # | 文件 | 问题 | 修复 |
|---|------|------|------|
| 1 | `utils/safety.py` | `python -c`、`node -e`、`find -exec` 在白名单中，允许任意代码执行 | 从白名单移除 |
| 2 | `tools/file_ops.py` | EditFileTool 用 `check_file_read` 而非 `check_file_write`，可编辑工作区外文件 | 改用 `check_file_write` |
| 3 | `tools/web_fetch.py` | 无 SSRF 防护，可访问 localhost/私有IP/file:// | 加 URL 校验 |
| 4 | `utils/safety.py` | Windows symlink 检查被禁用（`path_real = path_abs`） | 改用 `pathlib.resolve()` |

### P1 逻辑修复（6项）
| # | 文件 | 问题 | 修复 |
|---|------|------|------|
| 5 | `agent/nodes/act.py` | except 块引用未定义变量导致 UnboundLocalError | 加 try/except 防护 |
| 6 | `agent/nodes/act.py` | `stop_reason == "error"` 与枚举比较永远为 False | 改为 `== StopReason.ERROR` |
| 7 | `tools/file_ops.py` + `utils/file_lock.py` | ForceWriteTool 忽略锁释放返回值，实际不强制 | 新增 `force_release` 方法 |
| 8 | `tools/file_ops.py` | 三个写入工具直接 `open("w")`，进程崩溃导致文件损坏 | 改为 temp+rename 原子写入 |
| 9 | `tools/file_ops.py` | 全局 `_is_subagent_mode` 并行 agent 竞态 | 改用 `contextvars` |
| 10 | `context/providers.py` | 命令注册表遗漏 SkillCommandHandler | 补上 |

### P2 功能修复（2项）
| # | 文件 | 问题 | 修复 |
|---|------|------|------|
| 11 | `cli/commands/help_handler.py` | `/model` 命令打印成功但不切换模型 | 移除虚假切换，改为提示用 .env 配置 |
| 12 | `monitoring/health.py` | 健康检查每次发真实 LLM 请求 | liveness 不调 LLM，readiness 缓存 60 秒 |

### P3 测试修复（2项）
| # | 文件 | 问题 | 修复 |
|---|------|------|------|
| 13 | `tools/agent_spawn.py` + 测试 | 假安全测试验证自身常量而非源码 | 白名单提取为 `ALLOWED_TOOLS` 类常量 |
| 14 | `pyproject.toml` | `coverage.fail_under = 0` 不强制覆盖率 | 设为 60 |

**测试**: 1729 测试通过（302 个直接相关测试），覆盖率 66%

## 2026-06-26 待办修复（11项）

**触发**: 代码审查确认的待办问题清单，经源码验证后逐项修复。

### 并发安全 + 数据一致性（7项）
| # | 文件 | 问题 | 修复 |
|---|------|------|------|
| 1 | `agent/coordinator.py` | `_lock` 创建但从未 acquire，并发修改无保护 | 6 个方法加 `async with self._lock` |
| 2 | `agent/subagent.py` | `progress_queue` 无 maxsize，无限增长 | 改为 `maxsize=100` |
| 3 | `agent/nodes/_act_helpers.py` | messages/litellm_messages 截断策略不一致 | 统一截断策略，messages 同步 litellm_messages 长度 |
| 4 | `utils/token_manager.py` | 模型名子串匹配错误（gpt-4o-2024 匹配到 gpt-4） | 改为最长匹配优先 |
| 5 | `utils/vector_store.py` | FAISS update 不更新索引向量 | 更新时真正添加新向量到索引 |
| 6 | `tools/file_ops.py` | search_content 无文件大小限制 | 加 1MB 限制 |
| 7 | `monitoring/health.py` | check_tools_health 永远返回 HEALTHY | 真正检查工具可用性 |

### LLM 健壮性（2项）
| # | 文件 | 问题 | 修复 |
|---|------|------|------|
| 8 | `llm/provider.py` | chat() 无重试，429/超时直接抛异常 | 加指数退避重试（3次） |
| 9 | `llm/provider.py` | chat_stream 静默丢弃 tool_calls | 检测时抛 ValueError |
| 10 | `utils/token_manager.py` | token 计数不含 tool schema 开销 | 加可选 tools 参数 |

### 功能接入（3项）
| # | 文件 | 问题 | 修复 |
|---|------|------|------|
| 11 | `agent/graph.py` | Checkpointer 用 MemorySaver，进程退出丢失状态 | 改用 AsyncSqliteSaver（SQLite 持久化） |
| 12 | `cli/repl.py` | 启动时不检测/恢复上次会话 | 新增 _check_previous_session + 恢复提示 |
| 13 | `tools/base.py` | ToolDegradation 未集成到 ToolRegistry | execute() 加降级检查 + 成功/失败记录 |

**测试**: 1606 测试通过，36 个预存 caplog 顺序问题

## 2026-06-18 Code Review 修复（7项）

**修复**: mock路径错误、断言被条件包裹、setup()返回值丢弃、CI过滤、断言加强
**文件**: test_alerts.py, test_tracing.py, providers.py, test.yml
**测试**: 1734 测试通过

## 可用工具（21个）

| 类别 | 工具 |
|------|------|
| 文件操作 (8) | read_file, write_file, edit_file, force_write, list_dir, search_files, search_content, list_locks |
| 命令执行 (2) | run_command, run_background |
| Web (3) | web_search, web_fetch, weather |
| Agent协作 (8) | spawn_agent, spawn_parallel, list_agents, get_result, plan_parallel, execute_parallel, parallel_status, aggregate_results |

**子代理白名单**（`SpawnAgentTool.ALLOWED_TOOLS`）：read_file, write_file, edit_file, list_dir, search_files, search_content, web_search

## 重要决策记录

| 决策 | 选择 | 原因 | 日期 |
|------|------|------|------|
| LLM 统一接口 | LiteLLM | 支持 5 个 provider，单一 API | 2026-04-13 |
| 状态机框架 | LangGraph | 条件路由 + 检查点 + 可视化 | 2026-04-13 |
| 文件锁策略 | 读写锁 + MD5 冲突检测 | 并行 agent 安全写同一项目 | 2026-04-13 |
| 子代理隔离 | contextvars + 工具白名单 | asyncio 协程级隔离，无竞态 | 2026-06-25 |
| 文件写入 | temp+rename 原子操作 | 防止进程崩溃导致文件损坏 | 2026-06-25 |
| /model 命令 | 移除，改用 .env 配置 | 动态切换涉及 provider/key/token 复杂依赖 | 2026-06-25 |
| 健康检查 | 分层：liveness 不调 LLM | K8s 最佳实践，避免频繁探测消耗 token | 2026-06-25 |
| Checkpointer | AsyncSqliteSaver（SQLite） | 进程退出后状态持久化，/resume 可用 | 2026-06-26 |
| 会话恢复 | 启动时提示用户 | 不自动恢复（避免 surprise），不静默跳过（避免丢失上下文） | 2026-06-26 |
| 工具降级 | 集成到 ToolRegistry.execute | 所有调用路径统一受保护，连续失败 3 次自动跳过 | 2026-06-26 |
| EnhancedMemory | 不集成 | CLI 工具不需要跨会话语义搜索，SessionManager 已够用 | 2026-06-26 |
| 同步 HTTP | ~~不修~~ → 已异步化（httpx 共享 client + to_thread，多 Agent 并行不互拖） | 原判"单用户 CLI 影响有限"低估了并发卖点下的互拖；2026-09-28 推翻旧决策 | 2026-06-26 → 2026-09-28 |
| SSRF 防护 | 补全 IPv6 映射 + 十进制 IP | DNS rebinding 改动大，标记后续优化 | 2026-06-26 |
| 后台进程跟踪 | PID 基础跟踪 + 清理函数 | 完整生命周期管理改动过大，当前方案够用 | 2026-06-26 |
| Windows 8.3 路径 | fixture 规范化 + safety.py 用 workspace_real 比较 | 短路径展开不是 symlink，不应拦截 | 2026-06-26 |
| DNS 重绑定防护 | `socket.getaddrinfo()` 预解析域名 IP | 字面 IP 检查不覆盖域名，DNS rebinding 可绕过 | 2026-06-26 |
| python -m 模块安全 | 黑名单（subprocess/os/sys/ctypes/runpy）而非白名单 | 编程助手需 `python -m pytest/http.server`，白名单阻塞合法用途 | 2026-06-26 |
| observe_node 错误检测 | 匹配中英文双语错误标识 | 07165af 将错误消息改为中文但未更新检测逻辑，导致死代码 | 2026-06-26 |
