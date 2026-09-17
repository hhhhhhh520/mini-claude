# Mini Claude Code 项目进度

> 创建时间: 2026-04-13
> 最后更新: 2026-09-14 (P0/P1 好用优化：extras/doctor/--json纯净/logs去跟踪/model诚实/ask--full/报错中文/会话按thread)

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
| 低 | 同步 HTTP | `web_fetch/weather/web_search` 阻塞事件循环，并行 agent 下互拖；`httpx async` 或文档声明 |

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
| 同步 HTTP | 不修 | web_fetch/weather/web_search 阻塞事件循环，但单用户 CLI 影响有限 | 2026-06-26 |
| SSRF 防护 | 补全 IPv6 映射 + 十进制 IP | DNS rebinding 改动大，标记后续优化 | 2026-06-26 |
| 后台进程跟踪 | PID 基础跟踪 + 清理函数 | 完整生命周期管理改动过大，当前方案够用 | 2026-06-26 |
| Windows 8.3 路径 | fixture 规范化 + safety.py 用 workspace_real 比较 | 短路径展开不是 symlink，不应拦截 | 2026-06-26 |
| DNS 重绑定防护 | `socket.getaddrinfo()` 预解析域名 IP | 字面 IP 检查不覆盖域名，DNS rebinding 可绕过 | 2026-06-26 |
| python -m 模块安全 | 黑名单（subprocess/os/sys/ctypes/runpy）而非白名单 | 编程助手需 `python -m pytest/http.server`，白名单阻塞合法用途 | 2026-06-26 |
| observe_node 错误检测 | 匹配中英文双语错误标识 | 07165af 将错误消息改为中文但未更新检测逻辑，导致死代码 | 2026-06-26 |
