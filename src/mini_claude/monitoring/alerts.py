"""Alert system for Mini Claude Code monitoring.

Provides comprehensive alerting capabilities:
- Multiple alert levels (INFO, WARNING, ERROR, CRITICAL)
- Configurable alert rules with conditions and thresholds
- Extensible alert handlers (log, console, webhook, email)
- Alert silence period to prevent duplicate alerts
- Multi-channel notification management

Usage:
    from mini_claude.monitoring.alerts import (
        AlertManager,
        AlertLevel,
        HighFailureRateRule,
        HighLatencyRule,
        EmailHandler,
        NotificationManager,
    )

    manager = AlertManager()
    manager.add_rule(HighFailureRateRule(threshold=0.2))
    manager.add_handler(LogHandler())

    # Check alerts
    alerts = manager.check_alerts(metrics)

    # Or use NotificationManager for multi-channel notifications
    notification_mgr = NotificationManager.from_settings()
    notification_mgr.notify(alert)
"""

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from mini_claude.config.settings import settings
from mini_claude.utils.logger import get_logger

logger = get_logger("mini_claude.monitoring.alerts")


class AlertLevel(str, Enum):
    """Alert severity levels."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

    def __str__(self) -> str:
        return self.value

    @property
    def emoji(self) -> str:
        """Get emoji representation for the level."""
        emojis = {
            AlertLevel.INFO: "ℹ️",  # information source
            AlertLevel.WARNING: "⚠️",  # warning sign
            AlertLevel.ERROR: "❌",  # cross mark
            AlertLevel.CRITICAL: "\U0001f6a8",  # police car light
        }
        return emojis.get(self, "")


@dataclass
class Alert:
    """Represents a single alert instance."""

    level: AlertLevel
    message: str
    timestamp: datetime = field(default_factory=datetime.now)
    metrics: Dict[str, Any] = field(default_factory=dict)
    threshold: Optional[float] = None
    rule_name: str = ""
    alert_id: str = ""
    acknowledged: bool = False
    silenced_until: Optional[datetime] = None

    def __post_init__(self):
        """Generate alert ID if not provided."""
        if not self.alert_id:
            content = f"{self.rule_name}:{self.message}:{self.timestamp.isoformat()}"
            self.alert_id = hashlib.md5(content.encode(), usedforsecurity=False).hexdigest()[:8]

    def to_dict(self) -> Dict[str, Any]:
        """Convert alert to dictionary representation."""
        return {
            "alert_id": self.alert_id,
            "level": self.level.value,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "metrics": self.metrics,
            "threshold": self.threshold,
            "rule_name": self.rule_name,
            "acknowledged": self.acknowledged,
            "silenced_until": self.silenced_until.isoformat() if self.silenced_until else None,
        }


@dataclass
class AlertRule:
    """Base class for alert rules.

    Attributes:
        name: Human-readable rule name
        condition: Function that takes metrics dict and returns True if alert should fire
        threshold: Threshold value for the condition
        duration: Optional duration in seconds that condition must be true before alerting
        level: Alert severity level
        silence_period: Period to silence after alert fires (default: 300 seconds / 5 minutes)
        description: Human-readable description of what this rule checks
    """

    name: str
    condition: Callable[[Dict[str, Any]], bool]
    threshold: float
    duration: Optional[float] = None  # Seconds condition must be true
    level: AlertLevel = AlertLevel.WARNING
    silence_period: float = 300.0  # 5 minutes default silence
    description: str = ""

    def __post_init__(self):
        """Set default description if not provided."""
        if not self.description:
            self.description = f"Alert when {self.name} exceeds {self.threshold}"

    def check(self, metrics: Dict[str, Any]) -> Optional[Alert]:
        """Check if the rule condition is met.

        Args:
            metrics: Dictionary of current metric values

        Returns:
            Alert if condition is met, None otherwise
        """
        try:
            if self.condition(metrics):
                return Alert(
                    level=self.level,
                    message=self._format_message(metrics),
                    metrics=metrics,
                    threshold=self.threshold,
                    rule_name=self.name,
                )
        except Exception as e:
            logger.error(
                "alert_rule_check_failed",
                rule=self.name,
                error=str(e),
            )
        return None

    def _format_message(self, metrics: Dict[str, Any]) -> str:
        """Format the alert message.

        Override in subclasses for custom formatting.
        """
        return f"{self.name} triggered (threshold: {self.threshold})"


# =============================================================================
# Built-in Alert Rules
# =============================================================================


class HighFailureRateRule(AlertRule):
    """Alert when request failure rate exceeds threshold.

    Default threshold: 20% (0.2)
    Level: ERROR
    """

    def __init__(
        self,
        threshold: float = 0.2,
        level: AlertLevel = AlertLevel.ERROR,
        silence_period: float = 300.0,
    ):
        """Initialize the high failure rate rule.

        Args:
            threshold: Failure rate threshold (0.0 to 1.0)
            level: Alert severity level
            silence_period: Silence period in seconds
        """
        super().__init__(
            name="high_failure_rate",
            condition=self._check_failure_rate,
            threshold=threshold,
            level=level,
            silence_period=silence_period,
            description=f"Alert when request failure rate exceeds {threshold * 100:.0f}%",
        )

    def _check_failure_rate(self, metrics: Dict[str, Any]) -> bool:
        """Check if failure rate exceeds threshold."""
        requests = metrics.get("requests", {})
        total = requests.get("total", 0)
        failed = requests.get("failed", 0)

        if total == 0:
            return False

        failure_rate = failed / total
        return failure_rate > self.threshold

    def _format_message(self, metrics: Dict[str, Any]) -> str:
        requests = metrics.get("requests", {})
        total = requests.get("total", 0)
        failed = requests.get("failed", 0)
        failure_rate = (failed / total * 100) if total > 0 else 0

        return (
            f"High failure rate detected: {failure_rate:.1f}% "
            f"({failed}/{total} requests failed). "
            f"Threshold: {self.threshold * 100:.0f}%"
        )


class HighLatencyRule(AlertRule):
    """Alert when average request latency exceeds threshold.

    Default threshold: 5.0 seconds
    Level: WARNING
    """

    def __init__(
        self,
        threshold: float = 5.0,
        level: AlertLevel = AlertLevel.WARNING,
        silence_period: float = 300.0,
    ):
        """Initialize the high latency rule.

        Args:
            threshold: Latency threshold in seconds
            level: Alert severity level
            silence_period: Silence period in seconds
        """
        super().__init__(
            name="high_latency",
            condition=self._check_latency,
            threshold=threshold,
            level=level,
            silence_period=silence_period,
            description=f"Alert when average latency exceeds {threshold}s",
        )

    def _check_latency(self, metrics: Dict[str, Any]) -> bool:
        """Check if average latency exceeds threshold."""
        performance = metrics.get("performance", {})
        avg_duration = performance.get("avg_duration_seconds", 0)

        return avg_duration > self.threshold

    def _format_message(self, metrics: Dict[str, Any]) -> str:
        performance = metrics.get("performance", {})
        avg_duration = performance.get("avg_duration_seconds", 0)

        return (
            f"High average latency detected: {avg_duration:.2f}s. "
            f"Threshold: {self.threshold}s"
        )


class TokenBudgetRule(AlertRule):
    """Alert when token usage exceeds budget threshold.

    Default threshold: 80% (0.8)
    Level: WARNING
    """

    def __init__(
        self,
        threshold: float = 0.8,
        level: AlertLevel = AlertLevel.WARNING,
        silence_period: float = 300.0,
    ):
        """Initialize the token budget rule.

        Args:
            threshold: Token usage threshold as fraction of budget (0.0 to 1.0)
            level: Alert severity level
            silence_period: Silence period in seconds
        """
        super().__init__(
            name="token_budget_exceeded",
            condition=self._check_token_budget,
            threshold=threshold,
            level=level,
            silence_period=silence_period,
            description=f"Alert when token usage exceeds {threshold * 100:.0f}% of budget",
        )

    def _check_token_budget(self, metrics: Dict[str, Any]) -> bool:
        """Check if token usage exceeds threshold."""
        token_usage = metrics.get("token_usage", {})
        usage_ratio = token_usage.get("usage_ratio", 0)

        return usage_ratio > self.threshold

    def _format_message(self, metrics: Dict[str, Any]) -> str:
        token_usage = metrics.get("token_usage", {})
        current_tokens = token_usage.get("current_tokens", 0)
        token_budget = token_usage.get("token_budget", 0)
        usage_ratio = token_usage.get("usage_ratio", 0)

        return (
            f"Token budget exceeded: {usage_ratio * 100:.1f}% used "
            f"({current_tokens}/{token_budget} tokens). "
            f"Threshold: {self.threshold * 100:.0f}%"
        )


class ToolFailureRule(AlertRule):
    """Alert when tool failure rate exceeds threshold.

    Default threshold: 30% (0.3)
    Level: WARNING
    """

    def __init__(
        self,
        threshold: float = 0.3,
        level: AlertLevel = AlertLevel.WARNING,
        silence_period: float = 300.0,
        min_calls: int = 5,
    ):
        """Initialize the tool failure rule.

        Args:
            threshold: Tool failure rate threshold (0.0 to 1.0)
            level: Alert severity level
            silence_period: Silence period in seconds
            min_calls: Minimum number of calls before checking (avoid false positives)
        """
        self.min_calls = min_calls
        super().__init__(
            name="tool_failure_rate",
            condition=self._check_tool_failure,
            threshold=threshold,
            level=level,
            silence_period=silence_period,
            description=f"Alert when tool failure rate exceeds {threshold * 100:.0f}%",
        )

    def _check_tool_failure(self, metrics: Dict[str, Any]) -> bool:
        """Check if any tool has high failure rate."""
        tools = metrics.get("tools", {})
        success = tools.get("success", {})
        failure = tools.get("failure", {})

        # Get all tools
        all_tools = set(success.keys()) | set(failure.keys())

        for tool_name in all_tools:
            success_count = success.get(tool_name, 0)
            failure_count = failure.get(tool_name, 0)
            total = success_count + failure_count

            if total < self.min_calls:
                continue

            failure_rate = failure_count / total if total > 0 else 0
            if failure_rate > self.threshold:
                return True

        return False

    def _format_message(self, metrics: Dict[str, Any]) -> str:
        tools = metrics.get("tools", {})
        success = tools.get("success", {})
        failure = tools.get("failure", {})

        failing_tools = []
        all_tools = set(success.keys()) | set(failure.keys())

        for tool_name in all_tools:
            success_count = success.get(tool_name, 0)
            failure_count = failure.get(tool_name, 0)
            total = success_count + failure_count

            if total < self.min_calls:
                continue

            failure_rate = failure_count / total if total > 0 else 0
            if failure_rate > self.threshold:
                failing_tools.append(
                    f"{tool_name}: {failure_rate * 100:.0f}% ({failure_count}/{total})"
                )

        tools_str = ", ".join(failing_tools) if failing_tools else "unknown"
        return (
            f"High tool failure rate detected: {tools_str}. "
            f"Threshold: {self.threshold * 100:.0f}%"
        )


# =============================================================================
# Alert Handlers
# =============================================================================


class AlertHandler:
    """Base class for alert handlers.

    Alert handlers process alerts when they are triggered.
    """

    def handle(self, alert: Alert) -> None:
        """Process an alert.

        Args:
            alert: The alert to process
        """
        raise NotImplementedError("Subclasses must implement handle()")


class LogHandler(AlertHandler):
    """Log alerts to the structured logger."""

    def handle(self, alert: Alert) -> None:
        """Log the alert."""
        # Use info level for all alerts to avoid conflicts with StructuredLogger
        # The alert level is included in the message
        logger.info(
            f"alert_triggered: [{alert.level.value.upper()}] {alert.message}",
            alert_id=alert.alert_id,
            alert_level=alert.level.value,
            rule=alert.rule_name,
            threshold=alert.threshold,
        )


class ConsoleHandler(AlertHandler):
    """Print alerts to console with Rich formatting."""

    def __init__(self, use_rich: bool = True):
        """Initialize console handler.

        Args:
            use_rich: Whether to use Rich for formatting
        """
        self.use_rich = use_rich

    def handle(self, alert: Alert) -> None:
        """Print alert to console."""
        try:
            if self.use_rich:
                from rich.console import Console
                from rich.panel import Panel

                console = Console()

                # Color based on level
                level_colors = {
                    AlertLevel.INFO: "blue",
                    AlertLevel.WARNING: "yellow",
                    AlertLevel.ERROR: "red",
                    AlertLevel.CRITICAL: "red bold",
                }
                color = level_colors.get(alert.level, "yellow")

                console.print(Panel(
                    f"[{color}]{alert.message}[/]\n\n"
                    f"[dim]Rule: {alert.rule_name} | "
                    f"ID: {alert.alert_id} | "
                    f"Time: {alert.timestamp.strftime('%H:%M:%S')}[/]",
                    title=f"{alert.level.emoji} {alert.level.value.upper()} ALERT",
                    border_style=color,
                ))
            else:
                print(f"[{alert.level.value.upper()}] {alert.message}")
        except Exception as e:
            # Fallback to plain print if Rich fails
            print(f"[{alert.level.value.upper()}] {alert.message} (formatting error: {e})")


class WebhookHandler(AlertHandler):
    """Send alerts to a webhook endpoint.

    Supports POST requests with JSON payload.
    """

    def __init__(
        self,
        webhook_url: str,
        timeout: float = 5.0,
        headers: Optional[Dict[str, str]] = None,
    ):
        """Initialize webhook handler.

        Args:
            webhook_url: URL to send alerts to
            timeout: Request timeout in seconds
            headers: Optional additional headers
        """
        self.webhook_url = webhook_url
        self.timeout = timeout
        self.headers = headers or {"Content-Type": "application/json"}

    def handle(self, alert: Alert) -> None:
        """Send alert to webhook.

        Note: This is a non-blocking operation. Errors are logged but don't
        interrupt the main flow.
        """
        try:
            import json
            import urllib.request
            import urllib.error

            payload = json.dumps({
                "alert": alert.to_dict(),
                "timestamp": datetime.now().isoformat(),
            }).encode("utf-8")

            req = urllib.request.Request(
                self.webhook_url,
                data=payload,
                headers=self.headers,
                method="POST",
            )

            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                if response.status >= 400:
                    logger.warning(
                        "webhook_alert_failed",
                        status=response.status,
                        alert_id=alert.alert_id,
                    )
                else:
                    logger.debug(
                        "webhook_alert_sent",
                        alert_id=alert.alert_id,
                        status=response.status,
                    )
        except urllib.error.URLError as e:
            logger.warning(
                "webhook_alert_url_error",
                error=str(e),
                alert_id=alert.alert_id,
                url=self.webhook_url,
            )
        except Exception as e:
            logger.error(
                "webhook_alert_error",
                error=str(e),
                alert_id=alert.alert_id,
            )


class EmailHandler(AlertHandler):
    """Send alerts via SMTP email.

    Supports TLS/SSL connections and multiple recipients.
    """

    # Alert level priority for filtering
    LEVEL_PRIORITY = {
        AlertLevel.INFO: 0,
        AlertLevel.WARNING: 1,
        AlertLevel.ERROR: 2,
        AlertLevel.CRITICAL: 3,
    }

    def __init__(
        self,
        smtp_host: str,
        smtp_port: int = 587,
        smtp_user: Optional[str] = None,
        smtp_password: Optional[str] = None,
        smtp_from: Optional[str] = None,
        smtp_to: List[str] = None,
        use_tls: bool = True,
        timeout: float = 10.0,
        min_level: AlertLevel = AlertLevel.ERROR,
    ):
        """Initialize email handler.

        Args:
            smtp_host: SMTP server hostname
            smtp_port: SMTP server port (default: 587 for TLS)
            smtp_user: SMTP username for authentication
            smtp_password: SMTP password for authentication
            smtp_from: Sender email address
            smtp_to: List of recipient email addresses
            use_tls: Whether to use TLS (default: True)
            timeout: Connection timeout in seconds
            min_level: Minimum alert level to send (default: ERROR)
        """
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.smtp_user = smtp_user
        self.smtp_password = smtp_password
        self.smtp_from = smtp_from or smtp_user
        self.smtp_to = smtp_to or []
        self.use_tls = use_tls
        self.timeout = timeout
        self.min_level = min_level

    def handle(self, alert: Alert) -> None:
        """Send alert via email.

        Note: This is a non-blocking operation. Errors are logged but don't
        interrupt the main flow.
        """
        # Check if alert level meets minimum threshold
        if not self._should_send(alert):
            logger.debug(
                "email_alert_skipped",
                alert_id=alert.alert_id,
                alert_level=alert.level.value,
                min_level=self.min_level.value,
            )
            return

        if not self.smtp_to:
            logger.warning("email_alert_no_recipients", alert_id=alert.alert_id)
            return

        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart

            # Create message
            msg = MIMEMultipart("alternative")
            msg["Subject"] = self._format_subject(alert)
            msg["From"] = self.smtp_from
            msg["To"] = ", ".join(self.smtp_to)

            # Plain text body
            text_body = self._format_text_body(alert)
            msg.attach(MIMEText(text_body, "plain", "utf-8"))

            # HTML body
            html_body = self._format_html_body(alert)
            msg.attach(MIMEText(html_body, "html", "utf-8"))

            # Send email
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=self.timeout) as server:
                if self.use_tls:
                    server.ehlo()
                    server.starttls()
                    server.ehlo()

                if self.smtp_user and self.smtp_password:
                    server.login(self.smtp_user, self.smtp_password)

                server.sendmail(self.smtp_from, self.smtp_to, msg.as_string())

            logger.debug(
                "email_alert_sent",
                alert_id=alert.alert_id,
                recipients=len(self.smtp_to),
            )

        except Exception as e:
            logger.error(
                "email_alert_error",
                error=str(e),
                alert_id=alert.alert_id,
                smtp_host=self.smtp_host,
            )

    def _should_send(self, alert: Alert) -> bool:
        """Check if alert level meets minimum threshold.

        Args:
            alert: The alert to check

        Returns:
            True if alert should be sent
        """
        alert_priority = self.LEVEL_PRIORITY.get(alert.level, 0)
        min_priority = self.LEVEL_PRIORITY.get(self.min_level, 0)
        return alert_priority >= min_priority

    def _format_subject(self, alert: Alert) -> str:
        """Format email subject.

        Args:
            alert: The alert

        Returns:
            Formatted subject string
        """
        return f"[{alert.level.value.upper()}] Mini Claude Alert: {alert.rule_name}"

    def _format_text_body(self, alert: Alert) -> str:
        """Format plain text email body.

        Args:
            alert: The alert

        Returns:
            Plain text body
        """
        lines = [
            f"Alert: {alert.rule_name}",
            f"Level: {alert.level.value.upper()}",
            f"Time: {alert.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Alert ID: {alert.alert_id}",
            "",
            "Message:",
            f"  {alert.message}",
            "",
        ]

        if alert.threshold is not None:
            lines.append(f"Threshold: {alert.threshold}")

        if alert.metrics:
            lines.append("")
            lines.append("Metrics:")
            for key, value in alert.metrics.items():
                lines.append(f"  {key}: {value}")

        return "\n".join(lines)

    def _format_html_body(self, alert: Alert) -> str:
        """Format HTML email body.

        Args:
            alert: The alert

        Returns:
            HTML body
        """
        # Color based on level
        level_colors = {
            AlertLevel.INFO: "#3498db",
            AlertLevel.WARNING: "#f39c12",
            AlertLevel.ERROR: "#e74c3c",
            AlertLevel.CRITICAL: "#c0392b",
        }
        color = level_colors.get(alert.level, "#666666")

        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background-color: {color}; color: white; padding: 15px; border-radius: 5px 5px 0 0;">
                <h2 style="margin: 0;">{alert.level.emoji} {alert.level.value.upper()} Alert</h2>
            </div>
            <div style="border: 1px solid #ddd; border-top: none; padding: 20px;">
                <p><strong>Rule:</strong> {alert.rule_name}</p>
                <p><strong>Time:</strong> {alert.timestamp.strftime('%Y-%m-%d %H:%M:%S')}</p>
                <p><strong>Alert ID:</strong> <code>{alert.alert_id}</code></p>
                <hr style="border: none; border-top: 1px solid #eee; margin: 15px 0;">
                <p style="font-size: 16px;">{alert.message}</p>
        """

        if alert.threshold is not None:
            html += f'<p><strong>Threshold:</strong> {alert.threshold}</p>'

        html += """
            </div>
            <div style="background-color: #f5f5f5; padding: 10px; font-size: 12px; color: #666; border-radius: 0 0 5px 5px;">
                Mini Claude Code Alert System
            </div>
        </body>
        </html>
        """

        return html


# =============================================================================
# Notification Manager
# =============================================================================


class NotificationManager:
    """Unified manager for multi-channel notifications.

    Manages multiple notification channels (webhook, email, etc.) and provides
    centralized configuration for sending alerts through multiple channels.

    Example:
        manager = NotificationManager()
        manager.add_channel(WebhookHandler(webhook_url="..."))
        manager.add_channel(EmailHandler(smtp_host="...", smtp_to=["admin@example.com"]))

        # Send notification through all channels
        manager.notify(alert)
    """

    # Alert level priority for filtering
    LEVEL_PRIORITY = {
        AlertLevel.INFO: 0,
        AlertLevel.WARNING: 1,
        AlertLevel.ERROR: 2,
        AlertLevel.CRITICAL: 3,
    }

    def __init__(
        self,
        enabled: bool = True,
        channels: Optional[List[str]] = None,
        min_level: AlertLevel = AlertLevel.ERROR,
    ):
        """Initialize notification manager.

        Args:
            enabled: Whether notifications are enabled
            channels: List of channel names to use (e.g., ["webhook", "email"])
            min_level: Minimum alert level to send notifications
        """
        self._enabled = enabled
        self._channels: List[AlertHandler] = []
        self._channel_names: List[str] = channels or []
        self._min_level = min_level

    def add_channel(self, handler: AlertHandler) -> None:
        """Add a notification channel handler.

        Args:
            handler: The handler to add (e.g., WebhookHandler, EmailHandler)
        """
        self._channels.append(handler)
        logger.debug(
            "notification_channel_added",
            handler=handler.__class__.__name__,
            total_channels=len(self._channels),
        )

    def remove_channel(self, handler: AlertHandler) -> bool:
        """Remove a notification channel handler.

        Args:
            handler: The handler to remove

        Returns:
            True if handler was removed, False if not found
        """
        try:
            self._channels.remove(handler)
            logger.debug(
                "notification_channel_removed",
                handler=handler.__class__.__name__,
            )
            return True
        except ValueError:
            return False

    def notify(self, alert: Alert) -> bool:
        """Send notification through all configured channels.

        Args:
            alert: The alert to notify about

        Returns:
            True if notification was processed (even if some channels failed)
        """
        if not self._enabled:
            logger.debug("notification_disabled", alert_id=alert.alert_id)
            return False

        # Check if alert level meets minimum threshold
        if not self._should_notify(alert):
            logger.debug(
                "notification_skipped",
                alert_id=alert.alert_id,
                alert_level=alert.level.value,
                min_level=self._min_level.value,
            )
            return False

        # Send through all channels
        success_count = 0
        for handler in self._channels:
            try:
                handler.handle(alert)
                success_count += 1
            except Exception as e:
                logger.error(
                    "notification_channel_error",
                    handler=handler.__class__.__name__,
                    alert_id=alert.alert_id,
                    error=str(e),
                )

        logger.info(
            "notification_sent",
            alert_id=alert.alert_id,
            channels=len(self._channels),
            successful=success_count,
        )

        return success_count > 0

    def _should_notify(self, alert: Alert) -> bool:
        """Check if alert level meets minimum threshold.

        Args:
            alert: The alert to check

        Returns:
            True if notification should be sent
        """
        alert_priority = self.LEVEL_PRIORITY.get(alert.level, 0)
        min_priority = self.LEVEL_PRIORITY.get(self._min_level, 0)
        return alert_priority >= min_priority

    def get_channels(self) -> List[AlertHandler]:
        """Get all registered channel handlers.

        Returns:
            List of handlers
        """
        return list(self._channels)

    def get_status(self) -> Dict[str, Any]:
        """Get notification manager status.

        Returns:
            Dictionary with status information
        """
        return {
            "enabled": self._enabled,
            "channels_count": len(self._channels),
            "channel_names": self._channel_names,
            "min_level": self._min_level.value,
        }

    @classmethod
    def from_settings(cls) -> "NotificationManager":
        """Create NotificationManager from settings.

        Returns:
            NotificationManager configured from Settings
        """
        # Parse min_level from settings
        min_level_str = settings.notification_min_level.lower()
        min_level = {
            "info": AlertLevel.INFO,
            "warning": AlertLevel.WARNING,
            "error": AlertLevel.ERROR,
            "critical": AlertLevel.CRITICAL,
        }.get(min_level_str, AlertLevel.ERROR)

        manager = cls(
            enabled=settings.notification_enabled,
            channels=settings.notification_channels,
            min_level=min_level,
        )

        # Add webhook channel if configured
        if "webhook" in settings.notification_channels and settings.alert_webhook_url:
            manager.add_channel(
                WebhookHandler(webhook_url=settings.alert_webhook_url)
            )

        # Add email channel if configured
        if "email" in settings.notification_channels and settings.smtp_host:
            if settings.smtp_to:  # Only add if recipients are configured
                manager.add_channel(
                    EmailHandler(
                        smtp_host=settings.smtp_host,
                        smtp_port=settings.smtp_port,
                        smtp_user=settings.smtp_user,
                        smtp_password=settings.smtp_password,
                        smtp_from=settings.smtp_from,
                        smtp_to=settings.smtp_to,
                        use_tls=settings.smtp_use_tls,
                        min_level=min_level,
                    )
                )

        logger.debug(
            "notification_manager_from_settings",
            enabled=settings.notification_enabled,
            channels=settings.notification_channels,
            webhook_enabled=settings.alert_webhook_url is not None,
            email_enabled=settings.smtp_host is not None and len(settings.smtp_to) > 0,
        )

        return manager


# =============================================================================
# Alert Manager
# =============================================================================


class AlertManager:
    """Central alert management system.

    Manages alert rules, handlers, and active alerts.
    Provides silence periods to prevent alert storms.

    Example:
        manager = AlertManager()
        manager.add_rule(HighFailureRateRule(threshold=0.2))
        manager.add_handler(LogHandler())

        # Check alerts after collecting metrics
        alerts = manager.check_alerts(metrics)
        for alert in alerts:
            print(alert.message)
    """

    def __init__(self):
        """Initialize the alert manager."""
        self._rules: Dict[str, AlertRule] = {}
        self._handlers: List[AlertHandler] = []
        self._active_alerts: Dict[str, Alert] = {}
        self._silenced_rules: Dict[str, datetime] = {}

    def add_rule(self, rule: AlertRule) -> None:
        """Add an alert rule.

        Args:
            rule: The alert rule to add
        """
        self._rules[rule.name] = rule
        logger.debug("alert_rule_added", rule=rule.name, threshold=rule.threshold)

    def remove_rule(self, name: str) -> bool:
        """Remove an alert rule by name.

        Args:
            name: Name of the rule to remove

        Returns:
            True if rule was removed, False if not found
        """
        if name in self._rules:
            del self._rules[name]
            logger.debug("alert_rule_removed", rule=name)
            return True
        return False

    def get_rules(self) -> List[AlertRule]:
        """Get all registered rules.

        Returns:
            List of alert rules
        """
        return list(self._rules.values())

    def add_handler(self, handler: AlertHandler) -> None:
        """Add an alert handler.

        Args:
            handler: The handler to add
        """
        self._handlers.append(handler)
        logger.debug("alert_handler_added", handler=handler.__class__.__name__)

    def remove_handler(self, handler: AlertHandler) -> bool:
        """Remove an alert handler.

        Args:
            handler: The handler to remove

        Returns:
            True if handler was removed, False if not found
        """
        try:
            self._handlers.remove(handler)
            logger.debug("alert_handler_removed", handler=handler.__class__.__name__)
            return True
        except ValueError:
            return False

    def check_alerts(self, metrics: Dict[str, Any]) -> List[Alert]:
        """Check all rules against current metrics.

        Args:
            metrics: Dictionary of current metric values

        Returns:
            List of alerts that were triggered
        """
        if not settings.alert_enabled:
            return []

        triggered_alerts = []

        for rule_name, rule in self._rules.items():
            # Check if rule is silenced
            if self._is_silenced(rule_name):
                continue

            # Check the rule
            alert = rule.check(metrics)
            if alert:
                # Store as active alert
                self._active_alerts[alert.alert_id] = alert

                # Silence the rule
                self._silence_rule(rule_name, rule.silence_period)

                # Trigger handlers
                self._trigger_handlers(alert)

                triggered_alerts.append(alert)

        return triggered_alerts

    def get_active_alerts(self, include_acknowledged: bool = False) -> List[Alert]:
        """Get all active (unacknowledged) alerts.

        Args:
            include_acknowledged: Whether to include acknowledged alerts

        Returns:
            List of active alerts
        """
        if include_acknowledged:
            return list(self._active_alerts.values())

        return [a for a in self._active_alerts.values() if not a.acknowledged]

    def acknowledge(self, alert_id: str) -> bool:
        """Acknowledge an alert.

        Args:
            alert_id: ID of the alert to acknowledge

        Returns:
            True if alert was acknowledged, False if not found
        """
        if alert_id in self._active_alerts:
            self._active_alerts[alert_id].acknowledged = True
            logger.debug("alert_acknowledged", alert_id=alert_id)
            return True
        return False

    def clear_alert(self, alert_id: str) -> bool:
        """Remove an alert from active alerts.

        Args:
            alert_id: ID of the alert to clear

        Returns:
            True if alert was cleared, False if not found
        """
        if alert_id in self._active_alerts:
            del self._active_alerts[alert_id]
            logger.debug("alert_cleared", alert_id=alert_id)
            return True
        return False

    def clear_all_alerts(self) -> int:
        """Clear all active alerts.

        Returns:
            Number of alerts cleared
        """
        count = len(self._active_alerts)
        self._active_alerts.clear()
        logger.debug("all_alerts_cleared", count=count)
        return count

    def _is_silenced(self, rule_name: str) -> bool:
        """Check if a rule is currently silenced.

        Args:
            rule_name: Name of the rule to check

        Returns:
            True if the rule is silenced
        """
        if rule_name not in self._silenced_rules:
            return False

        silence_end = self._silenced_rules[rule_name]
        if datetime.now() > silence_end:
            del self._silenced_rules[rule_name]
            return False

        return True

    def _silence_rule(self, rule_name: str, duration_seconds: float) -> None:
        """Silence a rule for a duration.

        Args:
            rule_name: Name of the rule to silence
            duration_seconds: Duration in seconds
        """
        self._silenced_rules[rule_name] = datetime.now() + timedelta(seconds=duration_seconds)
        logger.debug(
            "rule_silenced",
            rule=rule_name,
            duration=duration_seconds,
            until=self._silenced_rules[rule_name].isoformat(),
        )

    def _trigger_handlers(self, alert: Alert) -> None:
        """Trigger all handlers for an alert.

        Handler exceptions are caught to prevent disrupting the system.

        Args:
            alert: The alert to process
        """
        for handler in self._handlers:
            try:
                handler.handle(alert)
            except Exception as e:
                logger.error(
                    "alert_handler_error",
                    handler=handler.__class__.__name__,
                    alert_id=alert.alert_id,
                    error=str(e),
                )

    def get_status(self) -> Dict[str, Any]:
        """Get alert manager status.

        Returns:
            Dictionary with status information
        """
        active = self.get_active_alerts()
        acknowledged = [a for a in self._active_alerts.values() if a.acknowledged]

        return {
            "enabled": settings.alert_enabled,
            "rules_count": len(self._rules),
            "handlers_count": len(self._handlers),
            "active_alerts": len(active),
            "acknowledged_alerts": len(acknowledged),
            "silenced_rules": list(self._silenced_rules.keys()),
        }


# =============================================================================
# Global Instance
# =============================================================================

_alert_manager: Optional[AlertManager] = None


def get_alert_manager() -> AlertManager:
    """Get or create the global alert manager instance.

    This function provides backward compatibility with existing code.
    New code should prefer ApplicationContext.alert_manager.

    Returns:
        Singleton AlertManager instance.
    """
    global _alert_manager
    if _alert_manager is None:
        # Try to use ApplicationContext first
        try:
            from mini_claude.context import get_context
            ctx = get_context()
            if ctx._alert_manager.is_initialized():
                _alert_manager = ctx.alert_manager
            else:
                _alert_manager = _create_alert_manager()
                ctx.alert_manager = _alert_manager
        except ImportError:
            _alert_manager = _create_alert_manager()
    return _alert_manager


def _create_alert_manager() -> AlertManager:
    """Create and configure an AlertManager instance."""
    manager = AlertManager()

    # Add built-in rules based on settings
    if settings.alert_enabled:
        manager.add_rule(
            HighFailureRateRule(threshold=settings.alert_failure_rate_threshold)
        )
        manager.add_rule(
            HighLatencyRule(threshold=settings.alert_latency_threshold_seconds)
        )
        manager.add_rule(
            TokenBudgetRule(threshold=settings.alert_token_budget_threshold)
        )
        manager.add_rule(ToolFailureRule())

        # Add default handlers
        manager.add_handler(LogHandler())

        # Add webhook handler if configured
        if settings.alert_webhook_url:
            manager.add_handler(
                WebhookHandler(webhook_url=settings.alert_webhook_url)
            )

    logger.debug("alert_manager_initialized", enabled=settings.alert_enabled)
    return manager


def reset_alert_manager() -> None:
    """Reset the global alert manager.

    Useful for testing.
    """
    global _alert_manager
    _alert_manager = None
    # Also reset in context
    try:
        from mini_claude.context import get_context
        ctx = get_context()
        ctx._alert_manager.reset()
    except ImportError:
        pass


# =============================================================================
# Convenience Functions
# =============================================================================


def check_alerts(metrics: Dict[str, Any]) -> List[Alert]:
    """Check alerts using global manager."""
    return get_alert_manager().check_alerts(metrics)


def get_active_alerts() -> List[Alert]:
    """Get active alerts using global manager."""
    return get_alert_manager().get_active_alerts()


def acknowledge_alert(alert_id: str) -> bool:
    """Acknowledge an alert using global manager."""
    return get_alert_manager().acknowledge(alert_id)
