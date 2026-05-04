"""LLM settings: API keys, models, token budgets, and agent configuration.

This module provides LLM-related configuration:
- API keys for different providers
- Model settings and defaults
- Token budget management
- Agent iteration limits
- Sub-agent configuration
- Session settings
"""

from typing import Optional, List
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .base_settings import ModelProvider


class LLMSettings(BaseSettings):
    """LLM and agent configuration settings.

    This class handles:
    - API keys for Anthropic, OpenAI, Google
    - Model selection and provider detection
    - Token budget management
    - Agent iteration limits
    - Sub-agent tools and limits
    - Session persistence
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # API Keys
    anthropic_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    google_api_key: Optional[str] = None

    # OpenAI compatible (DeepSeek, etc.)
    openai_base_url: Optional[str] = None

    # Model settings
    default_model: str = Field(default="deepseek-v4-flash")
    ollama_base_url: str = Field(default="http://localhost:11434")

    # Agent settings
    max_sub_agents: int = Field(default=3)
    max_iterations: int = Field(default=10)

    # Sub-agent settings
    max_subagent_iterations: int = Field(default=5)
    subagent_allowed_tools: List[str] = Field(default=[
        "read_file", "write_file", "edit_file",
        "list_dir", "search_files", "search_content",
        "run_command", "web_search"
    ])

    # Session settings
    auto_save_enabled: bool = Field(default=True)
    session_db_path: str = Field(default="sessions.db")

    # Streaming settings
    streaming_enabled: bool = Field(default=True)

    # Token budget settings
    # Note: budget_ratio lowered from 0.8 to 0.65 to trigger compression earlier
    # This leaves more headroom for summarization to succeed
    token_budget_ratio: float = Field(default=0.65)
    token_warn_ratio: float = Field(default=0.55)
    token_strategy: str = Field(default="summarize")
    token_reserved_output: int = Field(default=4096)

    # LLM output settings
    llm_max_tokens: int = Field(default=16384)  # Max output tokens for LLM calls

    @field_validator("max_iterations")
    @classmethod
    def validate_max_iterations(cls, v: int) -> int:
        """Validate max_iterations is in valid range (1-100)."""
        if not 1 <= v <= 100:
            raise ValueError(f"max_iterations must be between 1 and 100, got {v}")
        return v

    @field_validator("max_sub_agents")
    @classmethod
    def validate_max_sub_agents(cls, v: int) -> int:
        """Validate max_sub_agents is in valid range (1-10)."""
        if not 1 <= v <= 10:
            raise ValueError(f"max_sub_agents must be between 1 and 10, got {v}")
        return v

    @field_validator("token_budget_ratio")
    @classmethod
    def validate_token_budget_ratio(cls, v: float) -> float:
        """Validate token_budget_ratio is in valid range (0.1-1.0)."""
        if not 0.1 <= v <= 1.0:
            raise ValueError(f"token_budget_ratio must be between 0.1 and 1.0, got {v}")
        return v

    @field_validator("token_warn_ratio")
    @classmethod
    def validate_token_warn_ratio(cls, v: float) -> float:
        """Validate token_warn_ratio is in valid range (0.1-1.0)."""
        if not 0.1 <= v <= 1.0:
            raise ValueError(f"token_warn_ratio must be between 0.1 and 1.0, got {v}")
        return v

    @field_validator("llm_max_tokens")
    @classmethod
    def validate_llm_max_tokens(cls, v: int) -> int:
        """Validate llm_max_tokens is in valid range (1024-128000)."""
        if not 1024 <= v <= 128000:
            raise ValueError(f"llm_max_tokens must be between 1024 and 128000, got {v}")
        return v

    def get_model_provider(self, model: Optional[str] = None) -> ModelProvider:
        """Detect model provider from model name."""
        model_name = model or self.default_model
        model_lower = model_name.lower()

        if "claude" in model_lower or model_lower.startswith("anthropic"):
            return ModelProvider.CLAUDE
        elif "deepseek" in model_lower:
            return ModelProvider.DEEPSEEK
        elif "gpt" in model_lower or "o1" in model_lower or model_lower.startswith("openai"):
            return ModelProvider.OPENAI
        elif "gemini" in model_lower:
            return ModelProvider.GEMINI
        else:
            return ModelProvider.OLLAMA


__all__ = ["LLMSettings"]
