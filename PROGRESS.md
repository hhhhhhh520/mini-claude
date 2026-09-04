# Mini Claude Code 项目进度

> 创建时间: 2026-04-13
> 最后更新: 2026-06-28 (多角度 Review 8项修复)

## 项目概述
**项目地址**: D:\my project\mini-claude
**技术选型**: LangGraph + LiteLLM + Rich + Prompt Toolkit
**目标**: 构建一个迷你版Claude Code，支持多Agent并发处理
**当前状态**: ✅ 核心功能完成，1673 测试通过，覆盖率 66%

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

### ⏳ 进行中

| 任务 | 状态 | 说明 |
|------|------|------|
| 假测试清理 | 待继续 | 部分测试断言过于宽泛或验证自身常量 |
| 覆盖率提升 | 66% → 目标 70% | CLI 和 parallel 模块覆盖率最低 |

### 📋 待办

| 优先级 | 任务 | 说明 |
|--------|------|------|
| 低 | reflect_node 异常吞没 | 非关键节点，但应至少记录 ERROR 级别日志 |
| 低 | caplog 测试顺序问题 | test_prompts.py 在全量运行时 36 个测试因 logger handler 冲突失败 |
| 低 | 假测试清理 | ~52 个虚弱测试（弱断言/无断言/验证 Python 机制） |
| 低 | 无测试覆盖模块 | ~15 个源模块无测试（provider.py, observe.py, web_fetch.py 等） |

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

## 可用工具（18个）

| 类别 | 工具 |
|------|------|
| 文件操作 (8) | read_file, write_file, edit_file, force_write, list_dir, search_files, search_content, list_locks |
| 命令执行 (2) | run_command, run_background |
| Web (3) | web_search, web_fetch, weather |
| Agent协作 (7) | spawn_agent, spawn_parallel, list_agents, get_result, plan_parallel, execute_parallel, parallel_status, aggregate_results |

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
