"""Tests for rate limiting functionality."""

import time
import threading
import pytest

from mini_claude.utils.safety import (
    RateLimiter,
    get_rate_limiter,
    reset_rate_limiter,
)


class TestRateLimiterFixedWindow:
    """Tests for fixed_window strategy."""

    def test_basic_limiting(self):
        """Test basic rate limiting with fixed window."""
        limiter = RateLimiter(
            requests_per_minute=5,
            strategy="fixed_window",
            enabled=True,
        )

        # Should allow first 5 requests
        for i in range(5):
            assert limiter.check_limit("user1") is True, f"Request {i+1} should be allowed"

        # 6th request should be denied
        assert limiter.check_limit("user1") is False

    def test_window_reset(self):
        """Test that count resets after window expires."""
        limiter = RateLimiter(
            requests_per_minute=3,
            strategy="fixed_window",
            enabled=True,
        )

        # Use all requests
        for _ in range(3):
            limiter.check_limit("user1")

        # Should be denied
        assert limiter.check_limit("user1") is False

        # Wait for next window (simulate by manipulating internal state)
        # In real usage, time passes naturally
        with limiter._lock:
            entry = limiter._entries["user1"]
            entry.window_start = 0  # Force new window

        # Should be allowed again
        assert limiter.check_limit("user1") is True

    def test_multiple_identifiers(self):
        """Test that different identifiers have separate limits."""
        limiter = RateLimiter(
            requests_per_minute=3,
            strategy="fixed_window",
            enabled=True,
        )

        # Use all requests for user1
        for _ in range(3):
            limiter.check_limit("user1")

        # user1 should be denied
        assert limiter.check_limit("user1") is False

        # user2 should still be allowed
        assert limiter.check_limit("user2") is True
        assert limiter.check_limit("user2") is True
        assert limiter.check_limit("user2") is True
        assert limiter.check_limit("user2") is False


class TestRateLimiterSlidingWindow:
    """Tests for sliding_window strategy."""

    def test_basic_limiting(self):
        """Test basic rate limiting with sliding window."""
        limiter = RateLimiter(
            requests_per_minute=5,
            strategy="sliding_window",
            enabled=True,
        )

        # Should allow first 5 requests
        for i in range(5):
            assert limiter.check_limit("user1") is True, f"Request {i+1} should be allowed"

        # 6th request should be denied
        assert limiter.check_limit("user1") is False

    def test_sliding_expiry(self):
        """Test that old requests expire in sliding window."""
        limiter = RateLimiter(
            requests_per_minute=3,
            strategy="sliding_window",
            enabled=True,
        )

        # Make 3 requests
        for _ in range(3):
            limiter.check_limit("user1")

        # Should be denied
        assert limiter.check_limit("user1") is False

        # Simulate time passing by removing old timestamps
        with limiter._lock:
            # Remove oldest timestamp
            limiter._entries["user1"].timestamps.pop(0)

        # Should be allowed again (one slot freed)
        assert limiter.check_limit("user1") is True

    def test_accurate_counting(self):
        """Test that sliding window counts accurately."""
        limiter = RateLimiter(
            requests_per_minute=10,
            strategy="sliding_window",
            enabled=True,
        )

        # Make 5 requests
        for _ in range(5):
            limiter.check_limit("user1")

        # Check remaining
        remaining = limiter.get_remaining("user1")
        assert remaining == 5, f"Expected 5 remaining, got {remaining}"

    def test_multiple_identifiers(self):
        """Test separate limits for different identifiers."""
        limiter = RateLimiter(
            requests_per_minute=3,
            strategy="sliding_window",
            enabled=True,
        )

        # Use all for user1
        for _ in range(3):
            limiter.check_limit("user1")

        assert limiter.check_limit("user1") is False
        assert limiter.check_limit("user2") is True


class TestRateLimiterTokenBucket:
    """Tests for token_bucket strategy."""

    def test_basic_limiting(self):
        """Test basic rate limiting with token bucket."""
        limiter = RateLimiter(
            requests_per_minute=5,
            strategy="token_bucket",
            burst_size=3,
            enabled=True,
        )

        # Should allow burst_size requests immediately
        for i in range(3):
            assert limiter.check_limit("user1") is True, f"Request {i+1} should be allowed"

        # Next request should be denied (bucket empty)
        assert limiter.check_limit("user1") is False

    def test_token_refill(self):
        """Test that tokens refill over time."""
        limiter = RateLimiter(
            requests_per_minute=60,  # 1 token per second
            strategy="token_bucket",
            burst_size=3,
            enabled=True,
        )

        # Use all tokens
        for _ in range(3):
            limiter.check_limit("user1")

        # Should be denied
        assert limiter.check_limit("user1") is False

        # Simulate time passing (1 second = 1 token)
        with limiter._lock:
            entry = limiter._entries["user1"]
            entry.tokens += 1.0  # Simulate 1 second passing

        # Should be allowed (1 token refilled)
        assert limiter.check_limit("user1") is True

    def test_burst_capacity(self):
        """Test that burst size limits maximum tokens."""
        limiter = RateLimiter(
            requests_per_minute=60,
            strategy="token_bucket",
            burst_size=5,
            enabled=True,
        )

        # Should allow burst_size requests
        for _ in range(5):
            assert limiter.check_limit("user1") is True

        # Should be denied after burst
        assert limiter.check_limit("user1") is False

    def test_remaining_tokens(self):
        """Test get_remaining for token bucket."""
        limiter = RateLimiter(
            requests_per_minute=60,
            strategy="token_bucket",
            burst_size=10,
            enabled=True,
        )

        # Initial tokens should be burst_size
        remaining = limiter.get_remaining("user1")
        assert remaining == 10

        # Use some tokens
        for _ in range(3):
            limiter.check_limit("user1")

        remaining = limiter.get_remaining("user1")
        assert remaining == 7


class TestRateLimiterGeneral:
    """General tests for RateLimiter."""

    def test_disabled_allows_all(self):
        """Test that disabled limiter allows all requests."""
        limiter = RateLimiter(
            requests_per_minute=1,
            strategy="fixed_window",
            enabled=False,
        )

        # Should allow unlimited requests when disabled
        for _ in range(100):
            assert limiter.check_limit("user1") is True

    def test_reset(self):
        """Test reset functionality."""
        limiter = RateLimiter(
            requests_per_minute=3,
            strategy="sliding_window",
            enabled=True,
        )

        # Use all requests
        for _ in range(3):
            limiter.check_limit("user1")

        # Should be denied
        assert limiter.check_limit("user1") is False

        # Reset
        limiter.reset("user1")

        # Should be allowed again
        assert limiter.check_limit("user1") is True

    def test_reset_all(self):
        """Test reset_all functionality."""
        limiter = RateLimiter(
            requests_per_minute=2,
            strategy="fixed_window",
            enabled=True,
        )

        # Use requests for multiple users
        for _ in range(2):
            limiter.check_limit("user1")
            limiter.check_limit("user2")

        # Both should be denied
        assert limiter.check_limit("user1") is False
        assert limiter.check_limit("user2") is False

        # Reset all
        limiter.reset_all()

        # Both should be allowed
        assert limiter.check_limit("user1") is True
        assert limiter.check_limit("user2") is True

    def test_get_stats(self):
        """Test get_stats functionality."""
        limiter = RateLimiter(
            requests_per_minute=10,
            strategy="sliding_window",
            burst_size=5,
            enabled=True,
        )

        # Make some requests
        for _ in range(3):
            limiter.check_limit("user1")

        stats = limiter.get_stats("user1")

        assert stats["identifier"] == "user1"
        assert stats["strategy"] == "sliding_window"
        assert stats["enabled"] is True
        assert stats["limit"] == 10
        assert stats["remaining"] == 7

    def test_get_retry_after(self):
        """Test get_retry_after functionality."""
        limiter = RateLimiter(
            requests_per_minute=3,
            strategy="fixed_window",
            enabled=True,
        )

        # Use all requests
        for _ in range(3):
            limiter.check_limit("user1")

        # Should be rate limited
        assert limiter.check_limit("user1") is False

        # Should have retry_after > 0
        retry_after = limiter.get_retry_after("user1")
        assert retry_after > 0
        assert retry_after <= 60  # At most 60 seconds

    def test_thread_safety(self):
        """Test thread safety of rate limiter."""
        limiter = RateLimiter(
            requests_per_minute=100,
            strategy="sliding_window",
            enabled=True,
        )

        results = []
        errors = []

        def make_requests(identifier, count):
            try:
                for _ in range(count):
                    result = limiter.check_limit(identifier)
                    results.append(result)
            except Exception as e:
                errors.append(e)

        # Create multiple threads
        threads = [
            threading.Thread(target=make_requests, args=("user1", 30))
            for _ in range(4)
        ]

        # Start all threads
        for t in threads:
            t.start()

        # Wait for all threads
        for t in threads:
            t.join()

        # Should have no errors
        assert len(errors) == 0

        # Should have exactly 100 allowed (limit) and rest denied
        allowed = sum(1 for r in results if r is True)
        denied = sum(1 for r in results if r is False)
        assert allowed == 100
        assert denied == 20


class TestGlobalRateLimiter:
    """Tests for global rate limiter instance."""

    def test_get_rate_limiter_singleton(self):
        """Test that get_rate_limiter returns same instance."""
        reset_rate_limiter()

        limiter1 = get_rate_limiter()
        limiter2 = get_rate_limiter()

        assert limiter1 is limiter2

    def test_reset_rate_limiter(self):
        """Test that reset_rate_limiter creates new instance."""
        limiter1 = get_rate_limiter()
        reset_rate_limiter()
        limiter2 = get_rate_limiter()

        # Should be different instances
        assert limiter1 is not limiter2


class TestRateLimiterStrategies:
    """Test all strategies work correctly."""

    @pytest.mark.parametrize("strategy", ["fixed_window", "sliding_window", "token_bucket"])
    def test_strategy_allows_then_denies(self, strategy):
        """Test that all strategies allow then deny correctly."""
        burst_size = 5 if strategy == "token_bucket" else 10
        limiter = RateLimiter(
            requests_per_minute=10,
            strategy=strategy,
            burst_size=burst_size,
            enabled=True,
        )

        # Should allow requests up to limit
        allowed_count = 0
        for _ in range(20):
            if limiter.check_limit("user1"):
                allowed_count += 1

        # Token bucket allows burst_size, others allow requests_per_minute
        expected_allowed = burst_size if strategy == "token_bucket" else 10
        assert allowed_count == expected_allowed

    def test_sliding_window_smooother_than_fixed(self):
        """Test that sliding window provides smoother limiting."""
        # This is more of a documentation test
        # Fixed window can allow 2x rate at boundaries
        # Sliding window is more accurate

        # Both start at same state
        fixed = RateLimiter(requests_per_minute=10, strategy="fixed_window")
        sliding = RateLimiter(requests_per_minute=10, strategy="sliding_window")

        # Both should allow same number initially
        fixed_count = sum(1 for _ in range(15) if fixed.check_limit("user1"))
        sliding_count = sum(1 for _ in range(15) if sliding.check_limit("user1"))

        assert fixed_count == 10
        assert sliding_count == 10
