"""Multi-environment configuration management.

Supports dev/staging/prod environment configuration separation.
Environment is controlled by MINI_CLAUDE_ENV environment variable.
"""

import os
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field

from dotenv import dotenv_values


@dataclass
class EnvironmentDiff:
    """Represents a difference between two environment configurations."""
    key: str
    base_value: Any
    env_value: Any


@dataclass
class EnvironmentInfo:
    """Information about an environment configuration."""
    name: str
    config_file: Path
    exists: bool
    config_count: int = 0
    missing_required: List[str] = field(default_factory=list)


class EnvironmentConfigManager:
    """Manages multi-environment configuration loading and switching.

    Environment Configuration Hierarchy:
    1. Base config: .env (shared across all environments)
    2. Environment config: .env.{env} (overrides base config)
    3. Environment variable: MINI_CLAUDE_ENV (selects current environment)

    Usage:
        manager = EnvironmentConfigManager()
        manager.load_environment("staging")
        settings = manager.get_settings()
    """

    ENVIRONMENTS = ["dev", "staging", "prod"]
    ENV_VAR_NAME = "MINI_CLAUDE_ENV"

    def __init__(self, config_dir: Optional[Path] = None):
        """Initialize the environment config manager.

        Args:
            config_dir: Directory containing .env files. Defaults to current directory.
        """
        self.config_dir = config_dir or Path.cwd()
        self._current_environment: Optional[str] = None
        self._loaded_configs: Dict[str, Dict[str, str]] = {}

    def get_current_environment(self) -> str:
        """Get the current environment name.

        Priority:
        1. MINI_CLAUDE_ENV environment variable
        2. Previously set environment
        3. Default to 'dev'

        Returns:
            Current environment name (dev/staging/prod)
        """
        # Check environment variable first
        env_var = os.environ.get(self.ENV_VAR_NAME)
        if env_var and env_var.lower() in self.ENVIRONMENTS:
            return env_var.lower()

        # Check previously set environment
        if self._current_environment:
            return self._current_environment

        # Default to dev
        return "dev"

    def set_environment(self, env: str) -> None:
        """Set the current environment.

        Args:
            env: Environment name (dev/staging/prod)

        Raises:
            ValueError: If environment name is invalid
        """
        if env.lower() not in self.ENVIRONMENTS:
            raise ValueError(f"Invalid environment '{env}'. Must be one of {self.ENVIRONMENTS}")
        self._current_environment = env.lower()
        os.environ[self.ENV_VAR_NAME] = env.lower()

    def get_env_file_path(self, env: Optional[str] = None) -> Path:
        """Get the path to an environment's config file.

        Args:
            env: Environment name. Defaults to current environment.

        Returns:
            Path to .env.{env} file
        """
        env_name = env or self.get_current_environment()
        return self.config_dir / f".env.{env_name}"

    def get_base_env_file_path(self) -> Path:
        """Get the path to the base config file.

        Returns:
            Path to .env file
        """
        return self.config_dir / ".env"

    def load_env_file(self, file_path: Path) -> Dict[str, str]:
        """Load a .env file and return its contents.

        Args:
            file_path: Path to the .env file

        Returns:
            Dictionary of config key-value pairs
        """
        if not file_path.exists():
            return {}

        # Use dotenv_values to parse the file
        values = dict(dotenv_values(file_path))
        return values

    def load_environment_config(self, env: Optional[str] = None) -> Dict[str, str]:
        """Load configuration for a specific environment.

        Loads base .env first, then overlays .env.{env}.

        Args:
            env: Environment name. Defaults to current environment.

        Returns:
            Merged configuration dictionary
        """
        env_name = env or self.get_current_environment()

        # Check cache
        if env_name in self._loaded_configs:
            return self._loaded_configs[env_name]

        # Load base config first
        base_config = self.load_env_file(self.get_base_env_file_path())

        # Load environment-specific config
        env_config = self.load_env_file(self.get_env_file_path(env_name))

        # Merge: env config overrides base config
        merged = {**base_config, **env_config}

        # Cache the result
        self._loaded_configs[env_name] = merged

        return merged

    def get_environment_diff(self, env: str) -> List[EnvironmentDiff]:
        """Get the differences between base config and environment config.

        Args:
            env: Environment name to compare

        Returns:
            List of configuration differences
        """
        base_config = self.load_env_file(self.get_base_env_file_path())
        env_config = self.load_env_file(self.get_env_file_path(env))

        diffs = []

        # Find keys that exist in env config with different values
        for key, env_value in env_config.items():
            base_value = base_config.get(key)
            if base_value != env_value:
                diffs.append(EnvironmentDiff(
                    key=key,
                    base_value=base_value,
                    env_value=env_value
                ))

        return diffs

    def get_environment_info(self, env: str) -> EnvironmentInfo:
        """Get information about an environment configuration.

        Args:
            env: Environment name

        Returns:
            EnvironmentInfo with details about the configuration
        """
        config_file = self.get_env_file_path(env)
        config = self.load_env_file(config_file)

        return EnvironmentInfo(
            name=env,
            config_file=config_file,
            exists=config_file.exists(),
            config_count=len(config),
            missing_required=self._check_required_fields(config)
        )

    def list_environments(self) -> List[EnvironmentInfo]:
        """List all available environments and their status.

        Returns:
            List of EnvironmentInfo for each environment
        """
        return [self.get_environment_info(env) for env in self.ENVIRONMENTS]

    def _check_required_fields(self, config: Dict[str, str]) -> List[str]:
        """Check if required fields are present in config.

        Args:
            config: Configuration dictionary

        Returns:
            List of missing required field names
        """
        # For prod environment, check critical fields
        required_for_prod = [
            "OPENAI_API_KEY",
            "DEFAULT_MODEL",
        ]

        missing = []
        for field_name in required_for_prod:
            if field_name not in config or not config[field_name]:
                missing.append(field_name)

        return missing

    def create_env_file_template(self, env: str, overwrite: bool = False) -> Path:
        """Create a template .env file for an environment.

        Args:
            env: Environment name
            overwrite: Whether to overwrite existing file

        Returns:
            Path to created file

        Raises:
            FileExistsError: If file exists and overwrite=False
        """
        file_path = self.get_env_file_path(env)

        if file_path.exists() and not overwrite:
            raise FileExistsError(f"Config file already exists: {file_path}")

        # Create template content based on environment
        template = self._get_env_template(env)

        file_path.write_text(template, encoding="utf-8")

        # Clear cache
        if env in self._loaded_configs:
            del self._loaded_configs[env]

        return file_path

    def _get_env_template(self, env: str) -> str:
        """Get template content for an environment config file.

        Args:
            env: Environment name

        Returns:
            Template content string
        """
        templates = {
            "dev": """# Development Environment Configuration
# This file overrides settings from .env for development

# Environment identifier
MINI_CLAUDE_ENV=dev

# Development-friendly settings
LOG_LEVEL=DEBUG
LOG_TO_CONSOLE=true
LOG_TO_JSON=false

# Lower rate limits for development testing
RATE_LIMIT_ENABLED=true
RATE_LIMIT_REQUESTS_PER_MINUTE=120

# Health check for local development
HEALTH_CHECK_ENABLED=true
HEALTH_CHECK_PORT=8080

# Disable tracing in development
TRACING_ENABLED=false
""",
            "staging": """# Staging Environment Configuration
# This file overrides settings from .env for staging

# Environment identifier
MINI_CLAUDE_ENV=staging

# Staging settings
LOG_LEVEL=INFO
LOG_TO_CONSOLE=true
LOG_TO_JSON=true

# Production-like rate limits
RATE_LIMIT_ENABLED=true
RATE_LIMIT_REQUESTS_PER_MINUTE=60

# Health check enabled
HEALTH_CHECK_ENABLED=true

# Enable tracing for debugging
TRACING_ENABLED=true
TRACING_EXPORTER=console
""",
            "prod": """# Production Environment Configuration
# This file overrides settings from .env for production

# Environment identifier
MINI_CLAUDE_ENV=prod

# Production settings - stricter security
LOG_LEVEL=WARNING
LOG_TO_CONSOLE=false
LOG_TO_JSON=true

# Production security requirements (enforced)
AUDIT_ENABLED=true
RATE_LIMIT_ENABLED=true
HEALTH_CHECK_ENABLED=true

# Production rate limits
RATE_LIMIT_REQUESTS_PER_MINUTE=60

# Enable tracing for observability
TRACING_ENABLED=true
TRACING_EXPORTER=otlp

# Alerting configuration
ALERT_ENABLED=true
"""
        }

        return templates.get(env, templates["dev"])

    def switch_environment(self, env: str) -> Tuple[bool, str]:
        """Switch to a different environment.

        Args:
            env: Target environment name

        Returns:
            Tuple of (success, message)
        """
        if env.lower() not in self.ENVIRONMENTS:
            return False, f"Invalid environment '{env}'. Must be one of {self.ENVIRONMENTS}"

        old_env = self.get_current_environment()

        # Check if target environment config exists
        env_file = self.get_env_file_path(env)
        if not env_file.exists():
            return False, f"Environment config file not found: {env_file}"

        # Set the environment
        self.set_environment(env)

        # Clear cached configs to force reload
        self._loaded_configs.clear()

        return True, f"Switched from '{old_env}' to '{env}' environment"

    def validate_environment_config(self, env: str) -> Tuple[bool, List[str]]:
        """Validate configuration for an environment.

        Args:
            env: Environment name

        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []

        if env.lower() not in self.ENVIRONMENTS:
            errors.append(f"Invalid environment '{env}'")
            return False, errors

        config = self.load_environment_config(env)

        # Check required fields based on environment
        if env == "prod":
            # Production must have API key
            if not config.get("OPENAI_API_KEY") and not config.get("ANTHROPIC_API_KEY"):
                errors.append("Production environment requires OPENAI_API_KEY or ANTHROPIC_API_KEY")

            # Production must have security settings
            required_bool_true = [
                "AUDIT_ENABLED",
                "RATE_LIMIT_ENABLED",
                "HEALTH_CHECK_ENABLED",
                "LOG_TO_JSON",
            ]
            for field in required_bool_true:
                value = config.get(field, "false").lower()
                if value != "true":
                    errors.append(f"Production environment requires {field}=true")

        # Check model configuration
        if not config.get("DEFAULT_MODEL"):
            errors.append("DEFAULT_MODEL must be set")

        return len(errors) == 0, errors

    def get_config_summary(self) -> Dict[str, Any]:
        """Get a summary of the current configuration state.

        Returns:
            Dictionary with environment status and config counts
        """
        current_env = self.get_current_environment()
        environments = self.list_environments()

        return {
            "current_environment": current_env,
            "config_directory": str(self.config_dir),
            "environments": [
                {
                    "name": env.name,
                    "exists": env.exists,
                    "config_count": env.config_count,
                    "missing_required": env.missing_required,
                }
                for env in environments
            ],
            "base_config_exists": self.get_base_env_file_path().exists(),
        }


# Global instance
env_config_manager = EnvironmentConfigManager()
