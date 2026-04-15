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
