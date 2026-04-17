# Mini Claude Code 项目规范

## 项目概述

基于 LangGraph 状态机与 LiteLLM 统一接口的多 Agent CLI 编程助手。

**核心特性**:
- THINK→PLAN→ACT→OBSERVE 四阶段状态机循环
- 支持 Claude/OpenAI/DeepSeek/Gemini/Ollama 五种模型提供商
- 18个工具：文件操作、命令执行、Web搜索、Agent协作
- 子 Agent 并行执行 + 文件锁机制
- SQLite 会话持久化 + REPL 交互

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
