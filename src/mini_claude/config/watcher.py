"""Configuration file watcher for hot reload support."""

import time
import threading
from pathlib import Path
from typing import Callable, Optional
from dataclasses import dataclass

from mini_claude.utils.logger import get_logger

logger = get_logger("mini_claude.config.watcher")


@dataclass
class WatcherState:
    """State of the config watcher."""
    enabled: bool = False
    watching: bool = False
    last_mtime: float = 0.0
    last_check: float = 0.0


class ConfigFileWatcher:
    """Watch configuration file for changes and trigger reload.

    Uses polling-based watching (no watchdog dependency required).
    Falls back gracefully if file watching is not available.
    """

    def __init__(
        self,
        settings,  # Settings instance (avoid circular import)
        callback: Optional[Callable] = None,
        debounce_seconds: float = 1.0,
    ):
        """Initialize the config file watcher.

        Args:
            settings: The Settings instance to watch.
            callback: Optional callback to invoke on config change.
            debounce_seconds: Debounce time to avoid rapid reloads.
        """
        self._settings = settings
        self._callback = callback
        self._debounce_seconds = debounce_seconds
        self._state = WatcherState()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # Determine config file path
        env_file = settings.model_config.get("env_file", ".env")
        self._config_path = Path(env_file)

    @property
    def is_watching(self) -> bool:
        """Check if the watcher is currently active."""
        return self._state.watching

    @property
    def config_path(self) -> Path:
        """Get the path to the config file being watched."""
        return self._config_path

    def start(self) -> bool:
        """Start watching the configuration file.

        Returns:
            True if watching started successfully, False otherwise.
        """
        if self._state.watching:
            logger.warning("Config watcher already running")
            return True

        if not self._config_path.exists():
            logger.warning(f"Config file not found: {self._config_path}")
            return False

        # Get initial modification time
        try:
            self._state.last_mtime = self._config_path.stat().st_mtime
        except OSError as e:
            logger.error(f"Failed to stat config file: {e}")
            return False

        # Start watcher thread
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._watch_loop,
            name="ConfigWatcher",
            daemon=True,
        )
        self._thread.start()
        self._state.watching = True
        self._state.enabled = True

        logger.info(
            "Config watcher started",
            path=str(self._config_path),
            debounce=self._debounce_seconds,
        )
        return True

    def stop(self) -> None:
        """Stop watching the configuration file."""
        if not self._state.watching:
            return

        self._stop_event.set()
        self._state.watching = False
        self._state.enabled = False

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

        logger.info("Config watcher stopped")

    def _watch_loop(self) -> None:
        """Main watch loop (runs in separate thread)."""
        last_change_time = 0.0

        while not self._stop_event.is_set():
            try:
                # Check file modification time
                current_mtime = self._config_path.stat().st_mtime

                if current_mtime != self._state.last_mtime:
                    current_time = time.time()

                    # Apply debounce
                    if current_time - last_change_time >= self._debounce_seconds:
                        logger.info(
                            "Config file changed, triggering reload",
                            path=str(self._config_path),
                        )

                        # Trigger reload
                        result = self._settings.reload()

                        if result.success:
                            logger.info(
                                "Config reloaded successfully",
                                changes=len(result.changes),
                            )
                        else:
                            logger.error(
                                "Config reload failed",
                                error=result.error,
                            )

                        # Invoke callback if provided
                        if self._callback:
                            try:
                                self._callback(result)
                            except Exception as e:
                                logger.error(f"Callback failed: {e}")

                        self._state.last_mtime = current_mtime
                        last_change_time = current_time

                # Poll interval (check every 500ms)
                self._stop_event.wait(0.5)

            except OSError as e:
                # File might have been deleted/renamed
                logger.warning(f"Error checking config file: {e}")
                self._stop_event.wait(1.0)  # Wait longer on error

            except Exception as e:
                logger.error(f"Unexpected error in watch loop: {e}")
                self._stop_event.wait(1.0)

    def check_now(self) -> bool:
        """Force an immediate check for changes.

        Returns:
            True if changes were detected and reload succeeded, False otherwise.
        """
        if not self._config_path.exists():
            return False

        try:
            current_mtime = self._config_path.stat().st_mtime
            if current_mtime != self._state.last_mtime:
                result = self._settings.reload()
                self._state.last_mtime = current_mtime
                return result.success
            return True  # No changes, but check succeeded
        except OSError:
            return False

    def get_state(self) -> WatcherState:
        """Get the current state of the watcher."""
        return WatcherState(
            enabled=self._state.enabled,
            watching=self._state.watching,
            last_mtime=self._state.last_mtime,
            last_check=time.time(),
        )


# Global watcher instance (created on demand)
_watcher: Optional[ConfigFileWatcher] = None


def get_config_watcher(
    settings=None,
    callback: Optional[Callable] = None,
    debounce_seconds: float = 1.0,
) -> ConfigFileWatcher:
    """Get or create the global config file watcher.

    Args:
        settings: The Settings instance (required on first call).
        callback: Optional callback for config changes.
        debounce_seconds: Debounce time for file changes.

    Returns:
        The global ConfigFileWatcher instance.
    """
    global _watcher

    if _watcher is None:
        if settings is None:
            from mini_claude.config.settings import settings as default_settings
            settings = default_settings
        _watcher = ConfigFileWatcher(
            settings=settings,
            callback=callback,
            debounce_seconds=debounce_seconds,
        )

    return _watcher


def start_config_watcher(settings=None, callback: Optional[Callable] = None) -> bool:
    """Start the global config file watcher.

    Args:
        settings: The Settings instance (required on first call).
        callback: Optional callback for config changes.

    Returns:
        True if watcher started successfully, False otherwise.
    """
    watcher = get_config_watcher(settings=settings, callback=callback)
    return watcher.start()


def stop_config_watcher() -> None:
    """Stop the global config file watcher."""
    global _watcher
    if _watcher:
        _watcher.stop()
