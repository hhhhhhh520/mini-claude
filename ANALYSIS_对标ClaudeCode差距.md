# 对标 Claude Code 功能差距分析

> 分析时间: 2026-09-26（会话内完成），2026-09-27 补档落盘
> 结论供《PLAN_对标ClaudeCode差距收敛.md》引用；补充参考：free-code 逆向源码（`D:\Free-Claude\free-code-main`，仅作规格参考，不搬运代码）
>
> **⚠️ 状态（2026-10-02）：本文是历史分析，下列差距已全部收敛**——MCP（stdio+HTTP+OAuth，7286e32）、
> Hooks 十事件、CLAUDE.md 自动加载、TodoWrite/任务系统、细粒度权限、rewind、/compact、
> 自动压缩均已落地，销项明细见 PLAN 文档。本文保留作为起点基线，勿据此判断现状。

## 总体判断

**核心 Agent 循环已达到 85–90% 的对等度**，差距主要在**平台化能力**（扩展生态、细粒度权限、上下文工程约定）和**交互打磨**上。整体按"功能广度 × 完成度"估算，大约是本体的 50–60%——但有几处反而 mini-claude 领先。

## 一、已对齐或接近对齐

| 能力 | mini-claude | 说明 |
|---|---|---|
| Agent 主循环 | THINK→PLAN→ACT→OBSERVE→REFLECT→错误恢复 | 比 Claude Code 的自由循环更结构化，反思/重试是显式节点 |
| 无头模式 | `ask` / `ask --full` / `--json` | 对应 `claude -p`，含 JSON 输出契约 |
| 会话持久化 | SQLite checkpoint + `/resume` | 对齐 |
| 上下文压缩 | token 预算 + summarize | 对应 auto-compact，基本对齐 |
| 子 Agent 隔离 | contextvars 协程级隔离 + 工具白名单 | 对齐 |
| Skills 系统 | `~/.mini-claude/skills/` + `/skill` + 自动匹配 | 对齐 Claude Code 的 SKILL.md 机制 |
| 流式输出 / Rich 展示 | 有 | 对齐 |

## 二、主要差距（按价值排序）

1. **MCP 客户端支持——最大的生态缺口。** Claude Code 能接入任意外部工具服务器（数据库、浏览器、API），这是它的可扩展性根基。mini-claude 目前零支持，所有工具都得自己写 Python。补上 MCP 意味着瞬间获得整个生态的工具，单项收益最大。
2. **Hooks（工具调用拦截）。** PreToolUse/PostToolUse 钩子允许在每次工具执行前后插入自定义逻辑（审计、拦截、自动格式化）。mini-claude 的 ToolRegistry 是内聚的，没有暴露这个切面。
3. **CLAUDE.md 上下文自动加载。** Claude Code 启动时自动读取并注入项目级 CLAUDE.md 作为持久约定。mini-claude 只有内置系统提示 + skills 注入——讽刺的是本项目自己的开发流程天天在用 CLAUDE.md，它自己却读不到。
4. **任务追踪（TodoWrite）+ 面向用户的计划模式。** Claude Code 用 todo 列表向用户展示执行进度、支持 plan mode 先审后做。mini-claude 的 PLAN 节点是内部状态，用户看不到也改不了；长任务时"现在在干嘛"缺乏可见性。
5. **细粒度权限系统。** Claude Code 是按工具分类的 allow/ask/deny + 四种权限模式（default/acceptEdits/plan/bypass）。mini-claude 只有命令白名单 + 路径确认两种粒度——安全检查的**深度**不差（SSRF/注入/供应链都覆盖），差的是**用户可控性**。
6. **Checkpoint 回退（rewind）。** Claude Code 可以回到任意检查点重跑。mini-claude 只能整体 `/resume`，不能回退到中途。
7. **交互细节一批**：图片/视觉输入、扩展思考模式、`/model` 热切换、编辑 diff 预览确认、后台任务输出读取（`run_background` 有了但没有对应的取输出工具）、vim 模式、自定义 statusline。单个都不大，合起来决定"手感"。

## 三、mini-claude 反而领先的点

- **文件锁 + 冲突检测**：多 Agent 并发写同一项目的读写锁 + hash 乐观锁，Claude Code 本体没有内建（靠 Task agent 自觉分工）。
- **依赖拓扑并行编排**：`plan_parallel` 依赖分析 + 分层执行 + 自动聚合，比本体 Task 工具更结构化。
- **工具降级熔断**：连续失败 3 次自动跳过、10 分钟恢复，本体没有。
- **命令白名单深度**：供应链（pip）、模块级黑名单、DNS 重绑定防护，比本体的 bash 沙箱思路更"白盒"。

## 四、收敛路线建议

MCP（最大生态收益）→ TodoWrite + 计划可视化（用户感知最强、成本最低）→ CLAUDE.md 自动加载（成本低、与自身开发习惯闭环）→ Hooks → 细粒度权限 → rewind。

> 实际排期按"先快赢后硬骨头"调整为：TodoWrite + CLAUDE.md → MCP → Hooks + 权限 → rewind，见 PLAN 文档。
