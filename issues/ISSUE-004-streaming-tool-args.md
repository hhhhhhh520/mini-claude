# 流式输出工具参数实现

> 创建时间: 2026-04-16
> 状态: 🟢 已解决

## 问题描述

用户期望在模型生成代码时能够实时看到代码内容流式输出，而不是等工具执行完成后才一次性显示。

原始行为：
```
[DEBUG] act_node: tool_calls=[{'name': 'write_file', 'args': {...}}]
# 所有代码一次性显示
```

期望行为：
```
[tool] write_file({"path": "index.html", "content": "<!DOCTYPE html>
<html>
...（代码逐字符流式显示）
"})
```

## 技术背景

DeepSeek API 的流式 tool calling 格式：
- 第一个 chunk：包含 `id` 和 `function.name`
- 后续 chunks：`id` 为 `None`，`function.arguments` 逐字符传输（每个 chunk 1-15 字符）

测试显示一次 tool call 会被拆分成 **771 个 chunks**，总共约 2843 字符的参数。

## 解决方案

### 1. 新增 `tool_stream_callback` 参数

`provider.py`:
```python
async def chat_stream_with_tools(
    self,
    ...
    stream_callback=None,
    tool_stream_callback=None,  # New: callback for tool arguments streaming
) -> Dict[str, Any]:
```

### 2. 流式输出工具名称和参数

```python
if hasattr(tc.function, 'name') and tc.function.name:
    tool_calls_data[tc_index]["name"] = tc.function.name
    if tool_stream_callback:
        tool_stream_callback("name", tc.function.name)  # 输出工具名

if hasattr(tc.function, 'arguments') and tc.function.arguments:
    tool_calls_data[tc_index]["arguments"] += tc.function.arguments
    if tool_stream_callback:
        tool_stream_callback("args", tc.function.arguments)  # 流式输出参数
```

### 3. Display 类新增方法

```python
def show_tool_call_start(self, tool_name: str):
    """Display tool call start (for streaming)."""
    sys.stdout.write(f"\n[tool] {tool_name}(")
    sys.stdout.flush()

def stream_tool_args(self, args_chunk: str):
    """Stream tool arguments (code content)."""
    sys.stdout.write(args_chunk)
    sys.stdout.flush()
```

### 4. Windows 终端兼容

使用 `sys.stdout.write()` + `sys.stdout.flush()` 而不是 `print()`，确保 Windows 终端立即输出。

## 相关文件

- `src/mini_claude/llm/provider.py` - `chat_stream_with_tools()` 方法
- `src/mini_claude/cli/display.py` - `show_tool_call_start()`, `stream_tool_args()` 方法
- `src/mini_claude/agent/nodes.py` - `act_node()` 中的回调设置

## 测试验证

```
[tool] write_file({"path": "test.html", "content": "<!DOCTYPE html>
<html lang=\"zh-CN\">
<head>
...
"})
```

代码内容逐字符流式显示，用户体验显著提升。
