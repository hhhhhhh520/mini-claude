"""Tests for multi-environment configuration."""

import pytest
import os
from pathlib import Path
from unittest.mock import patch, mock_open
import tempfile

from mini_claude.config.settings import Settings, Environment
from mini_claude.config.environment import (
    EnvironmentConfigManager,
    EnvironmentInfo,
    EnvironmentDiff,
    env_config_manager,
)


class TestEnvironmentEnum:
    """Tests for Environment enum."""

    def test_enum_values(self):
        """Test Environment enum has correct values."""
        assert Environment.DEV.value == "dev"
        assert Environment.STAGING.value == "staging"
        assert Environment.PROD.value == "prod"

    def test_enum_count(self):
        """Test Environment has exactly 3 values."""
        assert len(Environment) == 3


class TestSettingsEnvironment:
    """Tests for environment configuration in Settings."""

    def test_default_environment(self):
        """Test default environment is dev."""
        settings = Settings()
        assert settings.environment == "dev"

    def test_custom_environment_dev(self):
        """Test setting environment to dev."""
        settings = Settings(environment="dev")
        assert settings.environment == "dev"

    def test_custom_environment_staging(self):
        """Test setting environment to staging."""
        settings = Settings(environment="staging")
        assert settings.environment == "staging"

    def test_custom_environment_prod(self):
        """Test setting environment to prod with valid security settings."""
        settings = Settings(
            environment="prod",
            audit_enabled=True,
            log_to_json=True,
            rate_limit_enabled=True,
            health_check_enabled=True,
            log_level="WARNING",
        )
        assert settings.environment == "prod"

    def test_environment_case_insensitive(self):
        """Test environment validation is case insensitive."""
        settings = Settings(environment="DEV")
        assert settings.environment == "dev"

        settings2 = Settings(environment="Staging")
        assert settings2.environment == "staging"

    def test_invalid_environment_raises_error(self):
        """Test invalid environment raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            Settings(environment="invalid")
        assert "environment must be one of" in str(exc_info.value)


class TestProductionSecurityValidation:
    """Tests for production environment security validation."""

    def test_prod_requires_audit_enabled(self):
        """Test production requires audit_enabled=True."""
        with pytest.raises(ValueError) as exc_info:
            Settings(
                environment="prod",
                audit_enabled=False,
                log_to_json=True,
                rate_limit_enabled=True,
                health_check_enabled=True,
            )
        assert "audit_enabled must be True" in str(exc_info.value)

    def test_prod_requires_log_to_json(self):
        """Test production requires log_to_json=True."""
        with pytest.raises(ValueError) as exc_info:
            Settings(
                environment="prod",
                audit_enabled=True,
                log_to_json=False,
                rate_limit_enabled=True,
                health_check_enabled=True,
            )
        assert "log_to_json must be True" in str(exc_info.value)

    def test_prod_requires_rate_limit_enabled(self):
        """Test production requires rate_limit_enabled=True."""
        with pytest.raises(ValueError) as exc_info:
            Settings(
                environment="prod",
                audit_enabled=True,
                log_to_json=True,
                rate_limit_enabled=False,
                health_check_enabled=True,
            )
        assert "rate_limit_enabled must be True" in str(exc_info.value)

    def test_prod_requires_health_check_enabled(self):
        """Test production requires health_check_enabled=True."""
        with pytest.raises(ValueError) as exc_info:
            Settings(
                environment="prod",
                audit_enabled=True,
                log_to_json=True,
                rate_limit_enabled=True,
                health_check_enabled=False,
            )
        assert "health_check_enabled must be True" in str(exc_info.value)

    def test_prod_disallows_debug_log_level(self):
        """Test production disallows DEBUG log level."""
        with pytest.raises(ValueError) as exc_info:
            Settings(
                environment="prod",
                audit_enabled=True,
                log_to_json=True,
                rate_limit_enabled=True,
                health_check_enabled=True,
                log_level="DEBUG",
            )
        assert "log_level must not be DEBUG" in str(exc_info.value)

    def test_prod_valid_with_all_security_settings(self):
        """Test production is valid with all required security settings."""
        settings = Settings(
            environment="prod",
            audit_enabled=True,
            log_to_json=True,
            rate_limit_enabled=True,
            health_check_enabled=True,
            log_level="WARNING",
        )
        assert settings.environment == "prod"
        assert settings.audit_enabled is True
        assert settings.log_to_json is True

    def test_dev_allows_relaxed_security(self):
        """Test dev environment allows relaxed security settings."""
        settings = Settings(
            environment="dev",
            audit_enabled=False,
            log_to_json=False,
            rate_limit_enabled=False,
            health_check_enabled=False,
            log_level="DEBUG",
        )
        assert settings.environment == "dev"
        assert settings.audit_enabled is False
        assert settings.log_to_json is False


class TestEnvironmentConfigManager:
    """Tests for EnvironmentConfigManager."""

    @pytest.fixture
    def temp_config_dir(self, tmp_path):
        """Create a temporary config directory with .env files."""
        # Create base .env
        (tmp_path / ".env").write_text("""
DEFAULT_MODEL=deepseek-chat
MAX_SUB_AGENTS=3
LOG_LEVEL=INFO
""")
        # Create .env.dev
        (tmp_path / ".env.dev").write_text("""
MINI_CLAUDE_ENV=dev
LOG_LEVEL=DEBUG
""")
        # Create .env.staging
        (tmp_path / ".env.staging").write_text("""
MINI_CLAUDE_ENV=staging
LOG_LEVEL=WARNING
""")
        return tmp_path

    def test_default_environment_is_dev(self, temp_config_dir):
        """Test default environment is dev."""
        manager = EnvironmentConfigManager(config_dir=temp_config_dir)
        assert manager.get_current_environment() == "dev"

    def test_get_env_file_path(self, temp_config_dir):
        """Test getting env file path."""
        manager = EnvironmentConfigManager(config_dir=temp_config_dir)
        path = manager.get_env_file_path("staging")
        assert path == temp_config_dir / ".env.staging"

    def test_load_env_file_exists(self, temp_config_dir):
        """Test loading an existing env file."""
        manager = EnvironmentConfigManager(config_dir=temp_config_dir)
        config = manager.load_env_file(temp_config_dir / ".env.dev")
        assert config["MINI_CLAUDE_ENV"] == "dev"
        assert config["LOG_LEVEL"] == "DEBUG"

    def test_load_env_file_not_exists(self, temp_config_dir):
        """Test loading a non-existent env file returns empty dict."""
        manager = EnvironmentConfigManager(config_dir=temp_config_dir)
        config = manager.load_env_file(temp_config_dir / ".env.prod")
        assert config == {}

    def test_load_environment_config_merges(self, temp_config_dir):
        """Test that environment config merges with base config."""
        manager = EnvironmentConfigManager(config_dir=temp_config_dir)
        config = manager.load_environment_config("dev")

        # Base config value
        assert config["DEFAULT_MODEL"] == "deepseek-chat"
        # Overridden by dev config
        assert config["LOG_LEVEL"] == "DEBUG"

    def test_set_environment(self, temp_config_dir):
        """Test setting the environment."""
        manager = EnvironmentConfigManager(config_dir=temp_config_dir)
        manager.set_environment("staging")
        assert manager.get_current_environment() == "staging"

    def test_set_invalid_environment_raises_error(self, temp_config_dir):
        """Test setting invalid environment raises error."""
        manager = EnvironmentConfigManager(config_dir=temp_config_dir)
        with pytest.raises(ValueError):
            manager.set_environment("invalid")

    def test_get_environment_diff(self, temp_config_dir):
        """Test getting environment diff."""
        manager = EnvironmentConfigManager(config_dir=temp_config_dir)
        diffs = manager.get_environment_diff("dev")

        # Should have diff for LOG_LEVEL
        log_level_diff = next((d for d in diffs if d.key == "LOG_LEVEL"), None)
        assert log_level_diff is not None
        assert log_level_diff.base_value == "INFO"
        assert log_level_diff.env_value == "DEBUG"

    def test_list_environments(self, temp_config_dir):
        """Test listing all environments."""
        manager = EnvironmentConfigManager(config_dir=temp_config_dir)
        envs = manager.list_environments()

        assert len(envs) == 3
        env_names = [e.name for e in envs]
        assert "dev" in env_names
        assert "staging" in env_names
        assert "prod" in env_names

        # Check dev exists
        dev_env = next(e for e in envs if e.name == "dev")
        assert dev_env.exists is True

        # Check prod doesn't exist
        prod_env = next(e for e in envs if e.name == "prod")
        assert prod_env.exists is False

    def test_switch_environment_success(self, temp_config_dir):
        """Test successful environment switch."""
        manager = EnvironmentConfigManager(config_dir=temp_config_dir)
        success, message = manager.switch_environment("staging")

        assert success is True
        assert "Switched" in message
        assert manager.get_current_environment() == "staging"

    def test_switch_environment_invalid(self, temp_config_dir):
        """Test switch to invalid environment fails."""
        manager = EnvironmentConfigManager(config_dir=temp_config_dir)
        success, message = manager.switch_environment("invalid")

        assert success is False
        assert "Invalid environment" in message

    def test_switch_environment_missing_file(self, temp_config_dir):
        """Test switch to environment without config file fails."""
        manager = EnvironmentConfigManager(config_dir=temp_config_dir)
        success, message = manager.switch_environment("prod")

        assert success is False
        assert "not found" in message

    def test_create_env_file_template(self, tmp_path):
        """Test creating env file template."""
        manager = EnvironmentConfigManager(config_dir=tmp_path)
        path = manager.create_env_file_template("prod")

        assert path.exists()
        content = path.read_text()
        assert "MINI_CLAUDE_ENV=prod" in content
        assert "AUDIT_ENABLED=true" in content

    def test_create_env_file_template_no_overwrite(self, tmp_path):
        """Test creating env file template without overwrite fails if exists."""
        manager = EnvironmentConfigManager(config_dir=tmp_path)
        manager.create_env_file_template("dev")

        with pytest.raises(FileExistsError):
            manager.create_env_file_template("dev", overwrite=False)

    def test_create_env_file_template_with_overwrite(self, tmp_path):
        """Test creating env file template with overwrite."""
        manager = EnvironmentConfigManager(config_dir=tmp_path)
        manager.create_env_file_template("dev")
        # Should not raise
        manager.create_env_file_template("dev", overwrite=True)


class TestEnvironmentValidation:
    """Tests for environment configuration validation."""

    @pytest.fixture
    def temp_config_dir(self, tmp_path):
        """Create a temporary config directory."""
        (tmp_path / ".env").write_text("""
DEFAULT_MODEL=deepseek-chat
""")
        return tmp_path

    def test_validate_dev_environment(self, temp_config_dir):
        """Test validating dev environment."""
        manager = EnvironmentConfigManager(config_dir=temp_config_dir)
        is_valid, errors = manager.validate_environment_config("dev")

        # Dev should be valid even with minimal config
        assert is_valid is True
        assert len(errors) == 0

    def test_validate_prod_environment_missing_api_key(self, temp_config_dir):
        """Test validating prod environment without API key."""
        (temp_config_dir / ".env.prod").write_text("""
MINI_CLAUDE_ENV=prod
AUDIT_ENABLED=true
RATE_LIMIT_ENABLED=true
HEALTH_CHECK_ENABLED=true
LOG_TO_JSON=true
DEFAULT_MODEL=deepseek-chat
""")
        manager = EnvironmentConfigManager(config_dir=temp_config_dir)
        is_valid, errors = manager.validate_environment_config("prod")

        assert is_valid is False
        assert any("API_KEY" in e for e in errors)

    def test_validate_prod_environment_valid(self, temp_config_dir):
        """Test validating prod environment with all requirements."""
        (temp_config_dir / ".env.prod").write_text("""
MINI_CLAUDE_ENV=prod
OPENAI_API_KEY=test-key
DEFAULT_MODEL=deepseek-chat
AUDIT_ENABLED=true
RATE_LIMIT_ENABLED=true
HEALTH_CHECK_ENABLED=true
LOG_TO_JSON=true
""")
        manager = EnvironmentConfigManager(config_dir=temp_config_dir)
        is_valid, errors = manager.validate_environment_config("prod")

        assert is_valid is True
        assert len(errors) == 0


class TestEnvironmentVariableOverride:
    """Tests for MINI_CLAUDE_ENV environment variable."""

    def test_env_var_overrides_default(self, tmp_path):
        """Test MINI_CLAUDE_ENV overrides default environment."""
        with patch.dict(os.environ, {"MINI_CLAUDE_ENV": "staging"}):
            manager = EnvironmentConfigManager(config_dir=tmp_path)
            assert manager.get_current_environment() == "staging"

    def test_env_var_case_insensitive(self, tmp_path):
        """Test MINI_CLAUDE_ENV is case insensitive."""
        with patch.dict(os.environ, {"MINI_CLAUDE_ENV": "STAGING"}):
            manager = EnvironmentConfigManager(config_dir=tmp_path)
            assert manager.get_current_environment() == "staging"

    def test_env_var_invalid_falls_back(self, tmp_path):
        """Test invalid MINI_CLAUDE_ENV falls back to default."""
        with patch.dict(os.environ, {"MINI_CLAUDE_ENV": "invalid"}):
            manager = EnvironmentConfigManager(config_dir=tmp_path)
            # Should fall back to dev
            assert manager.get_current_environment() == "dev"


class TestConfigSummary:
    """Tests for configuration summary."""

    @pytest.fixture
    def temp_config_dir(self, tmp_path):
        """Create a temporary config directory."""
        (tmp_path / ".env").write_text("DEFAULT_MODEL=deepseek-chat\n")
        (tmp_path / ".env.dev").write_text("MINI_CLAUDE_ENV=dev\n")
        return tmp_path

    def test_get_config_summary(self, temp_config_dir):
        """Test getting config summary."""
        # Clear any lingering environment variable from previous tests
        with patch.dict(os.environ, {}, clear=True):
            manager = EnvironmentConfigManager(config_dir=temp_config_dir)
            summary = manager.get_config_summary()

            assert summary["current_environment"] == "dev"
            assert summary["config_directory"] == str(temp_config_dir)
            assert summary["base_config_exists"] is True
            assert len(summary["environments"]) == 3


class TestEnvironmentInfo:
    """Tests for EnvironmentInfo dataclass."""

    def test_environment_info_creation(self, tmp_path):
        """Test creating EnvironmentInfo."""
        info = EnvironmentInfo(
            name="dev",
            config_file=tmp_path / ".env.dev",
            exists=True,
            config_count=5,
            missing_required=[],
        )

        assert info.name == "dev"
        assert info.exists is True
        assert info.config_count == 5
        assert info.missing_required == []


class TestEnvironmentDiff:
    """Tests for EnvironmentDiff dataclass."""

    def test_environment_diff_creation(self):
        """Test creating EnvironmentDiff."""
        diff = EnvironmentDiff(
            key="LOG_LEVEL",
            base_value="INFO",
            env_value="DEBUG",
        )

        assert diff.key == "LOG_LEVEL"
        assert diff.base_value == "INFO"
        assert diff.env_value == "DEBUG"


class TestBackwardCompatibility:
    """Tests for backward compatibility."""

    def test_settings_still_work_without_environment(self):
        """Test Settings works without environment-specific config."""
        settings = Settings()
        # Should have all expected fields
        assert hasattr(settings, "default_model")
        assert hasattr(settings, "log_level")
        assert hasattr(settings, "environment")

    def test_settings_environment_defaults_to_dev(self):
        """Test Settings environment defaults to dev."""
        settings = Settings()
        assert settings.environment == "dev"

    def test_dev_environment_allows_all_log_levels(self):
        """Test dev environment allows all log levels."""
        for log_level in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
            settings = Settings(environment="dev", log_level=log_level)
            assert settings.log_level == log_level
