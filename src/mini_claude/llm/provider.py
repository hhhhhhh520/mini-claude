"""LiteLLM provider wrapper."""

import os
from typing import Optional, List, Dict, Any, AsyncIterator
from enum import Enum

from litellm import acompletion, completion

from mini_claude.config.settings import settings, ModelProvider


class LLMProvider:
    """Unified LLM provider using LiteLLM."""

    def __init__(self, model: Optional[str] = None):
        self.model = model or settings.default_model
        self.provider = settings.get_model_provider(self.model)
        self._setup_api_keys()

    def _setup_api_keys(self):
        """Set up API keys based on provider."""
        # Already set in settings.py
        pass

    def get_model_name(self) -> str:
        """Get the full model name for LiteLLM."""
        model = self.model

        # LiteLLM format: provider/model
        if self.provider == ModelProvider.CLAUDE:
            if not model.startswith("anthropic/"):
                model = f"anthropic/{model}"
        elif self.provider == ModelProvider.DEEPSEEK:
            # DeepSeek uses OpenAI-compatible API
            if not model.startswith("openai/"):
                model = f"openai/{model}"
        elif self.provider == ModelProvider.OPENAI:
            if not model.startswith("openai/"):
                model = f"openai/{model}"
        elif self.provider == ModelProvider.GEMINI:
            if not model.startswith("gemini/"):
                model = f"gemini/{model}"
        elif self.provider == ModelProvider.OLLAMA:
            if not model.startswith("ollama/"):
                model = f"ollama/{model}"

        return model

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> Dict[str, Any]:
        """Send a chat completion request."""
        model_name = self.get_model_name()

        kwargs = {
            "model": model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if tools:
            kwargs["tools"] = tools
        if tool_choice:
            kwargs["tool_choice"] = tool_choice

        response = await acompletion(**kwargs)
        return response

    async def chat_stream(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        """Stream chat completion."""
        model_name = self.get_model_name()

        kwargs = {
            "model": model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }

        if tools:
            kwargs["tools"] = tools

        response = await acompletion(**kwargs)

        async for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    async def chat_stream_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        stream_callback=None,
        tool_stream_callback=None,  # New: callback for tool arguments streaming
    ) -> Dict[str, Any]:
        """
        Stream chat completion with tool support.
        Streams content tokens, then returns final response with tool_calls if any.
        """
        model_name = self.get_model_name()

        kwargs = {
            "model": model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }

        if tools:
            kwargs["tools"] = tools
        if tool_choice:
            kwargs["tool_choice"] = tool_choice

        response = await acompletion(**kwargs)

        # Collect streamed response
        content_parts = []
        tool_calls_data = {}  # index -> {id, name, arguments}
        current_tool_name = None  # Track current tool for streaming display

        async for chunk in response:
            delta = chunk.choices[0].delta

            # Stream content
            if delta.content:
                content_parts.append(delta.content)
                if stream_callback:
                    stream_callback(delta.content)

            # Collect tool calls (streamed incrementally)
            # Use 'index' as key since subsequent chunks have id=None
            if hasattr(delta, 'tool_calls') and delta.tool_calls:
                for tc in delta.tool_calls:
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
                            current_tool_name = tc.function.name
                            # Announce tool call start
                            if tool_stream_callback:
                                tool_stream_callback("name", tc.function.name)

                        if hasattr(tc.function, 'arguments') and tc.function.arguments:
                            tool_calls_data[tc_index]["arguments"] += tc.function.arguments
                            # Stream each argument chunk
                            if tool_stream_callback:
                                tool_stream_callback("args", tc.function.arguments)

        # Build final response
        final_content = "".join(content_parts)

        # Convert tool_calls_data to list format
        final_tool_calls = None
        if tool_calls_data:
            final_tool_calls = []
            for index in sorted(tool_calls_data.keys()):
                tc = tool_calls_data[index]
                if tc["name"]:  # Only include if we have a function name
                    final_tool_calls.append({
                        "id": tc["id"] or f"call_{index}",
                        "name": tc["name"],
                        "arguments": tc["arguments"]
                    })

        # Return in same format as non-streaming
        return {
            "content": final_content,
            "tool_calls": final_tool_calls,
        }

    def sync_chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> Dict[str, Any]:
        """Synchronous chat completion."""
        model_name = self.get_model_name()

        kwargs = {
            "model": model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if tools:
            kwargs["tools"] = tools

        return completion(**kwargs)


# Tool conversion utilities
def convert_tools_to_litellm(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert tool definitions to LiteLLM format."""
    litellm_tools = []

    for tool in tools:
        litellm_tool = {
            "type": "function",
            "function": {
                "name": tool.get("name", ""),
                "description": tool.get("description", ""),
                "parameters": tool.get("parameters", {}),
            }
        }
        litellm_tools.append(litellm_tool)

    return litellm_tools
