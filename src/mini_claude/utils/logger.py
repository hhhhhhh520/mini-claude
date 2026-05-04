"""Structured logging system for Mini Claude Code.

Provides:
- StructuredLogger: JSON-formatted logging with level control
- AuditLogger: Tool call auditing
- Log rotation and file persistence
- Output sanitization for sensitive data
"""

import logging
import json
import re
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Import sensitive patterns from safety module
from mini_claude.utils.safety import SENSITIVE_PATTERNS


class OutputSanitizer:
    """Sanitize sensitive data in log output."""

    def __init__(self):
        # Compile patterns from safety module for efficiency
        self._patterns: List[Tuple[re.Pattern, str, str]] = []
        for pattern, category, severity in SENSITIVE_PATTERNS:
            try:
                compiled = re.compile(pattern, re.IGNORECASE)
                self._patterns.append((compiled, category, severity))
            except re.error:
                pass  # Skip invalid patterns

    def sanitize(self, text: str) -> str:
        """Sanitize sensitive data in text.

        Args:
            text: The text to sanitize.

        Returns:
            Text with sensitive data replaced by **** markers.
        """
        if not text:
            return text

        result = text
        for pattern, category, _ in self._patterns:
            result = self._apply_sanitization(result, pattern, category)

        return result

    def _apply_sanitization(self, text: str, pattern: re.Pattern, category: str) -> str:
        """Apply sanitization for a specific pattern.

        Args:
            text: Text to sanitize.
            pattern: Compiled regex pattern.
            category: Category of sensitive data.

        Returns:
            Sanitized text.
        """
        def replace_match(match: re.Match) -> str:
            matched_text = match.group(0)

            if category == "api_key":
                # Preserve prefix like "sk-", "sk-proj-", "AKIA"
                return self._sanitize_api_key(matched_text)
            elif category == "token":
                # Preserve "Bearer ", "ghp_", etc.
                return self._sanitize_token(matched_text)
            elif category == "password":
                # Preserve key name, sanitize value
                return self._sanitize_key_value(matched_text)
            elif category == "connection_string":
                # Preserve protocol and host, sanitize password
                return self._sanitize_connection_string(matched_text)
            else:
                # Generic sanitization
                return "****"

        return pattern.sub(replace_match, text)

    def _sanitize_api_key(self, matched: str) -> str:
        """Sanitize API key while preserving prefix.

        Examples:
            sk-abc123 -> sk-****
            AKIAIOSFODNN7EXAMPLE -> AKIA****
        """
        # Find the prefix (sk-, sk-proj-, AKIA, etc.)
        prefix_match = re.match(r'^(sk-proj-|sk-|AKIA|x-api-key\s*[:=]\s*["\']?|api[_-]?key\s*=\s*["\']?)', matched, re.IGNORECASE)
        if prefix_match:
            prefix = prefix_match.group(1)
            # Clean up trailing quotes/whitespace in prefix
            prefix_clean = re.sub(r'["\']$', '', prefix)
            return f"{prefix_clean}****"
        return "****"

    def _sanitize_token(self, matched: str) -> str:
        """Sanitize token while preserving type prefix.

        Examples:
            Bearer abc123 -> Bearer ****
            ghp_xxx -> ghp_****
            token=xxx -> token=****
        """
        # Handle Bearer/JWT prefix
        bearer_match = re.match(r'^(bearer\s+|jwt\s+)', matched, re.IGNORECASE)
        if bearer_match:
            return f"{bearer_match.group(1).rstrip()} ****"

        # Handle GitHub tokens (ghp_, gho_, ghr_, etc.)
        gh_match = re.match(r'^(gh[porsu]_)', matched, re.IGNORECASE)
        if gh_match:
            return f"{gh_match.group(1)}****"

        # Handle key=value format
        return self._sanitize_key_value(matched)

    def _sanitize_key_value(self, matched: str) -> str:
        """Sanitize key=value format.

        Examples:
            password=xxx -> password=****
            token: xxx -> token: ****
        """
        # Match key=value or key: value or key = value
        kv_match = re.match(r'^(\w+\s*[=:]\s*["\']?)', matched, re.IGNORECASE)
        if kv_match:
            prefix = kv_match.group(1)
            # Remove trailing quote if present
            prefix_clean = re.sub(r'["\']$', '', prefix)
            return f"{prefix_clean}****"
        return "****"

    def _sanitize_connection_string(self, matched: str) -> str:
        """Sanitize connection string password.

        Examples:
            mysql://user:pass@host -> mysql://user:****@host
            postgresql://user:pass@host/db -> postgresql://user:****@host/db
        """
        # Pattern: protocol://user:password@host
        conn_match = re.match(r'^([a-z]+://[^:]+:)([^@]+)(@.+)', matched, re.IGNORECASE)
        if conn_match:
            protocol_user = conn_match.group(1)
            host_rest = conn_match.group(3)
            return f"{protocol_user}****{host_rest}"
        return "****"

    def sanitize_json(self, text: str) -> str:
        """Sanitize sensitive data in JSON content.

        Handles both valid JSON and JSON-like strings embedded in text.

        Args:
            text: Text that may contain JSON.

        Returns:
            Text with sensitive data in JSON sanitized.
        """
        if not text:
            return text

        # First apply standard text sanitization
        result = self.sanitize(text)

        # Then try to find and sanitize JSON structures
        result = self._sanitize_json_structures(result)

        return result

    def _sanitize_json_structures(self, text: str) -> str:
        """Find and sanitize JSON structures in text.

        Args:
            text: Text potentially containing JSON.

        Returns:
            Text with JSON structures sanitized.
        """
        # Try to parse entire text as JSON
        try:
            data = json.loads(text)
            sanitized_data = self._sanitize_json_value(data)
            return json.dumps(sanitized_data, ensure_ascii=False)
        except (json.JSONDecodeError, TypeError):
            pass

        # Look for JSON objects embedded in text
        json_pattern = re.compile(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}')

        def sanitize_embedded(match: re.Match) -> str:
            try:
                data = json.loads(match.group(0))
                sanitized_data = self._sanitize_json_value(data)
                return json.dumps(sanitized_data, ensure_ascii=False)
            except (json.JSONDecodeError, TypeError):
                return match.group(0)

        return json_pattern.sub(sanitize_embedded, text)

    def _sanitize_json_value(self, value: Any) -> Any:
        """Recursively sanitize JSON values.

        Args:
            value: JSON value (dict, list, str, or primitive).

        Returns:
            Sanitized value.
        """
        if isinstance(value, dict):
            result = {}
            for k, v in value.items():
                # Check if key is sensitive
                if k.lower() in AuditLogger.SENSITIVE_KEYS:
                    result[k] = "****"
                else:
                    result[k] = self._sanitize_json_value(v)
            return result
        elif isinstance(value, list):
            return [self._sanitize_json_value(item) for item in value]
        elif isinstance(value, str):
            # Apply pattern-based sanitization to string values
            return self.sanitize(value)
        else:
            return value


# Global sanitizer instance
_sanitizer: Optional[OutputSanitizer] = None


def get_sanitizer() -> OutputSanitizer:
    """Get or create the global output sanitizer.

    This function provides backward compatibility with existing code.
    New code should prefer ApplicationContext.output_sanitizer.
    """
    global _sanitizer
    if _sanitizer is None:
        # Try to use ApplicationContext first
        try:
            from mini_claude.context import get_context
            ctx = get_context()
            if ctx._output_sanitizer.is_initialized():
                _sanitizer = ctx.output_sanitizer
            else:
                _sanitizer = OutputSanitizer()
                ctx.output_sanitizer = _sanitizer
        except ImportError:
            _sanitizer = OutputSanitizer()
    return _sanitizer


def reset_sanitizer() -> None:
    """Reset the global sanitizer (for testing)."""
    global _sanitizer
    _sanitizer = None
    # Also reset in context
    try:
        from mini_claude.context import get_context
        ctx = get_context()
        ctx._output_sanitizer.reset()
    except ImportError:
        pass


class StructuredFormatter(logging.Formatter):
    """JSON formatter for structured logging with output sanitization."""

    def __init__(self, sanitize_output: bool = True):
        """Initialize formatter.

        Args:
            sanitize_output: Whether to sanitize sensitive data in output.
        """
        super().__init__()
        self._sanitize_output = sanitize_output
        self._sanitizer = get_sanitizer() if sanitize_output else None

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add extra data if present
        if hasattr(record, "extra_data"):
            log_entry["data"] = record.extra_data

        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        output = json.dumps(log_entry, ensure_ascii=False)

        # Sanitize output if enabled
        if self._sanitize_output and self._sanitizer:
            output = self._sanitizer.sanitize_json(output)

        return output


class ColoredFormatter(logging.Formatter):
    """Colored formatter for console output."""

    COLORS = {
        "DEBUG": "\033[36m",     # Cyan
        "INFO": "\033[32m",      # Green
        "WARNING": "\033[33m",   # Yellow
        "ERROR": "\033[31m",     # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, "")
        record.levelname = f"{color}{record.levelname}{self.RESET}"
        return super().format(record)


class StructuredLogger:
    """Structured logger wrapper with extra data support."""

    def __init__(self, name: str):
        self._logger = logging.getLogger(name)

    def debug(self, message: str, **kwargs) -> None:
        """Log debug message."""
        self._log(logging.DEBUG, message, **kwargs)

    def info(self, message: str, **kwargs) -> None:
        """Log info message."""
        self._log(logging.INFO, message, **kwargs)

    def warning(self, message: str, **kwargs) -> None:
        """Log warning message."""
        self._log(logging.WARNING, message, **kwargs)

    def error(self, message: str, exc_info: bool = False, **kwargs) -> None:
        """Log error message."""
        extra = {"extra_data": kwargs} if kwargs else None
        self._logger.error(message, exc_info=exc_info, extra=extra)

    def critical(self, message: str, **kwargs) -> None:
        """Log critical message."""
        self._log(logging.CRITICAL, message, **kwargs)

    def _log(self, level: int, message: str, **kwargs) -> None:
        extra = {"extra_data": kwargs} if kwargs else None
        self._logger.log(level, message, extra=extra)

    def is_debug_enabled(self) -> bool:
        """Check if debug level is enabled."""
        return self._logger.isEnabledFor(logging.DEBUG)


class AuditLogger:
    """Audit logger for tool call tracking with sensitive data sanitization."""

    # Extended sensitive keys for argument sanitization
    SENSITIVE_KEYS = {
        "password", "passwd", "pwd",
        "api_key", "apikey", "api_token",
        "token", "access_token", "refresh_token", "auth_token",
        "secret", "secret_key", "secret_token",
        "credential", "credentials",
        "private_key", "privatekey",
        "authorization", "auth",
        "session_key", "session_token",
        "api_secret", "apisecret",
        "access_key", "secret_access_key",
    }

    def __init__(
        self,
        log_path: str,
        max_bytes: int = 10 * 1024 * 1024,
        backup_count: int = 5,
        sanitize_output: bool = True,
    ):
        self._logger = logging.getLogger("audit")
        self._logger.setLevel(logging.INFO)
        self._logger.propagate = False  # Don't propagate to root logger

        # Create log directory
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)

        # Dedicated file handler with sanitized output
        handler = RotatingFileHandler(
            log_path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        handler.setFormatter(StructuredFormatter(sanitize_output=sanitize_output))
        self._logger.addHandler(handler)

        # Use shared sanitizer for result sanitization
        self._sanitizer = get_sanitizer() if sanitize_output else None

    def log_tool_call(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        result: Optional[str],
        success: bool,
        duration_ms: float,
        agent_id: str = "main",
        session_id: str = "default",
    ) -> None:
        """Log a tool call for auditing."""
        # Sanitize result if sanitizer is available
        sanitized_result = result
        if self._sanitizer and result:
            sanitized_result = self._sanitizer.sanitize_json(result)

        self._logger.info(
            f"Tool call: {tool_name}",
            extra={
                "extra_data": {
                    "event": "tool_call",
                    "tool_name": tool_name,
                    "arguments": self._sanitize_args(arguments),
                    "result": self._truncate_result(sanitized_result),
                    "success": success,
                    "duration_ms": round(duration_ms, 2),
                    "agent_id": agent_id,
                    "session_id": session_id,
                }
            }
        )

    def log_agent_spawn(
        self,
        agent_id: str,
        task: str,
        model: str,
    ) -> None:
        """Log sub-agent spawn."""
        self._logger.info(
            f"Agent spawn: {agent_id}",
            extra={
                "extra_data": {
                    "event": "agent_spawn",
                    "agent_id": agent_id,
                    "task": task[:200],  # Truncate long tasks
                    "model": model,
                }
            }
        )

    def log_agent_complete(
        self,
        agent_id: str,
        success: bool,
        duration_ms: float,
        result_length: int,
    ) -> None:
        """Log sub-agent completion."""
        self._logger.info(
            f"Agent complete: {agent_id}",
            extra={
                "extra_data": {
                    "event": "agent_complete",
                    "agent_id": agent_id,
                    "success": success,
                    "duration_ms": round(duration_ms, 2),
                    "result_length": result_length,
                }
            }
        )

    def _sanitize_args(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Redact sensitive arguments recursively.

        Args:
            args: Dictionary of arguments to sanitize.

        Returns:
            Sanitized dictionary with sensitive values redacted.
        """
        return self._sanitize_dict(args)

    def _sanitize_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively sanitize dictionary values.

        Args:
            data: Dictionary to sanitize.

        Returns:
            Sanitized dictionary.
        """
        result = {}
        for k, v in data.items():
            # Check if key is sensitive
            if k.lower() in self.SENSITIVE_KEYS:
                result[k] = "****"
            elif isinstance(v, dict):
                # Recursively sanitize nested dictionaries
                result[k] = self._sanitize_dict(v)
            elif isinstance(v, list):
                # Sanitize list items
                result[k] = self._sanitize_list(v)
            elif isinstance(v, str):
                # Check for sensitive patterns in string values
                if self._sanitizer:
                    result[k] = self._sanitizer.sanitize(v)
                    # Truncate long strings
                    if len(result[k]) > 200:
                        result[k] = result[k][:200] + "...[truncated]"
                else:
                    # No sanitizer, just truncate
                    if len(v) > 200:
                        result[k] = v[:200] + "...[truncated]"
                    else:
                        result[k] = v
            else:
                result[k] = v
        return result

    def _sanitize_list(self, data: List[Any]) -> List[Any]:
        """Recursively sanitize list items.

        Args:
            data: List to sanitize.

        Returns:
            Sanitized list.
        """
        result = []
        for item in data:
            if isinstance(item, dict):
                result.append(self._sanitize_dict(item))
            elif isinstance(item, list):
                result.append(self._sanitize_list(item))
            elif isinstance(item, str) and self._sanitizer:
                result.append(self._sanitizer.sanitize(item))
            else:
                result.append(item)
        return result

    def _truncate_result(self, result: Optional[str]) -> Optional[str]:
        """Truncate result for logging."""
        if result is None:
            return None
        if len(result) > 500:
            return result[:500] + "...[truncated]"
        return result


# Global logger cache
_loggers: Dict[str, StructuredLogger] = {}
_audit_logger: Optional[AuditLogger] = None
_logging_initialized: bool = False


def get_logger(name: str) -> StructuredLogger:
    """Get or create a structured logger."""
    if name not in _loggers:
        _loggers[name] = StructuredLogger(name)
    return _loggers[name]


def get_audit_logger() -> Optional[AuditLogger]:
    """Get the audit logger (may be None if not initialized)."""
    return _audit_logger


def reset_logging():
    """Reset logging state for testing."""
    global _audit_logger, _logging_initialized, _loggers

    # Clear all handlers from mini_claude logger
    root_logger = logging.getLogger("mini_claude")
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Clear audit logger handlers
    if _audit_logger:
        audit_logger = logging.getLogger("audit")
        for handler in audit_logger.handlers[:]:
            audit_logger.removeHandler(handler)

    _audit_logger = None
    _logging_initialized = False
    _loggers.clear()


def init_logging(
    log_level: str = "INFO",
    log_to_console: bool = True,
    log_to_file: bool = True,
    log_to_json: bool = False,
    log_file_path: str = "logs/mini_claude.log",
    log_json_path: str = "logs/mini_claude.json",
    log_audit_path: str = "logs/audit.log",
    log_max_bytes: int = 10 * 1024 * 1024,
    log_backup_count: int = 5,
    audit_enabled: bool = True,
    log_format: str = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    log_date_format: str = "%H:%M:%S",
    force: bool = False,
) -> logging.Logger:
    """Initialize the logging system.

    Args:
        log_level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_to_console: Enable console output
        log_to_file: Enable file output
        log_to_json: Enable JSON file output
        log_file_path: Path to log file
        log_json_path: Path to JSON log file
        log_audit_path: Path to audit log file
        log_max_bytes: Max size per log file
        log_backup_count: Number of backup files
        audit_enabled: Enable audit logging
        log_format: Log format string
        log_date_format: Date format string

    Returns:
        Root logger for mini_claude
    """
    global _audit_logger, _logging_initialized

    if _logging_initialized and not force:
        return logging.getLogger("mini_claude")

    # Reset if force is True
    if force:
        reset_logging()

    # Create log directory
    if log_to_file or log_to_json or audit_enabled:
        log_dir = Path(log_file_path).parent
        log_dir.mkdir(parents=True, exist_ok=True)

    # Root logger for mini_claude
    root_logger = logging.getLogger("mini_claude")
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    root_logger.propagate = False  # Don't propagate to root logger

    # Console handler
    if log_to_console:
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setLevel(logging.DEBUG)
        console_handler.setFormatter(ColoredFormatter(
            fmt=log_format,
            datefmt=log_date_format,
        ))
        root_logger.addHandler(console_handler)

    # File handler (human-readable)
    if log_to_file:
        file_handler = RotatingFileHandler(
            log_file_path,
            maxBytes=log_max_bytes,
            backupCount=log_backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(
            fmt=log_format,
            datefmt=log_date_format,
        ))
        root_logger.addHandler(file_handler)

    # JSON file handler (machine-readable)
    if log_to_json:
        json_handler = RotatingFileHandler(
            log_json_path,
            maxBytes=log_max_bytes,
            backupCount=log_backup_count,
            encoding="utf-8",
        )
        json_handler.setLevel(logging.DEBUG)
        json_handler.setFormatter(StructuredFormatter())
        root_logger.addHandler(json_handler)

    # Audit logger
    if audit_enabled:
        _audit_logger = AuditLogger(
            log_path=log_audit_path,
            max_bytes=log_max_bytes,
            backup_count=log_backup_count,
        )

    _logging_initialized = True
    return root_logger


def init_logging_from_settings() -> logging.Logger:
    """Initialize logging from settings."""
    try:
        from ..config.settings import settings
        return init_logging(
            log_level=getattr(settings, "log_level", "INFO"),
            log_to_console=getattr(settings, "log_to_console", True),
            log_to_file=getattr(settings, "log_to_file", True),
            log_to_json=getattr(settings, "log_to_json", False),
            log_file_path=getattr(settings, "log_file_path", "logs/mini_claude.log"),
            log_json_path=getattr(settings, "log_json_path", "logs/mini_claude.json"),
            log_audit_path=getattr(settings, "log_audit_path", "logs/audit.log"),
            log_max_bytes=getattr(settings, "log_max_bytes", 10 * 1024 * 1024),
            log_backup_count=getattr(settings, "log_backup_count", 5),
            audit_enabled=getattr(settings, "audit_enabled", True),
        )
    except ImportError:
        # Fallback if settings not available
        return init_logging()


# Convenience function for backward compatibility
def safe_print(msg: str) -> None:
    """Backward-compatible safe_print that uses logging.

    Parses old format: "[DEBUG] function: message"
    """
    logger = get_logger("mini_claude.legacy")

    if msg.startswith("[DEBUG]"):
        logger.debug(msg[7:].strip())
    elif msg.startswith("[WARN]"):
        logger.warning(msg[6:].strip())
    elif msg.startswith("[ERROR]"):
        logger.error(msg[7:].strip())
    elif msg.startswith("[INFO]"):
        logger.info(msg[6:].strip())
    else:
        logger.info(msg)


class ExecutionLogExporter:
    """Export execution logs in various formats.

    Supports JSON, Markdown, and HTML export formats.
    Automatically sanitizes sensitive data (API keys, passwords, etc.).

    Example:
        exporter = ExecutionLogExporter()

        # Export to JSON
        json_output = exporter.export_json(session_id="default")

        # Export to Markdown
        md_output = exporter.export_markdown(session_id="default")

        # Export to file
        exporter.export_to_file(session_id="default", format="json", path="log.json")
    """

    def __init__(self, sanitize_output: bool = True):
        """Initialize the exporter.

        Args:
            sanitize_output: Whether to sanitize sensitive data in output.
        """
        self._sanitizer = get_sanitizer() if sanitize_output else None

    def export_json(
        self,
        session_id: str,
        include_metrics: bool = True,
        include_audit: bool = True,
    ) -> str:
        """Export session execution log as formatted JSON.

        Args:
            session_id: Session ID to export.
            include_metrics: Include Prometheus metrics summary.
            include_audit: Include audit log entries.

        Returns:
            Formatted JSON string.
        """
        import json
        from datetime import datetime

        # Build export data
        export_data = {
            "export_metadata": {
                "exported_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "exporter_version": "1.0.0",
                "session_id": session_id,
            },
            "session": self._get_session_data(session_id),
        }

        # Add metrics if requested
        if include_metrics:
            export_data["metrics"] = self._get_metrics_data()

        # Add audit log if requested
        if include_audit:
            export_data["audit_log"] = self._get_audit_data(session_id)

        # Convert to JSON
        output = json.dumps(export_data, ensure_ascii=False, indent=2)

        # Sanitize if enabled
        if self._sanitizer:
            output = self._sanitizer.sanitize_json(output)

        return output

    def export_markdown(
        self,
        session_id: str,
        include_metrics: bool = True,
        include_audit: bool = True,
    ) -> str:
        """Export session execution log as Markdown.

        Args:
            session_id: Session ID to export.
            include_metrics: Include Prometheus metrics summary.
            include_audit: Include audit log entries.

        Returns:
            Markdown formatted string.
        """
        from datetime import datetime

        lines = []

        # Header
        lines.append("# Execution Log Export")
        lines.append(f"\n**Session ID**: `{session_id}`")
        lines.append(f"**Exported At**: {datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')}")
        lines.append("")

        # Session metadata
        session_data = self._get_session_data(session_id)
        if session_data:
            lines.append("## Session Metadata")
            lines.append("")
            lines.append("| Field | Value |")
            lines.append("|-------|-------|")
            if session_data.get("created_at"):
                lines.append(f"| Created At | {session_data['created_at']} |")
            if session_data.get("updated_at"):
                lines.append(f"| Updated At | {session_data['updated_at']} |")
            lines.append(f"| Message Count | {len(session_data.get('messages', []))} |")
            if session_data.get("token_count"):
                lines.append(f"| Token Count | {session_data['token_count']} |")
            if session_data.get("summary"):
                lines.append(f"| Summary | {session_data['summary'][:100]}... |")
            lines.append("")

            # Message history
            messages = session_data.get("messages", [])
            if messages:
                lines.append("## Message History")
                lines.append("")
                for i, msg in enumerate(messages, 1):
                    role = msg.get("role", "unknown")
                    content = msg.get("content", "")
                    # Truncate long content
                    if len(content) > 200:
                        content = content[:200] + "...[truncated]"
                    # Sanitize if enabled
                    if self._sanitizer:
                        content = self._sanitizer.sanitize(content)
                    lines.append(f"### {i}. {role.title()}")
                    lines.append("")
                    lines.append(f"```\n{content}\n```")
                    lines.append("")

        # Metrics
        if include_metrics:
            metrics = self._get_metrics_data()
            if metrics:
                lines.append("## Performance Metrics")
                lines.append("")
                lines.append("### Request Statistics")
                lines.append("")
                lines.append("| Metric | Value |")
                lines.append("|--------|-------|")
                req = metrics.get("requests", {})
                lines.append(f"| Total Requests | {req.get('total', 0)} |")
                lines.append(f"| Successful | {req.get('success', 0)} |")
                lines.append(f"| Failed | {req.get('failed', 0)} |")
                lines.append(f"| Success Rate | {req.get('success_rate', 0):.1f}% |")
                lines.append("")

                lines.append("### Token Usage")
                lines.append("")
                lines.append("| Type | Count |")
                lines.append("|------|-------|")
                tokens = metrics.get("tokens", {})
                lines.append(f"| Input | {tokens.get('input', 0)} |")
                lines.append(f"| Output | {tokens.get('output', 0)} |")
                lines.append(f"| Total | {tokens.get('total', 0)} |")
                lines.append("")

                lines.append("### Tool Calls")
                lines.append("")
                tools = metrics.get("tools", {})
                all_tools = set(tools.get("success", {}).keys()) | set(tools.get("failure", {}).keys())
                if all_tools:
                    lines.append("| Tool | Success | Failure |")
                    lines.append("|------|---------|---------|")
                    for tool_name in sorted(all_tools):
                        success = tools.get("success", {}).get(tool_name, 0)
                        failure = tools.get("failure", {}).get(tool_name, 0)
                        lines.append(f"| {tool_name} | {success} | {failure} |")
                    lines.append("")

                perf = metrics.get("performance", {})
                if perf:
                    lines.append(f"**Average Duration**: {perf.get('avg_duration_seconds', 0):.3f}s")
                    lines.append(f"**Total Duration**: {perf.get('total_duration_seconds', 0):.3f}s")
                    lines.append("")

        # Audit log
        if include_audit:
            audit_entries = self._get_audit_data(session_id)
            if audit_entries:
                lines.append("## Audit Log")
                lines.append("")
                lines.append("| Timestamp | Event | Details |")
                lines.append("|-----------|-------|---------|")
                for entry in audit_entries[:50]:  # Limit to 50 entries
                    timestamp = entry.get("timestamp", "N/A")
                    event = entry.get("data", {}).get("event", "unknown")
                    # Build details string
                    details_parts = []
                    data = entry.get("data", {})
                    if "tool_name" in data:
                        details_parts.append(f"tool: {data['tool_name']}")
                    if "success" in data:
                        details_parts.append(f"success: {data['success']}")
                    if "duration_ms" in data:
                        details_parts.append(f"duration: {data['duration_ms']}ms")
                    details = ", ".join(details_parts) or "N/A"
                    # Sanitize details if enabled
                    if self._sanitizer:
                        details = self._sanitizer.sanitize(details)
                    lines.append(f"| {timestamp} | {event} | {details} |")
                lines.append("")

        return "\n".join(lines)

    def export_html(
        self,
        session_id: str,
        include_metrics: bool = True,
        include_audit: bool = True,
    ) -> str:
        """Export session execution log as HTML.

        Args:
            session_id: Session ID to export.
            include_metrics: Include Prometheus metrics summary.
            include_audit: Include audit log entries.

        Returns:
            HTML formatted string with embedded CSS.
        """
        from datetime import datetime

        # Get data
        session_data = self._get_session_data(session_id)
        metrics = self._get_metrics_data() if include_metrics else None
        audit_entries = self._get_audit_data(session_id) if include_audit else []

        lines = []

        # HTML header
        lines.append("<!DOCTYPE html>")
        lines.append("<html lang='en'>")
        lines.append("<head>")
        lines.append("<meta charset='UTF-8'>")
        lines.append("<title>Execution Log - " + session_id + "</title>")
        lines.append("<style>")
        lines.append(self._get_html_css())
        lines.append("</style>")
        lines.append("</head>")
        lines.append("<body>")

        # Header
        lines.append("<div class='header'>")
        lines.append("<h1>Execution Log Export</h1>")
        lines.append(f"<p>Session: <code>{session_id}</code></p>")
        lines.append(f"<p>Exported: {datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')}</p>")
        lines.append("</div>")

        # Session info
        if session_data:
            lines.append("<div class='section'>")
            lines.append("<h2>Session Metadata</h2>")
            lines.append("<table>")
            lines.append("<tr><th>Field</th><th>Value</th></tr>")
            if session_data.get("created_at"):
                lines.append(f"<tr><td>Created At</td><td>{session_data['created_at']}</td></tr>")
            if session_data.get("updated_at"):
                lines.append(f"<tr><td>Updated At</td><td>{session_data['updated_at']}</td></tr>")
            lines.append(f"<tr><td>Message Count</td><td>{len(session_data.get('messages', []))}</td></tr>")
            if session_data.get("token_count"):
                lines.append(f"<tr><td>Token Count</td><td>{session_data['token_count']}</td></tr>")
            lines.append("</table>")
            lines.append("</div>")

            # Messages
            messages = session_data.get("messages", [])
            if messages:
                lines.append("<div class='section'>")
                lines.append("<h2>Message History</h2>")
                for i, msg in enumerate(messages, 1):
                    role = msg.get("role", "unknown")
                    content = msg.get("content", "")
                    if self._sanitizer:
                        content = self._sanitizer.sanitize(content)
                    # Escape HTML
                    content = content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    role_class = "user" if role == "user" else "assistant"
                    lines.append(f"<div class='message {role_class}'>")
                    lines.append(f"<h3>{i}. {role.title()}</h3>")
                    lines.append(f"<pre>{content}</pre>")
                    lines.append("</div>")
                lines.append("</div>")

        # Metrics
        if metrics:
            lines.append("<div class='section'>")
            lines.append("<h2>Performance Metrics</h2>")

            req = metrics.get("requests", {})
            lines.append("<h3>Request Statistics</h3>")
            lines.append("<table>")
            lines.append("<tr><th>Metric</th><th>Value</th></tr>")
            lines.append(f"<tr><td>Total Requests</td><td>{req.get('total', 0)}</td></tr>")
            lines.append(f"<tr><td>Successful</td><td>{req.get('success', 0)}</td></tr>")
            lines.append(f"<tr><td>Failed</td><td>{req.get('failed', 0)}</td></tr>")
            lines.append(f"<tr><td>Success Rate</td><td>{req.get('success_rate', 0):.1f}%</td></tr>")
            lines.append("</table>")

            tokens = metrics.get("tokens", {})
            lines.append("<h3>Token Usage</h3>")
            lines.append("<table>")
            lines.append("<tr><th>Type</th><th>Count</th></tr>")
            lines.append(f"<tr><td>Input</td><td>{tokens.get('input', 0)}</td></tr>")
            lines.append(f"<tr><td>Output</td><td>{tokens.get('output', 0)}</td></tr>")
            lines.append(f"<tr><td>Total</td><td>{tokens.get('total', 0)}</td></tr>")
            lines.append("</table>")
            lines.append("</div>")

        # Audit log
        if audit_entries:
            lines.append("<div class='section'>")
            lines.append("<h2>Audit Log</h2>")
            lines.append("<table>")
            lines.append("<tr><th>Timestamp</th><th>Event</th><th>Details</th></tr>")
            for entry in audit_entries[:50]:
                timestamp = entry.get("timestamp", "N/A")
                event = entry.get("data", {}).get("event", "unknown")
                data = entry.get("data", {})
                details_parts = []
                if "tool_name" in data:
                    details_parts.append(f"tool: {data['tool_name']}")
                if "success" in data:
                    details_parts.append(f"success: {data['success']}")
                details = ", ".join(details_parts) or "N/A"
                if self._sanitizer:
                    details = self._sanitizer.sanitize(details)
                details = details.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                lines.append(f"<tr><td>{timestamp}</td><td>{event}</td><td>{details}</td></tr>")
            lines.append("</table>")
            lines.append("</div>")

        lines.append("</body>")
        lines.append("</html>")

        return "\n".join(lines)

    def export_to_file(
        self,
        session_id: str,
        format: str,
        path: str,
        include_metrics: bool = True,
        include_audit: bool = True,
    ) -> bool:
        """Export session execution log to a file.

        Args:
            session_id: Session ID to export.
            format: Export format ('json', 'markdown', 'md', 'html').
            path: File path to write to.
            include_metrics: Include Prometheus metrics summary.
            include_audit: Include audit log entries.

        Returns:
            True if export succeeded, False otherwise.
        """
        format = format.lower()

        if format == "json":
            content = self.export_json(session_id, include_metrics, include_audit)
        elif format in ("markdown", "md"):
            content = self.export_markdown(session_id, include_metrics, include_audit)
        elif format == "html":
            content = self.export_html(session_id, include_metrics, include_audit)
        else:
            raise ValueError(f"Unsupported export format: {format}")

        # Write to file
        file_path = Path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")

        return True

    def _get_session_data(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session data from session manager.

        Args:
            session_id: Session ID to get.

        Returns:
            Session data dictionary or None if not found.
        """
        try:
            from .session import get_session_manager
            manager = get_session_manager()
            return manager.load_session_full(session_id)
        except Exception:
            return None

    def _get_metrics_data(self) -> Dict[str, Any]:
        """Get metrics summary from metrics collector.

        Returns:
            Metrics summary dictionary.
        """
        try:
            from ..monitoring.metrics import get_metrics_collector
            collector = get_metrics_collector()
            return collector.get_summary()
        except Exception:
            return {}

    def _get_audit_data(self, session_id: str) -> List[Dict[str, Any]]:
        """Get audit log entries for a session.

        Args:
            session_id: Session ID to filter by.

        Returns:
            List of audit log entries.
        """
        import json

        entries = []

        try:
            # Read audit log file
            from ..config.settings import settings
            audit_path = Path(getattr(settings, "log_audit_path", "logs/audit.log"))

            if not audit_path.exists():
                return entries

            with open(audit_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        # Filter by session_id if present
                        entry_session = entry.get("data", {}).get("session_id", "default")
                        if entry_session == session_id or session_id == "default":
                            entries.append(entry)
                    except json.JSONDecodeError:
                        continue

        except Exception:
            pass

        return entries

    def _get_html_css(self) -> str:
        """Get CSS styles for HTML export.

        Returns:
            CSS string.
        """
        return """
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                max-width: 1200px;
                margin: 0 auto;
                padding: 20px;
                background: #f5f5f5;
            }
            .header {
                background: #2c3e50;
                color: white;
                padding: 20px;
                border-radius: 8px;
                margin-bottom: 20px;
            }
            .header h1 { margin: 0; }
            .header p { margin: 5px 0; opacity: 0.8; }
            .section {
                background: white;
                padding: 20px;
                border-radius: 8px;
                margin-bottom: 20px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }
            .section h2 { margin-top: 0; color: #2c3e50; }
            .section h3 { color: #34495e; }
            table {
                width: 100%;
                border-collapse: collapse;
            }
            th, td {
                padding: 10px;
                text-align: left;
                border-bottom: 1px solid #eee;
            }
            th {
                background: #f8f9fa;
                font-weight: 600;
            }
            .message {
                background: #f8f9fa;
                padding: 15px;
                border-radius: 8px;
                margin-bottom: 15px;
            }
            .message.user { border-left: 4px solid #3498db; }
            .message.assistant { border-left: 4px solid #27ae60; }
            .message h3 { margin: 0 0 10px 0; font-size: 14px; }
            .message pre {
                margin: 0;
                white-space: pre-wrap;
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 13px;
                background: #fff;
                padding: 10px;
                border-radius: 4px;
                overflow-x: auto;
            }
            code {
                background: #eee;
                padding: 2px 6px;
                border-radius: 4px;
            }
        """


# Global exporter instance
_exporter: Optional[ExecutionLogExporter] = None


def get_execution_log_exporter(sanitize_output: bool = True) -> ExecutionLogExporter:
    """Get or create the global execution log exporter.

    This function provides backward compatibility with existing code.
    New code should prefer ApplicationContext.execution_log_exporter.

    Args:
        sanitize_output: Whether to sanitize sensitive data.

    Returns:
        ExecutionLogExporter instance.
    """
    global _exporter
    if _exporter is None:
        # Try to use ApplicationContext first
        try:
            from mini_claude.context import get_context
            ctx = get_context()
            if ctx._execution_log_exporter.is_initialized():
                _exporter = ctx.execution_log_exporter
            else:
                _exporter = ExecutionLogExporter(sanitize_output=sanitize_output)
                ctx.execution_log_exporter = _exporter
        except ImportError:
            _exporter = ExecutionLogExporter(sanitize_output=sanitize_output)
    return _exporter


def reset_execution_log_exporter() -> None:
    """Reset the global exporter (for testing)."""
    global _exporter
    _exporter = None
    # Also reset in context
    try:
        from mini_claude.context import get_context
        ctx = get_context()
        ctx._execution_log_exporter.reset()
    except ImportError:
        pass
