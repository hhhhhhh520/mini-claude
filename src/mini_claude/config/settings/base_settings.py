"""Base settings: enums, project paths, and environment configuration.

This module provides the foundational configuration components:
- Environment type enum
- Model provider enum
- Vector database type enum
- ConfigReloadResult dataclass for hot reload
- Base environment and workspace settings
"""

from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ModelProvider(str, Enum):
    """Supported LLM providers."""
    CLAUDE = "claude"
    OPENAI = "openai"
    GEMINI = "gemini"
    DEEPSEEK = "deepseek"
    OLLAMA = "ollama"


class VectorDBType(str, Enum):
    """Supported vector database types."""
    CHROMA = "chroma"
    FAISS = "faiss"


class Environment(str, Enum):
    """Supported environment types."""
    DEV = "dev"
    STAGING = "staging"
    PROD = "prod"


@dataclass
class ConfigChange:
    """Represents a single configuration change."""
    key: str
    old_value: Any
    new_value: Any


@dataclass
class ConfigReloadResult:
    """Result of a configuration reload operation."""
    success: bool
    changes: List[ConfigChange] = field(default_factory=list)
    error: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def has_changes(self) -> bool:
        """Check if any changes were made."""
        return len(self.changes) > 0

    def get_change_summary(self) -> Dict[str, Any]:
        """Get a summary of changes for display."""
        return {
            "success": self.success,
            "changed_count": len(self.changes),
            "changed_keys": [c.key for c in self.changes],
            "changes": [
                {"key": c.key, "old": c.old_value, "new": c.new_value}
                for c in self.changes
            ],
            "error": self.error,
            "timestamp": self.timestamp,
        }


class BaseEnvironmentSettings(BaseSettings):
    """Base environment and workspace settings.

    This class handles:
    - Environment type (dev/staging/prod)
    - Workspace root path
    - Config hot reload settings
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Environment settings
    environment: str = Field(default="dev")

    # Workspace
    workspace_root: str = Field(default="D:/my project/mini-claude/workspace")

    # Config Hot Reload settings
    config_watch_enabled: bool = Field(default=False)
    config_watch_debounce_seconds: float = Field(default=1.0)

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        """Validate environment is a supported type."""
        valid_envs = [e.value for e in Environment]
        if v.lower() not in valid_envs:
            raise ValueError(f"environment must be one of {valid_envs}, got '{v}'")
        return v.lower()


# Expose common enums and types at module level
__all__ = [
    "ModelProvider",
    "VectorDBType",
    "Environment",
    "ConfigChange",
    "ConfigReloadResult",
    "BaseEnvironmentSettings",
]
