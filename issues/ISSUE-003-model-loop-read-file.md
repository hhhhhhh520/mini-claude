# 模型反复读取文件而不创建缺失文件

> 创建时间: 2026-04-16
> 状态: 🟢 已解决

## 问题描述

当模型创建 HTML 和 CSS 后，需要创建 JS 文件，但模型反复调用 `read_file` 而不是 `write_file`，导致递归限制达到25次。

```
[DEBUG] observe_node: checking disk FIRST: has_html=True, has_css=True, has_js=False
[DEBUG] act_node: tool_calls=[{'name': 'read_file', 'args': {'path': 'style.css'}}]
```

另外，流式解析时出现空的 tool call：
```
tool_calls=[{'name': 'write_file', 'args': {}}]
```

## 出现原因

1. **提醒消息不够明确**：模型没有理解应该创建文件而不是读取
2. **空参数处理**：流式解析时某些 tool call 参数丢失

## 解决方案

1. 增强提醒消息，明确禁止使用 `read_file`：
```python
reminder = f"""重要提醒：项目文件不完整，缺少: {', '.join(missing)}

请立即使用 write_file 工具创建这些文件：
- write_file(path="script.js", content="...")

禁止使用 read_file 或 list_dir，必须使用 write_file 创建新文件！"""
```

2. 跳过空的 tool call：
```python
if not tc.get("name"):
    safe_print(f"[DEBUG] act_node: skipping tool call with empty name: {tc}")
    continue
```

## 相关文件

- `src/mini_claude/agent/nodes.py` - `observe_node()` 和 `act_node()` 函数
