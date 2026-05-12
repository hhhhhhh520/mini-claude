"""Security settings: rate limiting, vector database, and user profile configuration.

This module provides security-related configuration:
- Rate limiting settings (strategies, limits)
- Vector database configuration
- User profile persistence settings
"""

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .base_settings import VectorDBType


class SecuritySettings(BaseSettings):
    """Security and data configuration settings.

    This class handles:
    - Rate limiting configuration (fixed_window, sliding_window, token_bucket)
    - Vector database settings for semantic search
    - User profile persistence settings
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Rate Limiting settings
    rate_limit_enabled: bool = Field(default=True)
    rate_limit_requests_per_minute: int = Field(default=60)
    rate_limit_strategy: str = Field(default="sliding_window")
    rate_limit_burst_size: int = Field(default=10)

    # Vector Database settings
    vector_db_type: str = Field(default="chroma")
    vector_db_path: str = Field(default="~/.mini_claude/vectors")
    embedding_model: str = Field(default="sentence-transformers/all-MiniLM-L6-v2")
    enable_semantic_search: bool = Field(default=True)

    # User Profile settings
    user_profile_path: str = Field(default="~/.mini_claude/profile.json")
    profile_auto_save: bool = Field(default=True)
    profile_save_interval: int = Field(default=300)

    @field_validator("rate_limit_strategy")
    @classmethod
    def validate_rate_limit_strategy(cls, v: str) -> str:
        """Validate rate_limit_strategy is a supported type."""
        valid_strategies = ["fixed_window", "sliding_window", "token_bucket"]
        if v.lower() not in valid_strategies:
            raise ValueError(f"rate_limit_strategy must be one of {valid_strategies}, got '{v}'")
        return v.lower()

    @field_validator("rate_limit_requests_per_minute")
    @classmethod
    def validate_rate_limit_rpm(cls, v: int) -> int:
        """Validate requests per minute is positive."""
        if v < 1:
            raise ValueError(f"rate_limit_requests_per_minute must be positive, got {v}")
        return v

    @field_validator("rate_limit_burst_size")
    @classmethod
    def validate_rate_limit_burst(cls, v: int) -> int:
        """Validate burst size is positive."""
        if v < 1:
            raise ValueError(f"rate_limit_burst_size must be positive, got {v}")
        return v

    @field_validator("vector_db_type")
    @classmethod
    def validate_vector_db_type(cls, v: str) -> str:
        """Validate vector_db_type is a supported type."""
        valid_types = [e.value for e in VectorDBType]
        if v.lower() not in valid_types:
            raise ValueError(f"vector_db_type must be one of {valid_types}, got '{v}'")
        return v.lower()

    @field_validator("vector_db_path", "user_profile_path")
    @classmethod
    def expand_path(cls, v: str) -> str:
        """Expand ~ to user home directory."""
        return str(Path(v).expanduser())

    @field_validator("profile_save_interval")
    @classmethod
    def validate_save_interval(cls, v: int) -> int:
        """Validate save interval is positive."""
        if v < 0:
            raise ValueError(f"profile_save_interval must be non-negative, got {v}")
        return v


__all__ = ["SecuritySettings"]
