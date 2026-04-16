# DeepSeek 流式 Tool Calling 解析错误

> 创建时间: 2026-04-16
> 状态: 🟢 已解决

## 问题描述

使用 DeepSeek API 的流式输出时，tool_calls 解析失败，生成数千个无效的 tool_calls，导致 Pydantic 验证错误：

```
156 validation errors for AIMessage
tool_calls.0.args: Input should be a valid dictionary [type=dict_type, input_value=0, input_type=int]
tool_calls.1.args: Input should be a valid dictionary [type=dict_type, input_value=1, input_type=int]
... (3000+ 个错误)
```

## 出现原因

DeepSeek 流式 API 的 tool_calls 分块传输格式特殊：

1. **第一个 chunk**：包含 `id` 和 `function.name`
2. **后续 chunks**：`id` 为 `None`，只包含 `function.arguments` 的单个字符片段

原代码使用 `id` 作为 key 来聚合 tool_calls：
```python
tc_id = tc.id if hasattr(tc, 'id') and tc.id else f"call_{len(tool_calls_data)}"
```

当后续 chunks 的 `id` 为 `None` 时，每次都生成新的 key，导致每个字符片段被当作独立的 tool call。

## 解决方案

使用 `index` 属性作为稳定标识符来跟踪同一个 tool call：

```python
# Get index - this is the stable identifier for streaming tool calls
tc_index = tc.index if hasattr(tc, 'index') and tc.index is not None else 0

# Initialize or update tool call data
if tc_index not in tool_calls_data:
    tool_calls_data[tc_index] = {
        "id": None,
        "name": "",
        "arguments": ""
    }

# Update id if present (first chunk)
if hasattr(tc, 'id') and tc.id:
    tool_calls_data[tc_index]["id"] = tc.id

# Update function name and arguments
if hasattr(tc, 'function') and tc.function:
    if hasattr(tc.function, 'name') and tc.function.name:
        tool_calls_data[tc_index]["name"] = tc.function.name
    if hasattr(tc.function, 'arguments') and tc.function.arguments:
        tool_calls_data[tc_index]["arguments"] += tc.function.arguments
```

## 相关文件

- `src/mini_claude/llm/provider.py` - `chat_stream_with_tools()` 方法
- `src/mini_claude/config/settings.py` - `streaming_enabled` 配置

## 参考资料

- [LiteLLM Streaming Documentation](https://docs.litellm.ai/docs/completion/stream)
- [OpenAI Chat Completions API - Streaming](https://platform.openai.com/docs/api-reference/chat/streaming)
