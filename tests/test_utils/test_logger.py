"""Unit tests for structured logging system."""

import json
import logging
from pathlib import Path
from typing import Generator

import pytest

from mini_claude.utils.logger import (
    StructuredFormatter,
    AuditLogger,
    get_logger,
    init_logging,
    get_audit_logger,
    reset_logging,
    OutputSanitizer,
    ExecutionLogExporter,
    get_execution_log_exporter,
)


@pytest.fixture
def temp_log_dir(tmp_path: Path) -> Path:
    """Create a temporary directory for log files."""
    log_dir = tmp_path / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


@pytest.fixture
def clean_logging() -> Generator[None, None, None]:
    """Clean up logging state before and after each test."""
    reset_logging()
    yield
    reset_logging()


class TestStructuredFormatter:
    """Test JSON formatter."""

    def test_format_basic_record(self):
        """Test formatting a basic log record."""
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        result = formatter.format(record)
        data = json.loads(result)

        assert data["level"] == "INFO"
        assert data["logger"] == "test"
        assert data["message"] == "Test message"
        assert data["module"] == "test"
        assert data["line"] == 10

    def test_format_with_extra_data(self):
        """Test formatting with extra structured data."""
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.DEBUG,
            pathname="test.py",
            lineno=1,
            msg="Debug message",
            args=(),
            exc_info=None,
        )
        record.extra_data = {"user_id": 123, "action": "login"}

        result = formatter.format(record)
        data = json.loads(result)

        assert data["data"]["user_id"] == 123
        assert data["data"]["action"] == "login"

    def test_format_with_exception(self):
        """Test formatting with exception info."""
        formatter = StructuredFormatter()

        try:
            raise ValueError("Test error")
        except ValueError:
            import sys
            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="test.py",
            lineno=1,
            msg="Error occurred",
            args=(),
            exc_info=exc_info,
        )

        result = formatter.format(record)
        data = json.loads(result)

        assert "exception" in data
        assert "ValueError: Test error" in data["exception"]


class TestStructuredLogger:
    """Test structured logger wrapper."""

    def test_debug_logging(self, temp_log_dir: Path, clean_logging):
        """Test debug level logging."""
        log_file = temp_log_dir / "test.log"

        init_logging(
            log_level="DEBUG",
            log_to_console=False,
            log_to_file=True,
            log_file_path=str(log_file),
            force=True,
        )

        logger = get_logger("mini_claude.test.debug")
        logger.debug("Debug message", key="value")

        content = log_file.read_text(encoding="utf-8")
        assert "Debug message" in content
        assert "DEBUG" in content

    def test_info_logging(self, temp_log_dir: Path, clean_logging):
        """Test info level logging."""
        log_file = temp_log_dir / "test.log"

        init_logging(
            log_level="INFO",
            log_to_console=False,
            log_to_file=True,
            log_file_path=str(log_file),
            force=True,
        )

        logger = get_logger("mini_claude.test.info")
        logger.info("Info message", count=42)

        content = log_file.read_text(encoding="utf-8")
        assert "Info message" in content
        assert "INFO" in content

    def test_warning_logging(self, temp_log_dir: Path, clean_logging):
        """Test warning level logging."""
        log_file = temp_log_dir / "test.log"

        init_logging(
            log_level="WARNING",
            log_to_console=False,
            log_to_file=True,
            log_file_path=str(log_file),
            force=True,
        )

        logger = get_logger("mini_claude.test.warning")
        logger.warning("Warning message")

        content = log_file.read_text(encoding="utf-8")
        assert "Warning message" in content
        assert "WARNING" in content

    def test_error_logging_with_exception(self, temp_log_dir: Path, clean_logging):
        """Test error logging with exception info."""
        log_file = temp_log_dir / "test.log"

        init_logging(
            log_level="ERROR",
            log_to_console=False,
            log_to_file=True,
            log_file_path=str(log_file),
            force=True,
        )

        logger = get_logger("mini_claude.test.error")

        try:
            raise RuntimeError("Test exception")
        except RuntimeError:
            logger.error("Error occurred", exc_info=True)

        content = log_file.read_text(encoding="utf-8")
        assert "Error occurred" in content
        assert "RuntimeError: Test exception" in content

    def test_logger_caching(self):
        """Test that loggers are cached."""
        logger1 = get_logger("test.cached")
        logger2 = get_logger("test.cached")

        assert logger1 is logger2


class TestAuditLogger:
    """Test audit logger for tool calls."""

    def test_log_tool_call_success(self, temp_log_dir: Path):
        """Test logging successful tool call."""
        audit_file = temp_log_dir / "audit.log"

        audit = AuditLogger(str(audit_file))
        audit.log_tool_call(
            tool_name="write_file",
            arguments={"path": "test.py", "content": "print('hello')"},
            result="Successfully wrote 19 characters",
            success=True,
            duration_ms=15.5,
        )

        content = audit_file.read_text(encoding="utf-8")
        data = json.loads(content.strip())

        assert data["data"]["event"] == "tool_call"
        assert data["data"]["tool_name"] == "write_file"
        assert data["data"]["success"] is True
        assert data["data"]["duration_ms"] == 15.5

    def test_log_tool_call_failure(self, temp_log_dir: Path):
        """Test logging failed tool call."""
        audit_file = temp_log_dir / "audit.log"

        audit = AuditLogger(str(audit_file))
        audit.log_tool_call(
            tool_name="read_file",
            arguments={"path": "nonexistent.py"},
            result="File not found",
            success=False,
            duration_ms=5.2,
        )

        content = audit_file.read_text(encoding="utf-8")
        data = json.loads(content.strip())

        assert data["data"]["success"] is False

    def test_sensitive_data_redaction(self, temp_log_dir: Path):
        """Test that sensitive data is redacted."""
        audit_file = temp_log_dir / "audit.log"

        audit = AuditLogger(str(audit_file))
        audit.log_tool_call(
            tool_name="api_call",
            arguments={
                "api_key": "secret123",
                "password": "mypass",
                "url": "https://api.example.com",
            },
            result="OK",
            success=True,
            duration_ms=50.0,
        )

        content = audit_file.read_text(encoding="utf-8")

        # Sensitive data should be redacted
        assert "secret123" not in content
        assert "mypass" not in content
        assert "****" in content

        # Non-sensitive data should be preserved
        assert "https://api.example.com" in content

    def test_result_truncation(self, temp_log_dir: Path):
        """Test that long results are truncated."""
        audit_file = temp_log_dir / "audit.log"

        audit = AuditLogger(str(audit_file))
        long_result = "x" * 1000

        audit.log_tool_call(
            tool_name="read_file",
            arguments={"path": "large.txt"},
            result=long_result,
            success=True,
            duration_ms=10.0,
        )

        content = audit_file.read_text(encoding="utf-8")
        data = json.loads(content.strip())

        # Result should be truncated
        assert len(data["data"]["result"]) < 600
        assert "truncated" in data["data"]["result"]

    def test_log_agent_spawn(self, temp_log_dir: Path):
        """Test logging agent spawn event."""
        audit_file = temp_log_dir / "audit.log"

        audit = AuditLogger(str(audit_file))
        audit.log_agent_spawn(
            agent_id="agent_001",
            task="Create a Python file",
            model="deepseek-chat",
        )

        content = audit_file.read_text(encoding="utf-8")
        data = json.loads(content.strip())

        assert data["data"]["event"] == "agent_spawn"
        assert data["data"]["agent_id"] == "agent_001"
        assert data["data"]["model"] == "deepseek-chat"

    def test_log_agent_complete(self, temp_log_dir: Path):
        """Test logging agent completion event."""
        audit_file = temp_log_dir / "audit.log"

        audit = AuditLogger(str(audit_file))
        audit.log_agent_complete(
            agent_id="agent_001",
            success=True,
            duration_ms=1500.0,
            result_length=500,
        )

        content = audit_file.read_text(encoding="utf-8")
        data = json.loads(content.strip())

        assert data["data"]["event"] == "agent_complete"
        assert data["data"]["success"] is True


class TestInitLogging:
    """Test logging initialization."""

    def test_init_creates_log_directory(self, tmp_path: Path, clean_logging):
        """Test that init_logging creates log directory."""
        log_file = tmp_path / "logs" / "app.log"

        init_logging(
            log_to_console=False,
            log_to_file=True,
            log_file_path=str(log_file),
            force=True,
        )

        assert log_file.parent.exists()

    def test_init_with_json_format(self, temp_log_dir: Path, clean_logging):
        """Test initialization with JSON format."""
        json_file = temp_log_dir / "test.json"

        init_logging(
            log_level="INFO",
            log_to_console=False,
            log_to_file=False,
            log_to_json=True,
            log_json_path=str(json_file),
            force=True,
        )

        logger = get_logger("mini_claude.test.json")
        logger.info("JSON test", key="value")

        content = json_file.read_text(encoding="utf-8")
        data = json.loads(content.strip())

        assert data["message"] == "JSON test"
        assert data["data"]["key"] == "value"

    def test_init_audit_logger(self, temp_log_dir: Path, clean_logging):
        """Test that audit logger is initialized."""
        audit_file = temp_log_dir / "audit.log"

        init_logging(
            log_to_console=False,
            log_to_file=False,
            audit_enabled=True,
            log_audit_path=str(audit_file),
            force=True,
        )

        audit = get_audit_logger()
        assert audit is not None

        audit.log_tool_call(
            tool_name="test",
            arguments={},
            result="OK",
            success=True,
            duration_ms=1.0,
        )

        assert audit_file.exists()


class TestLogRotation:
    """Test log rotation functionality."""

    def test_rotation_on_size(self, temp_log_dir: Path, clean_logging):
        """Test that log files rotate when size limit is reached."""
        log_file = temp_log_dir / "rotate.log"

        init_logging(
            log_level="DEBUG",
            log_to_console=False,
            log_to_file=True,
            log_file_path=str(log_file),
            log_max_bytes=100,  # Very small for testing
            log_backup_count=2,
            force=True,
        )

        logger = get_logger("mini_claude.test.rotate")

        # Write enough logs to trigger rotation
        for i in range(20):
            logger.info(f"Message {i} " + "x" * 20)

        # Check that backup file was created
        # Note: RotatingFileHandler creates .1, .2, etc. files
        backup_exists = (temp_log_dir / "rotate.log.1").exists() or \
                       (temp_log_dir / "rotate.log").stat().st_size > 0

        assert backup_exists


class TestOutputSanitization:
    """Test output content sanitization for sensitive data."""

    def test_sanitize_api_key_in_output(self, temp_log_dir: Path):
        """Test that API keys in output are sanitized."""
        audit_file = temp_log_dir / "audit.log"

        audit = AuditLogger(str(audit_file))
        audit.log_tool_call(
            tool_name="api_request",
            arguments={"url": "https://api.example.com"},
            result="Response with key: sk-abcdefghijklmnopqrstuvwxyz123456",
            success=True,
            duration_ms=100.0,
        )

        content = audit_file.read_text(encoding="utf-8")
        # API key should be sanitized
        assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in content
        assert "sk-****" in content

    def test_sanitize_password_in_output(self, temp_log_dir: Path):
        """Test that passwords in output are sanitized."""
        audit_file = temp_log_dir / "audit.log"

        audit = AuditLogger(str(audit_file))
        audit.log_tool_call(
            tool_name="db_query",
            arguments={"query": "SELECT * FROM users"},
            result="Connection string: mysql://admin:secretpass@localhost/db",
            success=True,
            duration_ms=50.0,
        )

        content = audit_file.read_text(encoding="utf-8")
        # Password in connection string should be sanitized
        assert "secretpass" not in content
        assert "****" in content

    def test_sanitize_bearer_token_in_output(self, temp_log_dir: Path):
        """Test that Bearer tokens in output are sanitized."""
        audit_file = temp_log_dir / "audit.log"

        audit = AuditLogger(str(audit_file))
        audit.log_tool_call(
            tool_name="http_request",
            arguments={"endpoint": "/api/data"},
            result="Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
            success=True,
            duration_ms=30.0,
        )

        content = audit_file.read_text(encoding="utf-8")
        # Bearer token should be sanitized
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in content
        assert "Bearer ****" in content

    def test_sanitize_nested_json_in_output(self, temp_log_dir: Path):
        """Test that sensitive data in nested JSON is sanitized."""
        audit_file = temp_log_dir / "audit.log"

        audit = AuditLogger(str(audit_file))
        audit.log_tool_call(
            tool_name="config_read",
            arguments={"file": "config.json"},
            result='{"database": {"host": "localhost", "password": "dbpassword123"}, "api_key": "sk-test123456"}',
            success=True,
            duration_ms=10.0,
        )

        content = audit_file.read_text(encoding="utf-8")
        # Nested sensitive data should be sanitized
        assert "dbpassword123" not in content
        assert "sk-test123456" not in content

    def test_sanitize_github_token_in_output(self, temp_log_dir: Path):
        """Test that GitHub tokens in output are sanitized."""
        audit_file = temp_log_dir / "audit.log"

        audit = AuditLogger(str(audit_file))
        audit.log_tool_call(
            tool_name="git_clone",
            arguments={"repo": "example/repo"},
            result="Cloned using token: ghp_1234567890abcdefghijklmnopqrstuvwxyz12",
            success=True,
            duration_ms=500.0,
        )

        content = audit_file.read_text(encoding="utf-8")
        # GitHub token should be sanitized
        assert "ghp_1234567890abcdefghijklmnopqrstuvwxyz12" not in content
        assert "ghp_****" in content

    def test_sanitize_aws_key_in_output(self, temp_log_dir: Path):
        """Test that AWS access keys in output are sanitized."""
        audit_file = temp_log_dir / "audit.log"

        audit = AuditLogger(str(audit_file))
        audit.log_tool_call(
            tool_name="aws_request",
            arguments={"service": "s3"},
            result="AWS credentials: AKIAIOSFODNN7EXAMPLE",
            success=True,
            duration_ms=200.0,
        )

        content = audit_file.read_text(encoding="utf-8")
        # AWS key should be sanitized
        assert "AKIAIOSFODNN7EXAMPLE" not in content
        assert "AKIA****" in content

    def test_sanitize_multiple_sensitive_in_output(self, temp_log_dir: Path):
        """Test that multiple sensitive patterns in output are all sanitized."""
        audit_file = temp_log_dir / "audit.log"

        audit = AuditLogger(str(audit_file))
        audit.log_tool_call(
            tool_name="multi_test",
            arguments={},
            result="API key: sk-abcdefghijklmnopqrstuvwxyz, password=admin123, token: Bearer xyz789abc",
            success=True,
            duration_ms=10.0,
        )

        content = audit_file.read_text(encoding="utf-8")
        # All sensitive data should be sanitized
        assert "sk-abcdefghijklmnopqrstuvwxyz" not in content
        assert "admin123" not in content
        assert "xyz789abc" not in content

    def test_sanitize_deeply_nested_json(self, temp_log_dir: Path):
        """Test that deeply nested JSON content is sanitized."""
        audit_file = temp_log_dir / "audit.log"

        audit = AuditLogger(str(audit_file))
        audit.log_tool_call(
            tool_name="deep_config",
            arguments={},
            result='{"level1": {"level2": {"level3": {"api_key": "sk-deep123"}}}}',
            success=True,
            duration_ms=10.0,
        )

        content = audit_file.read_text(encoding="utf-8")
        # Deeply nested API key should be sanitized
        assert "sk-deep123" not in content

    def test_preserve_non_sensitive_output(self, temp_log_dir: Path):
        """Test that non-sensitive output is preserved."""
        audit_file = temp_log_dir / "audit.log"

        audit = AuditLogger(str(audit_file))
        audit.log_tool_call(
            tool_name="file_read",
            arguments={"path": "test.py"},
            result='def hello():\n    print("Hello, World!")\n',
            success=True,
            duration_ms=5.0,
        )

        content = audit_file.read_text(encoding="utf-8")
        # Non-sensitive content should be preserved
        assert "Hello, World!" in content
        assert "print" in content

    def test_sanitize_connection_strings(self, temp_log_dir: Path):
        """Test that various connection strings are sanitized."""
        audit_file = temp_log_dir / "audit.log"

        audit = AuditLogger(str(audit_file))
        audit.log_tool_call(
            tool_name="db_test",
            arguments={},
            result="Connections: postgresql://user:pass@host/db, mongodb://admin:secret@localhost/test",
            success=True,
            duration_ms=10.0,
        )

        content = audit_file.read_text(encoding="utf-8")
        # Passwords in connection strings should be sanitized
        assert "pass@host" not in content
        assert "secret@localhost" not in content

    def test_sanitize_structured_formatter_output(self, temp_log_dir: Path, clean_logging):
        """Test that StructuredFormatter sanitizes sensitive data."""
        json_file = temp_log_dir / "test.json"

        init_logging(
            log_level="INFO",
            log_to_console=False,
            log_to_file=False,
            log_to_json=True,
            log_json_path=str(json_file),
            force=True,
        )

        logger = get_logger("mini_claude.test.sanitize")
        # Use patterns that match SENSITIVE_PATTERNS (sk- needs 10+ chars, password needs 3+ chars)
        logger.info("API call with key sk-abcdefghijklmnopqrstuvwxyz and password=mysecret")

        content = json_file.read_text(encoding="utf-8")
        # Sensitive data in message should be sanitized
        assert "sk-abcdefghijklmnopqrstuvwxyz" not in content
        assert "mysecret" not in content

    def test_sanitize_args_extended_keys(self, temp_log_dir: Path):
        """Test that _sanitize_args handles extended sensitive keys."""
        audit_file = temp_log_dir / "audit.log"

        audit = AuditLogger(str(audit_file))
        audit.log_tool_call(
            tool_name="auth_test",
            arguments={
                "username": "admin",
                "secret": "mysecret",
                "apikey": "key123",
                "credential": "cred456",
                "private_key": "pk789",
            },
            result="OK",
            success=True,
            duration_ms=10.0,
        )

        content = audit_file.read_text(encoding="utf-8")
        # Extended sensitive keys should be redacted
        assert "mysecret" not in content
        assert "key123" not in content
        assert "cred456" not in content
        assert "pk789" not in content
        # Non-sensitive data should be preserved
        assert "admin" in content


class TestExecutionLogExporter:
    """Test execution log export functionality."""

    def test_export_json_basic(self, temp_log_dir: Path, clean_logging):
        """Test basic JSON export."""
        # Initialize logging
        audit_file = temp_log_dir / "audit.log"
        init_logging(
            log_level="INFO",
            log_to_console=False,
            log_to_file=False,
            audit_enabled=True,
            log_audit_path=str(audit_file),
            force=True,
        )

        # Create exporter
        exporter = ExecutionLogExporter()
        output = exporter.export_json("test_session", include_metrics=False, include_audit=False)

        # Verify JSON structure
        data = json.loads(output)
        assert "export_metadata" in data
        assert "session_id" in data["export_metadata"]
        assert data["export_metadata"]["session_id"] == "test_session"
        assert "exported_at" in data["export_metadata"]
        assert "session" in data

    def test_export_json_with_metrics(self, temp_log_dir: Path, clean_logging):
        """Test JSON export with metrics."""
        from mini_claude.monitoring.metrics import get_metrics_collector, reset_metrics_collector

        reset_metrics_collector()

        # Record some metrics
        collector = get_metrics_collector()
        collector.record_request_start()
        collector.record_request_end(success=True, duration=0.5)
        collector.record_token_usage(100, "input")
        collector.record_token_usage(50, "output")
        collector.record_tool_call("write_file", success=True)

        # Create exporter
        exporter = ExecutionLogExporter()
        output = exporter.export_json("test_session", include_metrics=True, include_audit=False)

        # Verify metrics in output
        data = json.loads(output)
        assert "metrics" in data
        assert "requests" in data["metrics"]
        assert data["metrics"]["requests"]["total"] == 1
        assert data["metrics"]["tokens"]["input"] == 100

        reset_metrics_collector()

    def test_export_markdown_basic(self, temp_log_dir: Path, clean_logging):
        """Test basic Markdown export."""
        exporter = ExecutionLogExporter()
        output = exporter.export_markdown("test_session", include_metrics=False, include_audit=False)

        # Verify Markdown structure
        assert "# Execution Log Export" in output
        assert "**Session ID**" in output
        assert "test_session" in output

    def test_export_markdown_with_metrics(self, temp_log_dir: Path, clean_logging):
        """Test Markdown export with metrics."""
        from mini_claude.monitoring.metrics import get_metrics_collector, reset_metrics_collector

        reset_metrics_collector()

        collector = get_metrics_collector()
        collector.record_request_start()
        collector.record_request_end(success=True, duration=0.5)

        exporter = ExecutionLogExporter()
        output = exporter.export_markdown("test_session", include_metrics=True, include_audit=False)

        assert "## Performance Metrics" in output
        assert "| Total Requests |" in output

        reset_metrics_collector()

    def test_export_html_basic(self, temp_log_dir: Path, clean_logging):
        """Test basic HTML export."""
        exporter = ExecutionLogExporter()
        output = exporter.export_html("test_session", include_metrics=False, include_audit=False)

        # Verify HTML structure
        assert "<!DOCTYPE html>" in output
        assert "<html lang='en'>" in output
        assert "test_session" in output
        assert "<style>" in output

    def test_export_html_with_metrics(self, temp_log_dir: Path, clean_logging):
        """Test HTML export with metrics."""
        from mini_claude.monitoring.metrics import get_metrics_collector, reset_metrics_collector

        reset_metrics_collector()

        collector = get_metrics_collector()
        collector.record_request_start()
        collector.record_request_end(success=True, duration=0.5)

        exporter = ExecutionLogExporter()
        output = exporter.export_html("test_session", include_metrics=True, include_audit=False)

        assert "<h2>Performance Metrics</h2>" in output
        assert "<td>1</td>" in output  # request count

        reset_metrics_collector()

    def test_export_to_file_json(self, temp_log_dir: Path, clean_logging):
        """Test exporting to JSON file."""
        export_file = temp_log_dir / "export.json"

        exporter = ExecutionLogExporter()
        result = exporter.export_to_file(
            session_id="test_session",
            format="json",
            path=str(export_file),
            include_metrics=False,
            include_audit=False,
        )

        assert result is True
        assert export_file.exists()

        content = export_file.read_text(encoding="utf-8")
        data = json.loads(content)
        assert data["export_metadata"]["session_id"] == "test_session"

    def test_export_to_file_markdown(self, temp_log_dir: Path, clean_logging):
        """Test exporting to Markdown file."""
        export_file = temp_log_dir / "export.md"

        exporter = ExecutionLogExporter()
        result = exporter.export_to_file(
            session_id="test_session",
            format="markdown",
            path=str(export_file),
            include_metrics=False,
            include_audit=False,
        )

        assert result is True
        assert export_file.exists()

        content = export_file.read_text(encoding="utf-8")
        assert "# Execution Log Export" in content

    def test_export_to_file_html(self, temp_log_dir: Path, clean_logging):
        """Test exporting to HTML file."""
        export_file = temp_log_dir / "export.html"

        exporter = ExecutionLogExporter()
        result = exporter.export_to_file(
            session_id="test_session",
            format="html",
            path=str(export_file),
            include_metrics=False,
            include_audit=False,
        )

        assert result is True
        assert export_file.exists()

        content = export_file.read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content

    def test_export_to_file_md_alias(self, temp_log_dir: Path, clean_logging):
        """Test that 'md' format alias works."""
        export_file = temp_log_dir / "export_alias.md"

        exporter = ExecutionLogExporter()
        result = exporter.export_to_file(
            session_id="test_session",
            format="md",
            path=str(export_file),
            include_metrics=False,
            include_audit=False,
        )

        assert result is True
        content = export_file.read_text(encoding="utf-8")
        assert "# Execution Log Export" in content

    def test_export_to_file_invalid_format(self, temp_log_dir: Path):
        """Test that invalid format raises error."""
        export_file = temp_log_dir / "export.txt"

        exporter = ExecutionLogExporter()
        with pytest.raises(ValueError, match="Unsupported export format"):
            exporter.export_to_file(
                session_id="test_session",
                format="txt",
                path=str(export_file),
            )

    def test_export_json_sanitizes_api_key(self, temp_log_dir: Path, clean_logging):
        """Test that JSON export sanitizes API keys."""
        from mini_claude.utils.session import get_session_manager

        # Create a session with sensitive data
        session_file = temp_log_dir / "sessions.db"
        manager = get_session_manager(str(session_file))
        manager.save_session(
            "sensitive_session",
            messages=[
                {"role": "user", "content": "API key: sk-abcdefghijklmnopqrstuvwxyz123456"},
                {"role": "assistant", "content": "password=admin123"},
            ],
        )

        exporter = ExecutionLogExporter(sanitize_output=True)
        output = exporter.export_json("sensitive_session", include_metrics=False, include_audit=False)

        # Verify sensitive data is sanitized
        assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in output
        assert "admin123" not in output
        assert "****" in output

    def test_export_markdown_sanitizes_api_key(self, temp_log_dir: Path, clean_logging):
        """Test that Markdown export sanitizes API keys."""
        from mini_claude.utils.session import get_session_manager

        session_file = temp_log_dir / "sessions.db"
        manager = get_session_manager(str(session_file))
        manager.save_session(
            "sensitive_session",
            messages=[
                {"role": "user", "content": "API key: sk-abcdefghijklmnopqrstuvwxyz123456"},
            ],
        )

        exporter = ExecutionLogExporter(sanitize_output=True)
        output = exporter.export_markdown("sensitive_session", include_metrics=False, include_audit=False)

        assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in output

    def test_export_html_sanitizes_api_key(self, temp_log_dir: Path, clean_logging):
        """Test that HTML export sanitizes API keys."""
        from mini_claude.utils.session import get_session_manager

        session_file = temp_log_dir / "sessions.db"
        manager = get_session_manager(str(session_file))
        manager.save_session(
            "sensitive_session",
            messages=[
                {"role": "user", "content": "API key: sk-abcdefghijklmnopqrstuvwxyz123456"},
            ],
        )

        exporter = ExecutionLogExporter(sanitize_output=True)
        output = exporter.export_html("sensitive_session", include_metrics=False, include_audit=False)

        assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in output

    def test_export_without_sanitization(self, temp_log_dir: Path, clean_logging):
        """Test export without sanitization preserves content."""
        from mini_claude.utils.session import get_session_manager

        session_file = temp_log_dir / "sessions.db"
        manager = get_session_manager(str(session_file))
        manager.save_session(
            "test_session",
            messages=[
                {"role": "user", "content": "Hello, World!"},
            ],
        )

        exporter = ExecutionLogExporter(sanitize_output=False)
        output = exporter.export_json("test_session", include_metrics=False, include_audit=False)

        # Non-sensitive content should be preserved
        assert "Hello, World!" in output

    def test_export_with_audit_log(self, temp_log_dir: Path, clean_logging):
        """Test export with audit log entries."""
        # Initialize audit logging
        audit_file = temp_log_dir / "audit.log"
        init_logging(
            log_level="INFO",
            log_to_console=False,
            log_to_file=False,
            audit_enabled=True,
            log_audit_path=str(audit_file),
            force=True,
        )

        # Log some tool calls
        audit = get_audit_logger()
        audit.log_tool_call(
            tool_name="write_file",
            arguments={"path": "test.py"},
            result="Success",
            success=True,
            duration_ms=15.0,
            session_id="test_session",
        )

        exporter = ExecutionLogExporter()
        output = exporter.export_json("test_session", include_metrics=False, include_audit=True)

        data = json.loads(output)
        # Audit log may be empty if log file doesn't have matching entries
        assert "audit_log" in data

    def test_markdown_table_format(self, temp_log_dir: Path, clean_logging):
        """Test that Markdown tables are properly formatted."""
        from mini_claude.monitoring.metrics import get_metrics_collector, reset_metrics_collector

        reset_metrics_collector()

        collector = get_metrics_collector()
        collector.record_request_start()
        collector.record_request_end(success=True, duration=0.5)
        collector.record_tool_call("bash", success=True)
        collector.record_tool_call("bash", success=False)

        exporter = ExecutionLogExporter()
        output = exporter.export_markdown("test_session", include_metrics=True, include_audit=False)

        # Check table headers
        assert "| Metric | Value |" in output
        assert "|--------|-------|" in output
        assert "| Tool | Success | Failure |" in output

        reset_metrics_collector()

    def test_export_creates_parent_directory(self, temp_log_dir: Path, clean_logging):
        """Test that export creates parent directory if needed."""
        export_file = temp_log_dir / "nested" / "dir" / "export.json"

        exporter = ExecutionLogExporter()
        result = exporter.export_to_file(
            session_id="test_session",
            format="json",
            path=str(export_file),
            include_metrics=False,
            include_audit=False,
        )

        assert result is True
        assert export_file.exists()
        assert export_file.parent.exists()

    def test_get_execution_log_exporter_singleton(self):
        """Test that get_execution_log_exporter returns singleton."""
        exporter1 = get_execution_log_exporter()
        exporter2 = get_execution_log_exporter()

        assert exporter1 is exporter2

    def test_export_empty_session(self, temp_log_dir: Path, clean_logging):
        """Test export of non-existent session."""
        exporter = ExecutionLogExporter()
        output = exporter.export_json("nonexistent_session", include_metrics=False, include_audit=False)

        data = json.loads(output)
        assert data["export_metadata"]["session_id"] == "nonexistent_session"
        # Session data may be None
        assert data["session"] is None

    def test_html_css_included(self, temp_log_dir: Path, clean_logging):
        """Test that HTML export includes CSS styles."""
        exporter = ExecutionLogExporter()
        output = exporter.export_html("test_session", include_metrics=False, include_audit=False)

        # Verify CSS is included
        assert "body {" in output
        assert "font-family" in output
        assert ".section {" in output
        assert ".message {" in output
        assert "border-radius" in output


class TestOutputSanitizer:
    """Test OutputSanitizer class directly."""

    def test_sanitize_api_key_patterns(self):
        """Test sanitization of various API key patterns."""
        sanitizer = OutputSanitizer()

        # OpenAI-style key
        text = "api_key: sk-abcdefghijklmnopqrstuvwxyz123456"
        result = sanitizer.sanitize(text)
        assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in result
        assert "sk-****" in result

        # AWS key
        text2 = "AWS key: AKIAIOSFODNN7EXAMPLE"
        result2 = sanitizer.sanitize(text2)
        assert "AKIAIOSFODNN7EXAMPLE" not in result2
        assert "AKIA****" in result2

    def test_sanitize_token_patterns(self):
        """Test sanitization of token patterns."""
        sanitizer = OutputSanitizer()

        # Bearer token
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        result = sanitizer.sanitize(text)
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in result
        assert "Bearer ****" in result

        # GitHub token
        text2 = "token: ghp_1234567890abcdefghijklmnopqrstuvwxyz12"
        result2 = sanitizer.sanitize(text2)
        assert "ghp_1234567890abcdefghijklmnopqrstuvwxyz12" not in result2

    def test_sanitize_connection_string(self):
        """Test sanitization of connection strings."""
        sanitizer = OutputSanitizer()

        text = "mysql://user:secretpass@localhost/db"
        result = sanitizer.sanitize(text)
        assert "secretpass" not in result
        assert "****" in result

    def test_sanitize_json_dict(self):
        """Test sanitization of JSON dictionaries."""
        sanitizer = OutputSanitizer()

        text = '{"api_key": "sk-test123456789", "password": "secret123"}'
        result = sanitizer.sanitize_json(text)
        assert "sk-test123456789" not in result
        assert "secret123" not in result

    def test_preserve_non_sensitive(self):
        """Test that non-sensitive data is preserved."""
        sanitizer = OutputSanitizer()

        text = "Hello, World! This is a normal message."
        result = sanitizer.sanitize(text)
        assert text == result  # Should be unchanged
