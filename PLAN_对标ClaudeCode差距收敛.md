# mini-claude 对标 Claude Code 功能差距收敛计划

> 创建时间: 2026-09-27
> 依据: 《ANALYSIS_对标ClaudeCode差距.md》（2026-09-26 会话内分析，2026-09-27 补档）+ free-code 逆向源码参考（`D:\Free-Claude\free-code-main`，仅作规格参考）
> 前置状态: CI 已恢复绿（ISSUE-023/024 已修，run 36235828054 success），可安心迭代

---

## 一、目标与原则

**目标**：把 mini-claude 从"核心循环对齐（85-90%）"推进到"平台能力对齐"，按用户感知价值排序收敛差距，全程保持现有工程纪律。

**不可违反的原则**：

1. **IP 纪律**：free-code 是专有软件的逆向产物，**只读架构与行为语义，一律不搬运代码**（哪怕改名）。所有实现用 Python 按 mini-claude 现有架构风格从零写。
2. **先红后绿**：每个功能先写失败测试再实现（项目既有纪律）。
3. **完成定义（DoD）**，每个任务收尾必须全部满足：
   - [ ] 新增/修改代码有测试，两层全绿：
     `pytest tests/ -m "unit or not integration and not e2e and not stress and not chaos"`（CI 筛选层）
     与 `pytest tests/test_integration tests/test_e2e.py -m "integration"`（integration 层）
   - [ ] 无任何测试打真实网络：`OPENAI_BASE_URL=http://127.0.0.1:9` 下两层全绿
     （e2e 标记除外；2026-09-27 勘误后新增，防"环境运气绿"）
   - [ ] `ruff check` + `ruff format --check` 通过（规则集已锁定 E4/E7/E9/F）
   - [ ] push 后 CI 绿
   - [ ] 根因/设计记录进 `issues/`（本地，gitignored）
   - [ ] README.md 徽章同步（现有 4 枚徽章中的 **Tools-24** 工具数；目前无命令数徽章，若新增 `/mcp`、`/permissions` 等命令可顺带补建）
   - [ ] 至少 1 条真 Key 联调 E2E（mock 测试不等于功能正常）
   - [ ] 改动涉及工具循环（act/_act_helpers/main.py ask 路径）时，追加真网多步任务
     验收：连续 ≥3 轮工具调用全部以 API tool_calls 执行、无 `<tool_call>` 正文泄漏
     （2026-09-28 ISSUE-026 后新增；mock 层绿 ≠ 真实 provider 语义对）
4. **架构红线**（来自项目 CLAUDE.md，新功能不得破坏）：
   - `messages` 是累加 reducer，节点只返回增量；todo 等需要全量替换的状态**不得**挂 `add` reducer
   - 系统提示/CLAUDE.md/skills 不写入 `state["messages"]`，走 `build_system_messages()` 每次前置
   - 子代理工具白名单**有且有两份**：`SpawnAgentTool.ALLOWED_TOOLS` 与
     `SpawnParallelTool.ALLOWED_TOOLS`（`tools/agent_spawn.py`，两份内容相同）。
     新工具默认都不进；确需进子代理时**必须同步改两处**（消除重复已在 backlog）
   - 任何新退出路径必须 `finally` 清后台进程 + `close_checkpoint_connections()`

---

## 二、现状盘点

| 已对齐 | 缺口（按价值排序） |
|---|---|
| Agent 主循环（THINK→PLAN→ACT→OBSERVE→REFLECT→错误恢复） | MCP 客户端（生态缺口） |
| 无头模式 `ask` / `ask --full` / `--json` | TodoWrite + 计划可视化 |
| SQLite checkpoint + `/resume` | CLAUDE.md 自动加载 |
| 上下文压缩（token 预算 + summarize） | Hooks（PreToolUse/PostToolUse 切面） |
| 子 Agent 隔离（contextvars + 工具白名单） | 细粒度权限系统（模式 + allow/ask/deny 规则） |
| Skills 系统（`~/.mini-claude/skills/`） | Rewind（checkpoint 级回退） |
| 反而领先：文件锁/拓扑并行编排/工具降级熔断/白名单深度 | 交互细节（diff 预览、后台任务输出、/model 热切换等） |

> PLAN 可视化已有基础（`cli/plan_display.py` + state 的 `execution_plan`），本期补它与 todo 的联动。

---

## 三、阶段计划

### Phase 1：快赢包（预计 2~3 天）

用户感知最强、成本最低的两个功能，做完即可声称"对标 Claude Code"站得住。

#### P1-1 TodoWrite 工具

| 项 | 内容 |
|---|---|
| 数据模型 | 会话级 todo 列表：`[{content, status: pending\|in_progress\|completed, active_form}]`；**全量替换语义**（工具每次提交完整列表），放 `AgentState` 独立字段，不挂 `add` reducer |
| 新工具 | `todo_write`（`tools/`，注册进 ToolRegistry；不进子代理白名单——todo 属于主会话状态） |
| 渲染 | 每轮图执行后 REPL 渲染清单（✓/→/○），改动时增量刷新（`display.py`） |
| 联动 | PLAN 节点产出 `execution_plan` 步骤后提示 LLM 可一键生成对应 todos；完成 todo 时校验"恰好一个 in_progress" |
| 提示词 | `llm/prompts.py` 增补使用时机说明（何时建清单、何时更新），自己写，不抄 |
| 参考 | `src/tools/TodoWriteTool/`（数据模型、prompt 结构、`checkPermissions` 恒 allow 的设计） |
| 测试 | 工具 schema/非法状态拒绝（红→绿）；图级：fake LLM 连续 todo_write 断言状态替换语义；渲染快照测试 |

#### P1-2 CLAUDE.md 自动加载

| 项 | 内容 |
|---|---|
| 加载范围 | ① `settings.workspace_root` 下的 `CLAUDE.md`（项目级）；② `~/.mini-claude/CLAUDE.md`（用户级）。合并顺序：用户级在前、项目级在后 |
| 注入点 | `build_system_messages()` 前置，**不进持久化历史**（架构红线），与 skills 同位置 |
| 上限 | 单文件读取上限（如 64KB）+ 总注入上限（走 token 预算，超出截断并告警） |
| 开关 | settings 配置项 + REPL `/config` 可关 |
| 明确延后 | `@import` 语法、企业策略层级、external includes 对话框——backlog |
| 参考 | `src/utils/claudemd.ts`（1479 行；只借鉴层级与合并语义、截断策略） |
| 测试 | 加载器单测（缺失/为空/超限/合并顺序）；act 节点注入断言；`/config` 开关联动 |

**Phase 1 验收**：REPL 里让 LLM 修一个多文件 bug，能看到 todo 清单实时推进；mini-claude 自己的仓库放一份 CLAUDE.md，启动后行为受其约束（自举验证）。

---

### Phase 2：MCP 客户端（预计 5~8 天）

单项生态收益最大，把"所有工具自己写"变成"接整个 MCP 生态"。

| 项 | 内容 |
|---|---|
| 依赖 | 官方 `mcp` Python SDK（严格 pin 版本——ISSUE-024 的教训）；进 `[project.optional-dependencies] mcp`，缺件时给中文指引（沿用 web/vector 的 extras 模式） |
| 配置 | `.mini-claude/mcp.json`：`{server_name: {command, args, env}}`（stdio 为主）；对齐 Claude Code 的配置形态便于用户迁移 |
| 核心模块 | `src/mini_claude/mcp/`：`client.py`（连接生命周期 + 健康检查）、`manager.py`（多 server 启停/重连）、`bridge.py`（把远端工具适配成 `BaseTool` 注册进 ToolRegistry，命名 `mcp__<server>__<tool>`） |
| 安全 | MCP 工具默认 **confirmation 通道**（等同路径确认），settings 可对特定 server/tool 放行；子代理默认不可见 |
| REPL | `/mcp` 命令：列出 server/工具/连接状态，支持重连（`cli/commands/` 新 handler） |
| 资源与 OAuth | 明确延后：resource 读取、elicitation、OAuth——backlog |
| 参考 | `src/services/mcp/`（client/ConnectionManager/transport 划分）、`src/tools/MCPTool` |
| 测试 | bridge 单测（mock session）；E2E：仓库内放一个最小 stdio echo server 脚本，真实连接→发现→调用；缺 extras 指引测试 |
| 风险 | Windows stdio 子进程编码/关闭信号差异（E2E 必须真跑 Windows）；async SDK 与现有事件循环纪律（连接登记进统一清理表） |

**Phase 2 验收**：配置一个真实 MCP server（如 filesystem-server），`/mcp` 可见，`ask` 能调用其工具完成任务。

---

### Phase 3：Hooks + 细粒度权限（预计 5~7 天）

两个切面都在 `ToolRegistry.execute()` 这个既有位置收口（降级管理器已在此），做单一裁决点。

#### P3-1 Hooks

- 事件：`PreToolUse` / `PostToolUse` / `Stop`；配置 `.mini-claude/hooks.json`（形态对齐 Claude Code：事件 → 匹配器 → 命令）
- 执行：子进程跑用户命令，JSON 走 stdin/stdout；**超时强制杀**（复用后台进程清理纪律）；PreToolUse 返回阻断则工具不执行
- 挂点：`ToolRegistry.execute()` 工具执行前后分发（与降级管理器同位置，单一裁决点）
- 约束：hooks 是用户自配的受信配置，但不在子代理中执行；不与安全白名单冲突（白名单管 LLM，hooks 管用户）
- 参考：`src/services/tools/toolHooks.ts` + `toolExecution.ts`（事件挂点**实现**所在）、`src/components/hooks/`（配置 UI）、`src/entrypoints/sdk/coreTypes.ts`（事件类型 schema）。注意 `src/Tool.ts`/`commands/init.ts` 里 grep 到的 PreToolUse 只是 JSDoc 注释与 `/init` 提示词文本，不是实现
- 测试：分发器单测（mock 命令）、超时阻断、PostToolUse 修改输出

#### P3-2 权限系统

- 模式：`default` / `accept_edits` / `plan` / `bypass`（REPL shift+tab 循环切换，`/permissions` 查看）
- 规则：allow/ask/deny 三态，按 `工具名` / `工具名:前缀`（如 `run_command:git *`）匹配；存 `.mini-claude/settings.json`；规则解析器单测穷举
- 裁决顺序：**deny > ask > allow > 模式默认**；既有 `safety.py` 白名单作为 deny 之下的硬底线不变（双轨不冲突：白名单是安全底线，权限是用户意愿）
- 会话内记忆"本次会话不再询问"
- 参考：`src/utils/permissions/`（PermissionMode/Rule/permissionRuleParser/dangerousPatterns 的职责划分）
- 测试：解析器穷举、优先级组合、模式切换对裁决的影响、REPL 交互流

**Phase 3 验收**：deny 规则能拦住 LLM 的指定命令；accept_edits 下文件编辑不再逐次确认；hook 能在一次真实工具调用前后被触发。

---

### Phase 4：Rewind + 体验打磨（预计 5~7 天）

| 项 | 内容 | 说明 |
|---|---|---|
| P4-1 `/rewind` | 列出当前 thread 的 checkpoint 序列 → 选择 → 从该点重新 invoke | 我们用 `AsyncSqliteSaver` 存了每步全量状态，比本体（消息选择器方案）更直接；注意连接生命周期纪律与递归上限 |
| P4-2 后台任务输出 | `run_background` 已有，补 `task_output`/`task_kill` 工具，读输出文件 + 杀进程 | 对齐本体的 BashOutput/KillShell |
| P4-3 编辑 diff 预览 | `edit_file`/`write_file` 在 confirmation 流程展示 unified diff 再确认 | 复用现有 pending_confirmation 机制 |
| P4-4 `/model` 热切换 | **改造现有 `/model` 占位**（`cli/commands/help_handler.py` 中已注册，当前返回 "not supported"）：接入 provider/model 重建，替换 `.env` 默认值来源 | 对齐本体 `/model`；消息需同步 `llm_settings` 而非只改会话变量 |
| 参考 | `src/commands/rewind/`、BashTool 后台部分 | |

**Phase 4 验收**：真实会话中 rewind 回两步前重跑成功且 checkpoint 连接无泄漏（进程正常退出）。

---

### 加固收尾（2026-09-28 完成，属 Phases 收尾的工程加固）

- ✅ **constraints.txt 依赖锁合面**：全部直接依赖 + dev 工具链 + 强耦合传递依赖 pin 到实测绿版本；CI 全部安装步骤（lint/unit/integration/regression/coverage）统一带 `-c constraints.txt`，本地与 CI 解析同一合面——根治 ISSUE-023/024 类"上游发新版 → CI 无故全红"漂移
- ✅ **CI integration 层 job**：原 job 仅 PR/dispatch 触发（本仓库直推 master，等于从不运行）；现随每次 push 运行，且 `OPENAI_BASE_URL` 指向不可达端口——integration 层承诺全 mock，打真网即红，"CI 绿但 integration 假 mock"盲区关死
- ✅ **删除 `config/settings.py` shim**：与 `settings/` 包同名并存（包优先加载，shim 是死文件，已用 `sys.modules` 验证），却是 py3.10 mock 字符串目标事故的混乱根源；删除后所有导入解析到包，规范写入 CLAUDE.md

---

### 后续 Backlog（不承诺排期）

- ~~子代理白名单双份 `ALLOWED_TOOLS` 提取为共享常量~~ 已完成（2026-09-28 `SUBAGENT_ALLOWED_TOOLS`）
- ~~web 三件套异步化~~ 已完成（2026-09-28：httpx 共享 client + ddgs to_thread；注意 AsyncClient 构造的 SSL 证书库同步加载 ~0.2s，必须用进程级共享实例）
- ~~Task 系统 v2~~ 已完成（2026-09-28：task_create/update/list/get——编号只增不复用、依赖边双向同步防环、owner 委派子代理；state.tasks 全量替换唯一事实源，act 经 state_extras 通道回写、每轮覆盖模块级 store）
- ~~差距分析 Top3~~ 已完成（2026-09-28 收敛批次①）：①PreToolUse `updatedInput`/`allow` 结构化裁决 + payload 增强（session_id/permission_mode/cwd/$CLAUDE_PROJECT_DIR；ask 仍不支持）；②auto-compact 落盘（REPL 回合前 check_budget 超限即播种压缩，tasks/todos 随迁，60s 冷静期）；③/rewind 代码回退（file_history 会话日志 + `/rewind <n> [chat|code|both]`，进程内日志的诚实边界已声明）
- ~~hook 强制确认（ask）~~ / ~~MCP prompts 注册为斜杠命令~~ / ~~Task 清单跨会话落盘~~ / ~~工具结果尺寸统一上限~~ 已完成（2026-09-28 收敛批次②）
- ~~权限规则工具语法~~ / ~~可定义子代理 agents/*.md~~ / ~~plan 模式审批流~~ / ~~bash cwd 持久化~~ 已完成（2026-09-28 收敛批次③；cwd 版本诚实边界：env 不持久，本体的 shell snapshot 未做）
- ~~bash env 快照~~（会话级显式 export/set 持久化） / ~~系统提示词调校加厚~~ / ~~CLAUDE.md 记忆快捷面（/memory + #）~~ 已完成（2026-09-28 收敛批次④）
- ~~MCP OAuth（http transport）~~ 已完成（2026-10-02：`auth: "oauth"` / dict 形态（scope/callback/client_name）；401 自动触发 SDK 授权码+PKCE+动态注册+RFC 9728 发现，过期自动刷新；本地回环回调 server + OOB 手动粘贴兜底；token 落盘 ~/.mini-claude/mcp-auth/<server>.json（POSIX 0600）；授权失败/拒绝经异常翻译成 McpOAuthError，不阻断其他 server；三层测试——无 SDK 单测 / 真 SDK 单测 / FastMCP+uvicorn 回环 E2E 五场景）
- ~~任务完成能力四洞修复~~（2026-10-02 实测驱动）：①系统提示词注入 `<env>` 环境块（沙箱根/OS/shell 习惯，对齐本体 env 注入）②ask 模式接入完整系统消息（此前无系统提示词）③确认类异常翻译成工具错误回流（原 PathConfirmationRequired 炸穿 ask 循环）④ask 轮数预算 10→25 可配置。真机 2×2 复测：FizzBuzz 任务 ❌→✅、源码定位任务 崩溃→✅；附代根治 build_system_messages 迁移出 `_shared` 导入期单例副作用
- ~~敏感路径守卫~~（2026-10-02 拍板）：命令通道硬拒密钥/凭据路径（.env 模板变体放行/.ssh/mcp-auth/id_rsa/*.pem/credentials，白名单之前单点生效）；通用读面缺口文档化为已知边界
- ~~质量打磨小尾巴~~（2026-10-03）：`_shared` 导入期单例拔根（懒加载+四处绑定迁移+PEP 562 兼容面）；test_ask_exit_code 改依赖注入缝 `_build_ask_llm`（不再全局替换 LLMProvider 类）；新增 docs/mcp-oauth-guide.md 手测指南（GitHub 远程 MCP 端点实测核对）
- 差距清单剩余：Agent Teams/ScheduleCronTool（属未做新功能）——**已有功能对齐 Claude Code 的差距收敛完毕**
- 待独立评审：注入检查拦裸 $VAR（bash_env 测试因此改走 printenv）——放宽属安全策略变更，需单独评审+测试，勿顺手改
- `ScheduleCronTool` 定时任务、Agent Teams
- ~~CLAUDE.md `@import`~~ 已完成（2026-09-28：@path/@./x/@~/x/@abs 五跳防环 + CLAUDE.local.md）；扩展思考开关（/ultrathink 类）、视觉输入、statusline/主题
- ~~MCP HTTP transport + resources/prompts~~ 已完成（2026-09-28：`type:http` + url/headers（type 缺省按字段推断，sse 显式拒绝）；resources/prompts 四个全局只读工具，连接时幂等注册；真 FastMCP+uvicorn 回环 E2E；OAuth 已于 2026-10-02 补齐，见上）
- ~~Hooks 尾部四事件~~ 已完成（2026-09-28：SessionStart/SessionEnd/PreCompact/SubagentStart，事件面 6→10；SessionStart stdout/additionalContext 注入会话级上下文走 hook_context 通道；均已非阻断）
- ~~/compact 手动压缩 + PreCompact hook~~ 已完成（2026-09-28：复用 summarize_messages 引擎透传自定义指令；**压缩结果播种新 thread_id**——messages 是裸 add reducer，aupdate_state 无法替换；持久化前修剪孤儿 tool 结果防 ISSUE-026 复发）
- ~~/add-dir 多工作目录~~ 已完成（2026-09-28：safety.py 多根注册表 `_additional_roots`，validate_path 三处比较点 OR 并入；额外根带 os.sep 守卫防兄弟前缀误放行，主根行为不变）

---

## 四、风险与对策

| 风险 | 对策 |
|---|---|
| 依赖漂移再度引爆 CI（click/ruff 前科） | ~~尽快上 constraints~~ 已上（2026-09-28）：constraints.txt 锁合面 + CI 全步骤接入，升级依赖走显式流程（改 pin → 全绿 → 盯 CI） |
| TodoWrite 与 `add` reducer 语义冲突（ISSUE-014 同类） | todo 字段全量替换、图级测试锁死"不被复制" |
| MCP SDK 迭代快 + Windows stdio 差异 | pin 版本；E2E 真跑 Windows；连接进统一清理表 |
| 权限系统与 safety.py 双轨打架 | 单一裁决点收口，白名单定位为硬底线写进 CLAUDE.md |
| hooks 执行外部命令的供应链面 | 仅用户自配、超时强杀、子代理不可见 |
| 范围蔓延（本体 1934 个文件，学不完） | 按本计划阶段收口，每阶段有明确"明确延后"清单 |

## 五、明确不做（当前版本）

视觉/语音、IDE 集成、远程 bridge、GitHub Actions 集成、插件市场、企业策略管理。

## 六、参考源码索引（free-code，只读规格）

| 主题 | 路径 |
|---|---|
| Todo/Task | `src/tools/TodoWriteTool/`、`src/utils/todo/`、`src/tools/Task*Tool/` |
| CLAUDE.md | `src/utils/claudemd.ts`、`src/commands/memory/` |
| MCP | `src/services/mcp/`、`src/tools/MCPTool/`、`src/utils/mcp/` |
| 权限 | `src/utils/permissions/`、`src/hooks/toolPermission/` |
| Hooks | `src/services/tools/toolHooks.ts`、`toolExecution.ts`（实现）；`src/components/hooks/`（配置 UI）；`src/entrypoints/sdk/coreTypes.ts`（事件类型） |
| Rewind | `src/commands/rewind/` |
| 计划模式 | `src/tools/EnterPlanModeTool/`、`ExitPlanModeTool/` |
| 功能开关全景 | `FEATURES.md`（88 flags 审计） |
