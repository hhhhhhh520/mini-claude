"""Tests for configuration validation enhancements."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import os
import tempfile

from mini_claude.config.settings import Settings
from mini_claude.config.validation import (
    ValidationResult,
    ConfigValidator,
    validate_configuration,
)


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_empty_result_is_valid(self):
        """Test empty ValidationResult is valid."""
        result = ValidationResult()
        assert result.is_valid is True
        assert result.has_warnings is False
        assert len(result.warnings) == 0
        assert len(result.errors) == 0

    def test_result_with_warnings_only(self):
        """Test result with only warnings is valid."""
        result = ValidationResult()
        result.add_warning("test warning")
        assert result.is_valid is True
        assert result.has_warnings is True
        assert len(result.warnings) == 1
        assert len(result.errors) == 0

    def test_result_with_errors(self):
        """Test result with errors is not valid."""
        result = ValidationResult()
        result.add_error("test error")
        assert result.is_valid is False
        assert result.has_warnings is False
        assert len(result.warnings) == 0
        assert len(result.errors) == 1

    def test_result_with_both_warnings_and_errors(self):
        """Test result with both warnings and errors."""
        result = ValidationResult()
        result.add_warning("warning 1")
        result.add_warning("warning 2")
        result.add_error("error 1")
        assert result.is_valid is False
        assert result.has_warnings is True
        assert len(result.warnings) == 2
        assert len(result.errors) == 1

    def test_merge_results(self):
        """Test merging two ValidationResult objects."""
        result1 = ValidationResult()
        result1.add_warning("warning 1")
        result1.add_error("error 1")

        result2 = ValidationResult()
        result2.add_warning("warning 2")
        result2.add_error("error 2")

        result1.merge(result2)
        assert len(result1.warnings) == 2
        assert len(result1.errors) == 2
        assert "warning 1" in result1.warnings
        assert "warning 2" in result1.warnings
        assert "error 1" in result1.errors
        assert "error 2" in result1.errors

    def test_string_representation_empty(self):
        """Test string representation of empty result."""
        result = ValidationResult()
        assert str(result) == "No validation issues"

    def test_string_representation_with_warnings(self):
        """Test string representation with warnings."""
        result = ValidationResult()
        result.add_warning("test warning")
        expected = "Warnings:\n  - test warning"
        assert str(result) == expected

    def test_string_representation_with_errors(self):
        """Test string representation with errors."""
        result = ValidationResult()
        result.add_error("test error")
        expected = "Errors:\n  - test error"
        assert str(result) == expected

    def test_string_representation_with_both(self):
        """Test string representation with both warnings and errors."""
        result = ValidationResult()
        result.add_warning("warning")
        result.add_error("error")
        lines = str(result).split("\n")
        assert "Warnings:" in lines[0]
        assert "- warning" in lines[1]
        assert "Errors:" in lines[2]
        assert "- error" in lines[3]


class TestAPIKeyValidation:
    """Tests for API key format validation."""

    def test_valid_openai_key_format(self):
        """Test valid OpenAI API key format."""
        settings = Settings(openai_api_key="sk-validkey1234567890123")
        validator = ConfigValidator(settings)
        validator.validate_api_keys()
        # No warning for valid key format
        assert len(validator.result.warnings) == 0

    def test_openai_key_wrong_prefix(self):
        """Test OpenAI API key with wrong prefix."""
        settings = Settings(openai_api_key="invalid-key-format")
        validator = ConfigValidator(settings)
        validator.validate_api_keys()
        assert len(validator.result.warnings) == 1
        assert "openai_api_key should start with 'sk-'" in validator.result.warnings[0]

    def test_openai_key_too_short(self):
        """Test OpenAI API key that is too short."""
        settings = Settings(openai_api_key="sk-short")
        validator = ConfigValidator(settings)
        validator.validate_api_keys()
        assert len(validator.result.warnings) == 1
        assert "openai_api_key should be at least 20 characters" in validator.result.warnings[0]

    def test_valid_anthropic_key_format(self):
        """Test valid Anthropic API key format."""
        settings = Settings(anthropic_api_key="sk-ant-validkey1234567890123")
        validator = ConfigValidator(settings)
        validator.validate_api_keys()
        assert len(validator.result.warnings) == 0

    def test_anthropic_key_wrong_prefix(self):
        """Test Anthropic API key with wrong prefix."""
        settings = Settings(anthropic_api_key="sk-invalid-anthropic-key")
        validator = ConfigValidator(settings)
        validator.validate_api_keys()
        assert len(validator.result.warnings) == 1
        assert "anthropic_api_key should start with 'sk-ant-'" in validator.result.warnings[0]

    def test_empty_api_keys_no_warning(self):
        """Test empty API keys produce no warnings."""
        settings = Settings()
        validator = ConfigValidator(settings)
        validator.validate_api_keys()
        assert len(validator.result.warnings) == 0

    def test_google_key_too_short(self):
        """Test Google API key that is too short."""
        settings = Settings(google_api_key="shortkey")
        validator = ConfigValidator(settings)
        validator.validate_api_keys()
        assert len(validator.result.warnings) == 1
        assert "google_api_key seems too short" in validator.result.warnings[0]

    def test_valid_google_key(self):
        """Test valid Google API key."""
        settings = Settings(google_api_key="valid-long-google-api-key-12345")
        validator = ConfigValidator(settings)
        validator.validate_api_keys()
        assert len(validator.result.warnings) == 0


class TestPathValidation:
    """Tests for path existence validation."""

    def test_existing_workspace_no_warning(self):
        """Test existing workspace produces no warning."""
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(workspace_root=tmpdir)
            validator = ConfigValidator(settings)
            validator.validate_paths()
            # Should not have warning for existing workspace
            workspace_warnings = [
                w for w in validator.result.warnings
                if "workspace_root" in w and "does not exist" in w
            ]
            assert len(workspace_warnings) == 0

    def test_non_existing_workspace_warning(self):
        """Test non-existing workspace produces warning."""
        settings = Settings(workspace_root="/non/existing/path/to/workspace")
        validator = ConfigValidator(settings)
        validator.validate_paths()
        assert any("workspace_root" in w for w in validator.result.warnings)

    def test_valid_log_path_parent_exists(self):
        """Test log path with existing parent directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = str(Path(tmpdir) / "test.log")
            settings = Settings(log_file_path=log_path)
            validator = ConfigValidator(settings)
            validator.validate_paths()
            log_warnings = [
                w for w in validator.result.warnings
                if "log_file_path" in w
            ]
            assert len(log_warnings) == 0

    def test_log_path_parent_not_exists_warning(self):
        """Test log path with non-existing parent directory."""
        settings = Settings(log_file_path="/non/existing/dir/test.log")
        validator = ConfigValidator(settings)
        validator.validate_paths()
        assert any("log_file_path parent directory does not exist" in w for w in validator.result.warnings)

    def test_valid_session_db_path(self):
        """Test valid session db path."""
        settings = Settings(session_db_path="sessions.db")
        validator = ConfigValidator(settings)
        validator.validate_paths()
        session_errors = [
            e for e in validator.result.errors
            if "session_db_path" in e
        ]
        assert len(session_errors) == 0

    def test_non_existing_vector_db_path_warning(self):
        """Test non-existing vector db path produces warning."""
        settings = Settings(vector_db_path="/non/existing/vector/path")
        validator = ConfigValidator(settings)
        validator.validate_paths()
        assert any("vector_db_path does not exist" in w for w in validator.result.warnings)


class TestNumericRangeValidation:
    """Tests for numeric range validation."""

    def test_valid_max_iterations(self):
        """Test valid max_iterations value."""
        settings = Settings(max_iterations=50)
        validator = ConfigValidator(settings)
        validator.validate_numeric_ranges()
        iter_errors = [e for e in validator.result.errors if "max_iterations" in e]
        assert len(iter_errors) == 0

    def test_max_iterations_out_of_range_low(self):
        """Test max_iterations below minimum."""
        # Note: Pydantic validator will raise ValueError before ConfigValidator
        # But ConfigValidator should still catch it if it somehow passes
        settings = Settings()  # Use default, then manually check range
        settings.max_iterations = 0  # Bypass Pydantic validation for test
        validator = ConfigValidator(settings)
        validator.validate_numeric_ranges()
        assert any("max_iterations must be between" in e for e in validator.result.errors)

    def test_max_iterations_out_of_range_high(self):
        """Test max_iterations above maximum."""
        settings = Settings()
        settings.max_iterations = 150  # Bypass Pydantic validation
        validator = ConfigValidator(settings)
        validator.validate_numeric_ranges()
        assert any("max_iterations must be between" in e for e in validator.result.errors)

    def test_valid_max_sub_agents(self):
        """Test valid max_sub_agents value."""
        settings = Settings(max_sub_agents=5)
        validator = ConfigValidator(settings)
        validator.validate_numeric_ranges()
        subagent_errors = [e for e in validator.result.errors if "max_sub_agents" in e]
        assert len(subagent_errors) == 0

    def test_max_sub_agents_out_of_range(self):
        """Test max_sub_agents out of range."""
        settings = Settings()
        settings.max_sub_agents = 20  # Bypass Pydantic validation
        validator = ConfigValidator(settings)
        validator.validate_numeric_ranges()
        assert any("max_sub_agents must be between" in e for e in validator.result.errors)

    def test_valid_token_budget_ratio(self):
        """Test valid token_budget_ratio value."""
        settings = Settings(token_budget_ratio=0.8)
        validator = ConfigValidator(settings)
        validator.validate_numeric_ranges()
        ratio_errors = [e for e in validator.result.errors if "token_budget_ratio" in e]
        assert len(ratio_errors) == 0

    def test_token_budget_ratio_out_of_range(self):
        """Test token_budget_ratio out of range."""
        settings = Settings()
        settings.token_budget_ratio = 0.05  # Bypass Pydantic validation
        validator = ConfigValidator(settings)
        validator.validate_numeric_ranges()
        assert any("token_budget_ratio must be between" in e for e in validator.result.errors)

    def test_token_warn_ratio_greater_than_budget_warning(self):
        """Test token_warn_ratio >= token_budget_ratio produces warning."""
        settings = Settings()
        settings.token_warn_ratio = 0.9
        settings.token_budget_ratio = 0.8  # warn > budget
        validator = ConfigValidator(settings)
        validator.validate_numeric_ranges()
        assert any("token_warn_ratio" in w and "should be less than" in w for w in validator.result.warnings)

    def test_valid_health_check_port(self):
        """Test valid health_check_port value."""
        settings = Settings(health_check_port=8080)
        validator = ConfigValidator(settings)
        validator.validate_numeric_ranges()
        port_errors = [e for e in validator.result.errors if "health_check_port" in e]
        assert len(port_errors) == 0

    def test_health_check_port_out_of_range(self):
        """Test health_check_port out of range."""
        settings = Settings()
        settings.health_check_port = 70000  # Bypass Pydantic validation
        validator = ConfigValidator(settings)
        validator.validate_numeric_ranges()
        assert any("health_check_port must be between" in e for e in validator.result.errors)

    def test_valid_alert_thresholds(self):
        """Test valid alert threshold values."""
        settings = Settings(
            alert_failure_rate_threshold=0.2,
            alert_token_budget_threshold=0.8
        )
        validator = ConfigValidator(settings)
        validator.validate_numeric_ranges()
        threshold_errors = [e for e in validator.result.errors if "threshold" in e]
        assert len(threshold_errors) == 0

    def test_alert_threshold_out_of_range(self):
        """Test alert threshold out of range."""
        settings = Settings()
        settings.alert_failure_rate_threshold = 1.5  # Bypass Pydantic validation
        validator = ConfigValidator(settings)
        validator.validate_numeric_ranges()
        assert any("alert_failure_rate_threshold must be between" in e for e in validator.result.errors)


class TestCrossFieldValidation:
    """Tests for cross-field validation."""

    def test_dev_environment_no_api_key_required(self):
        """Test dev environment does not require API key."""
        settings = Settings(environment="dev")
        validator = ConfigValidator(settings)
        validator.validate_cross_fields()
        api_key_errors = [e for e in validator.result.errors if "API key" in e]
        assert len(api_key_errors) == 0

    def test_prod_environment_requires_api_key(self):
        """Test production environment requires at least one API key."""
        # Production environment has strict requirements enforced by Pydantic model_validator
        # We test the ConfigValidator's cross-field validation separately
        settings = Settings()  # Create with defaults
        settings.environment = "prod"  # Manually set for ConfigValidator test
        settings.alert_enabled = False  # Disable alerts to focus on API key check
        # Clear any existing API keys to test the validation
        settings.openai_api_key = None
        settings.anthropic_api_key = None
        settings.google_api_key = None
        # Note: API key validation happens in ConfigValidator, not Pydantic
        validator = ConfigValidator(settings)
        validator.validate_cross_fields()
        assert any("Production environment requires at least one API key" in e for e in validator.result.errors)

    def test_prod_environment_with_api_key(self):
        """Test production environment with API key configured."""
        # For Pydantic model creation, we need log_to_json=True for prod
        settings = Settings(
            environment="prod",
            openai_api_key="sk-validkey1234567890123",
            log_to_json=True  # Required for prod environment
        )
        validator = ConfigValidator(settings)
        validator.validate_cross_fields()
        api_key_errors = [e for e in validator.result.errors if "API key" in e]
        assert len(api_key_errors) == 0

    def test_prod_environment_requires_webhook(self):
        """Test production environment requires webhook when alert enabled."""
        settings = Settings()
        settings.environment = "prod"
        settings.alert_enabled = True
        settings.openai_api_key = "sk-validkey1234567890123"
        validator = ConfigValidator(settings)
        validator.validate_cross_fields()
        assert any("alert_webhook_url" in e for e in validator.result.errors)

    def test_prod_environment_with_webhook(self):
        """Test production environment with webhook configured."""
        settings = Settings(
            environment="prod",
            alert_enabled=True,
            alert_webhook_url="https://hooks.example.com/webhook",
            openai_api_key="sk-validkey1234567890123",
            log_to_json=True
        )
        validator = ConfigValidator(settings)
        validator.validate_cross_fields()
        webhook_errors = [e for e in validator.result.errors if "webhook" in e]
        assert len(webhook_errors) == 0

    def test_prod_environment_json_logging_warning(self):
        """Test production environment warns about JSON logging."""
        # This is enforced as error in Pydantic model_validator, not warning
        # Test ConfigValidator behavior separately
        settings = Settings()
        settings.environment = "prod"
        settings.log_to_json = False
        settings.openai_api_key = "sk-validkey1234567890123"
        validator = ConfigValidator(settings)
        validator.validate_cross_fields()
        assert any("log_to_json enabled" in w for w in validator.result.warnings)

    def test_tracing_enabled_without_otlp_endpoint(self):
        """Test tracing enabled with OTLP exporter but no endpoint."""
        # This is now enforced by Pydantic model_validator - test that it raises
        with pytest.raises(ValueError) as exc_info:
            Settings(
                tracing_enabled=True,
                tracing_exporter="otlp",
                tracing_otlp_endpoint=""
            )
        assert "tracing_otlp_endpoint must be configured" in str(exc_info.value)

    def test_tracing_enabled_with_valid_otlp(self):
        """Test tracing enabled with valid OTLP configuration."""
        settings = Settings(
            tracing_enabled=True,
            tracing_exporter="otlp",
            tracing_otlp_endpoint="http://localhost:4317"
        )
        validator = ConfigValidator(settings)
        validator.validate_cross_fields()
        otlp_errors = [e for e in validator.result.errors if "otlp" in e]
        assert len(otlp_errors) == 0

    def test_notification_email_without_smtp_warning(self):
        """Test email notification without SMTP settings produces warning."""
        settings = Settings(
            notification_enabled=True,
            notification_channels=["email"],
            smtp_host=None
        )
        validator = ConfigValidator(settings)
        validator.validate_cross_fields()
        assert any("SMTP settings are incomplete" in w for w in validator.result.warnings)

    def test_notification_email_with_smtp(self):
        """Test email notification with complete SMTP settings."""
        settings = Settings(
            notification_enabled=True,
            notification_channels=["email"],
            smtp_host="smtp.example.com",
            smtp_user="user@example.com",
            smtp_password="password123"
        )
        validator = ConfigValidator(settings)
        validator.validate_cross_fields()
        smtp_warnings = [w for w in validator.result.warnings if "SMTP" in w]
        assert len(smtp_warnings) == 0

    def test_token_bucket_burst_size_warning(self):
        """Test token bucket burst size exceeding requests per minute."""
        settings = Settings(
            rate_limit_strategy="token_bucket",
            rate_limit_burst_size=100,
            rate_limit_requests_per_minute=60
        )
        validator = ConfigValidator(settings)
        validator.validate_cross_fields()
        assert any("rate_limit_burst_size" in w for w in validator.result.warnings)


class TestValidateConfiguration:
    """Tests for the validate_configuration function."""

    def test_validate_configuration_returns_result(self):
        """Test validate_configuration returns ValidationResult."""
        settings = Settings()
        result = validate_configuration(settings)
        assert isinstance(result, ValidationResult)

    def test_validate_configuration_dev_environment(self):
        """Test validation for dev environment."""
        settings = Settings(environment="dev")
        result = validate_configuration(settings)
        # Dev environment should have no blocking errors
        assert result.is_valid is True

    def test_validate_configuration_runs_all_checks(self):
        """Test validate_configuration runs all validation checks."""
        settings = Settings(
            openai_api_key="invalid-format",  # Should produce warning
            workspace_root="/non/existing/path"  # Should produce warning
        )
        result = validate_configuration(settings)
        # Should have warnings from API key and path validation
        assert result.has_warnings is True

    def test_settings_validate_configuration_method(self):
        """Test Settings.validate_configuration method."""
        settings = Settings()
        result = settings.validate_configuration()
        assert isinstance(result, ValidationResult)


class TestFieldValidators:
    """Tests for Pydantic field validators in Settings."""

    def test_max_iterations_validator_accepts_valid(self):
        """Test max_iterations validator accepts valid values."""
        settings = Settings(max_iterations=50)
        assert settings.max_iterations == 50

    def test_max_iterations_validator_rejects_invalid(self):
        """Test max_iterations validator rejects invalid values."""
        with pytest.raises(ValueError) as exc_info:
            Settings(max_iterations=0)
        assert "max_iterations must be between 1 and 100" in str(exc_info.value)

    def test_max_iterations_validator_rejects_high(self):
        """Test max_iterations validator rejects high values."""
        with pytest.raises(ValueError) as exc_info:
            Settings(max_iterations=150)
        assert "max_iterations must be between 1 and 100" in str(exc_info.value)

    def test_max_sub_agents_validator_accepts_valid(self):
        """Test max_sub_agents validator accepts valid values."""
        settings = Settings(max_sub_agents=5)
        assert settings.max_sub_agents == 5

    def test_max_sub_agents_validator_rejects_invalid(self):
        """Test max_sub_agents validator rejects invalid values."""
        with pytest.raises(ValueError) as exc_info:
            Settings(max_sub_agents=0)
        assert "max_sub_agents must be between 1 and 10" in str(exc_info.value)

    def test_max_sub_agents_validator_rejects_high(self):
        """Test max_sub_agents validator rejects high values."""
        with pytest.raises(ValueError) as exc_info:
            Settings(max_sub_agents=20)
        assert "max_sub_agents must be between 1 and 10" in str(exc_info.value)

    def test_token_budget_ratio_validator_accepts_valid(self):
        """Test token_budget_ratio validator accepts valid values."""
        settings = Settings(token_budget_ratio=0.5)
        assert settings.token_budget_ratio == 0.5

    def test_token_budget_ratio_validator_rejects_low(self):
        """Test token_budget_ratio validator rejects low values."""
        with pytest.raises(ValueError) as exc_info:
            Settings(token_budget_ratio=0.05)
        assert "token_budget_ratio must be between 0.1 and 1.0" in str(exc_info.value)

    def test_token_budget_ratio_validator_rejects_high(self):
        """Test token_budget_ratio validator rejects high values."""
        with pytest.raises(ValueError) as exc_info:
            Settings(token_budget_ratio=1.5)
        assert "token_budget_ratio must be between 0.1 and 1.0" in str(exc_info.value)

    def test_token_warn_ratio_validator_accepts_valid(self):
        """Test token_warn_ratio validator accepts valid values."""
        settings = Settings(token_warn_ratio=0.6)
        assert settings.token_warn_ratio == 0.6

    def test_token_warn_ratio_validator_rejects_invalid(self):
        """Test token_warn_ratio validator rejects invalid values."""
        with pytest.raises(ValueError) as exc_info:
            Settings(token_warn_ratio=0.05)
        assert "token_warn_ratio must be between 0.1 and 1.0" in str(exc_info.value)

    def test_health_check_port_validator_accepts_valid(self):
        """Test health_check_port validator accepts valid values."""
        settings = Settings(health_check_port=9000)
        assert settings.health_check_port == 9000

    def test_health_check_port_validator_rejects_invalid(self):
        """Test health_check_port validator rejects invalid values."""
        with pytest.raises(ValueError) as exc_info:
            Settings(health_check_port=70000)
        assert "health_check_port must be between 1 and 65535" in str(exc_info.value)

    def test_alert_threshold_validator_accepts_valid(self):
        """Test alert threshold validators accept valid values."""
        settings = Settings(
            alert_failure_rate_threshold=0.5,
            alert_token_budget_threshold=0.7
        )
        assert settings.alert_failure_rate_threshold == 0.5
        assert settings.alert_token_budget_threshold == 0.7

    def test_alert_threshold_validator_rejects_invalid(self):
        """Test alert threshold validators reject invalid values."""
        with pytest.raises(ValueError) as exc_info:
            Settings(alert_failure_rate_threshold=1.5)
        assert "threshold must be between 0 and 1" in str(exc_info.value)


class TestModelValidator:
    """Tests for Pydantic model_validator in Settings."""

    def test_tracing_otlp_without_endpoint_raises_error(self):
        """Test tracing OTLP without endpoint raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            Settings(
                tracing_enabled=True,
                tracing_exporter="otlp",
                tracing_otlp_endpoint=""
            )
        assert "tracing_otlp_endpoint must be configured" in str(exc_info.value)

    def test_tracing_otlp_with_endpoint_valid(self):
        """Test tracing OTLP with endpoint is valid."""
        settings = Settings(
            tracing_enabled=True,
            tracing_exporter="otlp",
            tracing_otlp_endpoint="http://localhost:4317"
        )
        assert settings.tracing_enabled is True
        assert settings.tracing_exporter == "otlp"

    def test_production_environment_requires_log_to_json(self):
        """Test production environment requires log_to_json."""
        with pytest.raises(ValueError) as exc_info:
            Settings(environment="prod")
        assert "log_to_json must be True in production environment" in str(exc_info.value)

    def test_production_environment_with_all_requirements(self):
        """Test production environment with all required settings."""
        settings = Settings(
            environment="prod",
            log_to_json=True,
            openai_api_key="sk-validkey1234567890123"
        )
        assert settings.environment == "prod"
        assert settings.log_to_json is True

    def test_production_environment_debug_log_level_rejected(self):
        """Test production environment rejects DEBUG log level."""
        with pytest.raises(ValueError) as exc_info:
            Settings(
                environment="prod",
                log_to_json=True,
                log_level="DEBUG"
            )
        assert "log_level must not be DEBUG in production environment" in str(exc_info.value)


class TestBackwardCompatibility:
    """Tests for backward compatibility of validation enhancements."""

    def test_default_settings_still_valid(self):
        """Test default Settings is still valid."""
        settings = Settings()
        result = settings.validate_configuration()
        # Default settings should have only warnings (non-existing paths)
        # but no blocking errors
        assert result.is_valid is True

    def test_existing_settings_behavior_unchanged(self):
        """Test existing Settings behavior is unchanged."""
        settings = Settings(
            default_model="gpt-4",
            max_iterations=20,
            max_sub_agents=5
        )
        assert settings.default_model == "gpt-4"
        assert settings.max_iterations == 20
        assert settings.max_sub_agents == 5

    def test_validation_does_not_break_init(self):
        """Test validation does not break Settings initialization."""
        # Validation should only happen when explicitly called
        settings = Settings()  # Should not raise
        assert settings is not None
        # Explicit validation call
        result = settings.validate_configuration()
        assert result is not None