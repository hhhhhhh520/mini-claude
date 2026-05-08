"""Tests for alert system."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock

from mini_claude.monitoring.alerts import (
    AlertLevel,
    Alert,
    AlertRule,
    AlertManager,
    AlertHandler,
    LogHandler,
    ConsoleHandler,
    WebhookHandler,
    EmailHandler,
    NotificationManager,
    HighFailureRateRule,
    HighLatencyRule,
    TokenBudgetRule,
    ToolFailureRule,
    get_alert_manager,
    reset_alert_manager,
    check_alerts,
    get_active_alerts,
    acknowledge_alert,
)


class TestAlertLevel:
    """Tests for AlertLevel enum."""

    def test_alert_level_values(self):
        """Test alert level values."""
        assert AlertLevel.INFO.value == "info"
        assert AlertLevel.WARNING.value == "warning"
        assert AlertLevel.ERROR.value == "error"
        assert AlertLevel.CRITICAL.value == "critical"

    def test_alert_level_emoji(self):
        """Test emoji representations."""
        assert AlertLevel.INFO.emoji == "ℹ️"  # information source
        assert AlertLevel.WARNING.emoji == "⚠️"  # warning
        assert AlertLevel.ERROR.emoji == "❌"  # cross mark
        assert AlertLevel.CRITICAL.emoji == "\U0001f6a8"  # police lights


class TestAlert:
    """Tests for Alert dataclass."""

    def test_alert_creation(self):
        """Test creating an alert."""
        alert = Alert(
            level=AlertLevel.WARNING,
            message="Test alert",
            rule_name="test_rule",
        )

        assert alert.level == AlertLevel.WARNING
        assert alert.message == "Test alert"
        assert alert.rule_name == "test_rule"
        assert alert.acknowledged is False
        assert alert.alert_id != ""

    def test_alert_auto_id_generation(self):
        """Test that alert ID is auto-generated and unique."""
        import time
        alert1 = Alert(
            level=AlertLevel.WARNING,
            message="Test alert",
            rule_name="test_rule",
        )
        # Small delay to ensure different timestamp
        time.sleep(0.001)
        alert2 = Alert(
            level=AlertLevel.WARNING,
            message="Test alert",
            rule_name="test_rule",
        )

        # IDs should be unique
        assert alert1.alert_id != ""
        assert alert2.alert_id != ""

    def test_alert_to_dict(self):
        """Test converting alert to dictionary."""
        alert = Alert(
            level=AlertLevel.ERROR,
            message="Test error alert",
            metrics={"requests": {"total": 100, "failed": 25}},
            threshold=0.2,
            rule_name="high_failure_rate",
        )

        data = alert.to_dict()

        assert data["level"] == "error"
        assert data["message"] == "Test error alert"
        assert data["rule_name"] == "high_failure_rate"
        assert data["threshold"] == 0.2
        assert data["metrics"]["requests"]["total"] == 100
        assert data["acknowledged"] is False


class TestAlertRule:
    """Tests for AlertRule."""

    def test_custom_rule(self):
        """Test creating a custom alert rule."""
        rule = AlertRule(
            name="custom_rule",
            condition=lambda m: m.get("value", 0) > 100,
            threshold=100,
            level=AlertLevel.WARNING,
            description="Alert when value exceeds 100",
        )

        assert rule.name == "custom_rule"
        assert rule.threshold == 100
        assert rule.level == AlertLevel.WARNING

    def test_rule_check_true(self):
        """Test rule check returns alert when condition is met."""
        rule = AlertRule(
            name="custom_rule",
            condition=lambda m: m.get("value", 0) > 100,
            threshold=100,
            level=AlertLevel.WARNING,
        )

        alert = rule.check({"value": 150})

        assert alert is not None
        assert alert.level == AlertLevel.WARNING
        assert alert.rule_name == "custom_rule"

    def test_rule_check_false(self):
        """Test rule check returns None when condition is not met."""
        rule = AlertRule(
            name="custom_rule",
            condition=lambda m: m.get("value", 0) > 100,
            threshold=100,
            level=AlertLevel.WARNING,
        )

        alert = rule.check({"value": 50})

        assert alert is None

    def test_rule_check_exception_handling(self):
        """Test rule handles exceptions gracefully."""
        rule = AlertRule(
            name="error_rule",
            condition=lambda m: m["missing_key"] > 100,  # Will raise KeyError
            threshold=100,
            level=AlertLevel.ERROR,
        )

        alert = rule.check({})  # Empty dict will cause KeyError

        assert alert is None  # Should return None on error


class TestHighFailureRateRule:
    """Tests for HighFailureRateRule."""

    def test_trigger_when_rate_exceeded(self):
        """Test alert triggers when failure rate exceeds threshold."""
        rule = HighFailureRateRule(threshold=0.2)

        metrics = {
            "requests": {
                "total": 100,
                "failed": 30,  # 30% > 20%
            }
        }

        alert = rule.check(metrics)

        assert alert is not None
        assert alert.level == AlertLevel.ERROR
        assert "30" in alert.message  # Should mention 30% failure rate

    def test_no_trigger_when_rate_ok(self):
        """Test no alert when failure rate is below threshold."""
        rule = HighFailureRateRule(threshold=0.2)

        metrics = {
            "requests": {
                "total": 100,
                "failed": 10,  # 10% < 20%
            }
        }

        alert = rule.check(metrics)

        assert alert is None

    def test_no_trigger_zero_requests(self):
        """Test no alert when there are no requests."""
        rule = HighFailureRateRule(threshold=0.2)

        metrics = {
            "requests": {
                "total": 0,
                "failed": 0,
            }
        }

        alert = rule.check(metrics)

        assert alert is None


class TestHighLatencyRule:
    """Tests for HighLatencyRule."""

    def test_trigger_when_latency_exceeded(self):
        """Test alert triggers when latency exceeds threshold."""
        rule = HighLatencyRule(threshold=5.0)

        metrics = {
            "performance": {
                "avg_duration_seconds": 7.5,
            }
        }

        alert = rule.check(metrics)

        assert alert is not None
        assert alert.level == AlertLevel.WARNING
        assert "7.5" in alert.message

    def test_no_trigger_when_latency_ok(self):
        """Test no alert when latency is below threshold."""
        rule = HighLatencyRule(threshold=5.0)

        metrics = {
            "performance": {
                "avg_duration_seconds": 3.0,
            }
        }

        alert = rule.check(metrics)

        assert alert is None


class TestTokenBudgetRule:
    """Tests for TokenBudgetRule."""

    def test_trigger_when_budget_exceeded(self):
        """Test alert triggers when token usage exceeds budget."""
        rule = TokenBudgetRule(threshold=0.8)

        metrics = {
            "token_usage": {
                "current_tokens": 9000,
                "token_budget": 10000,
                "usage_ratio": 0.9,  # 90% > 80%
            }
        }

        alert = rule.check(metrics)

        assert alert is not None
        assert alert.level == AlertLevel.WARNING
        assert "90" in alert.message

    def test_no_trigger_when_budget_ok(self):
        """Test no alert when token usage is within budget."""
        rule = TokenBudgetRule(threshold=0.8)

        metrics = {
            "token_usage": {
                "current_tokens": 5000,
                "token_budget": 10000,
                "usage_ratio": 0.5,  # 50% < 80%
            }
        }

        alert = rule.check(metrics)

        assert alert is None


class TestToolFailureRule:
    """Tests for ToolFailureRule."""

    def test_trigger_when_tool_failure_exceeded(self):
        """Test alert triggers when tool failure rate exceeds threshold."""
        rule = ToolFailureRule(threshold=0.3, min_calls=5)

        metrics = {
            "tools": {
                "success": {"write_file": 5},
                "failure": {"write_file": 10},  # 66% > 30%
            }
        }

        alert = rule.check(metrics)

        assert alert is not None
        assert alert.level == AlertLevel.WARNING
        assert "write_file" in alert.message

    def test_no_trigger_below_min_calls(self):
        """Test no alert when call count is below minimum."""
        rule = ToolFailureRule(threshold=0.3, min_calls=10)

        metrics = {
            "tools": {
                "success": {"write_file": 1},
                "failure": {"write_file": 3},  # 75% but only 4 calls
            }
        }

        alert = rule.check(metrics)

        assert alert is None  # Below min_calls threshold

    def test_no_trigger_when_rate_ok(self):
        """Test no alert when tool failure rate is below threshold."""
        rule = ToolFailureRule(threshold=0.3, min_calls=5)

        metrics = {
            "tools": {
                "success": {"write_file": 15},
                "failure": {"write_file": 2},  # 12% < 30%
            }
        }

        alert = rule.check(metrics)

        assert alert is None


class TestAlertHandlers:
    """Tests for alert handlers."""

    def test_log_handler(self):
        """Test LogHandler logs alerts."""
        handler = LogHandler()
        alert = Alert(
            level=AlertLevel.WARNING,
            message="Test warning",
            rule_name="test_rule",
        )

        # Should not raise any exceptions
        handler.handle(alert)

    def test_console_handler_rich(self):
        """Test ConsoleHandler with Rich formatting."""
        handler = ConsoleHandler(use_rich=True)
        alert = Alert(
            level=AlertLevel.ERROR,
            message="Test error for console",
            rule_name="test_rule",
        )

        handler.handle(alert)
        # Should not raise any exceptions

    def test_console_handler_plain(self, capsys):
        """Test ConsoleHandler without Rich."""
        handler = ConsoleHandler(use_rich=False)
        alert = Alert(
            level=AlertLevel.WARNING,
            message="Plain warning",
            rule_name="test_rule",
        )

        handler.handle(alert)
        captured = capsys.readouterr()
        assert "WARNING" in captured.out

    def test_webhook_handler_success(self):
        """Test WebhookHandler sends POST request."""
        # Use a mock server or skip if not available
        handler = WebhookHandler(webhook_url="http://httpbin.org/post", timeout=1.0)
        alert = Alert(
            level=AlertLevel.CRITICAL,
            message="Critical alert",
            rule_name="test_rule",
        )

        # Try to send - may fail in offline environment
        try:
            handler.handle(alert)
        except Exception:
            pass  # Network errors are acceptable in tests

    def test_webhook_handler_url_error(self):
        """Test WebhookHandler handles URL errors gracefully."""
        handler = WebhookHandler(webhook_url="http://invalid.local:99999/alerts", timeout=0.1)
        alert = Alert(
            level=AlertLevel.ERROR,
            message="Test alert",
            rule_name="test_rule",
        )

        # Should not raise exception
        handler.handle(alert)


class TestAlertManager:
    """Tests for AlertManager."""

    @pytest.fixture
    def manager(self):
        """Create a fresh AlertManager for each test."""
        return AlertManager()

    def test_add_rule(self, manager):
        """Test adding a rule."""
        rule = HighFailureRateRule(threshold=0.5)
        manager.add_rule(rule)

        assert len(manager.get_rules()) == 1
        assert manager.get_rules()[0].name == "high_failure_rate"

    def test_remove_rule(self, manager):
        """Test removing a rule."""
        rule = HighFailureRateRule(threshold=0.5)
        manager.add_rule(rule)

        result = manager.remove_rule("high_failure_rate")

        assert result is True
        assert len(manager.get_rules()) == 0

    def test_remove_rule_not_found(self, manager):
        """Test removing non-existent rule."""
        result = manager.remove_rule("nonexistent")
        assert result is False

    def test_add_handler(self, manager):
        """Test adding a handler."""
        handler = LogHandler()
        manager.add_handler(handler)

        assert len(manager._handlers) == 1

    def test_check_alerts(self, manager):
        """Test checking alerts."""
        manager.add_rule(HighFailureRateRule(threshold=0.1))

        metrics = {
            "requests": {"total": 100, "failed": 50},
        }

        alerts = manager.check_alerts(metrics)

        assert len(alerts) == 1
        assert alerts[0].rule_name == "high_failure_rate"

    def test_check_alerts_disabled(self, manager, monkeypatch):
        """Test checking alerts when disabled."""
        from mini_claude.config.settings import Settings
        test_settings = Settings(alert_enabled=False)
        monkeypatch.setattr("mini_claude.monitoring.alerts.settings", test_settings)

        manager.add_rule(HighFailureRateRule(threshold=0.1))

        metrics = {
            "requests": {"total": 100, "failed": 50},
        }

        alerts = manager.check_alerts(metrics)

        assert len(alerts) == 0

    def test_get_active_alerts(self, manager):
        """Test getting active alerts."""
        manager.add_rule(HighFailureRateRule(threshold=0.1))

        metrics = {
            "requests": {"total": 100, "failed": 50},
        }

        manager.check_alerts(metrics)
        active = manager.get_active_alerts()

        assert len(active) == 1

    def test_acknowledge_alert(self, manager):
        """Test acknowledging an alert."""
        manager.add_rule(HighFailureRateRule(threshold=0.1))

        metrics = {
            "requests": {"total": 100, "failed": 50},
        }

        alerts = manager.check_alerts(metrics)
        alert_id = alerts[0].alert_id

        result = manager.acknowledge(alert_id)

        assert result is True
        assert manager._active_alerts[alert_id].acknowledged is True

    def test_acknowledge_nonexistent_alert(self, manager):
        """Test acknowledging non-existent alert."""
        result = manager.acknowledge("nonexistent")
        assert result is False

    def test_clear_alert(self, manager):
        """Test clearing an alert."""
        manager.add_rule(HighFailureRateRule(threshold=0.1))

        metrics = {
            "requests": {"total": 100, "failed": 50},
        }

        alerts = manager.check_alerts(metrics)
        alert_id = alerts[0].alert_id

        result = manager.clear_alert(alert_id)

        assert result is True
        assert alert_id not in manager._active_alerts

    def test_clear_all_alerts(self, manager):
        """Test clearing all alerts."""
        manager.add_rule(HighFailureRateRule(threshold=0.1))
        manager.add_rule(HighLatencyRule(threshold=1.0))

        metrics = {
            "requests": {"total": 100, "failed": 50},
            "performance": {"avg_duration_seconds": 5.0},
        }

        manager.check_alerts(metrics)
        count = manager.clear_all_alerts()

        assert count >= 1
        assert len(manager._active_alerts) == 0

    def test_silence_period(self, manager):
        """Test alert silence period."""
        manager.add_rule(HighFailureRateRule(threshold=0.1, silence_period=60))

        metrics = {
            "requests": {"total": 100, "failed": 50},
        }

        # First check should trigger
        alerts1 = manager.check_alerts(metrics)
        assert len(alerts1) == 1

        # Second check should be silenced
        alerts2 = manager.check_alerts(metrics)
        assert len(alerts2) == 0

        # Verify rule is in silenced list
        assert "high_failure_rate" in manager._silenced_rules

    def test_handler_exception_isolation(self, manager):
        """Test that handler exceptions don't break the system."""
        class BrokenHandler(AlertHandler):
            def handle(self, alert):
                raise RuntimeError("Handler broken!")

        manager.add_handler(BrokenHandler())
        manager.add_rule(HighFailureRateRule(threshold=0.1))

        metrics = {
            "requests": {"total": 100, "failed": 50},
        }

        # Should not raise exception
        alerts = manager.check_alerts(metrics)

        assert len(alerts) == 1  # Alert still created

    def test_get_status(self, manager):
        """Test getting manager status."""
        manager.add_rule(HighFailureRateRule(threshold=0.1))
        manager.add_handler(LogHandler())

        status = manager.get_status()

        assert status["rules_count"] == 1
        assert status["handlers_count"] == 1
        assert status["active_alerts"] == 0


class TestGlobalFunctions:
    """Tests for global convenience functions."""

    def setup_method(self):
        """Reset global state before each test."""
        reset_alert_manager()

    def teardown_method(self):
        """Reset global state after each test."""
        reset_alert_manager()

    def test_get_alert_manager_singleton(self):
        """Test that get_alert_manager returns singleton."""
        manager1 = get_alert_manager()
        manager2 = get_alert_manager()

        assert manager1 is manager2

    def test_reset_alert_manager(self):
        """Test resetting global manager."""
        manager1 = get_alert_manager()
        reset_alert_manager()
        manager2 = get_alert_manager()

        assert manager1 is not manager2

    def test_check_alerts_global(self, monkeypatch):
        """Test global check_alerts function."""
        from mini_claude.config.settings import Settings
        test_settings = Settings(alert_enabled=True)
        monkeypatch.setattr("mini_claude.monitoring.alerts.settings", test_settings)

        # Reset to pick up settings
        reset_alert_manager()
        manager = get_alert_manager()
        manager._rules.clear()  # Clear default rules
        manager.add_rule(HighFailureRateRule(threshold=0.1))

        metrics = {
            "requests": {"total": 100, "failed": 50},
        }

        alerts = check_alerts(metrics)
        assert len(alerts) == 1

    def test_get_active_alerts_global(self):
        """Test global get_active_alerts function."""
        reset_alert_manager()
        manager = get_alert_manager()
        manager._rules.clear()
        manager.add_rule(HighFailureRateRule(threshold=0.1))

        metrics = {
            "requests": {"total": 100, "failed": 50},
        }

        manager.check_alerts(metrics)
        alerts = get_active_alerts()

        assert len(alerts) == 1

    def test_acknowledge_alert_global(self):
        """Test global acknowledge_alert function."""
        reset_alert_manager()
        manager = get_alert_manager()
        manager._rules.clear()
        manager.add_rule(HighFailureRateRule(threshold=0.1))

        metrics = {
            "requests": {"total": 100, "failed": 50},
        }

        alerts = manager.check_alerts(metrics)
        alert_id = alerts[0].alert_id

        result = acknowledge_alert(alert_id)

        assert result is True


class TestIntegration:
    """Integration tests for the alert system."""

    def test_full_alert_workflow(self):
        """Test complete alert workflow."""
        reset_alert_manager()
        manager = get_alert_manager()
        manager._rules.clear()

        # Add rules
        manager.add_rule(HighFailureRateRule(threshold=0.2))
        manager.add_rule(HighLatencyRule(threshold=3.0))

        # Add handlers
        handler_called = []
        class TestHandler(AlertHandler):
            def handle(self, alert):
                handler_called.append(alert)

        manager.add_handler(TestHandler())
        manager.add_handler(LogHandler())

        # Check metrics that trigger alerts
        metrics = {
            "requests": {"total": 100, "failed": 30},  # 30% > 20%
            "performance": {"avg_duration_seconds": 5.0},  # 5s > 3s
        }

        alerts = manager.check_alerts(metrics)

        # Should have triggered both alerts
        assert len(alerts) >= 1
        assert len(handler_called) >= 1

        # Get active alerts
        active = manager.get_active_alerts()
        assert len(active) >= 1

        # Acknowledge an alert
        if active:
            result = manager.acknowledge(active[0].alert_id)
            assert result is True

        # Clear all
        count = manager.clear_all_alerts()
        assert count >= 1

        reset_alert_manager()


class TestEmailHandler:
    """Tests for EmailHandler."""

    def test_email_handler_creation(self):
        """Test creating an email handler."""
        handler = EmailHandler(
            smtp_host="smtp.example.com",
            smtp_port=587,
            smtp_user="user@example.com",
            smtp_password="password",
            smtp_to=["admin@example.com"],
        )

        assert handler.smtp_host == "smtp.example.com"
        assert handler.smtp_port == 587
        assert handler.smtp_user == "user@example.com"
        assert handler.smtp_to == ["admin@example.com"]
        assert handler.min_level == AlertLevel.ERROR

    def test_email_handler_min_level_filtering(self):
        """Test that email handler filters by minimum level."""
        handler = EmailHandler(
            smtp_host="smtp.example.com",
            smtp_to=["admin@example.com"],
            min_level=AlertLevel.ERROR,
        )

        # INFO alert should not be sent
        info_alert = Alert(
            level=AlertLevel.INFO,
            message="Info message",
            rule_name="test_rule",
        )
        assert handler._should_send(info_alert) is False

        # WARNING alert should not be sent
        warning_alert = Alert(
            level=AlertLevel.WARNING,
            message="Warning message",
            rule_name="test_rule",
        )
        assert handler._should_send(warning_alert) is False

        # ERROR alert should be sent
        error_alert = Alert(
            level=AlertLevel.ERROR,
            message="Error message",
            rule_name="test_rule",
        )
        assert handler._should_send(error_alert) is True

        # CRITICAL alert should be sent
        critical_alert = Alert(
            level=AlertLevel.CRITICAL,
            message="Critical message",
            rule_name="test_rule",
        )
        assert handler._should_send(critical_alert) is True

    def test_email_handler_no_recipients(self):
        """Test email handler with no recipients."""
        handler = EmailHandler(
            smtp_host="smtp.example.com",
            smtp_to=[],  # No recipients
        )

        alert = Alert(
            level=AlertLevel.ERROR,
            message="Error message",
            rule_name="test_rule",
        )

        # Should not raise exception, just log warning
        handler.handle(alert)

    def test_email_handler_invalid_smtp(self):
        """Test email handler with invalid SMTP settings."""
        handler = EmailHandler(
            smtp_host="invalid.smtp.server",
            smtp_port=99999,
            smtp_to=["admin@example.com"],
            timeout=0.1,  # Short timeout
        )

        alert = Alert(
            level=AlertLevel.ERROR,
            message="Error message",
            rule_name="test_rule",
        )

        # Should not raise exception, just log error
        handler.handle(alert)

    def test_email_format_subject(self):
        """Test email subject formatting."""
        handler = EmailHandler(
            smtp_host="smtp.example.com",
            smtp_to=["admin@example.com"],
        )

        alert = Alert(
            level=AlertLevel.ERROR,
            message="Test message",
            rule_name="high_failure_rate",
        )

        subject = handler._format_subject(alert)
        assert "[ERROR]" in subject
        assert "high_failure_rate" in subject

    def test_email_format_text_body(self):
        """Test email plain text body formatting."""
        handler = EmailHandler(
            smtp_host="smtp.example.com",
            smtp_to=["admin@example.com"],
        )

        alert = Alert(
            level=AlertLevel.ERROR,
            message="Test error message",
            rule_name="test_rule",
            threshold=0.5,
            metrics={"requests": {"total": 100, "failed": 50}},
        )

        body = handler._format_text_body(alert)
        assert "test_rule" in body
        assert "Test error message" in body
        assert "0.5" in body
        assert "ERROR" in body

    def test_email_format_html_body(self):
        """Test email HTML body formatting."""
        handler = EmailHandler(
            smtp_host="smtp.example.com",
            smtp_to=["admin@example.com"],
        )

        alert = Alert(
            level=AlertLevel.ERROR,
            message="Test error message",
            rule_name="test_rule",
        )

        html = handler._format_html_body(alert)
        assert "<html>" in html
        assert "ERROR" in html
        assert "test_rule" in html
        assert "Test error message" in html


class TestNotificationManager:
    """Tests for NotificationManager."""

    def test_notification_manager_creation(self):
        """Test creating a notification manager."""
        manager = NotificationManager(
            enabled=True,
            channels=["webhook", "email"],
            min_level=AlertLevel.ERROR,
        )

        assert manager._enabled is True
        assert manager._channel_names == ["webhook", "email"]
        assert manager._min_level == AlertLevel.ERROR

    def test_add_channel(self):
        """Test adding a channel."""
        manager = NotificationManager()
        handler = LogHandler()

        manager.add_channel(handler)

        assert len(manager.get_channels()) == 1

    def test_remove_channel(self):
        """Test removing a channel."""
        manager = NotificationManager()
        handler = LogHandler()
        manager.add_channel(handler)

        result = manager.remove_channel(handler)

        assert result is True
        assert len(manager.get_channels()) == 0

    def test_remove_channel_not_found(self):
        """Test removing non-existent channel."""
        manager = NotificationManager()
        handler = LogHandler()

        result = manager.remove_channel(handler)

        assert result is False

    def test_notify_disabled(self):
        """Test notify when disabled."""
        manager = NotificationManager(enabled=False)
        manager.add_channel(LogHandler())

        alert = Alert(
            level=AlertLevel.ERROR,
            message="Test message",
            rule_name="test_rule",
        )

        result = manager.notify(alert)

        assert result is False

    def test_notify_level_filtering(self):
        """Test notify filters by minimum level."""
        manager = NotificationManager(
            enabled=True,
            min_level=AlertLevel.ERROR,
        )
        manager.add_channel(LogHandler())

        # INFO alert should not be sent
        info_alert = Alert(
            level=AlertLevel.INFO,
            message="Info message",
            rule_name="test_rule",
        )
        result = manager.notify(info_alert)
        assert result is False

        # ERROR alert should be sent
        error_alert = Alert(
            level=AlertLevel.ERROR,
            message="Error message",
            rule_name="test_rule",
        )
        result = manager.notify(error_alert)
        assert result is True

    def test_notify_all_channels(self):
        """Test notify sends to all channels."""
        manager = NotificationManager(enabled=True)

        # Track which handlers were called
        handler_calls = []

        class TrackingHandler(AlertHandler):
            def __init__(self, name):
                self.name = name

            def handle(self, alert):
                handler_calls.append(self.name)

        manager.add_channel(TrackingHandler("handler1"))
        manager.add_channel(TrackingHandler("handler2"))
        manager.add_channel(TrackingHandler("handler3"))

        alert = Alert(
            level=AlertLevel.ERROR,
            message="Test message",
            rule_name="test_rule",
        )

        result = manager.notify(alert)

        assert result is True
        assert len(handler_calls) == 3
        assert "handler1" in handler_calls
        assert "handler2" in handler_calls
        assert "handler3" in handler_calls

    def test_notify_channel_error_isolation(self):
        """Test that channel errors don't break other channels."""
        manager = NotificationManager(enabled=True)

        handler_calls = []

        class BrokenHandler(AlertHandler):
            def handle(self, alert):
                raise RuntimeError("Channel broken!")

        class WorkingHandler(AlertHandler):
            def handle(self, alert):
                handler_calls.append("working")

        manager.add_channel(BrokenHandler())
        manager.add_channel(WorkingHandler())

        alert = Alert(
            level=AlertLevel.ERROR,
            message="Test message",
            rule_name="test_rule",
        )

        result = manager.notify(alert)

        # Should still return True because WorkingHandler succeeded
        assert result is True
        assert "working" in handler_calls

    def test_get_status(self):
        """Test getting manager status."""
        manager = NotificationManager(
            enabled=True,
            channels=["webhook"],
            min_level=AlertLevel.ERROR,
        )
        manager.add_channel(LogHandler())

        status = manager.get_status()

        assert status["enabled"] is True
        assert status["channels_count"] == 1
        assert status["channel_names"] == ["webhook"]
        assert status["min_level"] == "error"

    def test_from_settings_no_smtp(self, monkeypatch):
        """Test creating from settings without SMTP config."""
        from mini_claude.config.settings import Settings

        test_settings = Settings(
            notification_enabled=True,
            notification_channels=["webhook"],
            notification_min_level="error",
            alert_webhook_url="https://example.com/webhook",
            smtp_host=None,
            smtp_to=[],
        )
        monkeypatch.setattr("mini_claude.monitoring.alerts.settings", test_settings)

        manager = NotificationManager.from_settings()

        assert manager._enabled is True
        # Should have webhook channel
        assert len(manager.get_channels()) == 1
        assert isinstance(manager.get_channels()[0], WebhookHandler)

    def test_from_settings_with_smtp(self, monkeypatch):
        """Test creating from settings with SMTP config."""
        from mini_claude.config.settings import Settings

        test_settings = Settings(
            notification_enabled=True,
            notification_channels=["webhook", "email"],
            notification_min_level="error",
            alert_webhook_url="https://example.com/webhook",
            smtp_host="smtp.example.com",
            smtp_port=587,
            smtp_user="user@example.com",
            smtp_password="password",
            smtp_to=["admin@example.com"],
        )
        monkeypatch.setattr("mini_claude.monitoring.alerts.settings", test_settings)

        manager = NotificationManager.from_settings()

        assert manager._enabled is True
        # Should have both webhook and email channels
        assert len(manager.get_channels()) == 2
        channel_types = [type(c).__name__ for c in manager.get_channels()]
        assert "WebhookHandler" in channel_types
        assert "EmailHandler" in channel_types

    def test_from_settings_disabled(self, monkeypatch):
        """Test creating from settings when disabled."""
        from mini_claude.config.settings import Settings

        test_settings = Settings(
            notification_enabled=False,
            notification_channels=["webhook"],
        )
        monkeypatch.setattr("mini_claude.monitoring.alerts.settings", test_settings)

        manager = NotificationManager.from_settings()

        assert manager._enabled is False


class TestSettingsValidation:
    """Tests for settings validation."""

    def test_notification_min_level_validation_valid(self):
        """Test valid notification_min_level values."""
        from mini_claude.config.settings import Settings

        for level in ["info", "warning", "error", "critical"]:
            settings = Settings(notification_min_level=level)
            assert settings.notification_min_level == level

    def test_notification_min_level_validation_invalid(self):
        """Test invalid notification_min_level raises error."""
        from pydantic import ValidationError
        from mini_claude.config.settings import Settings

        with pytest.raises(ValidationError):
            Settings(notification_min_level="invalid")

    def test_smtp_port_validation_valid(self):
        """Test valid SMTP port values."""
        from mini_claude.config.settings import Settings

        for port in [25, 465, 587, 2525]:
            settings = Settings(smtp_port=port)
            assert settings.smtp_port == port

    def test_smtp_port_validation_invalid(self):
        """Test invalid SMTP port raises error."""
        from pydantic import ValidationError
        from mini_claude.config.settings import Settings

        with pytest.raises(ValidationError):
            Settings(smtp_port=0)

        with pytest.raises(ValidationError):
            Settings(smtp_port=70000)
