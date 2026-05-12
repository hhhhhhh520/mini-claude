"""Tests for tool result caching."""

import time

from mini_claude.tools.cache import (
    ToolCache,
    CacheEntry,
    CacheStats,
    get_tool_cache,
    reset_tool_cache,
)


class TestToolCacheBasic:
    """Basic cache functionality tests."""

    def test_cache_initialization(self):
        """Test cache initializes with correct defaults."""
        cache = ToolCache()

        assert cache._ttl_seconds == 300
        assert cache._max_size == 100
        assert len(cache._cacheable_tools) == 4

    def test_cache_custom_settings(self):
        """Test cache with custom settings."""
        cache = ToolCache(
            ttl_seconds=60,
            max_size=50,
            cacheable_tools=["read_file", "list_dir"],
        )

        assert cache._ttl_seconds == 60
        assert cache._max_size == 50
        assert cache._cacheable_tools == ["read_file", "list_dir"]

    def test_is_cacheable(self):
        """Test is_cacheable method."""
        cache = ToolCache()

        assert cache.is_cacheable("read_file") is True
        assert cache.is_cacheable("list_dir") is True
        assert cache.is_cacheable("run_command") is False
        assert cache.is_cacheable("web_search") is False


class TestToolCacheGetSet:
    """Test cache get/set operations."""

    def test_set_and_get(self):
        """Test basic set and get operations."""
        cache = ToolCache()

        # Set a cache entry
        result = cache.set("read_file", {"path": "/tmp/test.txt"}, "file content")
        assert result is True

        # Get the cached result
        cached, hit = cache.get("read_file", {"path": "/tmp/test.txt"})
        assert cached == "file content"
        assert hit is True

    def test_get_miss(self):
        """Test cache miss."""
        cache = ToolCache()

        cached, hit = cache.get("read_file", {"path": "/tmp/nonexistent.txt"})
        assert cached is None
        assert hit is False

    def test_cache_non_cacheable_tool(self):
        """Test that non-cacheable tools are not cached."""
        cache = ToolCache()

        # Try to cache a non-cacheable tool
        result = cache.set("run_command", {"command": "ls"}, "file1\nfile2")
        assert result is False

        cached, hit = cache.get("run_command", {"command": "ls"})
        assert cached is None
        assert hit is False

    def test_cache_error_result(self):
        """Test that error results are not cached."""
        cache = ToolCache()

        # Try to cache an error result
        result = cache.set("read_file", {"path": "/tmp/test.txt"}, "Error: File not found")
        assert result is False

    def test_cache_key_includes_params(self):
        """Test that different params produce different cache entries."""
        cache = ToolCache()

        cache.set("read_file", {"path": "/tmp/a.txt"}, "content A")
        cache.set("read_file", {"path": "/tmp/b.txt"}, "content B")

        cached_a, hit_a = cache.get("read_file", {"path": "/tmp/a.txt"})
        cached_b, hit_b = cache.get("read_file", {"path": "/tmp/b.txt"})

        assert cached_a == "content A"
        assert cached_b == "content B"
        assert hit_a is True
        assert hit_b is True

    def test_cache_params_order_independent(self):
        """Test that params order doesn't affect cache key."""
        cache = ToolCache()

        # Same params in different order
        cache.set("read_file", {"path": "/tmp/test.txt", "start_line": 1}, "content")

        cached, hit = cache.get("read_file", {"start_line": 1, "path": "/tmp/test.txt"})
        assert cached == "content"
        assert hit is True


class TestToolCacheTTL:
    """Test TTL (Time-To-Live) functionality."""

    def test_ttl_expiration(self):
        """Test that cache entries expire after TTL."""
        cache = ToolCache(ttl_seconds=1)  # 1 second TTL

        cache.set("read_file", {"path": "/tmp/test.txt"}, "content")

        # Immediate get should hit
        cached, hit = cache.get("read_file", {"path": "/tmp/test.txt"})
        assert hit is True

        # Wait for TTL to expire
        time.sleep(1.1)

        # Should miss now
        cached, hit = cache.get("read_file", {"path": "/tmp/test.txt"})
        assert hit is False

    def test_ttl_different_for_each_entry(self):
        """Test that TTL is set per entry based on creation time."""
        cache = ToolCache(ttl_seconds=2)

        cache.set("read_file", {"path": "/tmp/a.txt"}, "content A")
        time.sleep(1)
        cache.set("read_file", {"path": "/tmp/b.txt"}, "content B")

        # After 1.5 seconds, first entry should be expired, second should not
        time.sleep(1.5)

        cached_a, hit_a = cache.get("read_file", {"path": "/tmp/a.txt"})
        cached_b, hit_b = cache.get("read_file", {"path": "/tmp/b.txt"})

        assert hit_a is False
        assert hit_b is True


class TestToolCacheLRU:
    """Test LRU (Least Recently Used) eviction."""

    def test_lru_eviction(self):
        """Test that oldest entries are evicted when max size reached."""
        cache = ToolCache(max_size=3)

        cache.set("read_file", {"path": "/tmp/a.txt"}, "A")
        cache.set("read_file", {"path": "/tmp/b.txt"}, "B")
        cache.set("read_file", {"path": "/tmp/c.txt"}, "C")

        # All should be cached
        assert cache.get("read_file", {"path": "/tmp/a.txt"})[1] is True
        assert cache.get("read_file", {"path": "/tmp/b.txt"})[1] is True
        assert cache.get("read_file", {"path": "/tmp/c.txt"})[1] is True

        # Add one more - should evict oldest (a.txt)
        cache.set("read_file", {"path": "/tmp/d.txt"}, "D")

        # a.txt should be evicted
        assert cache.get("read_file", {"path": "/tmp/a.txt"})[1] is False
        assert cache.get("read_file", {"path": "/tmp/b.txt"})[1] is True
        assert cache.get("read_file", {"path": "/tmp/c.txt"})[1] is True
        assert cache.get("read_file", {"path": "/tmp/d.txt"})[1] is True

    def test_lru_access_order(self):
        """Test that get updates access order."""
        cache = ToolCache(max_size=3)

        cache.set("read_file", {"path": "/tmp/a.txt"}, "A")
        cache.set("read_file", {"path": "/tmp/b.txt"}, "B")
        cache.set("read_file", {"path": "/tmp/c.txt"}, "C")

        # Access a.txt to move it to end
        cache.get("read_file", {"path": "/tmp/a.txt"})

        # Add one more - should evict b.txt (now oldest)
        cache.set("read_file", {"path": "/tmp/d.txt"}, "D")

        assert cache.get("read_file", {"path": "/tmp/a.txt"})[1] is True
        assert cache.get("read_file", {"path": "/tmp/b.txt"})[1] is False
        assert cache.get("read_file", {"path": "/tmp/c.txt"})[1] is True


class TestToolCacheFileTracking:
    """Test file modification time tracking."""

    def test_file_mtime_tracking(self, tmp_path):
        """Test that cache invalidates when file is modified."""
        cache = ToolCache()

        # Create a test file
        test_file = tmp_path / "test.txt"
        test_file.write_text("original content")

        # Cache the read
        cache.set("read_file", {"path": str(test_file)}, "original content")

        # Should hit
        cached, hit = cache.get("read_file", {"path": str(test_file)})
        assert hit is True

        # Modify the file
        time.sleep(0.1)  # Ensure mtime changes
        test_file.write_text("modified content")

        # Should miss now
        cached, hit = cache.get("read_file", {"path": str(test_file)})
        assert hit is False

    def test_file_mtime_nonexistent_file(self):
        """Test that nonexistent files don't cause issues."""
        cache = ToolCache()

        # Cache with nonexistent file path
        cache.set("read_file", {"path": "/nonexistent/path.txt"}, "content")

        # Should still work
        cached, hit = cache.get("read_file", {"path": "/nonexistent/path.txt"})
        assert hit is True


class TestToolCacheInvalidate:
    """Test cache invalidation."""

    def test_invalidate_by_tool(self):
        """Test invalidating cache for a specific tool."""
        cache = ToolCache()

        cache.set("read_file", {"path": "/tmp/a.txt"}, "A")
        cache.set("read_file", {"path": "/tmp/b.txt"}, "B")
        cache.set("list_dir", {"path": "/tmp"}, "dir content")

        count = cache.invalidate("read_file")
        assert count == 2

        assert cache.get("read_file", {"path": "/tmp/a.txt"})[1] is False
        assert cache.get("read_file", {"path": "/tmp/b.txt"})[1] is False
        assert cache.get("list_dir", {"path": "/tmp"})[1] is True

    def test_invalidate_all(self):
        """Test invalidating all cache entries."""
        cache = ToolCache()

        cache.set("read_file", {"path": "/tmp/a.txt"}, "A")
        cache.set("list_dir", {"path": "/tmp"}, "dir content")

        count = cache.invalidate()
        assert count == 2

        assert cache.get("read_file", {"path": "/tmp/a.txt"})[1] is False
        assert cache.get("list_dir", {"path": "/tmp"})[1] is False

    def test_clear(self):
        """Test clear method."""
        cache = ToolCache()

        cache.set("read_file", {"path": "/tmp/a.txt"}, "A")
        cache.set("list_dir", {"path": "/tmp"}, "dir content")

        count = cache.clear()
        assert count == 2
        assert len(cache._cache) == 0


class TestToolCacheStats:
    """Test cache statistics."""

    def test_initial_stats(self):
        """Test initial statistics."""
        cache = ToolCache()
        stats = cache.get_stats()

        assert stats['size'] == 0
        assert stats['hits'] == 0
        assert stats['misses'] == 0
        assert stats['hit_rate'] == 0.0

    def test_hit_rate_calculation(self):
        """Test hit rate calculation."""
        cache = ToolCache()

        cache.set("read_file", {"path": "/tmp/a.txt"}, "A")

        # 3 hits
        cache.get("read_file", {"path": "/tmp/a.txt"})
        cache.get("read_file", {"path": "/tmp/a.txt"})
        cache.get("read_file", {"path": "/tmp/a.txt"})

        # 2 misses
        cache.get("read_file", {"path": "/tmp/b.txt"})
        cache.get("read_file", {"path": "/tmp/c.txt"})

        stats = cache.get_stats()
        assert stats['hits'] == 3
        assert stats['misses'] == 2
        assert stats['hit_rate'] == 60.0  # 3/(3+2) * 100

    def test_stats_includes_evictions(self):
        """Test that stats track evictions."""
        cache = ToolCache(max_size=2)

        cache.set("read_file", {"path": "/tmp/a.txt"}, "A")
        cache.set("read_file", {"path": "/tmp/b.txt"}, "B")
        cache.set("read_file", {"path": "/tmp/c.txt"}, "C")  # Evicts A

        stats = cache.get_stats()
        assert stats['evictions'] == 1
        assert stats['sets'] == 3

    def test_stats_includes_invalidations(self):
        """Test that stats track invalidations."""
        cache = ToolCache()

        cache.set("read_file", {"path": "/tmp/a.txt"}, "A")
        cache.invalidate("read_file")

        stats = cache.get_stats()
        assert stats['invalidations'] == 1


class TestToolCacheCleanup:
    """Test cache cleanup functionality."""

    def test_cleanup_expired(self):
        """Test cleaning up expired entries."""
        cache = ToolCache(ttl_seconds=1)

        cache.set("read_file", {"path": "/tmp/a.txt"}, "A")
        cache.set("read_file", {"path": "/tmp/b.txt"}, "B")

        # Wait for expiration
        time.sleep(1.1)

        count = cache.cleanup_expired()
        assert count == 2
        assert len(cache._cache) == 0

    def test_cleanup_partial(self):
        """Test cleaning up only expired entries."""
        cache = ToolCache(ttl_seconds=1)

        cache.set("read_file", {"path": "/tmp/a.txt"}, "A")
        time.sleep(1.1)
        cache.set("read_file", {"path": "/tmp/b.txt"}, "B")

        count = cache.cleanup_expired()
        assert count == 1
        assert len(cache._cache) == 1


class TestToolCacheEntries:
    """Test get_entries functionality."""

    def test_get_entries(self):
        """Test getting cache entries."""
        cache = ToolCache()

        cache.set("read_file", {"path": "/tmp/a.txt"}, "A")
        cache.set("list_dir", {"path": "/tmp"}, "dir")

        entries = cache.get_entries()
        assert len(entries) == 2

        # Check entry structure
        for entry in entries:
            assert 'key' in entry
            assert 'tool_name' in entry
            assert 'ttl_remaining' in entry
            assert 'hit_count' in entry

    def test_get_entries_empty(self):
        """Test getting entries when cache is empty."""
        cache = ToolCache()
        entries = cache.get_entries()
        assert entries == []


class TestGlobalCache:
    """Test global cache instance."""

    def test_get_tool_cache(self):
        """Test get_tool_cache returns singleton."""
        reset_tool_cache()

        cache1 = get_tool_cache()
        cache2 = get_tool_cache()

        assert cache1 is cache2

    def test_reset_tool_cache(self):
        """Test reset_tool_cache creates new instance."""
        cache1 = get_tool_cache()
        reset_tool_cache()
        cache2 = get_tool_cache()

        assert cache1 is not cache2


class TestCacheStatsDataclass:
    """Test CacheStats dataclass."""

    def test_hit_rate_zero(self):
        """Test hit rate when no operations."""
        stats = CacheStats()
        assert stats.hit_rate == 0.0

    def test_hit_rate_calculation(self):
        """Test hit rate calculation."""
        stats = CacheStats(total_hits=7, total_misses=3)
        assert stats.hit_rate == 0.7


class TestCacheEntryDataclass:
    """Test CacheEntry dataclass."""

    def test_cache_entry_creation(self):
        """Test creating a cache entry."""
        entry = CacheEntry(
            result="test content",
            created_at=1000.0,
            expires_at=1300.0,
            tool_name="read_file",
            params_hash="abc123",
        )

        assert entry.result == "test content"
        assert entry.hit_count == 0
        assert entry.file_mtime is None
