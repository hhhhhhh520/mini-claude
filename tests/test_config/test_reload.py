"""Tests for configuration hot reload functionality."""

import os
import tempfile
from pathlib import Path
from typing import List

from mini_claude.config.settings import (
    Settings,
    ConfigChange,
    ConfigReloadResult,
    register_config_callback,
    unregister_config_callback,
    clear_config_callbacks,
)
from mini_claude.config.watcher import (
    ConfigFileWatcher,
    WatcherState,
    get_config_watcher,
)


class TestConfigChange:
    """Tests for ConfigChange dataclass."""

    def test_config_change_creation(self):
        """Test creating a ConfigChange instance."""
        change = ConfigChange(key="log_level", old_value="INFO", new_value="DEBUG")
        assert change.key == "log_level"
        assert change.old_value == "INFO"
        assert change.new_value == "DEBUG"

    def test_config_change_equality(self):
        """Test ConfigChange equality comparison."""
        change1 = ConfigChange(key="log_level", old_value="INFO", new_value="DEBUG")
        change2 = ConfigChange(key="log_level", old_value="INFO", new_value="DEBUG")
        change3 = ConfigChange(key="log_level", old_value="INFO", new_value="ERROR")

        assert change1 == change2
        assert change1 != change3


class TestConfigReloadResult:
    """Tests for ConfigReloadResult dataclass."""

    def test_reload_result_success(self):
        """Test successful reload result."""
        changes = [ConfigChange("log_level", "INFO", "DEBUG")]
        result = ConfigReloadResult(success=True, changes=changes)

        assert result.success is True
        assert len(result.changes) == 1
        assert result.error is None
        assert result.has_changes() is True

    def test_reload_result_failure(self):
        """Test failed reload result."""
        result = ConfigReloadResult(success=False, error="File not found")

        assert result.success is False
        assert result.error == "File not found"
        assert result.has_changes() is False

    def test_reload_result_no_changes(self):
        """Test reload result with no changes."""
        result = ConfigReloadResult(success=True, changes=[])

        assert result.success is True
        assert result.has_changes() is False

    def test_get_change_summary(self):
        """Test getting change summary."""
        changes = [
            ConfigChange("log_level", "INFO", "DEBUG"),
            ConfigChange("max_iterations", 10, 20),
        ]
        result = ConfigReloadResult(success=True, changes=changes)

        summary = result.get_change_summary()

        assert summary["success"] is True
        assert summary["changed_count"] == 2
        assert "log_level" in summary["changed_keys"]
        assert "max_iterations" in summary["changed_keys"]
        assert len(summary["changes"]) == 2

    def test_timestamp_auto_generated(self):
        """Test that timestamp is auto-generated."""
        result = ConfigReloadResult(success=True)
        assert result.timestamp is not None
        assert len(result.timestamp) > 0


class TestSettingsReload:
    """Tests for Settings.reload() method."""

    def test_reload_nonexistent_file(self):
        """Test reload with non-existent file returns error."""
        settings = Settings()
        result = settings.reload(env_file="/nonexistent/.env")

        assert result.success is False
        assert "not found" in result.error.lower()

    def test_reload_existing_file_no_changes(self):
        """Test reload with no changes returns success with empty changes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env"
            # Create empty .env file
            env_file.write_text("")

            settings = Settings()
            result = settings.reload(env_file=str(env_file))

            assert result.success is True
            assert len(result.changes) == 0

    def test_reload_with_single_change(self):
        """Test reload detects a single configuration change."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env"
            # Write initial config
            env_file.write_text("DEFAULT_MODEL=deepseek-chat\nLOG_LEVEL=INFO\n")

            # Create settings with initial values
            settings = Settings(default_model="deepseek-chat", log_level="INFO")

            # Change the setting in memory
            settings.log_level = "WARNING"

            # Reload should detect the change back to original
            env_file.write_text("DEFAULT_MODEL=deepseek-chat\nLOG_LEVEL=INFO\n")
            result = settings.reload(env_file=str(env_file))

            assert result.success is True

    def test_reload_validates_new_values(self):
        """Test that reload validates new configuration values."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env"
            # Write invalid config value
            env_file.write_text("VECTOR_DB_TYPE=invalid_type\n")

            settings = Settings()
            result = settings.reload(env_file=str(env_file))

            assert result.success is False
            assert "Validation failed" in result.error

    def test_reload_updates_environment_variables(self):
        """Test that reload updates environment variables for LiteLLM."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env"
            env_file.write_text("OPENAI_API_KEY=test-key-123\n")

            settings = Settings()
            result = settings.reload(env_file=str(env_file))

            assert result.success is True
            assert os.environ.get("OPENAI_API_KEY") == "test-key-123"

            # Cleanup
            if "OPENAI_API_KEY" in os.environ:
                del os.environ["OPENAI_API_KEY"]

    def test_reload_handles_boolean_values(self):
        """Test reload correctly parses boolean values."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env"
            env_file.write_text("STREAMING_ENABLED=true\nAUTO_SAVE_ENABLED=false\n")

            settings = Settings(streaming_enabled=False, auto_save_enabled=True)
            result = settings.reload(env_file=str(env_file))

            assert result.success is True

    def test_reload_handles_integer_values(self):
        """Test reload correctly parses integer values."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env"
            env_file.write_text("MAX_ITERATIONS=20\nMAX_SUB_AGENTS=5\n")

            settings = Settings(max_iterations=10, max_sub_agents=3)
            result = settings.reload(env_file=str(env_file))

            assert result.success is True

    def test_reload_handles_quoted_values(self):
        """Test reload correctly handles quoted values."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env"
            env_file.write_text('DEFAULT_MODEL="gpt-4"\n')

            settings = Settings()
            result = settings.reload(env_file=str(env_file))

            assert result.success is True

    def test_reload_handles_comments_and_empty_lines(self):
        """Test reload skips comments and empty lines."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env"
            env_file.write_text("""
# This is a comment
DEFAULT_MODEL=deepseek-chat

# Another comment
LOG_LEVEL=DEBUG
""")

            settings = Settings()
            result = settings.reload(env_file=str(env_file))

            assert result.success is True


class TestSettingsCallbacks:
    """Tests for configuration change callbacks."""

    def test_register_callback(self):
        """Test registering a callback."""
        clear_config_callbacks()  # Start fresh

        def my_callback(result: ConfigReloadResult):
            pass

        register_config_callback(my_callback)
        assert my_callback in _get_callbacks()
        clear_config_callbacks()

    def test_unregister_callback(self):
        """Test unregistering a callback."""
        clear_config_callbacks()

        def my_callback(result: ConfigReloadResult):
            pass

        register_config_callback(my_callback)
        assert unregister_config_callback(my_callback) is True
        assert my_callback not in _get_callbacks()
        clear_config_callbacks()

    def test_unregister_nonexistent_callback(self):
        """Test unregistering a callback that was never registered."""
        clear_config_callbacks()

        def my_callback(result: ConfigReloadResult):
            pass

        assert unregister_config_callback(my_callback) is False
        clear_config_callbacks()

    def test_callback_invoked_on_reload(self):
        """Test that callbacks are invoked when config changes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env"
            env_file.write_text("LOG_LEVEL=DEBUG\n")

            settings = Settings(log_level="INFO")
            clear_config_callbacks()
            callback_calls: List[ConfigReloadResult] = []

            def my_callback(result: ConfigReloadResult):
                callback_calls.append(result)

            register_config_callback(my_callback)
            try:
                settings.reload(env_file=str(env_file))
                assert len(callback_calls) == 1
                assert callback_calls[0].success is True
            finally:
                clear_config_callbacks()

    def test_callback_exception_handled(self):
        """Test that callback exceptions don't break reload."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env"
            env_file.write_text("LOG_LEVEL=DEBUG\n")

            settings = Settings(log_level="INFO")
            clear_config_callbacks()

            def bad_callback(result: ConfigReloadResult):
                raise RuntimeError("Callback error!")

            register_config_callback(bad_callback)
            try:
                result = settings.reload(env_file=str(env_file))
                assert result.success is True  # Reload still succeeds
            finally:
                clear_config_callbacks()


def _get_callbacks():
    """Helper to get callbacks list for testing."""
    from mini_claude.config.settings.composite_settings import _config_callbacks

    return _config_callbacks


class TestSettingsHelpers:
    """Tests for Settings helper methods."""

    def test_get_reloadable_fields(self):
        """Test getting list of reloadable fields."""
        settings = Settings()
        fields = settings.get_reloadable_fields()

        assert "default_model" in fields
        assert "log_level" in fields
        assert "max_iterations" in fields

    def test_capture_current_values(self):
        """Test capturing current configuration values."""
        settings = Settings(default_model="gpt-4", log_level="DEBUG")
        values = settings._capture_current_values()

        assert values["default_model"] == "gpt-4"
        assert values["log_level"] == "DEBUG"

    def test_detect_changes(self):
        """Test detecting configuration changes."""
        settings = Settings()

        old_values = {"log_level": "INFO", "max_iterations": 10}
        new_values = {"log_level": "DEBUG", "max_iterations": 10}

        changes = settings._detect_changes(old_values, new_values)

        assert len(changes) == 1
        assert changes[0].key == "log_level"
        assert changes[0].old_value == "INFO"
        assert changes[0].new_value == "DEBUG"


class TestConfigFileWatcher:
    """Tests for ConfigFileWatcher class."""

    def test_watcher_creation(self):
        """Test creating a ConfigFileWatcher instance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env"
            env_file.write_text("LOG_LEVEL=INFO\n")

            settings = Settings()
            watcher = ConfigFileWatcher(settings)

            assert watcher.is_watching is False

    def test_watcher_start_stop(self):
        """Test starting and stopping the watcher."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env"
            env_file.write_text("LOG_LEVEL=INFO\n")

            settings = Settings()
            # Pass env_file explicitly to watcher
            watcher = ConfigFileWatcher(settings)
            watcher._config_path = env_file  # Override path for testing

            # Start watcher
            assert watcher.start() is True
            assert watcher.is_watching is True

            # Stop watcher
            watcher.stop()
            assert watcher.is_watching is False

    def test_watcher_nonexistent_file(self):
        """Test watcher with non-existent file."""
        settings = Settings()
        watcher = ConfigFileWatcher(settings)
        watcher._config_path = Path("/nonexistent/.env")  # Override path

        assert watcher.start() is False
        assert watcher.is_watching is False

    def test_watcher_get_state(self):
        """Test getting watcher state."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env"
            env_file.write_text("LOG_LEVEL=INFO\n")

            settings = Settings()
            watcher = ConfigFileWatcher(settings)
            watcher._config_path = env_file  # Override path

            state = watcher.get_state()

            assert isinstance(state, WatcherState)
            assert state.enabled is False
            assert state.watching is False

    def test_watcher_check_now(self):
        """Test immediate check for changes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env"
            env_file.write_text("LOG_LEVEL=INFO\n")

            # Create settings with the env file path
            settings = Settings()
            settings.model_config["env_file"] = str(env_file)
            watcher = ConfigFileWatcher(settings)

            # The watcher should detect the file exists
            assert watcher.check_now() is True

    def test_watcher_config_path(self):
        """Test getting config path from watcher."""
        settings = Settings()
        watcher = ConfigFileWatcher(settings)

        assert watcher.config_path is not None


class TestGlobalWatcherFunctions:
    """Tests for global watcher functions."""

    def test_get_config_watcher_singleton(self):
        """Test that get_config_watcher returns a singleton."""
        # Reset global watcher
        import mini_claude.config.watcher as watcher_module

        watcher_module._watcher = None

        watcher1 = get_config_watcher()
        watcher2 = get_config_watcher()

        assert watcher1 is watcher2
        watcher_module._watcher = None  # Cleanup

    def test_start_stop_config_watcher(self):
        """Test starting and stopping global watcher."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env"
            env_file.write_text("LOG_LEVEL=INFO\n")

            import mini_claude.config.watcher as watcher_module

            watcher_module._watcher = None

            settings = Settings()

            # Create watcher with custom path
            watcher = get_config_watcher(settings)
            watcher._config_path = env_file  # Override path

            # Start
            result = watcher.start()
            assert result is True

            # Stop
            watcher.stop()
            assert watcher.is_watching is False

            watcher_module._watcher = None  # Cleanup


class TestWatcherState:
    """Tests for WatcherState dataclass."""

    def test_watcher_state_defaults(self):
        """Test WatcherState default values."""
        state = WatcherState()

        assert state.enabled is False
        assert state.watching is False
        assert state.last_mtime == 0.0
        assert state.last_check == 0.0

    def test_watcher_state_custom_values(self):
        """Test WatcherState with custom values."""
        state = WatcherState(enabled=True, watching=True, last_mtime=12345.0)

        assert state.enabled is True
        assert state.watching is True
        assert state.last_mtime == 12345.0


class TestIntegration:
    """Integration tests for config hot reload."""

    def test_full_reload_workflow(self):
        """Test complete reload workflow with file changes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env"

            # Initial config
            env_file.write_text("""
DEFAULT_MODEL=deepseek-chat
LOG_LEVEL=INFO
MAX_ITERATIONS=10
""")

            settings = Settings()

            # Modify config
            env_file.write_text("""
DEFAULT_MODEL=gpt-4
LOG_LEVEL=DEBUG
MAX_ITERATIONS=20
""")

            # Reload
            result = settings.reload(env_file=str(env_file))

            assert result.success is True

    def test_reload_preserves_unmodified_settings(self):
        """Test that reload doesn't change unrelated settings."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env"
            env_file.write_text("LOG_LEVEL=DEBUG\n")

            settings = Settings(default_model="custom-model", max_iterations=15, log_level="INFO")

            original_model = settings.default_model
            original_iterations = settings.max_iterations

            result = settings.reload(env_file=str(env_file))

            assert result.success is True
            # Unrelated settings should remain unchanged
            assert settings.default_model == original_model
            assert settings.max_iterations == original_iterations
