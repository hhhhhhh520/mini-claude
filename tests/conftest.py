"""Pytest configuration and fixtures for mini-claude tests.

Provides:
- pytest markers: unit, integration, e2e
- E2ETestRunner for real API tests
- Common fixtures for testing
- ApplicationContext fixtures for dependency injection
"""

import gc
import os
import shutil
import tempfile
from typing import Optional, Dict, Any, List
from unittest.mock import MagicMock, AsyncMock

import pytest


# =============================================================================
# Pytest Markers
# =============================================================================

def pytest_configure(config):
    """Register custom pytest markers."""
    config.addinivalue_line(
        "markers", "unit: Unit tests (fast, no external dependencies)"
    )
    config.addinivalue_line(
        "markers", "integration: Integration tests (mocked external services)"
    )
    config.addinivalue_line(
        "markers", "e2e: End-to-end tests (real API calls, requires API key)"
    )


# =============================================================================
# E2ETestRunner
# =============================================================================

class E2ETestRunner:
    """Runner for end-to-end tests with real API support.

    Features:
    - Configurable to use real API or mock
    - Checks API availability before tests
    - Skips tests gracefully when API unavailable
    """

    def __init__(
        self,
        use_real_api: bool = False,
        required_api_keys: Optional[List[str]] = None,
    ):
        """Initialize E2ETestRunner.

        Args:
            use_real_api: Whether to use real API calls
            required_api_keys: List of required env var names for API keys
        """
        self.use_real_api = use_real_api
        self.required_api_keys = required_api_keys or ["OPENAI_API_KEY", "DEEPSEEK_API_KEY"]
        self._api_available: Optional[bool] = None
        self._available_key: Optional[str] = None

    def check_api_available(self) -> bool:
        """Check if at least one API key is available.

        Returns:
            True if API can be used, False otherwise
        """
        if self._api_available is not None:
            return self._api_available

        for key_name in self.required_api_keys:
            key_value = os.environ.get(key_name)
            if key_value and len(key_value) > 10:  # Reasonable key length
                self._api_available = True
                self._available_key = key_name
                return True

        self._api_available = False
        return False

    def get_available_provider(self) -> Optional[str]:
        """Get the name of available API provider.

        Returns:
            Provider name or None if no API available
        """
        if not self.check_api_available():
            return None

        key_name = self._available_key
        if "DEEPSEEK" in key_name:
            return "deepseek"
        elif "OPENAI" in key_name:
            return "openai"
        elif "ANTHROPIC" in key_name:
            return "claude"
        return "unknown"

    def should_skip(self) -> bool:
        """Check if test should be skipped.

        Returns:
            True if using real API but no API available
        """
        return self.use_real_api and not self.check_api_available()

    def get_skip_reason(self) -> str:
        """Get reason for skipping test.

        Returns:
            Human-readable skip reason
        """
        return f"No API key found. Required: {self.required_api_keys}"

    async def call_llm(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Call LLM with configured settings.

        Args:
            messages: Chat messages
            model: Model name (optional)
            **kwargs: Additional arguments

        Returns:
            LLM response

        Raises:
            pytest.skip if API not available
        """
        if self.should_skip():
            pytest.skip(self.get_skip_reason())

        from mini_claude.llm.provider import LLMProvider

        provider = LLMProvider(model=model) if model else LLMProvider()
        return await provider.chat(messages=messages, **kwargs)


# Global E2E runner instance
_e2e_runner: Optional[E2ETestRunner] = None


def get_e2e_runner(use_real_api: bool = False) -> E2ETestRunner:
    """Get or create the global E2E test runner.

    Args:
        use_real_api: Whether to use real API calls

    Returns:
        E2ETestRunner instance
    """
    global _e2e_runner
    if _e2e_runner is None:
        _e2e_runner = E2ETestRunner(use_real_api=use_real_api)
    return _e2e_runner


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing.

    Automatically cleaned up after test.
    """
    tmpdir = tempfile.mkdtemp()
    yield tmpdir
    gc.collect()
    try:
        shutil.rmtree(tmpdir, ignore_errors=True)
    except Exception:
        pass


@pytest.fixture
def temp_workspace():
    """Create a temporary workspace directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def temp_file(temp_dir):
    """Create a temporary file for testing.

    Returns path to the file.
    """
    file_path = os.path.join(temp_dir, "test_file.txt")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("test content")
    yield file_path


@pytest.fixture
def mock_llm_provider():
    """Create a mocked LLM provider for testing."""
    mock = MagicMock()
    mock.chat = AsyncMock()
    mock.chat_stream = AsyncMock()
    mock.chat_stream_with_tools = AsyncMock()
    return mock


@pytest.fixture
def real_session_manager(temp_dir):
    """Create a real SessionManager with temporary database for integration tests."""
    from mini_claude.utils.session import SessionManager
    db_path = os.path.join(temp_dir, "test_sessions.db")
    return SessionManager(db_path)


@pytest.fixture
def mock_vector_store():
    """Create a mock vector store for testing."""

    store = MagicMock()
    store.count.return_value = 0
    store.get_stats.return_value = {
        "db_type": "mock",
        "document_count": 0,
    }
    store.search_similar.return_value = []
    store.add_batch.return_value = True
    store.delete_by_id.return_value = True
    return store


@pytest.fixture
def e2e_runner():
    """Get E2E test runner (mock mode by default)."""
    return get_e2e_runner(use_real_api=False)


@pytest.fixture
def e2e_runner_real():
    """Get E2E test runner configured for real API calls."""
    return get_e2e_runner(use_real_api=True)


@pytest.fixture
def sample_messages():
    """Sample chat messages for testing."""
    return [
        {"role": "user", "content": "Hello, how are you?"},
        {"role": "assistant", "content": "I'm doing well, thank you!"},
    ]


@pytest.fixture
def sample_user_input():
    """Sample user input for testing."""
    return "Create a simple Python hello world script"


# =============================================================================
# ApplicationContext Fixtures
# =============================================================================

@pytest.fixture
def app_context():
    """Create a fresh ApplicationContext for testing.

    Automatically resets after each test.
    """
    from mini_claude.context import ApplicationContext, reset_context

    reset_context()
    ctx = ApplicationContext()
    yield ctx
    reset_context()


@pytest.fixture
def isolated_app_context():
    """Create an isolated context that doesn't affect global state.

    Use this for tests that need to mock specific components.
    """
    from mini_claude.context import ApplicationContext

    ctx = ApplicationContext()
    yield ctx


@pytest.fixture
def mock_metrics_collector():
    """Create a mock MetricsCollector for testing."""
    from mini_claude.monitoring.metrics import MetricsCollector
    mock = MagicMock(spec=MetricsCollector)
    mock.record_request_start.return_value = 0.0
    mock.record_request_end.return_value = None
    mock.record_token_usage.return_value = None
    mock.record_tool_call.return_value = None
    mock.get_metrics.return_value = "# mock metrics"
    mock.get_summary.return_value = {}
    return mock


@pytest.fixture
def mock_alert_manager():
    """Create a mock AlertManager for testing."""
    from mini_claude.monitoring.alerts import AlertManager
    mock = MagicMock(spec=AlertManager)
    mock.add_rule.return_value = None
    mock.add_handler.return_value = None
    mock.check.return_value = []
    return mock


@pytest.fixture
def mock_token_counter():
    """Create a mock TokenCounter for testing."""
    from mini_claude.utils.token_manager import TokenCounter
    mock = MagicMock(spec=TokenCounter)
    mock.count_tokens.return_value = 100
    mock.count_messages_tokens.return_value = 200
    mock.check_budget.return_value = (True, 0.5)
    return mock


@pytest.fixture
def mock_session_manager():
    """Create a mock SessionManager for testing."""
    from mini_claude.utils.session import SessionManager
    mock = MagicMock(spec=SessionManager)
    mock.create_session.return_value = "test-session-id"
    mock.get_session.return_value = None
    mock.save_message.return_value = None
    mock.get_messages.return_value = []
    return mock


@pytest.fixture
def mock_rate_limiter():
    """Create a mock RateLimiter for testing."""
    from mini_claude.utils.safety import RateLimiter
    mock = MagicMock(spec=RateLimiter)
    mock.acquire.return_value = True
    mock.release.return_value = None
    return mock


@pytest.fixture
def context_with_mocked_metrics(mock_metrics_collector):
    """Create a context with mocked metrics collector."""
    from mini_claude.context import init_context

    ctx = init_context(metrics_collector=mock_metrics_collector)
    yield ctx

    from mini_claude.context import reset_context
    reset_context()


# =============================================================================
# Skip decorators
# =============================================================================

def skip_if_no_api(func):
    """Decorator to skip test if no API key available."""
    def wrapper(*args, **kwargs):
        runner = get_e2e_runner(use_real_api=True)
        if runner.should_skip():
            pytest.skip(runner.get_skip_reason())
        return func(*args, **kwargs)
    return wrapper


def skip_if_windows(func):
    """Decorator to skip test on Windows."""
    def wrapper(*args, **kwargs):
        if os.name == "nt":
            pytest.skip("Test not supported on Windows")
        return func(*args, **kwargs)
    return wrapper
