"""Pydantic Settings configuration."""

import os
from enum import Enum
from typing import Optional, List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ModelProvider(str, Enum):
    CLAUDE = "claude"
    OPENAI = "openai"
    GEMINI = "gemini"
    DEEPSEEK = "deepseek"
    OLLAMA = "ollama"


class Settings(BaseSettings):
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
    default_model: str = Field(default="deepseek-chat")
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

    # Workspace
    workspace_root: str = Field(default="D:/my project/mini-claude/workspace")

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


# Global settings instance
settings = Settings()

# Set environment variables for LiteLLM
if settings.openai_api_key:
    os.environ["OPENAI_API_KEY"] = settings.openai_api_key
if settings.openai_base_url:
    os.environ["OPENAI_BASE_URL"] = settings.openai_base_url
if settings.anthropic_api_key:
    os.environ["ANTHROPIC_API_KEY"] = settings.anthropic_api_key
