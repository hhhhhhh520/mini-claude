"""Configuration validation utilities.

This module provides comprehensive validation for configuration settings,
including API key format validation, path existence checks, and cross-field validation.
"""

import re
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, TYPE_CHECKING

if TYPE_CHECKING:
    from .settings import Settings

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of configuration validation.

    Attributes:
        warnings: List of warning messages (non-blocking issues)
        errors: List of error messages (blocking issues for production)
    """

    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        """Check if configuration is valid (no errors)."""
        return len(self.errors) == 0

    @property
    def has_warnings(self) -> bool:
        """Check if there are any warnings."""
        return len(self.warnings) > 0

    def add_warning(self, message: str) -> None:
        """Add a warning message."""
        self.warnings.append(message)

    def add_error(self, message: str) -> None:
        """Add an error message."""
        self.errors.append(message)

    def merge(self, other: "ValidationResult") -> None:
        """Merge another ValidationResult into this one."""
        self.warnings.extend(other.warnings)
        self.errors.extend(other.errors)

    def __str__(self) -> str:
        """Return string representation."""
        lines = []
        if self.warnings:
            lines.append("Warnings:")
            for w in self.warnings:
                lines.append(f"  - {w}")
        if self.errors:
            lines.append("Errors:")
            for e in self.errors:
                lines.append(f"  - {e}")
        return "\n".join(lines) if lines else "No validation issues"


class ConfigValidator:
    """Configuration validator with comprehensive validation rules.

    This class provides validation methods for:
    - API key format validation (warning level)
    - Path existence checks
    - Numeric range validation
    - Cross-field validation
    """

    # API Key format patterns
    OPENAI_KEY_PATTERN = re.compile(r"^sk-[a-zA-Z0-9]{20,}$")
    ANTHROPIC_KEY_PATTERN = re.compile(r"^sk-ant-[a-zA-Z0-9-]{20,}$")

    # Numeric ranges
    MAX_ITERATIONS_MIN = 1
    MAX_ITERATIONS_MAX = 100
    MAX_SUB_AGENTS_MIN = 1
    MAX_SUB_AGENTS_MAX = 10
    TOKEN_BUDGET_RATIO_MIN = 0.1
    TOKEN_BUDGET_RATIO_MAX = 1.0

    def __init__(self, settings: "Settings"):
        """Initialize validator with settings instance.

        Args:
            settings: Settings instance to validate
        """
        self.settings = settings
        self.result = ValidationResult()

    def validate_all(self) -> ValidationResult:
        """Run all validation checks.

        Returns:
            ValidationResult containing all warnings and errors
        """
        self.validate_api_keys()
        self.validate_paths()
        self.validate_numeric_ranges()
        self.validate_cross_fields()

        return self.result

    def validate_api_keys(self) -> None:
        """Validate API key formats.

        Validates:
        - openai_api_key: should start with 'sk-' and be at least 20 chars
        - anthropic_api_key: should start with 'sk-ant-'

        Note: Validation failures are warnings, not errors (keys can be empty)
        """
        # Validate OpenAI API key
        if self.settings.openai_api_key:
            key = self.settings.openai_api_key
            if not key.startswith("sk-"):
                self.result.add_warning(
                    f"openai_api_key should start with 'sk-', got prefix '{key[:5]}...'"
                )
            elif len(key) < 20:
                self.result.add_warning(
                    f"openai_api_key should be at least 20 characters, got {len(key)}"
                )

        # Validate Anthropic API key
        if self.settings.anthropic_api_key:
            key = self.settings.anthropic_api_key
            if not key.startswith("sk-ant-"):
                self.result.add_warning(
                    f"anthropic_api_key should start with 'sk-ant-', got prefix '{key[:10]}...'"
                )

        # Validate Google API key (no specific format, just check non-empty if set)
        if self.settings.google_api_key:
            key = self.settings.google_api_key
            if len(key) < 10:
                self.result.add_warning(f"google_api_key seems too short ({len(key)} chars)")

    def validate_paths(self) -> None:
        """Validate path configurations.

        Validates:
        - workspace_root: path must exist or be creatable
        - log_file_path: parent directory must exist
        - session_db_path: path validity check
        """
        # Validate workspace_root
        workspace = Path(self.settings.workspace_root)
        if not workspace.exists():
            # Try to check if parent exists (can create)
            try:
                parent = workspace.parent
                if not parent.exists():
                    self.result.add_warning(
                        f"workspace_root parent directory does not exist: {parent}"
                    )
                else:
                    self.result.add_warning(
                        f"workspace_root does not exist, will be created: {workspace}"
                    )
            except Exception as e:
                self.result.add_error(
                    f"workspace_root path is invalid: {self.settings.workspace_root} ({e})"
                )

        # Validate log_file_path
        log_path = Path(self.settings.log_file_path)
        log_parent = log_path.parent
        if log_parent and not log_parent.exists():
            self.result.add_warning(f"log_file_path parent directory does not exist: {log_parent}")

        # Validate log_json_path
        json_path = Path(self.settings.log_json_path)
        json_parent = json_path.parent
        if json_parent and not json_parent.exists():
            self.result.add_warning(f"log_json_path parent directory does not exist: {json_parent}")

        # Validate log_audit_path
        audit_path = Path(self.settings.log_audit_path)
        audit_parent = audit_path.parent
        if audit_parent and not audit_parent.exists():
            self.result.add_warning(
                f"log_audit_path parent directory does not exist: {audit_parent}"
            )

        # Validate session_db_path
        session_path = Path(self.settings.session_db_path)
        if not session_path.is_absolute():
            # Relative path is OK, check if it's a valid path format
            try:
                session_path.resolve()
            except Exception as e:
                self.result.add_error(
                    f"session_db_path is invalid: {self.settings.session_db_path} ({e})"
                )

        # Validate vector_db_path
        vector_path = Path(self.settings.vector_db_path)
        if not vector_path.exists():
            self.result.add_warning(
                f"vector_db_path does not exist, will be created: {vector_path}"
            )

    def validate_numeric_ranges(self) -> None:
        """Validate numeric configuration ranges.

        Validates:
        - max_iterations: 1-100
        - max_sub_agents: 1-10
        - token_budget_ratio: 0.1-1.0
        - token_warn_ratio: should be less than token_budget_ratio
        """
        # Validate max_iterations
        if not (self.MAX_ITERATIONS_MIN <= self.settings.max_iterations <= self.MAX_ITERATIONS_MAX):
            self.result.add_error(
                f"max_iterations must be between {self.MAX_ITERATIONS_MIN} and "
                f"{self.MAX_ITERATIONS_MAX}, got {self.settings.max_iterations}"
            )

        # Validate max_sub_agents
        if not (self.MAX_SUB_AGENTS_MIN <= self.settings.max_sub_agents <= self.MAX_SUB_AGENTS_MAX):
            self.result.add_error(
                f"max_sub_agents must be between {self.MAX_SUB_AGENTS_MIN} and "
                f"{self.MAX_SUB_AGENTS_MAX}, got {self.settings.max_sub_agents}"
            )

        # Validate token_budget_ratio
        if not (
            self.TOKEN_BUDGET_RATIO_MIN
            <= self.settings.token_budget_ratio
            <= self.TOKEN_BUDGET_RATIO_MAX
        ):
            self.result.add_error(
                f"token_budget_ratio must be between {self.TOKEN_BUDGET_RATIO_MIN} and "
                f"{self.TOKEN_BUDGET_RATIO_MAX}, got {self.settings.token_budget_ratio}"
            )

        # Validate token_warn_ratio is less than token_budget_ratio
        if self.settings.token_warn_ratio >= self.settings.token_budget_ratio:
            self.result.add_warning(
                f"token_warn_ratio ({self.settings.token_warn_ratio}) should be less than "
                f"token_budget_ratio ({self.settings.token_budget_ratio})"
            )

        # Validate health_check_port
        if not (1 <= self.settings.health_check_port <= 65535):
            self.result.add_error(
                f"health_check_port must be between 1 and 65535, got {self.settings.health_check_port}"
            )

        # Validate alert thresholds
        if not (0.0 <= self.settings.alert_failure_rate_threshold <= 1.0):
            self.result.add_error(
                f"alert_failure_rate_threshold must be between 0 and 1, got {self.settings.alert_failure_rate_threshold}"
            )

        if not (0.0 <= self.settings.alert_token_budget_threshold <= 1.0):
            self.result.add_error(
                f"alert_token_budget_threshold must be between 0 and 1, got {self.settings.alert_token_budget_threshold}"
            )

    def validate_cross_fields(self) -> None:
        """Validate cross-field dependencies.

        Validates:
        - Production environment must have webhook_url configured
        - When tracing is enabled, must have valid exporter configuration
        - When notification is enabled, must have valid channel configuration
        """
        is_production = self.settings.environment.lower() == "prod"

        # Production-specific validations
        if is_production:
            # Must have webhook_url in production
            if self.settings.alert_enabled and not self.settings.alert_webhook_url:
                self.result.add_error(
                    "Production environment requires alert_webhook_url when alert_enabled is True"
                )

            # Must have JSON logging in production
            if not self.settings.log_to_json:
                self.result.add_warning(
                    "Production environment should have log_to_json enabled for structured logging"
                )

            # Must have at least one API key
            if not any(
                [
                    self.settings.anthropic_api_key,
                    self.settings.openai_api_key,
                    self.settings.google_api_key,
                ]
            ):
                self.result.add_error(
                    "Production environment requires at least one API key to be configured"
                )

        # Tracing validation
        if self.settings.tracing_enabled:
            valid_exporters = ["console", "otlp", "file"]
            if self.settings.tracing_exporter not in valid_exporters:
                self.result.add_error(
                    f"tracing_exporter must be one of {valid_exporters} when tracing_enabled is True, "
                    f"got '{self.settings.tracing_exporter}'"
                )

            if self.settings.tracing_exporter == "otlp" and not self.settings.tracing_otlp_endpoint:
                self.result.add_error(
                    "tracing_otlp_endpoint must be configured when tracing_exporter is 'otlp'"
                )

        # Notification validation
        if self.settings.notification_enabled:
            if "email" in self.settings.notification_channels:
                if not all(
                    [self.settings.smtp_host, self.settings.smtp_user, self.settings.smtp_password]
                ):
                    self.result.add_warning(
                        "Email notification enabled but SMTP settings are incomplete"
                    )

        # Rate limiting validation
        if self.settings.rate_limit_strategy == "token_bucket":
            if self.settings.rate_limit_burst_size > self.settings.rate_limit_requests_per_minute:
                self.result.add_warning(
                    f"rate_limit_burst_size ({self.settings.rate_limit_burst_size}) should not exceed "
                    f"rate_limit_requests_per_minute ({self.settings.rate_limit_requests_per_minute})"
                )


def validate_configuration(settings: "Settings") -> ValidationResult:
    """Validate configuration settings.

    This is the main entry point for configuration validation.

    Args:
        settings: Settings instance to validate

    Returns:
        ValidationResult containing all warnings and errors
    """
    validator = ConfigValidator(settings)
    return validator.validate_all()
